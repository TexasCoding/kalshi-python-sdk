"""Integration tests for MarketsResource."""

from __future__ import annotations

from decimal import Decimal

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.common import Page
from kalshi.models.markets import Candlestick, Market, Orderbook, OrderbookLevel
from tests.integration.coverage_harness import register

register("MarketsResource", ["candlesticks", "get", "list", "list_all", "orderbook"])


@pytest.mark.integration
class TestMarketsSync:
    def test_list(self, sync_client: KalshiClient) -> None:
        page = sync_client.markets.list(limit=5)
        assert isinstance(page, Page)
        assert isinstance(page.items, list)
        if page.items:
            market = page.items[0]
            assert isinstance(market, Market)
            assert market.ticker

    def test_get(self, sync_client: KalshiClient, demo_market_ticker: str) -> None:
        market = sync_client.markets.get(demo_market_ticker)
        assert isinstance(market, Market)
        assert market.ticker == demo_market_ticker

    def test_list_all(self, sync_client: KalshiClient) -> None:
        for count, market in enumerate(sync_client.markets.list_all(limit=2)):
            assert isinstance(market, Market)

            if count >= 2:
                break
        assert count > 0

    def test_orderbook(self, sync_client: KalshiClient, demo_market_ticker: str) -> None:
        ob = sync_client.markets.orderbook(demo_market_ticker)
        assert isinstance(ob, Orderbook)
        assert ob.ticker == demo_market_ticker
        assert isinstance(ob.yes, list)
        assert isinstance(ob.no, list)
        for level in ob.yes:
            assert isinstance(level, OrderbookLevel)
            assert isinstance(level.price, Decimal)
        for level in ob.no:
            assert isinstance(level, OrderbookLevel)
            assert isinstance(level.price, Decimal)

    def test_candlesticks(
        self, sync_client: KalshiClient, demo_market: Market, demo_event_ticker: str
    ) -> None:
        import time

        event = sync_client.events.get(demo_event_ticker)
        if not event.series_ticker:
            pytest.skip("Demo event has no series_ticker for candlestick endpoint")
        now = int(time.time())
        result = sync_client.markets.candlesticks(
            event.series_ticker,
            demo_market.ticker,
            start_ts=now - 86400 * 7,
            end_ts=now,
            period_interval=60,
        )
        assert isinstance(result, list)
        for candle in result:
            assert isinstance(candle, Candlestick)


@pytest.mark.integration
class TestMarketsAsync:
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.markets.list(limit=5)
        assert isinstance(page, Page)

    async def test_get(self, async_client: AsyncKalshiClient, demo_market_ticker: str) -> None:
        market = await async_client.markets.get(demo_market_ticker)
        assert isinstance(market, Market)
        assert market.ticker == demo_market_ticker

    async def test_list_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for market in async_client.markets.list_all(limit=2):
            assert isinstance(market, Market)
            count += 1
            if count >= 3:
                break
        assert count > 0

    async def test_orderbook(
        self, async_client: AsyncKalshiClient, demo_market_ticker: str
    ) -> None:
        ob = await async_client.markets.orderbook(demo_market_ticker)
        assert isinstance(ob, Orderbook)
        assert ob.ticker == demo_market_ticker

    async def test_candlesticks(
        self, async_client: AsyncKalshiClient, demo_market: Market, demo_event_ticker: str
    ) -> None:
        import time

        event = await async_client.events.get(demo_event_ticker)
        if not event.series_ticker:
            pytest.skip("Demo event has no series_ticker")
        now = int(time.time())
        result = await async_client.markets.candlesticks(
            event.series_ticker,
            demo_market.ticker,
            start_ts=now - 86400 * 7,
            end_ts=now,
            period_interval=60,
        )
        assert isinstance(result, list)
