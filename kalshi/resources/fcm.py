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

from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.models.orders import Order
from kalshi.models.portfolio import PositionsResponse
from kalshi.resources._base import AsyncResource, SyncResource, _params


class FcmResource(SyncResource):
    """Sync FCM API — orders and positions filtered by subtrader_id."""

    def orders(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return self._list("/fcm/orders", Order, "orders", params=params)

    def orders_all(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
    ) -> Iterator[Order]:
        self._require_auth()
        params = _params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
        )
        return self._list_all("/fcm/orders", Order, "orders", params=params)

    def positions(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        count_filter: str | None = None,
        settlement_status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> PositionsResponse:
        self._require_auth()
        params = _params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
            settlement_status=settlement_status,
            limit=limit,
            cursor=cursor,
        )
        data = self._get("/fcm/positions", params=params)
        return PositionsResponse.model_validate(data)


class AsyncFcmResource(AsyncResource):
    """Async FCM API."""

    async def orders(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return await self._list("/fcm/orders", Order, "orders", params=params)

    def orders_all(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Order]:
        """Returns an async iterator — use ``async for``."""
        self._require_auth()
        params = _params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
        )
        return self._list_all("/fcm/orders", Order, "orders", params=params)

    async def positions(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        count_filter: str | None = None,
        settlement_status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> PositionsResponse:
        self._require_auth()
        params = _params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
            settlement_status=settlement_status,
            limit=limit,
            cursor=cursor,
        )
        data = await self._get("/fcm/positions", params=params)
        return PositionsResponse.model_validate(data)
