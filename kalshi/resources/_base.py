"""Base resource class with shared request helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, TypeVar

from pydantic import BaseModel

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.errors import AuthRequiredError
from kalshi.models.common import Page

T = TypeVar("T", bound=BaseModel)


def _params(**kwargs: Any) -> dict[str, Any]:
    """Build a query-param dict, dropping None values."""
    return {k: v for k, v in kwargs.items() if v is not None}


def _join_tickers(value: list[str] | tuple[str, ...] | str | None) -> str | None:
    """Serialize the `tickers` query param.

    Spec (``TickersQuery``) says ``type: string``, comma-separated — NOT
    ``style: form, explode: true``. Accept a list, tuple, or pre-joined
    string. ``None``, empty list, empty tuple, and empty string all return
    ``None`` so ``_params()`` drops the key entirely (sending ``?tickers=``
    has undefined server semantics).
    """
    if not value:
        return None
    if isinstance(value, (list, tuple)):
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
        self, path: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = self._transport.request("POST", path, json=json)
        result: dict[str, Any] = response.json()
        return result

    def _put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._transport.request("PUT", path, params=params, json=json)
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

    def _list(
        self,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Page[T]:
        """Fetch a paginated list endpoint and return a Page[T]."""
        data = self._get(path, params=params)
        raw_items = data.get(items_key, [])
        items = [model_cls.model_validate(item) for item in raw_items]
        cursor = data.get("cursor")
        return Page(items=items, cursor=cursor if cursor else None)

    def _list_all(
        self,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
        max_pages: int = 1000,
    ) -> Iterator[T]:
        """Auto-paginate through all pages, yielding items."""
        current_params = dict(params) if params else {}
        for _ in range(max_pages):
            page = self._list(path, model_cls, items_key, params=current_params)
            yield from page.items
            if not page.has_next:
                break
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
        self, path: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = await self._transport.request("POST", path, json=json)
        result: dict[str, Any] = response.json()
        return result

    async def _put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._transport.request("PUT", path, params=params, json=json)
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

    async def _list(
        self,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Page[T]:
        data = await self._get(path, params=params)
        raw_items = data.get(items_key, [])
        items = [model_cls.model_validate(item) for item in raw_items]
        cursor = data.get("cursor")
        return Page(items=items, cursor=cursor if cursor else None)

    async def _list_all(
        self,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
        max_pages: int = 1000,
    ) -> AsyncIterator[T]:
        current_params = dict(params) if params else {}
        for _ in range(max_pages):
            page = await self._list(path, model_cls, items_key, params=current_params)
            for item in page.items:
                yield item
            if not page.has_next:
                break
            current_params["cursor"] = page.cursor
