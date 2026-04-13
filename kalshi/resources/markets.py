"""Markets resource — list, get, orderbook, candlesticks."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.models.markets import Candlestick, Market, Orderbook, OrderbookLevel
from kalshi.resources._base import AsyncResource, SyncResource, _params


class MarketsResource(SyncResource):
    """Sync markets API."""

    def list(
        self,
        *,
        status: str | None = None,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
        market_type: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Market]:
        params = _params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            market_type=market_type,
            limit=limit,
            cursor=cursor,
        )
        return self._list("/markets", Market, "markets", params=params)

    def list_all(
        self,
        *,
        status: str | None = None,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
        market_type: str | None = None,
        limit: int | None = None,
    ) -> Iterator[Market]:
        params = _params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            market_type=market_type,
            limit=limit,
        )
        return self._list_all("/markets", Market, "markets", params=params)

    def get(self, ticker: str) -> Market:
        data = self._get(f"/markets/{ticker}")
        market = data.get("market", data)
        return Market.model_validate(market)

    def orderbook(self, ticker: str) -> Orderbook:
        data = self._get(f"/markets/{ticker}/orderbook")
        # API returns {orderbook_fp: {yes_dollars: [...], no_dollars: [...]}}
        # Fall back to legacy keys for backward compatibility with tests/mocks
        ob = data.get("orderbook_fp") or data.get("orderbook", data)

        yes_raw = ob.get("yes_dollars") or ob.get("yes", []) or []
        no_raw = ob.get("no_dollars") or ob.get("no", []) or []

        yes_levels = [
            OrderbookLevel(price=pair[0], quantity=pair[1])
            for pair in yes_raw
            if len(pair) >= 2
        ]
        no_levels = [
            OrderbookLevel(price=pair[0], quantity=pair[1])
            for pair in no_raw
            if len(pair) >= 2
        ]

        return Orderbook(ticker=ticker, yes=yes_levels, no=no_levels)

    def candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        *,
        period_interval: int | None = None,
    ) -> builtins.list[Candlestick]:
        params = _params(period_interval=period_interval)
        data = self._get(
            f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            params=params,
        )
        raw = data.get("candlesticks", [])
        return [Candlestick.model_validate(c) for c in raw]


class AsyncMarketsResource(AsyncResource):
    """Async markets API."""

    async def list(
        self,
        *,
        status: str | None = None,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
        market_type: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Market]:
        params = _params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            market_type=market_type,
            limit=limit,
            cursor=cursor,
        )
        return await self._list("/markets", Market, "markets", params=params)

    def list_all(
        self,
        *,
        status: str | None = None,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
        market_type: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Market]:
        """Non-async method that returns an async iterator for direct use with `async for`."""
        params = _params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            market_type=market_type,
            limit=limit,
        )
        return self._list_all("/markets", Market, "markets", params=params)

    async def get(self, ticker: str) -> Market:
        data = await self._get(f"/markets/{ticker}")
        market = data.get("market", data)
        return Market.model_validate(market)

    async def orderbook(self, ticker: str) -> Orderbook:
        data = await self._get(f"/markets/{ticker}/orderbook")
        ob = data.get("orderbook_fp") or data.get("orderbook", data)

        yes_raw = ob.get("yes_dollars") or ob.get("yes", []) or []
        no_raw = ob.get("no_dollars") or ob.get("no", []) or []

        yes_levels = [
            OrderbookLevel(price=pair[0], quantity=pair[1])
            for pair in yes_raw
            if len(pair) >= 2
        ]
        no_levels = [
            OrderbookLevel(price=pair[0], quantity=pair[1])
            for pair in no_raw
            if len(pair) >= 2
        ]

        return Orderbook(ticker=ticker, yes=yes_levels, no=no_levels)

    async def candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        *,
        period_interval: int | None = None,
    ) -> builtins.list[Candlestick]:
        params = _params(period_interval=period_interval)
        data = await self._get(
            f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            params=params,
        )
        raw = data.get("candlesticks", [])
        return [Candlestick.model_validate(c) for c in raw]
