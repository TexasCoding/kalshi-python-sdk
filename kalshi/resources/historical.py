"""Historical resource — cutoff, markets, fills, orders, trades."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.models.historical import HistoricalCutoff, Trade
from kalshi.models.markets import Candlestick, Market
from kalshi.models.orders import Fill, Order
from kalshi.resources._base import AsyncResource, SyncResource, _params


class HistoricalResource(SyncResource):
    """Sync historical data API."""

    def cutoff(self) -> HistoricalCutoff:
        data = self._get("/historical/cutoff")
        return HistoricalCutoff.model_validate(data)

    def markets(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
    ) -> Page[Market]:
        params = _params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
        )
        return self._list("/historical/markets", Market, "markets", params=params)

    def markets_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
    ) -> Iterator[Market]:
        params = _params(
            limit=limit,
            ticker=ticker,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
        )
        return self._list_all("/historical/markets", Market, "markets", params=params)

    def market(self, ticker: str) -> Market:
        data = self._get(f"/historical/markets/{ticker}")
        raw = data.get("market", data)
        return Market.model_validate(raw)

    def candlesticks(
        self,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> builtins.list[Candlestick]:
        params = _params(
            period_interval=period_interval,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        data = self._get(
            f"/historical/markets/{ticker}/candlesticks",
            params=params,
        )
        raw = data.get("candlesticks", [])
        return [Candlestick.model_validate(c) for c in raw]

    def fills(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
    ) -> Page[Fill]:
        params = _params(limit=limit, cursor=cursor, ticker=ticker)
        return self._list("/historical/fills", Fill, "fills", params=params)

    def fills_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
    ) -> Iterator[Fill]:
        params = _params(limit=limit, ticker=ticker)
        return self._list_all("/historical/fills", Fill, "fills", params=params)

    def orders(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
    ) -> Page[Order]:
        params = _params(limit=limit, cursor=cursor, ticker=ticker)
        return self._list("/historical/orders", Order, "orders", params=params)

    def orders_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
    ) -> Iterator[Order]:
        params = _params(limit=limit, ticker=ticker)
        return self._list_all("/historical/orders", Order, "orders", params=params)

    def trades(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
    ) -> Page[Trade]:
        params = _params(limit=limit, cursor=cursor, ticker=ticker)
        return self._list("/historical/trades", Trade, "trades", params=params)

    def trades_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
    ) -> Iterator[Trade]:
        params = _params(limit=limit, ticker=ticker)
        return self._list_all("/historical/trades", Trade, "trades", params=params)

class AsyncHistoricalResource(AsyncResource):
    """Async historical data API."""

    async def cutoff(self) -> HistoricalCutoff:
        data = await self._get("/historical/cutoff")
        return HistoricalCutoff.model_validate(data)

    async def markets(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
    ) -> Page[Market]:
        params = _params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
        )
        return await self._list("/historical/markets", Market, "markets", params=params)

    def markets_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
    ) -> AsyncIterator[Market]:
        params = _params(
            limit=limit,
            ticker=ticker,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
        )
        return self._list_all("/historical/markets", Market, "markets", params=params)

    async def market(self, ticker: str) -> Market:
        data = await self._get(f"/historical/markets/{ticker}")
        raw = data.get("market", data)
        return Market.model_validate(raw)

    async def candlesticks(
        self,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> builtins.list[Candlestick]:
        params = _params(
            period_interval=period_interval,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        data = await self._get(
            f"/historical/markets/{ticker}/candlesticks",
            params=params,
        )
        raw = data.get("candlesticks", [])
        return [Candlestick.model_validate(c) for c in raw]

    async def fills(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
    ) -> Page[Fill]:
        params = _params(limit=limit, cursor=cursor, ticker=ticker)
        return await self._list("/historical/fills", Fill, "fills", params=params)

    def fills_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
    ) -> AsyncIterator[Fill]:
        params = _params(limit=limit, ticker=ticker)
        return self._list_all("/historical/fills", Fill, "fills", params=params)

    async def orders(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
    ) -> Page[Order]:
        params = _params(limit=limit, cursor=cursor, ticker=ticker)
        return await self._list("/historical/orders", Order, "orders", params=params)

    def orders_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
    ) -> AsyncIterator[Order]:
        params = _params(limit=limit, ticker=ticker)
        return self._list_all("/historical/orders", Order, "orders", params=params)

    async def trades(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
    ) -> Page[Trade]:
        params = _params(limit=limit, cursor=cursor, ticker=ticker)
        return await self._list("/historical/trades", Trade, "trades", params=params)

    def trades_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
    ) -> AsyncIterator[Trade]:
        params = _params(limit=limit, ticker=ticker)
        return self._list_all("/historical/trades", Trade, "trades", params=params)
