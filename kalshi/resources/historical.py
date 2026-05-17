"""Historical resource — cutoff, markets, fills, orders, trades."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator
from typing import Any

from kalshi.models.common import Page
from kalshi.models.historical import (
    HistoricalCutoff,
    MveHistoricalFilterLiteral,
    Trade,
)
from kalshi.models.markets import Candlestick, Market
from kalshi.models.orders import Fill, Order
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _join_tickers,
    _params,
    _validate_max_pages,
)

# Shared param builders (issue #46).


def _historical_markets_params(
    *,
    limit: int | None,
    cursor: str | None,
    tickers: builtins.list[str] | str | None,
    event_ticker: str | None,
    series_ticker: str | None,
    mve_filter: MveHistoricalFilterLiteral | None,
) -> dict[str, Any]:
    return _params(
        limit=limit,
        cursor=cursor,
        tickers=_join_tickers(tickers),
        event_ticker=event_ticker,
        series_ticker=series_ticker,
        mve_filter=mve_filter,
    )


def _historical_candlesticks_params(
    *, start_ts: int, end_ts: int, period_interval: int,
) -> dict[str, Any]:
    return _params(
        period_interval=period_interval,
        start_ts=start_ts,
        end_ts=end_ts,
    )


def _historical_fills_or_orders_params(
    *,
    limit: int | None,
    cursor: str | None,
    ticker: str | None,
    max_ts: int | None,
) -> dict[str, Any]:
    return _params(limit=limit, cursor=cursor, ticker=ticker, max_ts=max_ts)


def _historical_trades_params(
    *,
    limit: int | None,
    cursor: str | None,
    ticker: str | None,
    min_ts: int | None,
    max_ts: int | None,
) -> dict[str, Any]:
    return _params(
        limit=limit, cursor=cursor, ticker=ticker, min_ts=min_ts, max_ts=max_ts,
    )


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
        tickers: builtins.list[str] | str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        mve_filter: MveHistoricalFilterLiteral | None = None,
    ) -> Page[Market]:
        params = _historical_markets_params(
            limit=limit, cursor=cursor, tickers=tickers,
            event_ticker=event_ticker, series_ticker=series_ticker,
            mve_filter=mve_filter,
        )
        return self._list("/historical/markets", Market, "markets", params=params)

    def markets_all(
        self,
        *,
        limit: int | None = None,
        tickers: builtins.list[str] | str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        mve_filter: MveHistoricalFilterLiteral | None = None,
        max_pages: int | None = None,
    ) -> Iterator[Market]:
        _validate_max_pages(max_pages)
        params = _historical_markets_params(
            limit=limit, cursor=None, tickers=tickers,
            event_ticker=event_ticker, series_ticker=series_ticker,
            mve_filter=mve_filter,
        )
        return self._list_all(
            "/historical/markets", Market, "markets",
            params=params, max_pages=max_pages,
        )

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
        params = _historical_candlesticks_params(
            start_ts=start_ts, end_ts=end_ts,
            period_interval=period_interval,
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
        max_ts: int | None = None,
    ) -> Page[Fill]:
        self._require_auth()
        params = _historical_fills_or_orders_params(
            limit=limit, cursor=cursor, ticker=ticker, max_ts=max_ts,
        )
        return self._list("/historical/fills", Fill, "fills", params=params)

    def fills_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
    ) -> Iterator[Fill]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _historical_fills_or_orders_params(
            limit=limit, cursor=None, ticker=ticker, max_ts=max_ts,
        )
        return self._list_all(
            "/historical/fills", Fill, "fills",
            params=params, max_pages=max_pages,
        )

    def orders(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _historical_fills_or_orders_params(
            limit=limit, cursor=cursor, ticker=ticker, max_ts=max_ts,
        )
        return self._list("/historical/orders", Order, "orders", params=params)

    def orders_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
    ) -> Iterator[Order]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _historical_fills_or_orders_params(
            limit=limit, cursor=None, ticker=ticker, max_ts=max_ts,
        )
        return self._list_all(
            "/historical/orders", Order, "orders",
            params=params, max_pages=max_pages,
        )

    def trades(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
    ) -> Page[Trade]:
        params = _historical_trades_params(
            limit=limit, cursor=cursor, ticker=ticker,
            min_ts=min_ts, max_ts=max_ts,
        )
        return self._list("/historical/trades", Trade, "trades", params=params)

    def trades_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
    ) -> Iterator[Trade]:
        _validate_max_pages(max_pages)
        params = _historical_trades_params(
            limit=limit, cursor=None, ticker=ticker,
            min_ts=min_ts, max_ts=max_ts,
        )
        return self._list_all(
            "/historical/trades", Trade, "trades",
            params=params, max_pages=max_pages,
        )

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
        tickers: builtins.list[str] | str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        mve_filter: MveHistoricalFilterLiteral | None = None,
    ) -> Page[Market]:
        params = _historical_markets_params(
            limit=limit, cursor=cursor, tickers=tickers,
            event_ticker=event_ticker, series_ticker=series_ticker,
            mve_filter=mve_filter,
        )
        return await self._list("/historical/markets", Market, "markets", params=params)

    def markets_all(
        self,
        *,
        limit: int | None = None,
        tickers: builtins.list[str] | str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        mve_filter: MveHistoricalFilterLiteral | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[Market]:
        _validate_max_pages(max_pages)
        params = _historical_markets_params(
            limit=limit, cursor=None, tickers=tickers,
            event_ticker=event_ticker, series_ticker=series_ticker,
            mve_filter=mve_filter,
        )
        return self._list_all(
            "/historical/markets", Market, "markets",
            params=params, max_pages=max_pages,
        )

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
        params = _historical_candlesticks_params(
            start_ts=start_ts, end_ts=end_ts,
            period_interval=period_interval,
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
        max_ts: int | None = None,
    ) -> Page[Fill]:
        self._require_auth()
        params = _historical_fills_or_orders_params(
            limit=limit, cursor=cursor, ticker=ticker, max_ts=max_ts,
        )
        return await self._list("/historical/fills", Fill, "fills", params=params)

    def fills_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[Fill]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _historical_fills_or_orders_params(
            limit=limit, cursor=None, ticker=ticker, max_ts=max_ts,
        )
        return self._list_all(
            "/historical/fills", Fill, "fills",
            params=params, max_pages=max_pages,
        )

    async def orders(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _historical_fills_or_orders_params(
            limit=limit, cursor=cursor, ticker=ticker, max_ts=max_ts,
        )
        return await self._list("/historical/orders", Order, "orders", params=params)

    def orders_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[Order]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _historical_fills_or_orders_params(
            limit=limit, cursor=None, ticker=ticker, max_ts=max_ts,
        )
        return self._list_all(
            "/historical/orders", Order, "orders",
            params=params, max_pages=max_pages,
        )

    async def trades(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
    ) -> Page[Trade]:
        params = _historical_trades_params(
            limit=limit, cursor=cursor, ticker=ticker,
            min_ts=min_ts, max_ts=max_ts,
        )
        return await self._list("/historical/trades", Trade, "trades", params=params)

    def trades_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[Trade]:
        _validate_max_pages(max_pages)
        params = _historical_trades_params(
            limit=limit, cursor=None, ticker=ticker,
            min_ts=min_ts, max_ts=max_ts,
        )
        return self._list_all(
            "/historical/trades", Trade, "trades",
            params=params, max_pages=max_pages,
        )
