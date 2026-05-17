"""Tests for kalshi.resources.account — Account resource."""

from __future__ import annotations

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import AuthRequiredError, KalshiAuthError
from kalshi.resources.account import AccountResource, AsyncAccountResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def account(test_auth: KalshiAuth, config: KalshiConfig) -> AccountResource:
    return AccountResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_account(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> AsyncAccountResource:
    return AsyncAccountResource(AsyncTransport(test_auth, config))


@pytest.fixture
def unauth_account(config: KalshiConfig) -> AccountResource:
    return AccountResource(SyncTransport(None, config))


@pytest.fixture
def unauth_async_account(config: KalshiConfig) -> AsyncAccountResource:
    return AsyncAccountResource(AsyncTransport(None, config))


class TestAccountLimits:
    @respx.mock
    def test_returns_limits(self, account: AccountResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/account/limits").mock(
            return_value=httpx.Response(
                200,
                json={
                    "usage_tier": "standard",
                    "read": {"bucket_capacity": 200, "refill_rate": 100},
                    "write": {"bucket_capacity": 20, "refill_rate": 10},
                },
            )
        )
        limits = account.limits()
        assert limits.usage_tier == "standard"
        assert limits.read.bucket_capacity == 200
        assert limits.read.refill_rate == 100
        assert limits.write.bucket_capacity == 20
        assert limits.write.refill_rate == 10

    def test_requires_auth(self, unauth_account: AccountResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_account.limits()

    @respx.mock
    def test_server_rejects_auth(self, account: AccountResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/account/limits").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        with pytest.raises(KalshiAuthError):
            account.limits()


class TestAsyncAccountLimits:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_limits(
        self, async_account: AsyncAccountResource,
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/account/limits").mock(
            return_value=httpx.Response(
                200,
                json={
                    "usage_tier": "elevated",
                    "read": {"bucket_capacity": 1000, "refill_rate": 500},
                    "write": {"bucket_capacity": 100, "refill_rate": 50},
                },
            )
        )
        limits = await async_account.limits()
        assert limits.usage_tier == "elevated"
        assert limits.read.bucket_capacity == 1000
        assert limits.read.refill_rate == 500
        assert limits.write.bucket_capacity == 100
        assert limits.write.refill_rate == 50

    @pytest.mark.asyncio
    async def test_requires_auth(
        self, unauth_async_account: AsyncAccountResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_account.limits()

    @respx.mock
    @pytest.mark.asyncio
    async def test_server_rejects_auth(
        self, async_account: AsyncAccountResource,
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/account/limits").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        with pytest.raises(KalshiAuthError):
            await async_account.limits()
