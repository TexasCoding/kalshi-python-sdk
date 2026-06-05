"""Perps markets resource — list/get, orderbook, candlesticks (#390).

Four read-only ``GET`` endpoints, all public market data (the spec marks no
``security`` block on any of them) — so none call ``_require_auth()``, unlike the
public-markets ``orderbook`` which does. All retry on 429/502/503/504 (GET).

Divergence from :mod:`kalshi.resources.markets`: ``list()`` returns a plain
``builtins.list[MarginMarket]`` (NOT a ``Page``) and has **no** ``list_all()`` —
``GetMarginMarketsResponse`` carries no cursor, so there is nothing to paginate.
The orderbook is ``{bids, asks}`` (margin) rather than ``{yes, no}``.
"""

from __future__ import annotations

import builtins
from typing import Any

from kalshi.perps.models.markets import (
    MarginMarket,
    MarginMarketCandlestick,
    MarginMarketStatusLiteral,
    MarginOrderbook,
    MarginOrderbookLevel,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _bool_param,
    _params,
    _seg,
)


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


class PerpsMarketsResource(SyncResource):
    """Sync perps markets API (``list`` / ``get`` / ``orderbook`` / ``candlesticks``)."""

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
        raw = data.get("markets") or []
        return [MarginMarket.model_validate(m) for m in raw]

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
        raw = data.get("candlesticks") or []
        return [MarginMarketCandlestick.model_validate(c) for c in raw]


class AsyncPerpsMarketsResource(AsyncResource):
    """Async perps markets API (``list`` / ``get`` / ``orderbook`` / ``candlesticks``)."""

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
        raw = data.get("markets") or []
        return [MarginMarket.model_validate(m) for m in raw]

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
        raw = data.get("candlesticks") or []
        return [MarginMarketCandlestick.model_validate(c) for c in raw]
