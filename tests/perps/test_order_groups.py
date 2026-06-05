"""Tests for the perps (margin) order groups resource (#392)."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi.errors import (
    AuthRequiredError,
    KalshiAuthError,
    KalshiNotFoundError,
    KalshiValidationError,
)
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.models.order_groups import (
    CreateOrderGroupRequest,
    CreateOrderGroupResponse,
    GetOrderGroupResponse,
    OrderGroup,
    UpdateOrderGroupLimitRequest,
)

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


def _signed(request: httpx.Request) -> bool:
    """True if the request carries the RSA-PSS auth headers."""
    return (
        "KALSHI-ACCESS-KEY" in request.headers
        and "KALSHI-ACCESS-SIGNATURE" in request.headers
        and "KALSHI-ACCESS-TIMESTAMP" in request.headers
    )


# ── list ──────────────────────────────────────────────────────────────────────


class TestList:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/order_groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "order_groups": [
                        {
                            "id": "og-1",
                            "contracts_limit_fp": "10.00",
                            "is_auto_cancel_enabled": True,
                            "exchange_index": 0,
                        },
                        {
                            "id": "og-2",
                            "contracts_limit_fp": "25.50",
                            "is_auto_cancel_enabled": False,
                        },
                    ]
                },
            )
        )
        groups = perps_client.order_groups.list()
        assert isinstance(groups, list)
        assert [g.id for g in groups] == ["og-1", "og-2"]
        assert isinstance(groups[0], OrderGroup)
        assert groups[0].contracts_limit == Decimal("10.00")
        assert isinstance(groups[0].contracts_limit, Decimal)
        assert groups[1].contracts_limit == Decimal("25.50")
        assert groups[1].is_auto_cancel_enabled is False
        assert _signed(route.calls.last.request)

    @respx.mock
    def test_empty_when_absent(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/order_groups").mock(
            return_value=httpx.Response(200, json={})
        )
        assert perps_client.order_groups.list() == []

    @respx.mock
    def test_subaccount_query_param(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/order_groups").mock(
            return_value=httpx.Response(200, json={"order_groups": []})
        )
        perps_client.order_groups.list(subaccount=3)
        assert route.calls.last.request.url.params["subaccount"] == "3"

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/order_groups").mock(
            return_value=httpx.Response(200, json={"order_groups": []})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.order_groups.list()
        assert not route.called
        client.close()

    @respx.mock
    def test_server_401_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/order_groups").mock(
            return_value=httpx.Response(401, json={"error": {"code": "unauthorized"}})
        )
        with pytest.raises(KalshiAuthError):
            perps_client.order_groups.list()


# ── get ───────────────────────────────────────────────────────────────────────


class TestGet:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/order_groups/og-9").mock(
            return_value=httpx.Response(
                200,
                json={
                    "is_auto_cancel_enabled": True,
                    "orders": ["ord-1", "ord-2"],
                    "contracts_limit_fp": "5.00",
                },
            )
        )
        resp = perps_client.order_groups.get("og-9")
        assert isinstance(resp, GetOrderGroupResponse)
        assert resp.is_auto_cancel_enabled is True
        assert resp.orders == ["ord-1", "ord-2"]
        assert resp.contracts_limit == Decimal("5.00")
        assert _signed(route.calls.last.request)

    @respx.mock
    def test_null_orders_coerced_to_empty(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/order_groups/og-1").mock(
            return_value=httpx.Response(
                200,
                json={"is_auto_cancel_enabled": False, "orders": None},
            )
        )
        resp = perps_client.order_groups.get("og-1")
        assert resp.orders == []

    @respx.mock
    def test_subaccount_query_param(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/order_groups/og-1").mock(
            return_value=httpx.Response(
                200, json={"is_auto_cancel_enabled": False, "orders": []}
            )
        )
        perps_client.order_groups.get("og-1", subaccount=2)
        assert route.calls.last.request.url.params["subaccount"] == "2"

    @respx.mock
    def test_404_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/order_groups/missing").mock(
            return_value=httpx.Response(404, json={"error": {"code": "not_found"}})
        )
        with pytest.raises(KalshiNotFoundError):
            perps_client.order_groups.get("missing")


# ── create ────────────────────────────────────────────────────────────────────


class TestCreate:
    @respx.mock
    def test_happy_kwargs(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/order_groups/create").mock(
            return_value=httpx.Response(
                201, json={"order_group_id": "og-new", "subaccount": 0}
            )
        )
        resp = perps_client.order_groups.create(contracts_limit=10)
        assert isinstance(resp, CreateOrderGroupResponse)
        assert resp.order_group_id == "og-new"
        assert resp.subaccount == 0

        assert json.loads(route.calls.last.request.content) == {"contracts_limit": 10}
        assert _signed(route.calls.last.request)

    @respx.mock
    def test_happy_request_model(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/order_groups/create").mock(
            return_value=httpx.Response(
                201, json={"order_group_id": "og-2", "subaccount": 1, "exchange_index": 0}
            )
        )
        resp = perps_client.order_groups.create(
            request=CreateOrderGroupRequest(contracts_limit=5, subaccount=1)
        )
        assert resp.subaccount == 1

        assert json.loads(route.calls.last.request.content) == {
            "contracts_limit": 5,
            "subaccount": 1,
        }

    @respx.mock
    def test_subaccount_and_exchange_index_serialized(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/order_groups/create").mock(
            return_value=httpx.Response(
                201, json={"order_group_id": "og-3", "subaccount": 2}
            )
        )
        perps_client.order_groups.create(contracts_limit=7, subaccount=2, exchange_index=0)

        assert json.loads(route.calls.last.request.content) == {
            "contracts_limit": 7,
            "subaccount": 2,
            "exchange_index": 0,
        }

    def test_both_request_and_kwargs_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError):
            perps_client.order_groups.create(
                request=CreateOrderGroupRequest(contracts_limit=1), contracts_limit=2
            )

    def test_neither_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError):
            perps_client.order_groups.create()

    def test_phantom_kwarg_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateOrderGroupRequest(contracts_limit=1, bogus=True)  # type: ignore[call-arg]

    def test_contracts_limit_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateOrderGroupRequest(contracts_limit=0)

    @respx.mock
    def test_400_maps(self, perps_client: PerpsClient) -> None:
        respx.post(f"{BASE}/margin/order_groups/create").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            perps_client.order_groups.create(contracts_limit=10)

    @respx.mock
    def test_not_retried(self, perps_client: PerpsClient) -> None:
        # perps_config sets max_retries=2, but POST is never retried.
        route = respx.post(f"{BASE}/margin/order_groups/create").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(Exception):  # noqa: B017 — mapped 503
            perps_client.order_groups.create(contracts_limit=10)
        assert route.call_count == 1  # POST is never retried


# ── delete ────────────────────────────────────────────────────────────────────


class TestDelete:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/order_groups/og-1").mock(
            return_value=httpx.Response(200, json={})
        )
        assert perps_client.order_groups.delete("og-1") is None
        assert _signed(route.calls.last.request)

    @respx.mock
    def test_query_params(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/order_groups/og-1").mock(
            return_value=httpx.Response(200, json={})
        )
        perps_client.order_groups.delete("og-1", subaccount=4)
        params = route.calls.last.request.url.params
        assert params["subaccount"] == "4"

    @respx.mock
    def test_404_maps(self, perps_client: PerpsClient) -> None:
        respx.delete(f"{BASE}/margin/order_groups/missing").mock(
            return_value=httpx.Response(404, json={"error": {"code": "not_found"}})
        )
        with pytest.raises(KalshiNotFoundError):
            perps_client.order_groups.delete("missing")

    @respx.mock
    def test_not_retried(self, perps_client: PerpsClient) -> None:
        # perps_config sets max_retries=2, but DELETE is never retried.
        route = respx.delete(f"{BASE}/margin/order_groups/og-1").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(Exception):  # noqa: B017 — mapped 503
            perps_client.order_groups.delete("og-1")
        assert route.call_count == 1  # DELETE is never retried


# ── reset ─────────────────────────────────────────────────────────────────────


class TestReset:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.put(f"{BASE}/margin/order_groups/og-1/reset").mock(
            return_value=httpx.Response(200, json={})
        )
        assert perps_client.order_groups.reset("og-1", subaccount=1) is None
        req = route.calls.last.request
        assert req.headers["content-type"] == "application/json"
        assert req.content == b"{}"
        assert req.url.params["subaccount"] == "1"
        assert _signed(req)

    @respx.mock
    def test_404_maps(self, perps_client: PerpsClient) -> None:
        respx.put(f"{BASE}/margin/order_groups/missing/reset").mock(
            return_value=httpx.Response(404, json={"error": {"code": "not_found"}})
        )
        with pytest.raises(KalshiNotFoundError):
            perps_client.order_groups.reset("missing")


# ── trigger ───────────────────────────────────────────────────────────────────


class TestTrigger:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.put(f"{BASE}/margin/order_groups/og-1/trigger").mock(
            return_value=httpx.Response(200, json={})
        )
        assert perps_client.order_groups.trigger("og-1", subaccount=2) is None
        req = route.calls.last.request
        assert req.headers["content-type"] == "application/json"
        assert req.content == b"{}"
        assert req.url.params["subaccount"] == "2"
        assert _signed(req)

    @respx.mock
    def test_404_maps(self, perps_client: PerpsClient) -> None:
        respx.put(f"{BASE}/margin/order_groups/missing/trigger").mock(
            return_value=httpx.Response(404, json={"error": {"code": "not_found"}})
        )
        with pytest.raises(KalshiNotFoundError):
            perps_client.order_groups.trigger("missing")


# ── update_limit ──────────────────────────────────────────────────────────────


class TestUpdateLimit:
    @respx.mock
    def test_happy_kwargs(self, perps_client: PerpsClient) -> None:
        route = respx.put(f"{BASE}/margin/order_groups/og-1/limit").mock(
            return_value=httpx.Response(200, json={})
        )
        assert (
            perps_client.order_groups.update_limit("og-1", contracts_limit=25, subaccount=1)
            is None
        )
        req = route.calls.last.request

        assert json.loads(req.content) == {"contracts_limit": 25}
        assert req.url.params["subaccount"] == "1"
        assert _signed(req)

    @respx.mock
    def test_happy_request_model(self, perps_client: PerpsClient) -> None:
        route = respx.put(f"{BASE}/margin/order_groups/og-1/limit").mock(
            return_value=httpx.Response(200, json={})
        )
        perps_client.order_groups.update_limit(
            "og-1", request=UpdateOrderGroupLimitRequest(contracts_limit=50)
        )

        assert json.loads(route.calls.last.request.content) == {"contracts_limit": 50}

    def test_both_request_and_kwargs_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError):
            perps_client.order_groups.update_limit(
                "og-1",
                request=UpdateOrderGroupLimitRequest(contracts_limit=1),
                contracts_limit=2,
            )

    def test_neither_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError):
            perps_client.order_groups.update_limit("og-1")

    def test_phantom_kwarg_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UpdateOrderGroupLimitRequest(contracts_limit=1, bogus=True)  # type: ignore[call-arg]

    @respx.mock
    def test_400_maps(self, perps_client: PerpsClient) -> None:
        respx.put(f"{BASE}/margin/order_groups/og-1/limit").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            perps_client.order_groups.update_limit("og-1", contracts_limit=25)


# ── async coverage ────────────────────────────────────────────────────────────


class TestAsync:
    @respx.mock
    async def test_list(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/order_groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "order_groups": [
                        {"id": "og-1", "is_auto_cancel_enabled": True, "contracts_limit_fp": "3.00"}
                    ]
                },
            )
        )
        groups = await async_perps_client.order_groups.list()
        assert groups[0].id == "og-1"
        assert groups[0].contracts_limit == Decimal("3.00")
        await async_perps_client.close()

    @respx.mock
    async def test_create(self, async_perps_client: AsyncPerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/order_groups/create").mock(
            return_value=httpx.Response(
                201, json={"order_group_id": "og-a", "subaccount": 0}
            )
        )
        resp = await async_perps_client.order_groups.create(contracts_limit=8)
        assert resp.order_group_id == "og-a"
        assert resp.subaccount == 0

        assert json.loads(route.calls.last.request.content) == {"contracts_limit": 8}
        await async_perps_client.close()

    @respx.mock
    async def test_update_limit(self, async_perps_client: AsyncPerpsClient) -> None:
        route = respx.put(f"{BASE}/margin/order_groups/og-1/limit").mock(
            return_value=httpx.Response(200, json={})
        )
        await async_perps_client.order_groups.update_limit(
            "og-1", contracts_limit=12, subaccount=2
        )
        req = route.calls.last.request

        assert json.loads(req.content) == {"contracts_limit": 12}
        assert req.url.params["subaccount"] == "2"
        await async_perps_client.close()

    @respx.mock
    async def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/order_groups").mock(
            return_value=httpx.Response(200, json={"order_groups": []})
        )
        client = AsyncPerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            await client.order_groups.list()
        assert not route.called
        await client.close()
