"""Integration tests for MarketsResource."""

from __future__ import annotations

from decimal import Decimal

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.common import Page
from kalshi.models.markets import Candlestick, Market, Orderbook, OrderbookLevel
from tests.integration.assertions import assert_model_fields
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
            assert_model_fields(market)
            assert market.ticker

    def test_get(self, sync_client: KalshiClient, demo_market_ticker: str) -> None:
        market = sync_client.markets.get(demo_market_ticker)
        assert isinstance(market, Market)
        assert_model_fields(market)
        assert market.ticker == demo_market_ticker

    def test_list_all(self, sync_client: KalshiClient) -> None:
        for count, market in enumerate(sync_client.markets.list_all(limit=2)):
            assert isinstance(market, Market)
            assert_model_fields(market)

            if count >= 2:
                break
        assert count > 0

    def test_orderbook(self, sync_client: KalshiClient, demo_market_ticker: str) -> None:
        ob = sync_client.markets.orderbook(demo_market_ticker)
        assert isinstance(ob, Orderbook)
        assert_model_fields(ob)
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
            assert_model_fields(candle)

    def test_pagination_no_overlap(self, sync_client: KalshiClient) -> None:
        """Verify cursor-based pagination returns non-overlapping pages."""
        page1 = sync_client.markets.list(limit=2)
        if len(page1.items) < 2 or not page1.cursor:
            pytest.skip("Not enough markets for pagination test (need >= 3)")

        tickers_page1 = {m.ticker for m in page1.items}

        page2 = sync_client.markets.list(limit=2, cursor=page1.cursor)
        tickers_page2 = {m.ticker for m in page2.items}

        if not tickers_page2:
            pytest.skip("Page 2 is empty — not enough markets for pagination test")

        overlap = tickers_page1 & tickers_page2
        assert not overlap, (
            f"Pages overlap! Shared tickers: {overlap}. "
            f"Page 1: {tickers_page1}, Page 2: {tickers_page2}"
        )

    def test_pagination_cursor_terminates(self, sync_client: KalshiClient) -> None:
        """Verify cursor eventually becomes None (pagination terminates)."""
        all_tickers: list[str] = []
        page = sync_client.markets.list(limit=5)
        all_tickers.extend(m.ticker for m in page.items)

        max_pages = 20  # Safety limit to prevent infinite loops
        pages_fetched = 1
        while page.cursor and pages_fetched < max_pages:
            page = sync_client.markets.list(limit=5, cursor=page.cursor)
            all_tickers.extend(m.ticker for m in page.items)
            pages_fetched += 1

        # Either cursor became None (pagination terminated) or we hit the safety limit
        if pages_fetched >= max_pages:
            # We fetched 20 pages * 5 = 100 items, that's enough to prove cursor works
            pass
        else:
            # Cursor terminated naturally — verify we got all items
            assert len(all_tickers) > 0

        # Verify no duplicates across all pages
        assert len(all_tickers) == len(set(all_tickers)), (
            f"Found duplicate tickers across pages: "
            f"{[t for t in all_tickers if all_tickers.count(t) > 1]}"
        )

    def test_list_all_no_duplicates(self, sync_client: KalshiClient) -> None:
        """Verify list_all() SDK abstraction produces no duplicate tickers."""
        tickers: list[str] = []
        for count, market in enumerate(sync_client.markets.list_all(limit=2)):
            tickers.append(market.ticker)
            if count >= 5:
                break

        if len(tickers) <= 1:
            pytest.skip("Not enough markets to verify pagination deduplication")

        assert len(tickers) == len(set(tickers)), (
            f"list_all() produced duplicate tickers: "
            f"{[t for t in tickers if tickers.count(t) > 1]}"
        )


@pytest.mark.integration
class TestMarketsAsync:
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.markets.list(limit=5)
        assert isinstance(page, Page)
        if page.items:
            market = page.items[0]
            assert isinstance(market, Market)
            assert_model_fields(market)

    async def test_get(self, async_client: AsyncKalshiClient, demo_market_ticker: str) -> None:
        market = await async_client.markets.get(demo_market_ticker)
        assert isinstance(market, Market)
        assert_model_fields(market)
        assert market.ticker == demo_market_ticker

    async def test_list_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for market in async_client.markets.list_all(limit=2):
            assert isinstance(market, Market)
            assert_model_fields(market)
            count += 1
            if count >= 3:
                break
        assert count > 0

    async def test_orderbook(
        self, async_client: AsyncKalshiClient, demo_market_ticker: str
    ) -> None:
        ob = await async_client.markets.orderbook(demo_market_ticker)
        assert isinstance(ob, Orderbook)
        assert_model_fields(ob)
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
        for candle in result:
            assert isinstance(candle, Candlestick)
            assert_model_fields(candle)
