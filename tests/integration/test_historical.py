"""Integration tests for HistoricalResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.common import Page
from kalshi.models.historical import HistoricalCutoff, Trade
from kalshi.models.markets import Candlestick, Market
from kalshi.models.orders import Fill, Order
from tests.integration.coverage_harness import register

register(
    "HistoricalResource",
    [
        "candlesticks",
        "cutoff",
        "fills",
        "fills_all",
        "market",
        "markets",
        "markets_all",
        "orders",
        "orders_all",
        "trades",
        "trades_all",
    ],
)


@pytest.mark.integration
class TestHistoricalSync:
    def test_cutoff(self, sync_client: KalshiClient) -> None:
        result = sync_client.historical.cutoff()
        assert isinstance(result, HistoricalCutoff)

    def test_markets(self, sync_client: KalshiClient) -> None:
        page = sync_client.historical.markets(limit=5)
        assert isinstance(page, Page)
        for item in page.items:
            assert isinstance(item, Market)

    def test_markets_all(self, sync_client: KalshiClient) -> None:
        for count, market in enumerate(sync_client.historical.markets_all(limit=2)):
            assert isinstance(market, Market)

            if count >= 2:
                break

    def test_market(self, sync_client: KalshiClient) -> None:
        page = sync_client.historical.markets(limit=1)
        if not page.items:
            pytest.skip("No historical markets available")
        ticker = page.items[0].ticker
        result = sync_client.historical.market(ticker)
        assert isinstance(result, Market)
        assert result.ticker == ticker

    def test_candlesticks(self, sync_client: KalshiClient) -> None:
        import time

        page = sync_client.historical.markets(limit=1)
        if not page.items:
            pytest.skip("No historical markets for candlestick test")
        ticker = page.items[0].ticker
        # API requires start_ts, end_ts, AND period_interval
        now = int(time.time())
        start_ts = now - 86400 * 7  # 7 days ago
        result = sync_client.historical.candlesticks(
            ticker, start_ts=start_ts, end_ts=now, period_interval=60
        )
        assert isinstance(result, list)
        for candle in result:
            assert isinstance(candle, Candlestick)

    def test_fills(self, sync_client: KalshiClient) -> None:
        page = sync_client.historical.fills(limit=5)
        assert isinstance(page, Page)
        for item in page.items:
            assert isinstance(item, Fill)

    def test_fills_all(self, sync_client: KalshiClient) -> None:
        for count, fill in enumerate(sync_client.historical.fills_all(limit=2)):
            assert isinstance(fill, Fill)

            if count >= 2:
                break

    def test_orders(self, sync_client: KalshiClient) -> None:
        page = sync_client.historical.orders(limit=5)
        assert isinstance(page, Page)
        for item in page.items:
            assert isinstance(item, Order)

    def test_orders_all(self, sync_client: KalshiClient) -> None:
        for count, order in enumerate(sync_client.historical.orders_all(limit=2)):
            assert isinstance(order, Order)

            if count >= 2:
                break

    def test_trades(self, sync_client: KalshiClient) -> None:
        page = sync_client.historical.trades(limit=5)
        assert isinstance(page, Page)
        for item in page.items:
            assert isinstance(item, Trade)

    def test_trades_all(self, sync_client: KalshiClient) -> None:
        for count, trade in enumerate(sync_client.historical.trades_all(limit=2)):
            assert isinstance(trade, Trade)

            if count >= 2:
                break


@pytest.mark.integration
class TestHistoricalAsync:
    async def test_cutoff(self, async_client: AsyncKalshiClient) -> None:
        result = await async_client.historical.cutoff()
        assert isinstance(result, HistoricalCutoff)

    async def test_markets(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.historical.markets(limit=5)
        assert isinstance(page, Page)

    async def test_markets_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for market in async_client.historical.markets_all(limit=2):
            assert isinstance(market, Market)
            count += 1
            if count >= 3:
                break

    async def test_market(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.historical.markets(limit=1)
        if not page.items:
            pytest.skip("No historical markets available")
        ticker = page.items[0].ticker
        result = await async_client.historical.market(ticker)
        assert isinstance(result, Market)

    async def test_candlesticks(self, async_client: AsyncKalshiClient) -> None:
        import time

        page = await async_client.historical.markets(limit=1)
        if not page.items:
            pytest.skip("No historical markets for candlestick test")
        ticker = page.items[0].ticker
        now = int(time.time())
        start_ts = now - 86400 * 7
        result = await async_client.historical.candlesticks(
            ticker, start_ts=start_ts, end_ts=now, period_interval=60
        )
        assert isinstance(result, list)

    async def test_fills(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.historical.fills(limit=5)
        assert isinstance(page, Page)

    async def test_fills_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for fill in async_client.historical.fills_all(limit=2):
            assert isinstance(fill, Fill)
            count += 1
            if count >= 3:
                break

    async def test_orders(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.historical.orders(limit=5)
        assert isinstance(page, Page)

    async def test_orders_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for order in async_client.historical.orders_all(limit=2):
            assert isinstance(order, Order)
            count += 1
            if count >= 3:
                break

    async def test_trades(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.historical.trades(limit=5)
        assert isinstance(page, Page)

    async def test_trades_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for trade in async_client.historical.trades_all(limit=2):
            assert isinstance(trade, Trade)
            count += 1
            if count >= 3:
                break
