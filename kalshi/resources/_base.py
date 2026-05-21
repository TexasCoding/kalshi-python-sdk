"""Base resource class with shared request helpers."""

from __future__ import annotations

import urllib.parse
from collections.abc import AsyncIterator, Iterator
from typing import Any, TypeVar

from pydantic import BaseModel

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.errors import AuthRequiredError, KalshiError
from kalshi.models.common import Page

T = TypeVar("T", bound=BaseModel)


def _seg(value: str, *, name: str = "path segment") -> str:
    """URL-encode a single path segment; reject empty/whitespace and ``.``/``..``.

    Caller-supplied identifiers (tickers, order ids, etc.) get interpolated
    into request paths with f-strings. Without encoding, a value like
    ``"foo/../admin"`` would be normalized by intermediate proxies into a
    request signed for the intended endpoint but routed to a different one.
    ``urllib.parse.quote(..., safe="")`` percent-encodes ``/`` and every
    other reserved character. ``.``/``..`` are rejected outright because
    they survive URL encoding but still trigger path normalization.
    """
    if not value or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    if value in (".", ".."):
        raise ValueError(f"{name} cannot be '.' or '..'")
    return urllib.parse.quote(value, safe="")


def _validate_limit(
    value: int | None,
    *,
    hi: int,
    lo: int = 1,
    name: str = "limit",
) -> int | None:
    """Reject ``limit`` outside the spec-declared ``[lo, hi]`` window.

    Returns the value unchanged on success. Kalshi enforces these bounds
    server-side; failing client-side avoids a wasted round trip and a
    less-actionable 400.
    """
    if value is None:
        return None
    if not (lo <= value <= hi):
        raise ValueError(
            f"{name} must be in [{lo}, {hi}], got {value}."
        )
    return value



def _params(**kwargs: Any) -> dict[str, Any]:
    """Build a query-param dict, dropping None values."""
    return {k: v for k, v in kwargs.items() if v is not None}


def _bool_param(value: bool | None) -> str | None:
    """Serialize a tri-state bool for query params.

    ``True`` -> ``"true"``, ``False`` -> ``"false"``, ``None`` -> drop.
    Explicit ``False`` must survive so callers can opt out when the
    server default ever flips; a single ``"true" if x else None`` would
    erase that distinction.
    """
    if value is None:
        return None
    return "true" if value else "false"


def _check_request_exclusive(request: Any, **kwargs: Any) -> None:
    """Raise TypeError if ``request`` is set together with any individual kwarg."""
    if request is None:
        return
    provided = [k for k, v in kwargs.items() if v is not None]
    if provided:
        raise TypeError(
            "Pass either `request=...` or individual kwargs, not both. "
            f"Got both `request` and: {sorted(provided)}"
        )


def _validate_max_pages(max_pages: int | None) -> None:
    """Reject ``max_pages <= 0`` at the public ``*_all()`` boundary.

    ``None`` (unbounded — iterates until the server returns no cursor) and
    positive integers are valid. Zero or negative would silently produce an
    empty iterator deep inside ``_list_all``; surfacing the misuse here is
    friendlier.
    """
    if max_pages is not None and max_pages <= 0:
        raise ValueError(
            f"max_pages must be positive or None, got {max_pages}"
        )


def _join_tickers(value: list[str] | tuple[str, ...] | str | None) -> str | None:
    """Serialize the `tickers` query param (spec: comma-joined string, not explode:true).

    List/tuple elements must be non-empty and comma-free; pre-joined strings pass through.
    """
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        for i, elem in enumerate(value):
            if not elem:
                raise ValueError(
                    f"tickers[{i}] is empty; empty elements would poison "
                    f"the server-side filter (wire would be '...,,...')"
                )
            if "," in elem:
                raise ValueError(
                    f"tickers[{i}]={elem!r} contains a comma; embedded "
                    f"commas would silently expand the ticker list"
                )
        return ",".join(value)
    return value


class SyncResource:
    """Base class for sync resource modules."""

    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def _require_auth(self) -> None:
        """Raise AuthRequiredError if transport has no auth credentials."""
        if not self._transport.is_authenticated:
            raise AuthRequiredError()

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._transport.request("GET", path, params=params)
        result: dict[str, Any] = response.json()
        return result

    def _post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._transport.request("POST", path, params=params, json=json)
        result: dict[str, Any] = response.json()
        return result

    def _put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        response = self._transport.request("PUT", path, params=params, json=json)
        if response.status_code == 204:
            return None
        result: dict[str, Any] = response.json()
        return result

    def _delete(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        response = self._transport.request("DELETE", path, params=params)
        if response.status_code == 204:
            return None
        result: dict[str, Any] = response.json()
        return result

    def _delete_with_body(
        self, path: str, *, json: dict[str, Any]
    ) -> dict[str, Any] | None:
        response = self._transport.request("DELETE", path, json=json)
        if response.status_code == 204:
            return None
        result: dict[str, Any] = response.json()
        return result

    def _list(
        self,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
        cursor_key: str = "cursor",
    ) -> Page[T]:
        """Fetch a paginated list endpoint and return a Page[T].

        ``cursor_key`` overrides the response envelope key the paginator
        reads for the next-page cursor. Default ``"cursor"`` matches
        every Kalshi endpoint except ``GET /incentive_programs`` which
        uses ``"next_cursor"``.
        """
        data = self._get(path, params=params)
        # .get(key, []) misses explicit null; or [] coerces both.
        raw_items = data.get(items_key) or []
        items = [model_cls.model_validate(item) for item in raw_items]
        cursor = data.get(cursor_key)
        return Page(items=items, cursor=cursor if cursor else None)

    def _list_all(
        self,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
        max_pages: int | None = None,
        cursor_key: str = "cursor",
    ) -> Iterator[T]:
        """Auto-paginate through all pages, yielding items.

        The outbound cursor query param is always named ``cursor`` (spec
        convention). ``cursor_key`` only affects how the response envelope
        is parsed.

        ``max_pages`` is an optional hard cap on pages fetched. ``None``
        (default) iterates until the server returns an empty cursor; the
        cursor-repeat guard below provides the safety net against
        infinite loops.

        Raises ``KalshiError`` if a cursor value repeats, which indicates
        a server-side pagination bug.
        """
        current_params = dict(params) if params else {}
        seen_cursors: set[str] = set()
        pages_fetched = 0
        while max_pages is None or pages_fetched < max_pages:
            page = self._list(
                path, model_cls, items_key,
                params=current_params, cursor_key=cursor_key,
            )
            yield from page.items
            pages_fetched += 1
            if not page.cursor:
                break
            if page.cursor in seen_cursors:
                raise KalshiError(
                    f"Cursor loop detected on {path}: server returned "
                    f"cursor {page.cursor!r} which was already used. "
                    f"This indicates a server-side pagination bug."
                )
            seen_cursors.add(page.cursor)
            current_params["cursor"] = page.cursor


class AsyncResource:
    """Base class for async resource modules."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    def _require_auth(self) -> None:
        """Raise AuthRequiredError if transport has no auth credentials.

        Intentionally sync — only checks a bool property, no async I/O needed.
        """
        if not self._transport.is_authenticated:
            raise AuthRequiredError()

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self._transport.request("GET", path, params=params)
        result: dict[str, Any] = response.json()
        return result

    async def _post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._transport.request(
            "POST", path, params=params, json=json,
        )
        result: dict[str, Any] = response.json()
        return result

    async def _put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        response = await self._transport.request("PUT", path, params=params, json=json)
        if response.status_code == 204:
            return None
        result: dict[str, Any] = response.json()
        return result

    async def _delete(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        response = await self._transport.request("DELETE", path, params=params)
        if response.status_code == 204:
            return None
        result: dict[str, Any] = response.json()
        return result

    async def _delete_with_body(
        self, path: str, *, json: dict[str, Any]
    ) -> dict[str, Any] | None:
        response = await self._transport.request("DELETE", path, json=json)
        if response.status_code == 204:
            return None
        result: dict[str, Any] = response.json()
        return result

    async def _list(
        self,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
        cursor_key: str = "cursor",
    ) -> Page[T]:
        data = await self._get(path, params=params)
        # .get(key, []) misses explicit null; or [] coerces both.
        raw_items = data.get(items_key) or []
        items = [model_cls.model_validate(item) for item in raw_items]
        cursor = data.get(cursor_key)
        return Page(items=items, cursor=cursor if cursor else None)

    async def _list_all(
        self,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
        max_pages: int | None = None,
        cursor_key: str = "cursor",
    ) -> AsyncIterator[T]:
        """Async counterpart of :meth:`SyncResource._list_all`.

        Raises ``KalshiError`` on repeated cursor; see sync docstring.
        """
        current_params = dict(params) if params else {}
        seen_cursors: set[str] = set()
        pages_fetched = 0
        while max_pages is None or pages_fetched < max_pages:
            page = await self._list(
                path, model_cls, items_key,
                params=current_params, cursor_key=cursor_key,
            )
            for item in page.items:
                yield item
            pages_fetched += 1
            if not page.cursor:
                break
            if page.cursor in seen_cursors:
                raise KalshiError(
                    f"Cursor loop detected on {path}: server returned "
                    f"cursor {page.cursor!r} which was already used. "
                    f"This indicates a server-side pagination bug."
                )
            seen_cursors.add(page.cursor)
            current_params["cursor"] = page.cursor
