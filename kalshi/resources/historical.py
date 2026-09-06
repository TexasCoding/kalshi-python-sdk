"""Historical resource — cutoff, markets, fills, orders, trades, positions."""

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
from kalshi.models.portfolio import MarketPosition, PositionsResponse
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _bool_param,
    _join_tickers,
    _params,
    _seg,
    _validate_limit,
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
    limit = _validate_limit(limit, hi=1000, lo=0)
    return _params(
        limit=limit,
        cursor=cursor,
        tickers=_join_tickers(tickers),
        event_ticker=event_ticker,
        series_ticker=series_ticker,
        mve_filter=mve_filter,
    )


def _historical_candlesticks_params(
    *,
    start_ts: int,
    end_ts: int,
    period_interval: int,
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
    limit = _validate_limit(limit, hi=1000)
    return _params(limit=limit, cursor=cursor, ticker=ticker, max_ts=max_ts)


def _historical_trades_params(
    *,
    limit: int | None,
    cursor: str | None,
    ticker: str | None,
    min_ts: int | None,
    max_ts: int | None,
    is_block_trade: bool | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000, lo=0)
    return _params(
        limit=limit,
        cursor=cursor,
        ticker=ticker,
        min_ts=min_ts,
        max_ts=max_ts,
        is_block_trade=_bool_param(is_block_trade),
    )


def _historical_positions_params(
    *,
    limit: int | None,
    cursor: str | None,
    ticker: str | None,
    event_ticker: str | None,
    subaccount: int | None,
) -> dict[str, Any]:
    """Query params for GET /historical/positions.

    Spec params are a subset of /portfolio/positions (no ``count_filter``).
    ``subaccount`` defaults to the primary (0) server-side when omitted.
    """
    limit = _validate_limit(limit, hi=1000)
    return _params(
        limit=limit,
        cursor=cursor,
        ticker=ticker,
        event_ticker=event_ticker,
        subaccount=subaccount,
    )


class HistoricalResource(SyncResource):
    """Sync historical data API."""

    def cutoff(self, *, extra_headers: dict[str, str] | None = None) -> HistoricalCutoff:
        data = self._get("/historical/cutoff", extra_headers=extra_headers)
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
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Market]:
        params = _historical_markets_params(
            limit=limit,
            cursor=cursor,
            tickers=tickers,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
            mve_filter=mve_filter,
        )
        return self._list(
            "/historical/markets", Market, "markets", params=params, extra_headers=extra_headers
        )

    def markets_all(
        self,
        *,
        limit: int | None = None,
        tickers: builtins.list[str] | str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        mve_filter: MveHistoricalFilterLiteral | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Market]:
        _validate_max_pages(max_pages)
        params = _historical_markets_params(
            limit=limit,
            cursor=None,
            tickers=tickers,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
            mve_filter=mve_filter,
        )
        return self._list_all(
            "/historical/markets",
            Market,
            "markets",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def market(self, ticker: str, *, extra_headers: dict[str, str] | None = None) -> Market:
        data = self._get(
            f"/historical/markets/{_seg(ticker, name='ticker')}", extra_headers=extra_headers
        )
        raw = data.get("market", data)
        return Market.model_validate(raw)

    def candlesticks(
        self,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[Candlestick]:
        params = _historical_candlesticks_params(
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
        )
        data = self._get(
            f"/historical/markets/{_seg(ticker, name='ticker')}/candlesticks",
            params=params,
            extra_headers=extra_headers,
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
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Fill]:
        self._require_auth()
        params = _historical_fills_or_orders_params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            max_ts=max_ts,
        )
        return self._list(
            "/historical/fills", Fill, "fills", params=params, extra_headers=extra_headers
        )

    def fills_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Fill]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _historical_fills_or_orders_params(
            limit=limit,
            cursor=None,
            ticker=ticker,
            max_ts=max_ts,
        )
        return self._list_all(
            "/historical/fills",
            Fill,
            "fills",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def orders(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _historical_fills_or_orders_params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            max_ts=max_ts,
        )
        return self._list(
            "/historical/orders", Order, "orders", params=params, extra_headers=extra_headers
        )

    def orders_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Order]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _historical_fills_or_orders_params(
            limit=limit,
            cursor=None,
            ticker=ticker,
            max_ts=max_ts,
        )
        return self._list_all(
            "/historical/orders",
            Order,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def trades(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        is_block_trade: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Trade]:
        params = _historical_trades_params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            is_block_trade=is_block_trade,
        )
        return self._list(
            "/historical/trades", Trade, "trades", params=params, extra_headers=extra_headers
        )

    def trades_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        is_block_trade: bool | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Trade]:
        _validate_max_pages(max_pages)
        params = _historical_trades_params(
            limit=limit,
            cursor=None,
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            is_block_trade=is_block_trade,
        )
        return self._list_all(
            "/historical/trades",
            Trade,
            "trades",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def positions(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> PositionsResponse:
        """Settled market positions archived to the historical database.

        Positions whose markets were archived before
        ``market_positions_last_updated_ts`` on :meth:`cutoff` are available
        here. Unsettled positions remain on ``GET /portfolio/positions``.
        ``subaccount`` defaults to the primary (0) server-side when omitted.
        """
        self._require_auth()
        params = _historical_positions_params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        data = self._get("/historical/positions", params=params, extra_headers=extra_headers)
        return PositionsResponse.model_validate(data)

    def positions_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[MarketPosition]:
        """Auto-paginate ``/historical/positions``, yielding each ``MarketPosition``.

        Mirrors :meth:`kalshi.resources.portfolio.PortfolioResource.positions_all`.
        ``event_positions`` aggregates are not iterated (page boundaries cut them
        arbitrarily); use :meth:`positions` page-by-page for the event view.
        """
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _historical_positions_params(
            limit=limit,
            cursor=None,
            ticker=ticker,
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        return self._list_all(
            "/historical/positions",
            MarketPosition,
            "market_positions",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )


class AsyncHistoricalResource(AsyncResource):
    """Async historical data API."""

    async def cutoff(self, *, extra_headers: dict[str, str] | None = None) -> HistoricalCutoff:
        data = await self._get("/historical/cutoff", extra_headers=extra_headers)
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
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Market]:
        params = _historical_markets_params(
            limit=limit,
            cursor=cursor,
            tickers=tickers,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
            mve_filter=mve_filter,
        )
        return await self._list(
            "/historical/markets", Market, "markets", params=params, extra_headers=extra_headers
        )

    def markets_all(
        self,
        *,
        limit: int | None = None,
        tickers: builtins.list[str] | str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        mve_filter: MveHistoricalFilterLiteral | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Market]:
        _validate_max_pages(max_pages)
        params = _historical_markets_params(
            limit=limit,
            cursor=None,
            tickers=tickers,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
            mve_filter=mve_filter,
        )
        return self._list_all(
            "/historical/markets",
            Market,
            "markets",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def market(self, ticker: str, *, extra_headers: dict[str, str] | None = None) -> Market:
        data = await self._get(
            f"/historical/markets/{_seg(ticker, name='ticker')}", extra_headers=extra_headers
        )
        raw = data.get("market", data)
        return Market.model_validate(raw)

    async def candlesticks(
        self,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[Candlestick]:
        params = _historical_candlesticks_params(
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
        )
        data = await self._get(
            f"/historical/markets/{_seg(ticker, name='ticker')}/candlesticks",
            params=params,
            extra_headers=extra_headers,
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
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Fill]:
        self._require_auth()
        params = _historical_fills_or_orders_params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            max_ts=max_ts,
        )
        return await self._list(
            "/historical/fills", Fill, "fills", params=params, extra_headers=extra_headers
        )

    def fills_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Fill]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _historical_fills_or_orders_params(
            limit=limit,
            cursor=None,
            ticker=ticker,
            max_ts=max_ts,
        )
        return self._list_all(
            "/historical/fills",
            Fill,
            "fills",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def orders(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _historical_fills_or_orders_params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            max_ts=max_ts,
        )
        return await self._list(
            "/historical/orders", Order, "orders", params=params, extra_headers=extra_headers
        )

    def orders_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Order]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _historical_fills_or_orders_params(
            limit=limit,
            cursor=None,
            ticker=ticker,
            max_ts=max_ts,
        )
        return self._list_all(
            "/historical/orders",
            Order,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def trades(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        is_block_trade: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Trade]:
        params = _historical_trades_params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            is_block_trade=is_block_trade,
        )
        return await self._list(
            "/historical/trades", Trade, "trades", params=params, extra_headers=extra_headers
        )

    def trades_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        is_block_trade: bool | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Trade]:
        _validate_max_pages(max_pages)
        params = _historical_trades_params(
            limit=limit,
            cursor=None,
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            is_block_trade=is_block_trade,
        )
        return self._list_all(
            "/historical/trades",
            Trade,
            "trades",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def positions(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> PositionsResponse:
        """Settled market positions archived to the historical database.

        Positions whose markets were archived before
        ``market_positions_last_updated_ts`` on :meth:`cutoff` are available
        here. Unsettled positions remain on ``GET /portfolio/positions``.
        ``subaccount`` defaults to the primary (0) server-side when omitted.
        """
        self._require_auth()
        params = _historical_positions_params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        data = await self._get(
            "/historical/positions", params=params, extra_headers=extra_headers
        )
        return PositionsResponse.model_validate(data)

    def positions_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[MarketPosition]:
        """Auto-paginate ``/historical/positions``, yielding each ``MarketPosition``.

        Mirrors :meth:`kalshi.resources.portfolio.AsyncPortfolioResource.positions_all`.
        ``event_positions`` aggregates are not iterated (page boundaries cut them
        arbitrarily); use :meth:`positions` page-by-page for the event view.
        """
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _historical_positions_params(
            limit=limit,
            cursor=None,
            ticker=ticker,
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        return self._list_all(
            "/historical/positions",
            MarketPosition,
            "market_positions",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )
