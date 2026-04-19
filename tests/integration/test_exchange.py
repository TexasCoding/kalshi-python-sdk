"""Integration tests for ExchangeResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.exchange import (
    Announcement,
    ExchangeStatus,
    Schedule,
    UserDataTimestamp,
)
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register(
    "ExchangeResource",
    ["announcements", "schedule", "status", "user_data_timestamp"],
)


@pytest.mark.integration
class TestExchangeSync:
    def test_status(self, sync_client: KalshiClient) -> None:
        result = sync_client.exchange.status()
        assert isinstance(result, ExchangeStatus)
        assert_model_fields(result)
        assert isinstance(result.exchange_active, bool)
        assert isinstance(result.trading_active, bool)

    def test_schedule(self, sync_client: KalshiClient) -> None:
        result = sync_client.exchange.schedule()
        assert isinstance(result, Schedule)
        assert_model_fields(result)

    def test_announcements(self, sync_client: KalshiClient) -> None:
        result = sync_client.exchange.announcements()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, Announcement)
            assert_model_fields(item)

    def test_user_data_timestamp(self, sync_client: KalshiClient) -> None:
        result = sync_client.exchange.user_data_timestamp()
        assert isinstance(result, UserDataTimestamp)
        assert_model_fields(result)


@pytest.mark.integration
class TestExchangeAsync:
    async def test_status(self, async_client: AsyncKalshiClient) -> None:
        result = await async_client.exchange.status()
        assert isinstance(result, ExchangeStatus)
        assert_model_fields(result)
        assert isinstance(result.exchange_active, bool)

    async def test_schedule(self, async_client: AsyncKalshiClient) -> None:
        result = await async_client.exchange.schedule()
        assert isinstance(result, Schedule)
        assert_model_fields(result)

    async def test_announcements(self, async_client: AsyncKalshiClient) -> None:
        result = await async_client.exchange.announcements()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, Announcement)
            assert_model_fields(item)

    async def test_user_data_timestamp(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        result = await async_client.exchange.user_data_timestamp()
        assert isinstance(result, UserDataTimestamp)
        assert_model_fields(result)
