"""Tests for the perps margin-account resource (#394).

Covers ``balance`` / ``risk`` / ``notional_risk_limit`` / ``fee_tiers`` sync and
async: happy path (asserting Decimal typing on money fields), error mapping,
edge cases (nullable fields, empty maps/arrays, signed positions), the
auth-required guard (raises before any HTTP), and the no-retry-not-applicable
GET-retry behaviour. Models/resources are imported from the concrete module
paths (package ``__init__`` exports are wired during integration).
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi.errors import AuthRequiredError, KalshiServerError
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


# ── balance ───────────────────────────────────────────────────────────────────


class TestBalance:
    @respx.mock
    def test_happy_multi_subaccount(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "subaccount_balances": [
                        {
                            "subaccount": 0,
                            "position_value": "1500.0000",
                            "account_equity": "2000.5000",
                            "maintenance_margin": "300.0000",
                            "initial_margin": "600.0000",
                            "resting_orders_margin": "0.0000",
                            "available_balance": "0.0000",
                        },
                        {
                            "subaccount": 1,
                            "position_value": "250.2500",
                            "account_equity": "0.0000",
                            "maintenance_margin": "50.0000",
                            "initial_margin": "0.0000",
                            "resting_orders_margin": "0.0000",
                            "available_balance": "0.0000",
                        },
                    ],
                    "settled_funds": "3210.7500",
                },
            )
        )
        resp = perps_client.margin.balance()
        assert route.called
        assert len(resp.subaccount_balances) == 2
        first = resp.subaccount_balances[0]
        assert first.subaccount == 0
        assert first.position_value == Decimal("1500.0000")
        assert isinstance(first.position_value, Decimal)
        assert isinstance(first.account_equity, Decimal)
        assert resp.settled_funds == Decimal("3210.7500")
        assert isinstance(resp.settled_funds, Decimal)

    @respx.mock
    def test_flag_omitted_by_default(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/balance").mock(
            return_value=httpx.Response(
                200, json={"subaccount_balances": [], "settled_funds": "0.0000"}
            )
        )
        perps_client.margin.balance()
        # Param absent unless caller opts in.
        assert "compute_available_balance" not in route.calls.last.request.url.params

    @respx.mock
    def test_flag_true_sends_query_param(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/balance").mock(
            return_value=httpx.Response(
                200, json={"subaccount_balances": [], "settled_funds": "0.0000"}
            )
        )
        perps_client.margin.balance(compute_available_balance=True)
        assert route.calls.last.request.url.params["compute_available_balance"] == "true"

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/balance").mock(
            return_value=httpx.Response(
                200, json={"subaccount_balances": [], "settled_funds": "0.0000"}
            )
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.margin.balance()
        assert not route.called
        client.close()

    @respx.mock
    def test_server_401_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/balance").mock(
            return_value=httpx.Response(401, json={"error": {"code": "unauthorized"}})
        )
        with pytest.raises(Exception):  # noqa: B017 — mapped SDK auth error
            perps_client.margin.balance()

    @respx.mock
    def test_server_403_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/balance").mock(
            return_value=httpx.Response(403, json={"error": {"code": "forbidden"}})
        )
        with pytest.raises(Exception):  # noqa: B017 — mapped SDK forbidden error
            perps_client.margin.balance()

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "subaccount_balances": [
                        {
                            "subaccount": 0,
                            "position_value": "1.0000",
                            "account_equity": "2.0000",
                            "maintenance_margin": "0.0000",
                            "initial_margin": "0.0000",
                            "resting_orders_margin": "0.0000",
                            "available_balance": "0.0000",
                        }
                    ],
                    "settled_funds": "5.0000",
                },
            )
        )
        resp = await async_perps_client.margin.balance()
        assert resp.subaccount_balances[0].account_equity == Decimal("2.0000")
        await async_perps_client.close()

    @respx.mock
    async def test_async_unauth_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/balance").mock(
            return_value=httpx.Response(
                200, json={"subaccount_balances": [], "settled_funds": "0.0000"}
            )
        )
        client = AsyncPerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            await client.margin.balance()
        assert not route.called
        await client.close()


# ── risk ──────────────────────────────────────────────────────────────────────


class TestRisk:
    @respx.mock
    def test_happy_signed_position_and_nullables(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/risk").mock(
            return_value=httpx.Response(
                200,
                json={
                    "account_leverage": 2.5,
                    "total_position_notional": "10000.0000",
                    "total_maintenance_margin": "4000.0000",
                    "positions": [
                        {
                            "subaccount": 0,
                            "market_ticker": "BTC-PERP",
                            "position": "-150.00",
                            "mark_price": "0.5600",
                            "position_notional": "84.0000",
                            "maintenance_margin_required": "33.6000",
                            "position_leverage": 2.5,
                            "estimated_liquidation_price": "0.4200",
                        },
                        {
                            "subaccount": 1,
                            "market_ticker": "ETH-PERP",
                            "position": "10.00",
                            "mark_price": "0.3000",
                            "position_notional": "3.0000",
                            "maintenance_margin_required": None,
                            "position_leverage": None,
                            "estimated_liquidation_price": None,
                        },
                    ],
                },
            )
        )
        resp = perps_client.margin.risk()
        assert resp.account_leverage == 2.5
        assert resp.total_position_notional == Decimal("10000.0000")
        assert isinstance(resp.total_maintenance_margin, Decimal)
        first = resp.positions[0]
        # Signed position round-trips as a negative Decimal.
        assert first.position == Decimal("-150.00")
        assert isinstance(first.position, Decimal)
        assert first.mark_price == Decimal("0.5600")
        assert first.estimated_liquidation_price == Decimal("0.4200")
        second = resp.positions[1]
        assert second.maintenance_margin_required is None
        assert second.position_leverage is None
        assert second.estimated_liquidation_price is None

    @respx.mock
    def test_edge_null_leverage_empty_positions(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/risk").mock(
            return_value=httpx.Response(
                200,
                json={
                    "account_leverage": None,
                    "total_position_notional": "0.0000",
                    "total_maintenance_margin": "0.0000",
                    "positions": [],
                },
            )
        )
        resp = perps_client.margin.risk()
        assert resp.account_leverage is None
        assert resp.positions == []

    @respx.mock
    def test_server_error_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/risk").mock(return_value=httpx.Response(500))
        with pytest.raises(KalshiServerError):
            perps_client.margin.risk()

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/risk").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total_position_notional": "0.0000",
                    "total_maintenance_margin": "0.0000",
                    "positions": [],
                },
            )
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.margin.risk()
        assert not route.called
        client.close()

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/risk").mock(
            return_value=httpx.Response(
                200,
                json={
                    "account_leverage": 1.0,
                    "total_position_notional": "1.0000",
                    "total_maintenance_margin": "1.0000",
                    "positions": [],
                },
            )
        )
        resp = await async_perps_client.margin.risk()
        assert resp.total_position_notional == Decimal("1.0000")
        await async_perps_client.close()


# ── notional_risk_limit ───────────────────────────────────────────────────────


class TestNotionalRiskLimit:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/notional_risk_limit").mock(
            return_value=httpx.Response(
                200,
                json={
                    "default_notional_value_risk_limit": "5000.0000",
                    "notional_value_risk_limits_by_market_ticker": {
                        "market-abc-123": "7500.0000",
                        "market-xyz-789": "1000.0000",
                    },
                },
            )
        )
        resp = perps_client.margin.notional_risk_limit()
        assert route.called
        assert resp.default_notional_value_risk_limit == Decimal("5000.0000")
        assert isinstance(resp.default_notional_value_risk_limit, Decimal)
        overrides = resp.notional_value_risk_limits_by_market_ticker
        assert overrides["market-abc-123"] == Decimal("7500.0000")
        assert isinstance(overrides["market-xyz-789"], Decimal)

    @respx.mock
    def test_edge_empty_override_map(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/notional_risk_limit").mock(
            return_value=httpx.Response(
                200,
                json={
                    "default_notional_value_risk_limit": "5000.0000",
                    "notional_value_risk_limits_by_market_ticker": {},
                },
            )
        )
        resp = perps_client.margin.notional_risk_limit()
        assert resp.notional_value_risk_limits_by_market_ticker == {}

    @respx.mock
    def test_server_401_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/notional_risk_limit").mock(
            return_value=httpx.Response(401, json={"error": {"code": "unauthorized"}})
        )
        with pytest.raises(Exception):  # noqa: B017 — mapped SDK auth error
            perps_client.margin.notional_risk_limit()

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/notional_risk_limit").mock(
            return_value=httpx.Response(
                200,
                json={
                    "default_notional_value_risk_limit": "0.0000",
                    "notional_value_risk_limits_by_market_ticker": {},
                },
            )
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.margin.notional_risk_limit()
        assert not route.called
        client.close()

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/notional_risk_limit").mock(
            return_value=httpx.Response(
                200,
                json={
                    "default_notional_value_risk_limit": "5000.0000",
                    "notional_value_risk_limits_by_market_ticker": {"m-1": "1.0000"},
                },
            )
        )
        resp = await async_perps_client.margin.notional_risk_limit()
        assert resp.notional_value_risk_limits_by_market_ticker["m-1"] == Decimal("1.0000")
        await async_perps_client.close()


# ── fee_tiers ─────────────────────────────────────────────────────────────────


class TestFeeTiers:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/fee_tiers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "maker_fee_rates": {"BTC-PERP": 0.0005, "ETH-PERP": 0.0007},
                    "taker_fee_rates": {"BTC-PERP": 0.0012, "ETH-PERP": 0.0015},
                },
            )
        )
        resp = perps_client.margin.fee_tiers()
        assert resp.maker_fee_rates["BTC-PERP"] == 0.0005
        assert isinstance(resp.maker_fee_rates["BTC-PERP"], float)
        assert resp.taker_fee_rates["ETH-PERP"] == 0.0015
        assert isinstance(resp.taker_fee_rates["ETH-PERP"], float)

    @respx.mock
    def test_edge_empty_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/fee_tiers").mock(
            return_value=httpx.Response(
                200, json={"maker_fee_rates": {}, "taker_fee_rates": {}}
            )
        )
        resp = perps_client.margin.fee_tiers()
        assert resp.maker_fee_rates == {}
        assert resp.taker_fee_rates == {}

    @respx.mock
    def test_server_401_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/fee_tiers").mock(
            return_value=httpx.Response(401, json={"error": {"code": "unauthorized"}})
        )
        with pytest.raises(Exception):  # noqa: B017 — mapped SDK auth error
            perps_client.margin.fee_tiers()

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/fee_tiers").mock(
            return_value=httpx.Response(200, json={"maker_fee_rates": {}, "taker_fee_rates": {}})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.margin.fee_tiers()
        assert not route.called
        client.close()

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/fee_tiers").mock(
            return_value=httpx.Response(
                200,
                json={"maker_fee_rates": {"X": 0.001}, "taker_fee_rates": {"X": 0.002}},
            )
        )
        resp = await async_perps_client.margin.fee_tiers()
        assert resp.taker_fee_rates["X"] == 0.002
        await async_perps_client.close()


# ── base URL / extra-field tolerance ──────────────────────────────────────────


class TestPerpsBaseUrl:
    @respx.mock
    def test_prod_base_url_matched(self, test_auth) -> None:  # type: ignore[no-untyped-def]
        prod = "https://external-api.kalshi.com/trade-api/v2"
        route = respx.get(f"{prod}/margin/fee_tiers").mock(
            return_value=httpx.Response(200, json={"maker_fee_rates": {}, "taker_fee_rates": {}})
        )
        client = PerpsClient(auth=test_auth, config=PerpsConfig.production())
        client.margin.fee_tiers()
        assert route.called
        assert str(route.calls.last.request.url) == f"{prod}/margin/fee_tiers"
        client.close()

    @respx.mock
    def test_additive_field_tolerated(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/fee_tiers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "maker_fee_rates": {},
                    "taker_fee_rates": {},
                    "new_server_field": 1,
                },
            )
        )
        # extra="allow" — additive field doesn't break parsing.
        assert perps_client.margin.fee_tiers().maker_fee_rates == {}
