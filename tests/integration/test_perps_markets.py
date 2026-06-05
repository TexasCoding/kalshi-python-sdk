"""Integration tests for the perps (margin) markets resource — live demo.

Covers ``list`` / ``get`` / ``orderbook`` / ``candlesticks``. All four are public
read-only GETs; no margin-enabled account is required, only that the demo server
exposes at least one margin market (guarded by the ``perps_market_ticker``
fixture, which skips when the demo has no margin markets).

Margin market prices are NOT binary [0, 1] like the prediction API — they are
plain ``DollarDecimal`` and may exceed $1 — so these tests assert types/values
directly rather than using ``assert_model_fields`` (whose price-range check
targets binary markets).
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from kalshi.perps.async_client import AsyncPerpsClient
from kalshi.perps.client import PerpsClient
from kalshi.perps.models.markets import (
    MarginMarket,
    MarginMarketCandlestick,
    MarginOrderbook,
    MarginOrderbookLevel,
)
from tests.integration.coverage_harness import register_perps

register_perps(
    "PerpsMarketsResource",
    ["candlesticks", "get", "list", "orderbook"],
)


@pytest.mark.integration
class TestPerpsMarketsSync:
    def test_list(self, perps_sync_client: PerpsClient) -> None:
        markets = perps_sync_client.markets.list()
        assert isinstance(markets, list)
        if not markets:
            pytest.skip("No margin markets on demo server")
        market = markets[0]
        assert isinstance(market, MarginMarket)
        assert market.ticker
        assert isinstance(market.contract_size, Decimal)

    def test_get(self, perps_sync_client: PerpsClient, perps_market_ticker: str) -> None:
        market = perps_sync_client.markets.get(perps_market_ticker)
        assert isinstance(market, MarginMarket)
        assert market.ticker == perps_market_ticker
        assert isinstance(market.tick_size, Decimal)

    def test_orderbook(
        self, perps_sync_client: PerpsClient, perps_market_ticker: str
    ) -> None:
        ob = perps_sync_client.markets.orderbook(perps_market_ticker)
        assert isinstance(ob, MarginOrderbook)
        assert ob.ticker == perps_market_ticker
        assert isinstance(ob.bids, list)
        assert isinstance(ob.asks, list)
        for level in (*ob.bids, *ob.asks):
            assert isinstance(level, MarginOrderbookLevel)
            assert isinstance(level.price, Decimal)
            assert isinstance(level.quantity, Decimal)

    def test_candlesticks(
        self, perps_sync_client: PerpsClient, perps_market_ticker: str
    ) -> None:
        now = int(time.time())
        result = perps_sync_client.markets.candlesticks(
            perps_market_ticker,
            start_ts=now - 86400 * 7,
            end_ts=now,
            period_interval=60,
        )
        assert isinstance(result, list)
        for candle in result:
            assert isinstance(candle, MarginMarketCandlestick)
            assert isinstance(candle.end_period_ts, int)


@pytest.mark.integration
class TestPerpsMarketsAsync:
    async def test_list(self, perps_async_client: AsyncPerpsClient) -> None:
        markets = await perps_async_client.markets.list()
        assert isinstance(markets, list)
        for market in markets:
            assert isinstance(market, MarginMarket)
            assert market.ticker

    async def test_get(self, perps_async_client: AsyncPerpsClient) -> None:
        markets = await perps_async_client.markets.list()
        if not markets:
            pytest.skip("No margin markets on demo server")
        ticker = markets[0].ticker
        market = await perps_async_client.markets.get(ticker)
        assert isinstance(market, MarginMarket)
        assert market.ticker == ticker

    async def test_orderbook(self, perps_async_client: AsyncPerpsClient) -> None:
        markets = await perps_async_client.markets.list()
        if not markets:
            pytest.skip("No margin markets on demo server")
        ob = await perps_async_client.markets.orderbook(markets[0].ticker)
        assert isinstance(ob, MarginOrderbook)
        assert ob.ticker == markets[0].ticker
