"""Integration tests for IncentiveProgramsResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.incentive_programs import IncentiveProgram
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register("IncentiveProgramsResource", ["list", "list_all"])


@pytest.mark.integration
class TestIncentiveProgramsSync:
    def test_list(self, sync_client: KalshiClient) -> None:
        page = sync_client.incentive_programs.list(limit=10)
        assert isinstance(page.items, list)
        for item in page.items:
            assert isinstance(item, IncentiveProgram)
            assert_model_fields(item)

    def test_list_all(self, sync_client: KalshiClient) -> None:
        for count, item in enumerate(
            sync_client.incentive_programs.list_all(limit=5),
        ):
            assert isinstance(item, IncentiveProgram)
            if count >= 9:
                break

    def test_filter_by_status(self, sync_client: KalshiClient) -> None:
        page = sync_client.incentive_programs.list(status="active", limit=5)
        assert isinstance(page.items, list)


@pytest.mark.integration
class TestIncentiveProgramsAsync:
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.incentive_programs.list(limit=10)
        assert isinstance(page.items, list)

    async def test_list_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for item in async_client.incentive_programs.list_all(limit=5):
            assert isinstance(item, IncentiveProgram)
            count += 1
            if count >= 10:
                break
