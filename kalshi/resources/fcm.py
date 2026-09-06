"""FCM resource — Futures Commission Merchant endpoints.

These endpoints filter orders/positions by ``subtrader_id`` and are only
usable by FCM-member accounts. They REUSE the existing Order and
PositionsResponse shapes — the endpoints differ only in the subtrader
filter, not in response shape.

Non-FCM accounts receive 401/403 on these routes. Demo does service them
(per Path B audit 2026-04-18) but typically returns empty lists for an
arbitrary subtrader_id.
"""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator
from typing import Any

from kalshi.models.common import Page
from kalshi.models.orders import Order, OrderStatusLiteral
from kalshi.models.portfolio import MarketPosition, PositionsResponse, SettlementStatusLiteral
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _params,
    _validate_limit,
    _validate_max_pages,
)

# Shared param builders (issue #46).


def _join_client_order_ids(
    ids: str | builtins.list[str] | None,
) -> str | None:
    """Serialize ``client_order_ids`` as a comma-separated string (spec max 100)."""
    if ids is None:
        return None
    parts = [p for p in ids.split(",") if p] if isinstance(ids, str) else list(ids)
    if len(parts) > 100:
        raise ValueError(
            f"client_order_ids accepts at most 100 entries per spec (got {len(parts)})"
        )
    return ",".join(parts) if parts else None


def _fcm_orders_params(
    *,
    subtrader_id: str | None,
    client_order_ids: str | builtins.list[str] | None,
    ticker: str | None,
    event_ticker: str | None,
    status: OrderStatusLiteral | None,
    min_ts: int | None,
    max_ts: int | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    joined = _join_client_order_ids(client_order_ids)
    if not subtrader_id and not joined:
        raise ValueError("fcm.orders requires subtrader_id or client_order_ids")
    limit = _validate_limit(limit, hi=1000)
    return _params(
        subtrader_id=subtrader_id,
        client_order_ids=joined,
        ticker=ticker,
        event_ticker=event_ticker,
        status=status,
        min_ts=min_ts,
        max_ts=max_ts,
        limit=limit,
        cursor=cursor,
    )


def _fcm_positions_params(
    *,
    subtrader_id: str,
    ticker: str | None,
    event_ticker: str | None,
    count_filter: str | None,
    settlement_status: SettlementStatusLiteral | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000)
    return _params(
        subtrader_id=subtrader_id,
        ticker=ticker,
        event_ticker=event_ticker,
        count_filter=count_filter,
        settlement_status=settlement_status,
        limit=limit,
        cursor=cursor,
    )


class FcmResource(SyncResource):
    """Sync FCM API — orders and positions filtered by subtrader_id."""

    def orders(
        self,
        *,
        subtrader_id: str | None = None,
        client_order_ids: str | builtins.list[str] | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _fcm_orders_params(
            subtrader_id=subtrader_id,
            client_order_ids=client_order_ids,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return self._list(
            "/fcm/orders", Order, "orders", params=params, extra_headers=extra_headers
        )

    def orders_all(
        self,
        *,
        subtrader_id: str | None = None,
        client_order_ids: str | builtins.list[str] | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Order]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fcm_orders_params(
            subtrader_id=subtrader_id,
            client_order_ids=client_order_ids,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/fcm/orders",
            Order,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def positions(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        count_filter: str | None = None,
        settlement_status: SettlementStatusLiteral | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> PositionsResponse:
        self._require_auth()
        params = _fcm_positions_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
            settlement_status=settlement_status,
            limit=limit,
            cursor=cursor,
        )
        data = self._get("/fcm/positions", params=params, extra_headers=extra_headers)
        return PositionsResponse.model_validate(data)

    def positions_all(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        count_filter: str | None = None,
        settlement_status: SettlementStatusLiteral | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[MarketPosition]:
        """Auto-paginate ``/fcm/positions``, yielding each ``MarketPosition``.

        Mirrors :meth:`PortfolioResource.positions_all`. ``event_positions``
        from the response envelope are intentionally not yielded; see that
        docstring for the rationale.
        """
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fcm_positions_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
            settlement_status=settlement_status,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/fcm/positions",
            MarketPosition,
            "market_positions",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )


class AsyncFcmResource(AsyncResource):
    """Async FCM API."""

    async def orders(
        self,
        *,
        subtrader_id: str | None = None,
        client_order_ids: str | builtins.list[str] | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _fcm_orders_params(
            subtrader_id=subtrader_id,
            client_order_ids=client_order_ids,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return await self._list(
            "/fcm/orders", Order, "orders", params=params, extra_headers=extra_headers
        )

    def orders_all(
        self,
        *,
        subtrader_id: str | None = None,
        client_order_ids: str | builtins.list[str] | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Order]:
        """Returns an async iterator — use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fcm_orders_params(
            subtrader_id=subtrader_id,
            client_order_ids=client_order_ids,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/fcm/orders",
            Order,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def positions(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        count_filter: str | None = None,
        settlement_status: SettlementStatusLiteral | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> PositionsResponse:
        self._require_auth()
        params = _fcm_positions_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
            settlement_status=settlement_status,
            limit=limit,
            cursor=cursor,
        )
        data = await self._get("/fcm/positions", params=params, extra_headers=extra_headers)
        return PositionsResponse.model_validate(data)

    def positions_all(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        count_filter: str | None = None,
        settlement_status: SettlementStatusLiteral | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[MarketPosition]:
        """Async counterpart of :meth:`FcmResource.positions_all`. Use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fcm_positions_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
            settlement_status=settlement_status,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/fcm/positions",
            MarketPosition,
            "market_positions",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )
