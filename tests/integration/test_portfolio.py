"""Integration tests for PortfolioResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.common import Page
from kalshi.models.portfolio import Balance, PositionsResponse, Settlement
from tests.integration.coverage_harness import register

register("PortfolioResource", ["balance", "positions", "settlements", "settlements_all"])


@pytest.mark.integration
class TestPortfolioSync:
    def test_balance(self, sync_client: KalshiClient) -> None:
        result = sync_client.portfolio.balance()
        assert isinstance(result, Balance)
        assert isinstance(result.balance, int)

    def test_positions(self, sync_client: KalshiClient) -> None:
        result = sync_client.portfolio.positions()
        assert isinstance(result, PositionsResponse)
        assert isinstance(result.market_positions, list)
        assert isinstance(result.event_positions, list)

    def test_settlements(self, sync_client: KalshiClient) -> None:
        page = sync_client.portfolio.settlements(limit=5)
        assert isinstance(page, Page)
        for item in page.items:
            assert isinstance(item, Settlement)

    def test_settlements_all(self, sync_client: KalshiClient) -> None:
        for count, settlement in enumerate(sync_client.portfolio.settlements_all(limit=2)):
            assert isinstance(settlement, Settlement)

            if count >= 2:
                break


@pytest.mark.integration
class TestPortfolioAsync:
    async def test_balance(self, async_client: AsyncKalshiClient) -> None:
        result = await async_client.portfolio.balance()
        assert isinstance(result, Balance)

    async def test_positions(self, async_client: AsyncKalshiClient) -> None:
        result = await async_client.portfolio.positions()
        assert isinstance(result, PositionsResponse)

    async def test_settlements(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.portfolio.settlements(limit=5)
        assert isinstance(page, Page)

    async def test_settlements_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for settlement in async_client.portfolio.settlements_all(limit=2):
            assert isinstance(settlement, Settlement)
            count += 1
            if count >= 3:
                break
