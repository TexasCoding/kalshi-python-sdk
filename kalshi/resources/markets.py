"""Markets resource — list, get, orderbook, candlesticks, bulk variants."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator
from typing import Any

from kalshi.models.common import Page
from kalshi.models.historical import Trade
from kalshi.models.markets import (
    Candlestick,
    Market,
    MarketCandlesticks,
    Orderbook,
    OrderbookLevel,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _bool_param,
    _join_tickers,
    _params,
)

_MAX_BULK = 100


def _orderbook_from_item(item: dict[str, Any]) -> Orderbook:
    """Parse one entry from GET /markets/orderbooks into an Orderbook.

    Shape is ``{"ticker": "...", "orderbook_fp": {"yes_dollars": [...], "no_dollars": [...]}}``.
    Mirrors the single-orderbook unwrapping logic, with per-item ticker.
    Raises ``ValueError`` if the server response omits a per-item ticker —
    silently returning ``ticker=""`` would corrupt caller-side lookups.
    """
    ticker = item.get("ticker")
    if not ticker:
        raise ValueError(
            "bulk orderbook item missing required 'ticker' field; "
            f"got {item!r}"
        )
    # Key-presence check (not truthy): an empty dict under "orderbook_fp" must
    # NOT fall through to the legacy "orderbook" key — that would quietly
    # substitute two different server shapes.
    ob = (
        (item.get("orderbook_fp") or {})
        if "orderbook_fp" in item
        else (item.get("orderbook") or {})
    )
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
            include_latest_before_start=_bool_param(include_latest_before_start),
        )
        data = self._get(
            f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            params=params,
        )
        raw = data.get("candlesticks", [])
        return [Candlestick.model_validate(c) for c in raw]

    def list_trades(
        self,
        *,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Trade]:
        params = _params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return self._list("/markets/trades", Trade, "trades", params=params)

    def list_trades_all(
        self,
        *,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
    ) -> Iterator[Trade]:
        params = _params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
        )
        return self._list_all("/markets/trades", Trade, "trades", params=params)

    def bulk_candlesticks(
        self,
        *,
        market_tickers: builtins.list[str] | str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        include_latest_before_start: bool | None = None,
    ) -> builtins.list[MarketCandlesticks]:
        """Fetch candlesticks for up to 100 markets in a single call.

        ``market_tickers`` serializes as a comma-separated string per spec
        (not exploded). Accepts a list, tuple, or pre-joined string.
        Spec requires at least one ticker (max 100).
        """
        if not market_tickers:
            raise ValueError("market_tickers must be a non-empty list or string")
        joined = _join_tickers(market_tickers)
        # Count validates BOTH list/tuple and pre-joined-string inputs — a
        # string with 150 comma-separated tickers must fail the same way a
        # 150-element list does.
        ticker_count = joined.count(",") + 1 if joined else 0
        if ticker_count > _MAX_BULK:
            raise ValueError(
                f"market_tickers accepts at most {_MAX_BULK} entries per spec "
                f"(got {ticker_count})"
            )
        params = _params(
            market_tickers=joined,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
            include_latest_before_start=_bool_param(include_latest_before_start),
        )
        data = self._get("/markets/candlesticks", params=params)
        raw = data.get("markets", [])
        return [MarketCandlesticks.model_validate(m) for m in raw]

    def bulk_orderbooks(
        self, *, tickers: builtins.list[str],
    ) -> builtins.list[Orderbook]:
        """Fetch orderbooks for up to 100 tickers in a single call.

        Spec requires auth and at least one ticker (max 100). ``tickers``
        wire format is ``?tickers=a&tickers=b`` (spec ``style: form,
        explode: true``) — httpx serializes list values that way by default.
        """
        self._require_auth()
        if not tickers:
            raise ValueError("tickers must be a non-empty list")
        if len(tickers) > _MAX_BULK:
            raise ValueError(
                f"tickers accepts at most {_MAX_BULK} entries per spec "
                f"(got {len(tickers)})"
            )
        params = _params(tickers=tickers)
        data = self._get("/markets/orderbooks", params=params)
        raw = data.get("orderbooks", [])
        return [_orderbook_from_item(item) for item in raw]


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
            include_latest_before_start=_bool_param(include_latest_before_start),
        )
        data = await self._get(
            f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            params=params,
        )
        raw = data.get("candlesticks", [])
        return [Candlestick.model_validate(c) for c in raw]

    async def list_trades(
        self,
        *,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Trade]:
        params = _params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return await self._list("/markets/trades", Trade, "trades", params=params)

    def list_trades_all(
        self,
        *,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Trade]:
        """Returns an async iterator — use ``async for``."""
        params = _params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
        )
        return self._list_all("/markets/trades", Trade, "trades", params=params)

    async def bulk_candlesticks(
        self,
        *,
        market_tickers: builtins.list[str] | str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        include_latest_before_start: bool | None = None,
    ) -> builtins.list[MarketCandlesticks]:
        """Fetch candlesticks for up to 100 markets in a single call.

        ``market_tickers`` serializes as a comma-separated string per spec
        (not exploded). Accepts a list, tuple, or pre-joined string.
        Spec requires at least one ticker (max 100).
        """
        if not market_tickers:
            raise ValueError("market_tickers must be a non-empty list or string")
        joined = _join_tickers(market_tickers)
        ticker_count = joined.count(",") + 1 if joined else 0
        if ticker_count > _MAX_BULK:
            raise ValueError(
                f"market_tickers accepts at most {_MAX_BULK} entries per spec "
                f"(got {ticker_count})"
            )
        params = _params(
            market_tickers=joined,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
            include_latest_before_start=_bool_param(include_latest_before_start),
        )
        data = await self._get("/markets/candlesticks", params=params)
        raw = data.get("markets", [])
        return [MarketCandlesticks.model_validate(m) for m in raw]

    async def bulk_orderbooks(
        self, *, tickers: builtins.list[str],
    ) -> builtins.list[Orderbook]:
        self._require_auth()
        if not tickers:
            raise ValueError("tickers must be a non-empty list")
        if len(tickers) > _MAX_BULK:
            raise ValueError(
                f"tickers accepts at most {_MAX_BULK} entries per spec "
                f"(got {len(tickers)})"
            )
        params = _params(tickers=tickers)
        data = await self._get("/markets/orderbooks", params=params)
        raw = data.get("orderbooks", [])
        return [_orderbook_from_item(item) for item in raw]
