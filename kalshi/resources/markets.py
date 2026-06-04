"""Markets resource — list, get, orderbook, candlesticks, bulk variants."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator
from typing import Any

from typing_extensions import deprecated

from kalshi.errors import KalshiError
from kalshi.models.common import Page
from kalshi.models.historical import Trade
from kalshi.models.markets import (
    Candlestick,
    Market,
    MarketCandlesticks,
    MarketStatusLiteral,
    MveFilterLiteral,
    Orderbook,
    OrderbookLevel,
)
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

_MAX_BULK = 100


# ---------------------------------------------------------------------------
# Shared helpers (issue #46): query-param builders + response parsers shared
# between sync and async classes.
# ---------------------------------------------------------------------------


def _list_markets_params(
    *,
    status: MarketStatusLiteral | None,
    series_ticker: str | None,
    event_ticker: str | None,
    tickers: builtins.list[str] | str | None,
    mve_filter: MveFilterLiteral | None,
    min_created_ts: int | None,
    max_created_ts: int | None,
    min_updated_ts: int | None,
    min_close_ts: int | None,
    max_close_ts: int | None,
    min_settled_ts: int | None,
    max_settled_ts: int | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000, lo=0)
    return _params(
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


def _candlesticks_params(
    *,
    start_ts: int,
    end_ts: int,
    period_interval: int,
    include_latest_before_start: bool | None,
) -> dict[str, Any]:
    return _params(
        start_ts=start_ts,
        end_ts=end_ts,
        period_interval=period_interval,
        include_latest_before_start=_bool_param(include_latest_before_start),
    )


def _list_trades_params(
    *,
    ticker: str | None,
    min_ts: int | None,
    max_ts: int | None,
    limit: int | None,
    cursor: str | None,
    is_block_trade: bool | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000, lo=0)
    return _params(
        ticker=ticker,
        min_ts=min_ts,
        max_ts=max_ts,
        limit=limit,
        cursor=cursor,
        is_block_trade=_bool_param(is_block_trade),
    )


def _bulk_candlesticks_params(
    *,
    market_tickers: builtins.list[str] | str,
    start_ts: int,
    end_ts: int,
    period_interval: int,
    include_latest_before_start: bool | None,
) -> dict[str, Any]:
    """Validate + build params for GET /markets/candlesticks (bulk).

    Spec requires 1..100 tickers. Splits + filters empties so a pre-joined
    string like ``"A,B,,"`` and a 2-element list validate identically.
    """
    if not market_tickers:
        raise ValueError("market_tickers must be a non-empty list or string")
    joined = _join_tickers(market_tickers)
    ticker_count = sum(1 for t in joined.split(",") if t.strip()) if joined else 0
    if ticker_count > _MAX_BULK:
        raise ValueError(
            f"market_tickers accepts at most {_MAX_BULK} entries per spec (got {ticker_count})"
        )
    return _params(
        market_tickers=joined,
        start_ts=start_ts,
        end_ts=end_ts,
        period_interval=period_interval,
        include_latest_before_start=_bool_param(include_latest_before_start),
    )


def _bulk_orderbooks_params(
    *,
    tickers: builtins.list[str],
) -> dict[str, Any]:
    """Validate + build params for GET /markets/orderbooks (bulk).

    Spec requires 1..100 tickers. Wire format is ``?tickers=a&tickers=b``
    (style: form, explode: true).
    """
    if not tickers:
        raise ValueError("tickers must be a non-empty list")
    if len(tickers) > _MAX_BULK:
        raise ValueError(
            f"tickers accepts at most {_MAX_BULK} entries per spec (got {len(tickers)})"
        )
    return _params(tickers=tickers)


def _parse_orderbook(data: dict[str, Any], ticker: str) -> Orderbook:
    """Parse the GET /markets/{ticker}/orderbook envelope into an Orderbook."""
    # API returns {orderbook_fp: {yes_dollars: [...], no_dollars: [...]}}
    # Fall back to legacy keys for backward compatibility with tests/mocks
    ob = data.get("orderbook_fp") or data.get("orderbook", data)

    yes_raw = ob.get("yes_dollars") or ob.get("yes", []) or []
    no_raw = ob.get("no_dollars") or ob.get("no", []) or []

    yes_levels = [
        OrderbookLevel(price=pair[0], quantity=pair[1]) for pair in yes_raw if len(pair) >= 2
    ]
    no_levels = [
        OrderbookLevel(price=pair[0], quantity=pair[1]) for pair in no_raw if len(pair) >= 2
    ]
    return Orderbook(ticker=ticker, yes=yes_levels, no=no_levels)


def _orderbook_from_item(item: dict[str, Any]) -> Orderbook:
    """Parse one entry from GET /markets/orderbooks into an Orderbook.

    Shape is ``{"ticker": "...", "orderbook_fp": {"yes_dollars": [...], "no_dollars": [...]}}``.
    Mirrors the single-orderbook unwrapping logic, with per-item ticker.
    Raises ``KalshiError`` (server protocol violation) if the response omits
    or empty-strings the per-item ticker — silently returning ``ticker=""``
    would corrupt caller-side lookups.
    """
    ticker = item.get("ticker")
    if not ticker:
        raise KalshiError(
            "bulk orderbook item has empty or missing 'ticker' field "
            f"in server response; got {item!r}"
        )
    # Key-presence check (not truthy): an empty dict under "orderbook_fp" must
    # NOT fall through to the legacy "orderbook" key — that would quietly
    # substitute two different server shapes.
    ob = (
        (item.get("orderbook_fp") or {})
        if "orderbook_fp" in item
        else (item.get("orderbook") or {})
    )
    # `ob.get(key)` returns None on missing key; the trailing `or []` handles
    # both None and an explicitly-null JSON value from the server.
    yes_raw = ob.get("yes_dollars") or ob.get("yes") or []
    no_raw = ob.get("no_dollars") or ob.get("no") or []
    yes_levels = [
        OrderbookLevel(price=pair[0], quantity=pair[1]) for pair in yes_raw if len(pair) >= 2
    ]
    no_levels = [
        OrderbookLevel(price=pair[0], quantity=pair[1]) for pair in no_raw if len(pair) >= 2
    ]
    return Orderbook(ticker=ticker, yes=yes_levels, no=no_levels)


class MarketsResource(SyncResource):
    """Sync markets API."""

    def list(
        self,
        *,
        status: MarketStatusLiteral | None = None,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
        tickers: builtins.list[str] | str | None = None,
        mve_filter: MveFilterLiteral | None = None,
        min_created_ts: int | None = None,
        max_created_ts: int | None = None,
        min_updated_ts: int | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        min_settled_ts: int | None = None,
        max_settled_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Market]:
        params = _list_markets_params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            tickers=tickers,
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
        return self._list("/markets", Market, "markets", params=params, extra_headers=extra_headers)

    def list_all(
        self,
        *,
        status: MarketStatusLiteral | None = None,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
        tickers: builtins.list[str] | str | None = None,
        mve_filter: MveFilterLiteral | None = None,
        min_created_ts: int | None = None,
        max_created_ts: int | None = None,
        min_updated_ts: int | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        min_settled_ts: int | None = None,
        max_settled_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Market]:
        _validate_max_pages(max_pages)
        params = _list_markets_params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            tickers=tickers,
            mve_filter=mve_filter,
            min_created_ts=min_created_ts,
            max_created_ts=max_created_ts,
            min_updated_ts=min_updated_ts,
            min_close_ts=min_close_ts,
            max_close_ts=max_close_ts,
            min_settled_ts=min_settled_ts,
            max_settled_ts=max_settled_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/markets",
            Market,
            "markets",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def get(self, ticker: str, *, extra_headers: dict[str, str] | None = None) -> Market:
        data = self._get(f"/markets/{_seg(ticker, name='ticker')}", extra_headers=extra_headers)
        market = data.get("market", data)
        return Market.model_validate(market)

    def orderbook(
        self, ticker: str, *, depth: int | None = None, extra_headers: dict[str, str] | None = None
    ) -> Orderbook:
        self._require_auth()
        params = _params(depth=depth)
        data = self._get(
            f"/markets/{_seg(ticker, name='ticker')}/orderbook",
            params=params,
            extra_headers=extra_headers,
        )
        return _parse_orderbook(data, ticker)

    def candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        include_latest_before_start: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[Candlestick]:
        params = _candlesticks_params(
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
            include_latest_before_start=include_latest_before_start,
        )
        data = self._get(
            f"/series/{_seg(series_ticker, name='series_ticker')}/markets/{_seg(ticker, name='ticker')}/candlesticks",  # noqa: E501
            params=params,
            extra_headers=extra_headers,
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
        is_block_trade: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Trade]:
        params = _list_trades_params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            is_block_trade=is_block_trade,
        )
        return self._list(
            "/markets/trades", Trade, "trades", params=params, extra_headers=extra_headers
        )

    def list_all_trades(
        self,
        *,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        is_block_trade: bool | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Trade]:
        _validate_max_pages(max_pages)
        params = _list_trades_params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
            is_block_trade=is_block_trade,
        )
        return self._list_all(
            "/markets/trades",
            Trade,
            "trades",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @deprecated(
        "`MarketsResource.list_trades_all` is deprecated since v3.0.0 and will be "
        "removed in a future release; use `list_all_trades` instead."
    )
    def list_trades_all(
        self,
        *,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        is_block_trade: bool | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Trade]:
        """.. deprecated:: 3.0.0  Use :meth:`list_all_trades` instead."""
        return self.list_all_trades(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            is_block_trade=is_block_trade,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def bulk_candlesticks(
        self,
        *,
        market_tickers: builtins.list[str] | str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        include_latest_before_start: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarketCandlesticks]:
        """Fetch candlesticks for up to 100 markets in a single call.

        ``market_tickers`` serializes as a comma-separated string per spec
        (not exploded). Accepts a list, tuple, or pre-joined string.
        Spec requires at least one ticker (max 100).
        """
        params = _bulk_candlesticks_params(
            market_tickers=market_tickers,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
            include_latest_before_start=include_latest_before_start,
        )
        data = self._get("/markets/candlesticks", params=params, extra_headers=extra_headers)
        raw = data.get("markets", [])
        return [MarketCandlesticks.model_validate(m) for m in raw]

    def bulk_orderbooks(
        self, *, tickers: builtins.list[str], extra_headers: dict[str, str] | None = None
    ) -> builtins.list[Orderbook]:
        """Fetch orderbooks for up to 100 tickers in a single call.

        Spec requires auth and at least one ticker (max 100). ``tickers``
        wire format is ``?tickers=a&tickers=b`` (spec ``style: form,
        explode: true``) — httpx serializes list values that way by default.
        """
        self._require_auth()
        params = _bulk_orderbooks_params(tickers=tickers)
        data = self._get("/markets/orderbooks", params=params, extra_headers=extra_headers)
        raw = data.get("orderbooks", [])
        return [_orderbook_from_item(item) for item in raw]


class AsyncMarketsResource(AsyncResource):
    """Async markets API."""

    async def list(
        self,
        *,
        status: MarketStatusLiteral | None = None,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
        tickers: builtins.list[str] | str | None = None,
        mve_filter: MveFilterLiteral | None = None,
        min_created_ts: int | None = None,
        max_created_ts: int | None = None,
        min_updated_ts: int | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        min_settled_ts: int | None = None,
        max_settled_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Market]:
        params = _list_markets_params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            tickers=tickers,
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
        return await self._list(
            "/markets", Market, "markets", params=params, extra_headers=extra_headers
        )

    def list_all(
        self,
        *,
        status: MarketStatusLiteral | None = None,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
        tickers: builtins.list[str] | str | None = None,
        mve_filter: MveFilterLiteral | None = None,
        min_created_ts: int | None = None,
        max_created_ts: int | None = None,
        min_updated_ts: int | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        min_settled_ts: int | None = None,
        max_settled_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Market]:
        """Returns an async iterator — use ``async for``."""
        _validate_max_pages(max_pages)
        params = _list_markets_params(
            status=status,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            tickers=tickers,
            mve_filter=mve_filter,
            min_created_ts=min_created_ts,
            max_created_ts=max_created_ts,
            min_updated_ts=min_updated_ts,
            min_close_ts=min_close_ts,
            max_close_ts=max_close_ts,
            min_settled_ts=min_settled_ts,
            max_settled_ts=max_settled_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/markets",
            Market,
            "markets",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def get(self, ticker: str, *, extra_headers: dict[str, str] | None = None) -> Market:
        data = await self._get(
            f"/markets/{_seg(ticker, name='ticker')}", extra_headers=extra_headers
        )
        market = data.get("market", data)
        return Market.model_validate(market)

    async def orderbook(
        self, ticker: str, *, depth: int | None = None, extra_headers: dict[str, str] | None = None
    ) -> Orderbook:
        self._require_auth()
        params = _params(depth=depth)
        data = await self._get(
            f"/markets/{_seg(ticker, name='ticker')}/orderbook",
            params=params,
            extra_headers=extra_headers,
        )
        return _parse_orderbook(data, ticker)

    async def candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        include_latest_before_start: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[Candlestick]:
        params = _candlesticks_params(
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
            include_latest_before_start=include_latest_before_start,
        )
        data = await self._get(
            f"/series/{_seg(series_ticker, name='series_ticker')}/markets/{_seg(ticker, name='ticker')}/candlesticks",  # noqa: E501
            params=params,
            extra_headers=extra_headers,
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
        is_block_trade: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Trade]:
        params = _list_trades_params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            is_block_trade=is_block_trade,
        )
        return await self._list(
            "/markets/trades", Trade, "trades", params=params, extra_headers=extra_headers
        )

    def list_all_trades(
        self,
        *,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        is_block_trade: bool | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Trade]:
        """Returns an async iterator — use ``async for``."""
        _validate_max_pages(max_pages)
        params = _list_trades_params(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
            is_block_trade=is_block_trade,
        )
        return self._list_all(
            "/markets/trades",
            Trade,
            "trades",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @deprecated(
        "`AsyncMarketsResource.list_trades_all` is deprecated since v3.0.0 and "
        "will be removed in a future release; use `list_all_trades` instead."
    )
    def list_trades_all(
        self,
        *,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        is_block_trade: bool | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Trade]:
        """.. deprecated:: 3.0.0  Use :meth:`list_all_trades` instead."""
        return self.list_all_trades(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            is_block_trade=is_block_trade,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def bulk_candlesticks(
        self,
        *,
        market_tickers: builtins.list[str] | str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        include_latest_before_start: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarketCandlesticks]:
        """Fetch candlesticks for up to 100 markets in a single call.

        ``market_tickers`` serializes as a comma-separated string per spec
        (not exploded). Accepts a list, tuple, or pre-joined string.
        Spec requires at least one ticker (max 100).
        """
        params = _bulk_candlesticks_params(
            market_tickers=market_tickers,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
            include_latest_before_start=include_latest_before_start,
        )
        data = await self._get("/markets/candlesticks", params=params, extra_headers=extra_headers)
        raw = data.get("markets", [])
        return [MarketCandlesticks.model_validate(m) for m in raw]

    async def bulk_orderbooks(
        self, *, tickers: builtins.list[str], extra_headers: dict[str, str] | None = None
    ) -> builtins.list[Orderbook]:
        """Fetch orderbooks for up to 100 tickers in a single call.

        Spec requires auth and at least one ticker (max 100). ``tickers``
        wire format is ``?tickers=a&tickers=b`` (spec ``style: form,
        explode: true``) — httpx serializes list values that way by default.
        """
        self._require_auth()
        params = _bulk_orderbooks_params(tickers=tickers)
        data = await self._get("/markets/orderbooks", params=params, extra_headers=extra_headers)
        raw = data.get("orderbooks", [])
        return [_orderbook_from_item(item) for item in raw]
