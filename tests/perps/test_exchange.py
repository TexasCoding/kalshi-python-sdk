"""Tests for the perps exchange resource (#389)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi.errors import AuthRequiredError, KalshiServerError
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.models.common import ExchangeInstance

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


# ── status ──────────────────────────────────────────────────────────────────


class TestStatus:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/exchange/status").mock(
            return_value=httpx.Response(
                200, json={"exchange_active": True, "trading_active": False}
            )
        )
        status = perps_client.exchange.status()
        assert status.exchange_active is True
        assert status.trading_active is False

    @respx.mock
    def test_extra_field_tolerated(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/exchange/status").mock(
            return_value=httpx.Response(
                200,
                json={"exchange_active": True, "trading_active": True, "new_server_field": 1},
            )
        )
        status = perps_client.exchange.status()
        assert status.exchange_active is True

    @respx.mock
    async def test_async(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/exchange/status").mock(
            return_value=httpx.Response(200, json={"exchange_active": True, "trading_active": True})
        )
        status = await async_perps_client.exchange.status()
        assert status.trading_active is True
        await async_perps_client.close()


# ── enabled ─────────────────────────────────────────────────────────────────


class TestEnabled:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/enabled").mock(
            return_value=httpx.Response(200, json={"enabled": True})
        )
        assert perps_client.exchange.enabled().enabled is True

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/enabled").mock(
            return_value=httpx.Response(200, json={"enabled": True})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.exchange.enabled()
        assert not route.called  # no HTTP issued
        client.close()

    @respx.mock
    def test_server_401_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/enabled").mock(
            return_value=httpx.Response(401, json={"error": {"code": "unauthorized"}})
        )
        with pytest.raises(Exception):  # noqa: B017 — mapped SDK auth error
            perps_client.exchange.enabled()

    @respx.mock
    async def test_async_unauth_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/enabled").mock(
            return_value=httpx.Response(200, json={"enabled": True})
        )
        client = AsyncPerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            await client.exchange.enabled()
        assert not route.called
        await client.close()


# ── risk_parameters ─────────────────────────────────────────────────────────


class TestRiskParameters:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/risk_parameters").mock(
            return_value=httpx.Response(
                200,
                json={
                    "liquidation_margin_ratio_threshold": 0.05,
                    "queue_entry_margin_ratio_threshold": 0.08,
                    "initial_margin_multiplier": {"BTC-PERP": 2.0, "ETH-PERP": 1.5},
                },
            )
        )
        rp = perps_client.exchange.risk_parameters()
        assert rp.liquidation_margin_ratio_threshold == Decimal("0.05")
        assert isinstance(rp.liquidation_margin_ratio_threshold, Decimal)
        assert rp.initial_margin_multiplier["BTC-PERP"] == Decimal("2.0")
        assert isinstance(rp.initial_margin_multiplier["ETH-PERP"], Decimal)

    @respx.mock
    def test_empty_multiplier_map(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/risk_parameters").mock(
            return_value=httpx.Response(
                200,
                json={
                    "liquidation_margin_ratio_threshold": 0.05,
                    "queue_entry_margin_ratio_threshold": 0.08,
                    "initial_margin_multiplier": {},
                },
            )
        )
        assert perps_client.exchange.risk_parameters().initial_margin_multiplier == {}

    @respx.mock
    def test_high_precision_double_no_float_drift(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/risk_parameters").mock(
            return_value=httpx.Response(
                200,
                json={
                    "liquidation_margin_ratio_threshold": 0.12345678,
                    "queue_entry_margin_ratio_threshold": 0.08,
                    "initial_margin_multiplier": {},
                },
            )
        )
        rp = perps_client.exchange.risk_parameters()
        # MultiplierDecimal coerces via str() — no binary-float drift.
        assert rp.liquidation_margin_ratio_threshold == Decimal("0.12345678")

    @respx.mock
    def test_server_error_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/risk_parameters").mock(return_value=httpx.Response(500))
        with pytest.raises(KalshiServerError):
            perps_client.exchange.risk_parameters()


class TestSharedPrimitives:
    def test_exchange_instance(self) -> None:
        assert ExchangeInstance("event_contract") is ExchangeInstance.EVENT_CONTRACT
        assert ExchangeInstance("margined") is ExchangeInstance.MARGINED
        with pytest.raises(ValueError):
            ExchangeInstance("unknown")
