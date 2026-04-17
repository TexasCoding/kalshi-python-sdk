"""Markets resource — list, get, orderbook, candlesticks."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.models.markets import Candlestick, Market, Orderbook, OrderbookLevel
from kalshi.resources._base import AsyncResource, SyncResource, _join_tickers, _params


class MarketsResource(SyncResource):
    """Sync markets API."""

    def list(
        self,
        *,
        status: str | None = None,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
        tickers: builtins.list[str] | str | None = None,
        mve_filter: str | None = None,
        min_created_ts: int | None = None,
        max_created_ts: int | None = None,
        min_updated_ts: int | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        min_settled_ts: int | None = None,
        max_settled_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Market]:
        params = _params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            tickers=_join_tickers(tickers),
            mve_filter=mve_filter,
            min_created_ts=min_created_ts,
            max_created_ts=max_created_ts,
            min_updated_ts=min_updated_ts,
            min_close_ts=min_close_ts,
            max_close_ts=max_close_ts,
            min_settled_ts=min_settled_ts,
            max_settled_ts=max_settled_ts,
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
        tickers: builtins.list[str] | str | None = None,
        mve_filter: str | None = None,
        min_created_ts: int | None = None,
        max_created_ts: int | None = None,
        min_updated_ts: int | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        min_settled_ts: int | None = None,
        max_settled_ts: int | None = None,
        limit: int | None = None,
    ) -> Iterator[Market]:
        params = _params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            tickers=_join_tickers(tickers),
            mve_filter=mve_filter,
            min_created_ts=min_created_ts,
            max_created_ts=max_created_ts,
            min_updated_ts=min_updated_ts,
            min_close_ts=min_close_ts,
            max_close_ts=max_close_ts,
            min_settled_ts=min_settled_ts,
            max_settled_ts=max_settled_ts,
            limit=limit,
        )
        return self._list_all("/markets", Market, "markets", params=params)

    def get(self, ticker: str) -> Market:
        data = self._get(f"/markets/{ticker}")
        market = data.get("market", data)
        return Market.model_validate(market)

    def orderbook(self, ticker: str, *, depth: int | None = None) -> Orderbook:
        params = _params(depth=depth)
        data = self._get(f"/markets/{ticker}/orderbook", params=params)
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
        start_ts: int,
        end_ts: int,
        period_interval: int,
        include_latest_before_start: bool | None = None,
    ) -> builtins.list[Candlestick]:
        params = _params(
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
            include_latest_before_start="true" if include_latest_before_start else None,
        )
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
        tickers: builtins.list[str] | str | None = None,
        mve_filter: str | None = None,
        min_created_ts: int | None = None,
        max_created_ts: int | None = None,
        min_updated_ts: int | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        min_settled_ts: int | None = None,
        max_settled_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Market]:
        params = _params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            tickers=_join_tickers(tickers),
            mve_filter=mve_filter,
            min_created_ts=min_created_ts,
            max_created_ts=max_created_ts,
            min_updated_ts=min_updated_ts,
            min_close_ts=min_close_ts,
            max_close_ts=max_close_ts,
            min_settled_ts=min_settled_ts,
            max_settled_ts=max_settled_ts,
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
        tickers: builtins.list[str] | str | None = None,
        mve_filter: str | None = None,
        min_created_ts: int | None = None,
        max_created_ts: int | None = None,
        min_updated_ts: int | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        min_settled_ts: int | None = None,
        max_settled_ts: int | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Market]:
        """Non-async method that returns an async iterator for direct use with `async for`."""
        params = _params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            tickers=_join_tickers(tickers),
            mve_filter=mve_filter,
            min_created_ts=min_created_ts,
            max_created_ts=max_created_ts,
            min_updated_ts=min_updated_ts,
            min_close_ts=min_close_ts,
            max_close_ts=max_close_ts,
            min_settled_ts=min_settled_ts,
            max_settled_ts=max_settled_ts,
            limit=limit,
        )
        return self._list_all("/markets", Market, "markets", params=params)

    async def get(self, ticker: str) -> Market:
        data = await self._get(f"/markets/{ticker}")
        market = data.get("market", data)
        return Market.model_validate(market)

    async def orderbook(self, ticker: str, *, depth: int | None = None) -> Orderbook:
        params = _params(depth=depth)
        data = await self._get(f"/markets/{ticker}/orderbook", params=params)
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
        start_ts: int,
        end_ts: int,
        period_interval: int,
        include_latest_before_start: bool | None = None,
    ) -> builtins.list[Candlestick]:
        params = _params(
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
            include_latest_before_start="true" if include_latest_before_start else None,
        )
        data = await self._get(
            f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            params=params,
        )
        raw = data.get("candlesticks", [])
        return [Candlestick.model_validate(c) for c in raw]
