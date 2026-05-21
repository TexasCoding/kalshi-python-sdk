"""Base resource class with shared request helpers."""

from __future__ import annotations

import urllib.parse
from collections.abc import AsyncIterator, Iterator
from typing import Any, TypeVar

import httpx
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
        raise ValueError(f"{name} must be in [{lo}, {hi}], got {value}.")
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
        raise ValueError(f"max_pages must be positive or None, got {max_pages}")


def _join_tickers(
    value: list[str] | tuple[str, ...] | str | None,
    *,
    max_items: int | None = None,
) -> str | None:
    """Serialize a comma-joined ticker query param (spec: not explode:true).

    List/tuple elements must be non-empty and comma-free; pre-joined strings
    pass through. ``max_items`` (when set) caps the list length per spec —
    e.g. ``MultipleEventTickerQuery`` declares a max of 10. Pre-joined string
    inputs skip the cap (caller already opted into wire-format ownership).
    """
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        if max_items is not None and len(value) > max_items:
            raise ValueError(f"too many tickers: {len(value)} > spec max {max_items}")
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

    def _load_json(self, response: httpx.Response) -> Any:
        """Parse a response body, honoring ``config.rest_json_loads`` if set.

        Falls back to ``response.json()`` (stdlib) when no custom loader is
        configured. Custom loaders receive ``response.content`` (bytes).
        """
        loader = self._transport._config.rest_json_loads
        if loader is None:
            return response.json()
        return loader(response.content)

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._transport.request(
            "GET",
            path,
            params=params,
            extra_headers=extra_headers,
        )
        result: dict[str, Any] = self._load_json(response)
        return result

    def _post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._transport.request(
            "POST",
            path,
            params=params,
            json=json,
            extra_headers=extra_headers,
        )
        result: dict[str, Any] = self._load_json(response)
        return result

    def _post_json(
        self,
        path: str,
        *,
        content: bytes,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """POST a pre-serialized JSON body (bytes).

        Skips the dict-walk pass httpx's ``json=`` does. Use this when
        a Pydantic model already produced the wire bytes via
        ``model_dump_json(...).encode()``.
        """
        response = self._transport.request(
            "POST",
            path,
            params=params,
            content=content,
            headers={"Content-Type": "application/json"},
            extra_headers=extra_headers,
        )
        result: dict[str, Any] = self._load_json(response)
        return result

    def _put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        response = self._transport.request(
            "PUT",
            path,
            params=params,
            json=json,
            extra_headers=extra_headers,
        )
        if response.status_code == 204:
            return None
        result: dict[str, Any] = self._load_json(response)
        return result

    def _delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        response = self._transport.request(
            "DELETE",
            path,
            params=params,
            extra_headers=extra_headers,
        )
        if response.status_code == 204:
            return None
        result: dict[str, Any] = self._load_json(response)
        return result

    def _delete_with_body(
        self,
        path: str,
        *,
        json: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        response = self._transport.request(
            "DELETE",
            path,
            json=json,
            extra_headers=extra_headers,
        )
        if response.status_code == 204:
            return None
        result: dict[str, Any] = self._load_json(response)
        return result

    def _delete_with_body_json(
        self,
        path: str,
        *,
        content: bytes,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """DELETE with a pre-serialized JSON body (bytes). See :meth:`_post_json`."""
        response = self._transport.request(
            "DELETE",
            path,
            params=params,
            content=content,
            headers={"Content-Type": "application/json"},
            extra_headers=extra_headers,
        )
        if response.status_code == 204:
            return None
        result: dict[str, Any] = self._load_json(response)
        return result

    def _list(
        self,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
        cursor_key: str = "cursor",
        extra_headers: dict[str, str] | None = None,
    ) -> Page[T]:
        """Fetch a paginated list endpoint and return a Page[T].

        ``cursor_key`` overrides the response envelope key the paginator
        reads for the next-page cursor. Default ``"cursor"`` matches
        every Kalshi endpoint except ``GET /incentive_programs`` which
        uses ``"next_cursor"``.
        """
        data = self._get(path, params=params, extra_headers=extra_headers)
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
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[T]:
        """Auto-paginate through all pages, yielding items.

        The outbound cursor query param is always named ``cursor`` (spec
        convention). ``cursor_key`` only affects how the response envelope
        is parsed.

        ``max_pages`` is an optional hard cap on pages fetched. ``None``
        (default) iterates until the server returns an empty cursor; the
        cursor-repeat guard below provides the safety net against
        infinite loops.

        Raises ``KalshiError`` if the previous page's cursor repeats —
        the realistic server-pagination-bug shape (last page replayed
        forever). Only the most recent cursor is retained, so memory is
        O(1) regardless of page count.
        """
        current_params = dict(params) if params else {}
        last_cursor: str | None = None
        pages_fetched = 0
        while max_pages is None or pages_fetched < max_pages:
            page = self._list(
                path,
                model_cls,
                items_key,
                params=current_params,
                cursor_key=cursor_key,
                extra_headers=extra_headers,
            )
            yield from page.items
            pages_fetched += 1
            if not page.cursor:
                break
            if page.cursor == last_cursor:
                raise KalshiError(
                    f"Cursor loop detected on {path}: server returned "
                    f"cursor {page.cursor!r} which was already used. "
                    f"This indicates a server-side pagination bug."
                )
            last_cursor = page.cursor
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

    def _load_json(self, response: httpx.Response) -> Any:
        """Parse a response body, honoring ``config.rest_json_loads`` if set.

        Falls back to ``response.json()`` (stdlib) when no custom loader is
        configured. Custom loaders receive ``response.content`` (bytes).
        """
        loader = self._transport._config.rest_json_loads
        if loader is None:
            return response.json()
        return loader(response.content)

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = await self._transport.request(
            "GET",
            path,
            params=params,
            extra_headers=extra_headers,
        )
        result: dict[str, Any] = self._load_json(response)
        return result

    async def _post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = await self._transport.request(
            "POST",
            path,
            params=params,
            json=json,
            extra_headers=extra_headers,
        )
        result: dict[str, Any] = self._load_json(response)
        return result

    async def _post_json(
        self,
        path: str,
        *,
        content: bytes,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Async :meth:`SyncResource._post_json`."""
        response = await self._transport.request(
            "POST",
            path,
            params=params,
            content=content,
            headers={"Content-Type": "application/json"},
            extra_headers=extra_headers,
        )
        result: dict[str, Any] = self._load_json(response)
        return result

    async def _put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        response = await self._transport.request(
            "PUT",
            path,
            params=params,
            json=json,
            extra_headers=extra_headers,
        )
        if response.status_code == 204:
            return None
        result: dict[str, Any] = self._load_json(response)
        return result

    async def _delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        response = await self._transport.request(
            "DELETE",
            path,
            params=params,
            extra_headers=extra_headers,
        )
        if response.status_code == 204:
            return None
        result: dict[str, Any] = self._load_json(response)
        return result

    async def _delete_with_body(
        self,
        path: str,
        *,
        json: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        response = await self._transport.request(
            "DELETE",
            path,
            json=json,
            extra_headers=extra_headers,
        )
        if response.status_code == 204:
            return None
        result: dict[str, Any] = self._load_json(response)
        return result

    async def _delete_with_body_json(
        self,
        path: str,
        *,
        content: bytes,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Async :meth:`SyncResource._delete_with_body_json`."""
        response = await self._transport.request(
            "DELETE",
            path,
            params=params,
            content=content,
            headers={"Content-Type": "application/json"},
            extra_headers=extra_headers,
        )
        if response.status_code == 204:
            return None
        result: dict[str, Any] = self._load_json(response)
        return result

    async def _list(
        self,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
        cursor_key: str = "cursor",
        extra_headers: dict[str, str] | None = None,
    ) -> Page[T]:
        data = await self._get(path, params=params, extra_headers=extra_headers)
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
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[T]:
        """Async counterpart of :meth:`SyncResource._list_all`.

        Raises ``KalshiError`` on repeated cursor; see sync docstring.
        """
        current_params = dict(params) if params else {}
        last_cursor: str | None = None
        pages_fetched = 0
        while max_pages is None or pages_fetched < max_pages:
            page = await self._list(
                path,
                model_cls,
                items_key,
                params=current_params,
                cursor_key=cursor_key,
                extra_headers=extra_headers,
            )
            for item in page.items:
                yield item
            pages_fetched += 1
            if not page.cursor:
                break
            if page.cursor == last_cursor:
                raise KalshiError(
                    f"Cursor loop detected on {path}: server returned "
                    f"cursor {page.cursor!r} which was already used. "
                    f"This indicates a server-side pagination bug."
                )
            last_cursor = page.cursor
            current_params["cursor"] = page.cursor
