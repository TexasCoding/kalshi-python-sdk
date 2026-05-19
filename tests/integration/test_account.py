"""Integration tests for AccountResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.account import AccountApiLimits, AccountEndpointCosts
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register("AccountResource", ["endpoint_costs", "limits"])


@pytest.mark.integration
class TestAccountSync:
    def test_limits(self, sync_client: KalshiClient) -> None:
        result = sync_client.account.limits()
        assert isinstance(result, AccountApiLimits)
        assert_model_fields(result)
        assert result.read.bucket_capacity > 0
        assert result.read.refill_rate > 0
        assert result.write.bucket_capacity > 0
        assert result.write.refill_rate > 0
        assert result.usage_tier

    def test_endpoint_costs(self, sync_client: KalshiClient) -> None:
        result = sync_client.account.endpoint_costs()
        assert isinstance(result, AccountEndpointCosts)
        assert result.default_cost > 0
        for entry in result.endpoint_costs:
            assert entry.method
            assert entry.path
            assert entry.cost >= 0


@pytest.mark.integration
class TestAccountAsync:
    async def test_limits(self, async_client: AsyncKalshiClient) -> None:
        result = await async_client.account.limits()
        assert isinstance(result, AccountApiLimits)
        assert_model_fields(result)

    async def test_endpoint_costs(self, async_client: AsyncKalshiClient) -> None:
        result = await async_client.account.endpoint_costs()
        assert isinstance(result, AccountEndpointCosts)
        assert result.default_cost > 0
