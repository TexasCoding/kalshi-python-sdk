"""Integration tests for AccountResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.account import AccountApiLimits
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register("AccountResource", ["limits"])


@pytest.mark.integration
class TestAccountSync:
    def test_limits(self, sync_client: KalshiClient) -> None:
        result = sync_client.account.limits()
        assert isinstance(result, AccountApiLimits)
        assert_model_fields(result)
        assert result.read_limit >= 0
        assert result.write_limit >= 0
        assert result.usage_tier


@pytest.mark.integration
class TestAccountAsync:
    async def test_limits(self, async_client: AsyncKalshiClient) -> None:
        result = await async_client.account.limits()
        assert isinstance(result, AccountApiLimits)
        assert_model_fields(result)
