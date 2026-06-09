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
                    "grants": [
                        {
                            "exchange_instance": "event_contract",
                            "level": "premier",
                            "source": "volume",
                            "expires_ts": 1893456000,
                        }
                    ],
                },
            )
        )
        limits = account.limits()
        assert limits.usage_tier == "standard"
        assert limits.read.bucket_capacity == 200
        assert limits.read.refill_rate == 100
        assert limits.write.bucket_capacity == 20
        assert limits.write.refill_rate == 10
        assert len(limits.grants) == 1
        assert limits.grants[0].exchange_instance == "event_contract"
        assert limits.grants[0].level == "premier"
        assert limits.grants[0].source == "volume"
        assert limits.grants[0].expires_ts == 1893456000

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
                    # Kalshi's empty-as-null convention: NullableList coerces to [].
                    "grants": None,
                },
            )
        )
        limits = await async_account.limits()
        assert limits.usage_tier == "elevated"
        assert limits.read.bucket_capacity == 1000
        assert limits.read.refill_rate == 500
        assert limits.write.bucket_capacity == 100
        assert limits.write.refill_rate == 50
        assert limits.grants == []

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


class TestAccountEndpointCosts:
    @respx.mock
    def test_returns_costs(self, account: AccountResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/account/endpoint_costs",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "default_cost": 10,
                    "endpoint_costs": [
                        {"method": "POST", "path": "/portfolio/orders", "cost": 50},
                        {"method": "DELETE", "path": "/portfolio/orders/{order_id}", "cost": 2},
                    ],
                },
            )
        )
        costs = account.endpoint_costs()
        assert costs.default_cost == 10
        assert len(costs.endpoint_costs) == 2
        assert costs.endpoint_costs[0].method == "POST"
        assert costs.endpoint_costs[0].path == "/portfolio/orders"
        assert costs.endpoint_costs[0].cost == 50

    @respx.mock
    def test_returns_empty_costs(self, account: AccountResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/account/endpoint_costs",
        ).mock(
            return_value=httpx.Response(
                200, json={"default_cost": 10, "endpoint_costs": []},
            )
        )
        costs = account.endpoint_costs()
        assert costs.endpoint_costs == []

    def test_requires_auth(self, unauth_account: AccountResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_account.endpoint_costs()


class TestAsyncAccountEndpointCosts:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_costs(
        self, async_account: AsyncAccountResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/account/endpoint_costs",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "default_cost": 10,
                    "endpoint_costs": [
                        {"method": "POST", "path": "/portfolio/orders/batched", "cost": 100},
                    ],
                },
            )
        )
        costs = await async_account.endpoint_costs()
        assert costs.default_cost == 10
        assert costs.endpoint_costs[0].cost == 100

    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_empty_costs(
        self, async_account: AsyncAccountResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/account/endpoint_costs",
        ).mock(
            return_value=httpx.Response(
                200, json={"default_cost": 10, "endpoint_costs": []},
            )
        )
        costs = await async_account.endpoint_costs()
        assert costs.endpoint_costs == []

    @pytest.mark.asyncio
    async def test_requires_auth(
        self, unauth_async_account: AsyncAccountResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_account.endpoint_costs()


class TestAccountUpgrade:
    @respx.mock
    def test_upgrade_succeeds(self, account: AccountResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/account/api_usage_level/upgrade",
        ).mock(return_value=httpx.Response(201, json={}))
        assert account.upgrade() is None
        assert route.called
        # Bodyless POST: SDK sends json={} so httpx pins the Content-Type header.
        assert route.calls[0].request.content == b"{}"

    @respx.mock
    def test_upgrade_403_no_api_order(self, account: AccountResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/account/api_usage_level/upgrade",
        ).mock(return_value=httpx.Response(403, json={"message": "no API order"}))
        with pytest.raises(KalshiAuthError):
            account.upgrade()

    def test_requires_auth(self, unauth_account: AccountResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_account.upgrade()


class TestAsyncAccountUpgrade:
    @respx.mock
    @pytest.mark.asyncio
    async def test_upgrade_succeeds(
        self, async_account: AsyncAccountResource,
    ) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/account/api_usage_level/upgrade",
        ).mock(return_value=httpx.Response(201, json={}))
        assert await async_account.upgrade() is None
        assert route.called

    @pytest.mark.asyncio
    async def test_requires_auth(
        self, unauth_async_account: AsyncAccountResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_account.upgrade()
