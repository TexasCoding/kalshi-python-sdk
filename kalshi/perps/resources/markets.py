"""Perps markets resource — list/get, orderbook, bulk orderbooks, candlesticks, schedules.

Six read-only ``GET`` endpoints, all public market data (the spec marks no
``security`` block on any of them) — so none call ``_require_auth()``, unlike the
public-markets ``orderbook`` which does. All retry on 429/502/503/504 (GET).

Divergence from :mod:`kalshi.resources.markets`: ``list()`` returns a plain
``builtins.list[MarginMarket]`` (NOT a ``Page``) and has **no** ``list_all()`` —
``GetMarginMarketsResponse`` carries no cursor, so there is nothing to paginate.
The orderbook is ``{bids, asks}`` (margin) rather than ``{yes, no}``.
``bulk_orderbooks`` serializes ``tickers`` as a comma-separated string
(spec ``style: form, explode: false``).
"""

from __future__ import annotations

import builtins
from typing import Any

from kalshi.errors import KalshiError
from kalshi.perps.models.markets import (
    GetMarginMarketCandlesticksResponse,
    GetMarginMarketOrderbooksResponse,
    GetMarginMarketsResponse,
    MarginMarket,
    MarginMarketCandlestick,
    MarginMarketScheduleDetails,
    MarginMarketStatusLiteral,
    MarginOrderbook,
    MarginOrderbookLevel,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _bool_param,
    _join_tickers,
    _params,
    _seg,
)

_MAX_BULK = 100
_MAX_SCHEDULE_TICKERS = 100
_MAX_TICKER_LEN = 200


def _parse_orderbook(data: dict[str, Any], ticker: str) -> MarginOrderbook:
    """Parse the GET /margin/markets/{ticker}/orderbook envelope.

    Shape is ``{"orderbook": {"bids": [[price, qty], ...], "asks": [...]}}``.
    Each level is a 2-tuple ``[price_dollars, contract_count_fp]`` →
    ``MarginOrderbookLevel(price=pair[0], quantity=pair[1])``. ``ticker`` is
    injected from the path arg (not on the wire).
    """
    ob = data.get("orderbook", data)
    bids_raw = ob.get("bids") or []
    asks_raw = ob.get("asks") or []
    bids = [
        MarginOrderbookLevel(price=pair[0], quantity=pair[1]) for pair in bids_raw if len(pair) >= 2
    ]
    asks = [
        MarginOrderbookLevel(price=pair[0], quantity=pair[1]) for pair in asks_raw if len(pair) >= 2
    ]
    return MarginOrderbook(ticker=ticker, bids=bids, asks=asks)


def _orderbook_from_item(item: dict[str, Any]) -> MarginOrderbook:
    """Parse one entry from GET /margin/markets/orderbooks into a MarginOrderbook.

    Shape is ``{"ticker": "...", "orderbook": {"bids": [...], "asks": [...]}}``.
    Reuses :func:`_parse_orderbook` for the nested book. Raises
    :class:`~kalshi.errors.KalshiError` if the response omits or empty-strings
    the per-item ticker — silently returning ``ticker=""`` would corrupt
    caller-side lookups.
    """
    ticker = item.get("ticker")
    if not ticker:
        raise KalshiError(
            "bulk orderbook item has empty or missing 'ticker' field "
            f"in server response; got {item!r}"
        )
    return _parse_orderbook(item, ticker)


def _bulk_orderbooks_params(*, tickers: builtins.list[str]) -> dict[str, Any]:
    """Validate + build params for GET /margin/markets/orderbooks (bulk).

    Spec requires 1..100 tickers. Wire format is ``?tickers=a,b``
    (style: form, explode: false).
    """
    if not tickers:
        raise ValueError("tickers must be a non-empty list")
    if len(tickers) > _MAX_BULK:
        raise ValueError(
            f"tickers accepts at most {_MAX_BULK} entries per spec (got {len(tickers)})"
        )
    return _params(tickers=_join_tickers(tickers))


def _schedules_params(*, tickers: builtins.list[str]) -> dict[str, Any]:
    """Validate + build params for GET /margin/markets/schedules.

    Spec requires 1..100 tickers, each 1..200 characters. Wire format is
    ``?tickers=a,b`` (style: form, explode: false).
    """
    if not tickers:
        raise ValueError("tickers must be a non-empty list")
    if len(tickers) > _MAX_SCHEDULE_TICKERS:
        raise ValueError(
            f"tickers accepts at most {_MAX_SCHEDULE_TICKERS} entries per spec "
            f"(got {len(tickers)})"
        )
    for i, ticker in enumerate(tickers):
        if not ticker or not ticker.strip():
            raise ValueError(f"tickers[{i}] is empty")
        if len(ticker) > _MAX_TICKER_LEN:
            raise ValueError(
                f"tickers[{i}] exceeds {_MAX_TICKER_LEN} characters (got {len(ticker)})"
            )
    return _params(tickers=_join_tickers(tickers, max_items=_MAX_SCHEDULE_TICKERS))


def _parse_schedules(data: dict[str, Any]) -> dict[str, MarginMarketScheduleDetails]:
    """Parse the ticker → schedule-details map from GET /margin/markets/schedules."""
    return {
        ticker: MarginMarketScheduleDetails.model_validate(details)
        for ticker, details in data.items()
    }


class PerpsMarketsResource(SyncResource):
    """Sync perps markets API (list / get / orderbook / bulk / candlesticks / schedules)."""

    def list(
        self,
        *,
        status: MarginMarketStatusLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarginMarket]:
        """List margin markets.

        Non-paginated: ``GetMarginMarketsResponse`` has no cursor, so there is
        no ``list_all()`` here (unlike :class:`kalshi.resources.markets.MarketsResource`).
        """
        params = _params(status=status)
        data = self._get("/margin/markets", params=params, extra_headers=extra_headers)
        return GetMarginMarketsResponse.model_validate(data).markets

    def get(self, ticker: str, *, extra_headers: dict[str, str] | None = None) -> MarginMarket:
        data = self._get(
            f"/margin/markets/{_seg(ticker, name='ticker')}", extra_headers=extra_headers
        )
        market = data.get("market", data)
        return MarginMarket.model_validate(market)

    def orderbook(
        self,
        ticker: str,
        *,
        depth: int | None = None,
        aggregation_tick_size: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> MarginOrderbook:
        params = _params(depth=depth, aggregation_tick_size=aggregation_tick_size)
        data = self._get(
            f"/margin/markets/{_seg(ticker, name='ticker')}/orderbook",
            params=params,
            extra_headers=extra_headers,
        )
        return _parse_orderbook(data, ticker)

    def bulk_orderbooks(
        self,
        *,
        tickers: builtins.list[str],
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarginOrderbook]:
        """Fetch orderbooks for up to 100 margin tickers in a single call.

        Public market data (no auth). Spec requires at least one ticker
        (max 100). ``tickers`` serializes as a comma-separated string
        (spec ``style: form, explode: false``). A ticker that is not a
        margin market returns 404.
        """
        params = _bulk_orderbooks_params(tickers=tickers)
        data = self._get(
            "/margin/markets/orderbooks", params=params, extra_headers=extra_headers
        )
        raw = GetMarginMarketOrderbooksResponse.model_validate(data).orderbooks
        return [_orderbook_from_item(item) for item in raw]

    def candlesticks(
        self,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        include_latest_before_start: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarginMarketCandlestick]:
        params = _params(
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
            include_latest_before_start=_bool_param(include_latest_before_start),
        )
        data = self._get(
            f"/margin/markets/{_seg(ticker, name='ticker')}/candlesticks",
            params=params,
            extra_headers=extra_headers,
        )
        return GetMarginMarketCandlesticksResponse.model_validate(data).candlesticks

    def schedules(
        self,
        *,
        tickers: builtins.list[str],
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, MarginMarketScheduleDetails]:
        """``GET /margin/markets/schedules`` — holiday closures for up to 100 tickers.

        Public market data (no auth). ``tickers`` is required (1–100, each
        1–200 characters) and serializes as a comma-separated query string.
        The body is a map keyed by market ticker. Regular daily and weekend
        closures are not included.
        """
        params = _schedules_params(tickers=tickers)
        data = self._get(
            "/margin/markets/schedules", params=params, extra_headers=extra_headers
        )
        return _parse_schedules(data)


class AsyncPerpsMarketsResource(AsyncResource):
    """Async perps markets API (list / get / orderbook / bulk / candlesticks / schedules)."""

    async def list(
        self,
        *,
        status: MarginMarketStatusLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarginMarket]:
        """List margin markets.

        Non-paginated: ``GetMarginMarketsResponse`` has no cursor, so there is
        no ``list_all()`` here (unlike :class:`kalshi.resources.markets.MarketsResource`).
        """
        params = _params(status=status)
        data = await self._get("/margin/markets", params=params, extra_headers=extra_headers)
        return GetMarginMarketsResponse.model_validate(data).markets

    async def get(
        self, ticker: str, *, extra_headers: dict[str, str] | None = None
    ) -> MarginMarket:
        data = await self._get(
            f"/margin/markets/{_seg(ticker, name='ticker')}", extra_headers=extra_headers
        )
        market = data.get("market", data)
        return MarginMarket.model_validate(market)

    async def orderbook(
        self,
        ticker: str,
        *,
        depth: int | None = None,
        aggregation_tick_size: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> MarginOrderbook:
        params = _params(depth=depth, aggregation_tick_size=aggregation_tick_size)
        data = await self._get(
            f"/margin/markets/{_seg(ticker, name='ticker')}/orderbook",
            params=params,
            extra_headers=extra_headers,
        )
        return _parse_orderbook(data, ticker)

    async def bulk_orderbooks(
        self,
        *,
        tickers: builtins.list[str],
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarginOrderbook]:
        """Fetch orderbooks for up to 100 margin tickers in a single call.

        Public market data (no auth). Spec requires at least one ticker
        (max 100). ``tickers`` serializes as a comma-separated string
        (spec ``style: form, explode: false``). A ticker that is not a
        margin market returns 404.
        """
        params = _bulk_orderbooks_params(tickers=tickers)
        data = await self._get(
            "/margin/markets/orderbooks", params=params, extra_headers=extra_headers
        )
        raw = GetMarginMarketOrderbooksResponse.model_validate(data).orderbooks
        return [_orderbook_from_item(item) for item in raw]

    async def candlesticks(
        self,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        include_latest_before_start: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarginMarketCandlestick]:
        params = _params(
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
            include_latest_before_start=_bool_param(include_latest_before_start),
        )
        data = await self._get(
            f"/margin/markets/{_seg(ticker, name='ticker')}/candlesticks",
            params=params,
            extra_headers=extra_headers,
        )
        return GetMarginMarketCandlesticksResponse.model_validate(data).candlesticks

    async def schedules(
        self,
        *,
        tickers: builtins.list[str],
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, MarginMarketScheduleDetails]:
        """Async :meth:`PerpsMarketsResource.schedules`."""
        params = _schedules_params(tickers=tickers)
        data = await self._get(
            "/margin/markets/schedules", params=params, extra_headers=extra_headers
        )
        return _parse_schedules(data)
