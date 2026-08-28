"""Perps portfolio resource — positions, fills, trades (#393).

Three margin read endpoints on the standalone perps client:

- ``positions`` — ``GET /margin/positions``: auth required, single
  non-paginated array (no ``_all()``).
- ``fills`` / ``fills_all`` — ``GET /margin/fills``: auth required,
  cursor-paginated (the authenticated user's margin fills).
- ``trades`` / ``trades_all`` — ``GET /margin/trades``: **public** (no spec
  ``security`` block, tag ``market``) — like ``MarketsResource.list_trades`` it
  does **not** call ``_require_auth()``. ``ticker`` is required. Cursor-paginated.

All three are GET, so they reuse the transport's retry/error machinery
unchanged (retry on 429/502/503/504).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from kalshi.errors import KalshiError
from kalshi.models.common import Page
from kalshi.perps.models.portfolio import (
    ExitTrigger,
    ExitTriggerKindLiteral,
    GetExitTriggersResponse,
    GetMarginPositionsResponse,
    MarginFill,
    MarginTrade,
    SetCrossExitTriggerRequest,
    SetIsolatedExitTriggerRequest,
    UpdateExitTriggerRequest,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _params,
    _seg,
    _validate_limit,
    _validate_max_pages,
)


def _margin_fills_params(
    *,
    subaccount: int | None,
    min_ts: int | None,
    max_ts: int | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    """Build query params for ``GET /margin/fills`` (shared by sync/async)."""
    limit = _validate_limit(limit, hi=1000)
    return _params(
        subaccount=subaccount,
        min_ts=min_ts,
        max_ts=max_ts,
        limit=limit,
        cursor=cursor,
    )


def _margin_trades_params(
    *,
    ticker: str,
    min_ts: int | None,
    max_ts: int | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    """Build query params for ``GET /margin/trades`` (``ticker`` is required)."""
    limit = _validate_limit(limit, hi=1000)
    return _params(
        ticker=ticker,
        min_ts=min_ts,
        max_ts=max_ts,
        limit=limit,
        cursor=cursor,
    )


class PerpsPortfolioResource(SyncResource):
    """Sync perps portfolio API (``positions`` / ``fills`` / ``trades`` + paginators)."""

    def positions(
        self,
        *,
        subaccount: int | None = None,
        ticker: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginPositionsResponse:
        self._require_auth()
        params = _params(subaccount=subaccount, ticker=ticker)
        data = self._get("/margin/positions", params=params, extra_headers=extra_headers)
        return GetMarginPositionsResponse.model_validate(data)

    def fills(
        self,
        *,
        subaccount: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[MarginFill]:
        self._require_auth()
        params = _margin_fills_params(
            subaccount=subaccount,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return self._list(
            "/margin/fills", MarginFill, "fills", params=params, extra_headers=extra_headers
        )

    def fills_all(
        self,
        *,
        subaccount: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[MarginFill]:
        """Auto-paginate the authenticated user's margin fills, yielding each ``MarginFill``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _margin_fills_params(
            subaccount=subaccount,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/margin/fills",
            MarginFill,
            "fills",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def trades(
        self,
        *,
        ticker: str,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[MarginTrade]:
        """Public margin trades for ``ticker`` (no auth required)."""
        params = _margin_trades_params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return self._list(
            "/margin/trades", MarginTrade, "trades", params=params, extra_headers=extra_headers
        )

    def trades_all(
        self,
        *,
        ticker: str,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[MarginTrade]:
        """Auto-paginate public margin trades for ``ticker`` (no auth required)."""
        _validate_max_pages(max_pages)
        params = _margin_trades_params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/margin/trades",
            MarginTrade,
            "trades",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def cross_exit_triggers(
        self,
        ticker: str,
        *,
        kind: ExitTriggerKindLiteral | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetExitTriggersResponse:
        """``GET /margin/cross/positions/{ticker}/exit_trigger``."""
        self._require_auth()
        params = _params(kind=kind, subaccount=subaccount)
        data = self._get(
            f"/margin/cross/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            params=params,
            extra_headers=extra_headers,
        )
        return GetExitTriggersResponse.model_validate(data)

    def set_cross_exit_trigger(
        self,
        ticker: str,
        *,
        request: SetCrossExitTriggerRequest,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> ExitTrigger:
        """``PUT /margin/cross/positions/{ticker}/exit_trigger``. Not retried."""
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._put(
            f"/margin/cross/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            params=params,
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
        if data is None:
            raise KalshiError("Expected ExitTrigger body, got 204 No Content.")
        return ExitTrigger.model_validate(data)

    def cancel_cross_exit_triggers(
        self,
        ticker: str,
        *,
        kind: ExitTriggerKindLiteral | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """``DELETE /margin/cross/positions/{ticker}/exit_trigger``. Not retried."""
        self._require_auth()
        params = _params(kind=kind, subaccount=subaccount)
        self._delete(
            f"/margin/cross/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            params=params,
            extra_headers=extra_headers,
        )

    def update_cross_exit_trigger(
        self,
        ticker: str,
        trigger_id: str,
        *,
        request: UpdateExitTriggerRequest,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> ExitTrigger:
        """``PUT /margin/cross/positions/{ticker}/exit_trigger/{trigger_id}``."""
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._put(
            (
                f"/margin/cross/positions/{_seg(ticker, name='ticker')}"
                f"/exit_trigger/{_seg(trigger_id, name='trigger_id')}"
            ),
            params=params,
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
        if data is None:
            raise KalshiError("Expected ExitTrigger body, got 204 No Content.")
        return ExitTrigger.model_validate(data)

    def cancel_cross_exit_trigger(
        self,
        ticker: str,
        trigger_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """``DELETE /margin/cross/positions/{ticker}/exit_trigger/{trigger_id}``."""
        self._require_auth()
        params = _params(subaccount=subaccount)
        self._delete(
            (
                f"/margin/cross/positions/{_seg(ticker, name='ticker')}"
                f"/exit_trigger/{_seg(trigger_id, name='trigger_id')}"
            ),
            params=params,
            extra_headers=extra_headers,
        )

    def isolated_exit_triggers(
        self,
        ticker: str,
        *,
        kind: ExitTriggerKindLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetExitTriggersResponse:
        """``GET /margin/isolated/positions/{ticker}/exit_trigger``."""
        self._require_auth()
        params = _params(kind=kind)
        data = self._get(
            f"/margin/isolated/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            params=params,
            extra_headers=extra_headers,
        )
        return GetExitTriggersResponse.model_validate(data)

    def set_isolated_exit_trigger(
        self,
        ticker: str,
        *,
        request: SetIsolatedExitTriggerRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> ExitTrigger:
        """``PUT /margin/isolated/positions/{ticker}/exit_trigger``. Not retried."""
        self._require_auth()
        data = self._put(
            f"/margin/isolated/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
        if data is None:
            raise KalshiError("Expected ExitTrigger body, got 204 No Content.")
        return ExitTrigger.model_validate(data)

    def cancel_isolated_exit_triggers(
        self,
        ticker: str,
        *,
        kind: ExitTriggerKindLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """``DELETE /margin/isolated/positions/{ticker}/exit_trigger``. Not retried."""
        self._require_auth()
        params = _params(kind=kind)
        self._delete(
            f"/margin/isolated/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            params=params,
            extra_headers=extra_headers,
        )


class AsyncPerpsPortfolioResource(AsyncResource):
    """Async perps portfolio API (``positions`` / ``fills`` / ``trades`` + paginators)."""

    async def positions(
        self,
        *,
        subaccount: int | None = None,
        ticker: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginPositionsResponse:
        self._require_auth()
        params = _params(subaccount=subaccount, ticker=ticker)
        data = await self._get("/margin/positions", params=params, extra_headers=extra_headers)
        return GetMarginPositionsResponse.model_validate(data)

    async def fills(
        self,
        *,
        subaccount: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[MarginFill]:
        self._require_auth()
        params = _margin_fills_params(
            subaccount=subaccount,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return await self._list(
            "/margin/fills", MarginFill, "fills", params=params, extra_headers=extra_headers
        )

    def fills_all(
        self,
        *,
        subaccount: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[MarginFill]:
        """Returns an async iterator over the user's margin fills — use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _margin_fills_params(
            subaccount=subaccount,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/margin/fills",
            MarginFill,
            "fills",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def trades(
        self,
        *,
        ticker: str,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[MarginTrade]:
        """Public margin trades for ``ticker`` (no auth required)."""
        params = _margin_trades_params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return await self._list(
            "/margin/trades", MarginTrade, "trades", params=params, extra_headers=extra_headers
        )

    def trades_all(
        self,
        *,
        ticker: str,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[MarginTrade]:
        """Returns an async iterator over public margin trades — use ``async for`` (no auth)."""
        _validate_max_pages(max_pages)
        params = _margin_trades_params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/margin/trades",
            MarginTrade,
            "trades",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def cross_exit_triggers(
        self,
        ticker: str,
        *,
        kind: ExitTriggerKindLiteral | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetExitTriggersResponse:
        """Async :meth:`PerpsPortfolioResource.cross_exit_triggers`."""
        self._require_auth()
        params = _params(kind=kind, subaccount=subaccount)
        data = await self._get(
            f"/margin/cross/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            params=params,
            extra_headers=extra_headers,
        )
        return GetExitTriggersResponse.model_validate(data)

    async def set_cross_exit_trigger(
        self,
        ticker: str,
        *,
        request: SetCrossExitTriggerRequest,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> ExitTrigger:
        """Async :meth:`PerpsPortfolioResource.set_cross_exit_trigger`."""
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = await self._put(
            f"/margin/cross/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            params=params,
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
        if data is None:
            raise KalshiError("Expected ExitTrigger body, got 204 No Content.")
        return ExitTrigger.model_validate(data)

    async def cancel_cross_exit_triggers(
        self,
        ticker: str,
        *,
        kind: ExitTriggerKindLiteral | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Async :meth:`PerpsPortfolioResource.cancel_cross_exit_triggers`."""
        self._require_auth()
        params = _params(kind=kind, subaccount=subaccount)
        await self._delete(
            f"/margin/cross/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            params=params,
            extra_headers=extra_headers,
        )

    async def update_cross_exit_trigger(
        self,
        ticker: str,
        trigger_id: str,
        *,
        request: UpdateExitTriggerRequest,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> ExitTrigger:
        """Async :meth:`PerpsPortfolioResource.update_cross_exit_trigger`."""
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = await self._put(
            (
                f"/margin/cross/positions/{_seg(ticker, name='ticker')}"
                f"/exit_trigger/{_seg(trigger_id, name='trigger_id')}"
            ),
            params=params,
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
        if data is None:
            raise KalshiError("Expected ExitTrigger body, got 204 No Content.")
        return ExitTrigger.model_validate(data)

    async def cancel_cross_exit_trigger(
        self,
        ticker: str,
        trigger_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Async :meth:`PerpsPortfolioResource.cancel_cross_exit_trigger`."""
        self._require_auth()
        params = _params(subaccount=subaccount)
        await self._delete(
            (
                f"/margin/cross/positions/{_seg(ticker, name='ticker')}"
                f"/exit_trigger/{_seg(trigger_id, name='trigger_id')}"
            ),
            params=params,
            extra_headers=extra_headers,
        )

    async def isolated_exit_triggers(
        self,
        ticker: str,
        *,
        kind: ExitTriggerKindLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetExitTriggersResponse:
        """Async :meth:`PerpsPortfolioResource.isolated_exit_triggers`."""
        self._require_auth()
        params = _params(kind=kind)
        data = await self._get(
            f"/margin/isolated/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            params=params,
            extra_headers=extra_headers,
        )
        return GetExitTriggersResponse.model_validate(data)

    async def set_isolated_exit_trigger(
        self,
        ticker: str,
        *,
        request: SetIsolatedExitTriggerRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> ExitTrigger:
        """Async :meth:`PerpsPortfolioResource.set_isolated_exit_trigger`."""
        self._require_auth()
        data = await self._put(
            f"/margin/isolated/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
        if data is None:
            raise KalshiError("Expected ExitTrigger body, got 204 No Content.")
        return ExitTrigger.model_validate(data)

    async def cancel_isolated_exit_triggers(
        self,
        ticker: str,
        *,
        kind: ExitTriggerKindLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Async :meth:`PerpsPortfolioResource.cancel_isolated_exit_triggers`."""
        self._require_auth()
        params = _params(kind=kind)
        await self._delete(
            f"/margin/isolated/positions/{_seg(ticker, name='ticker')}/exit_trigger",
            params=params,
            extra_headers=extra_headers,
        )
