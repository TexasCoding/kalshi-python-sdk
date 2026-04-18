"""Tests for kalshi.resources.order_groups — Order Groups resource."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.async_client import AsyncKalshiClient
from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import DEMO_BASE_URL, KalshiConfig
from kalshi.errors import (  # noqa: F401
    AuthRequiredError,
    KalshiNotFoundError,
    KalshiValidationError,
)
from kalshi.models.order_groups import (
    CreateOrderGroupRequest,
    CreateOrderGroupResponse,
    GetOrderGroupResponse,
    OrderGroup,
    UpdateOrderGroupLimitRequest,
)
from kalshi.resources.order_groups import (
    AsyncOrderGroupsResource,
    OrderGroupsResource,
)


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def order_groups(test_auth: KalshiAuth, config: KalshiConfig) -> OrderGroupsResource:
    return OrderGroupsResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_order_groups(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> AsyncOrderGroupsResource:
    return AsyncOrderGroupsResource(AsyncTransport(test_auth, config))


@pytest.fixture
def client(test_auth: KalshiAuth) -> KalshiClient:
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, timeout=5.0, max_retries=0)
    return KalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def async_client(test_auth: KalshiAuth) -> AsyncKalshiClient:
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, timeout=5.0, max_retries=0)
    return AsyncKalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def unauth_order_groups(config: KalshiConfig) -> OrderGroupsResource:
    return OrderGroupsResource(SyncTransport(None, config))


class TestOrderGroupModels:
    def test_order_group_accepts_fp_alias(self) -> None:
        og = OrderGroup.model_validate(
            {"id": "grp-1", "contracts_limit_fp": "5", "is_auto_cancel_enabled": True}
        )
        assert og.id == "grp-1"
        assert og.contracts_limit == Decimal("5")
        assert og.is_auto_cancel_enabled is True

    def test_order_group_accepts_short_name(self) -> None:
        og = OrderGroup.model_validate(
            {"id": "grp-1", "contracts_limit": "5", "is_auto_cancel_enabled": False}
        )
        assert og.contracts_limit == Decimal("5")

    def test_order_group_limit_optional(self) -> None:
        # Spec marks contracts_limit_fp optional — omitted in minimal response
        og = OrderGroup.model_validate({"id": "grp-1", "is_auto_cancel_enabled": True})
        assert og.contracts_limit is None

    def test_get_order_group_response_parses_orders(self) -> None:
        resp = GetOrderGroupResponse.model_validate(
            {
                "is_auto_cancel_enabled": True,
                "orders": ["ord-a", "ord-b"],
                "contracts_limit_fp": "10",
            }
        )
        assert resp.orders == ["ord-a", "ord-b"]
        assert resp.contracts_limit == Decimal("10")

    def test_create_order_group_response_parses(self) -> None:
        resp = CreateOrderGroupResponse.model_validate({"order_group_id": "grp-new"})
        assert resp.order_group_id == "grp-new"


class TestOrderGroupRequestModels:
    def test_create_request_serializes_contracts_limit(self) -> None:
        req = CreateOrderGroupRequest(contracts_limit=5)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"contracts_limit": 5}

    def test_create_request_with_subaccount(self) -> None:
        req = CreateOrderGroupRequest(contracts_limit=10, subaccount=2)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"contracts_limit": 10, "subaccount": 2}

    def test_create_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError) as exc:
            CreateOrderGroupRequest(contracts_limit=1, phantom=True)  # type: ignore[call-arg]
        assert "phantom" in str(exc.value).lower() or "extra" in str(exc.value).lower()

    def test_create_request_rejects_zero_and_negative(self) -> None:
        with pytest.raises(ValidationError):
            CreateOrderGroupRequest(contracts_limit=0)
        with pytest.raises(ValidationError):
            CreateOrderGroupRequest(contracts_limit=-1)

    def test_update_limit_request_serializes(self) -> None:
        req = UpdateOrderGroupLimitRequest(contracts_limit=20)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"contracts_limit": 20}

    def test_update_limit_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError) as exc:
            UpdateOrderGroupLimitRequest(contracts_limit=1, subaccount=0)  # type: ignore[call-arg]
        # subaccount is NOT on this request per spec (no SubaccountQuery on /limit)
        assert "subaccount" in str(exc.value).lower() or "extra" in str(exc.value).lower()


_MINIMAL_OG = {"id": "grp-1", "contracts_limit_fp": "5", "is_auto_cancel_enabled": True}


class TestOrderGroupsList:
    @respx.mock
    def test_list_returns_typed_order_groups(
        self, order_groups: OrderGroupsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "order_groups": [_MINIMAL_OG, {"id": "grp-2", "is_auto_cancel_enabled": False}]
                },
            )
        )
        result = order_groups.list()
        assert len(result) == 2
        assert all(isinstance(og, OrderGroup) for og in result)
        assert result[0].id == "grp-1"
        assert result[0].contracts_limit == Decimal("5")

    @respx.mock
    def test_list_sends_subaccount_query(
        self, order_groups: OrderGroupsResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups"
        ).mock(return_value=httpx.Response(200, json={"order_groups": []}))
        order_groups.list(subaccount=3)
        assert route.calls[0].request.url.params["subaccount"] == "3"

    @respx.mock
    def test_list_empty_response(self, order_groups: OrderGroupsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups"
        ).mock(return_value=httpx.Response(200, json={"order_groups": []}))
        assert order_groups.list() == []


class TestOrderGroupsGet:
    @respx.mock
    def test_get_returns_full_response(self, order_groups: OrderGroupsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "is_auto_cancel_enabled": True,
                    "orders": ["ord-a"],
                    "contracts_limit_fp": "5",
                },
            )
        )
        resp = order_groups.get("grp-1")
        assert isinstance(resp, GetOrderGroupResponse)
        assert resp.orders == ["ord-a"]

    @respx.mock
    def test_get_404_maps_to_not_found(self, order_groups: OrderGroupsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/missing"
        ).mock(
            return_value=httpx.Response(404, json={"message": "order group not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            order_groups.get("missing")


class TestOrderGroupsCreate:
    @respx.mock
    def test_create_sends_correct_body(self, order_groups: OrderGroupsResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/create"
        ).mock(return_value=httpx.Response(201, json={"order_group_id": "grp-new"}))

        resp = order_groups.create(contracts_limit=5, subaccount=1)

        body = json.loads(route.calls[0].request.content)
        assert body == {"contracts_limit": 5, "subaccount": 1}
        assert isinstance(resp, CreateOrderGroupResponse)
        assert resp.order_group_id == "grp-new"

    @respx.mock
    def test_create_omits_subaccount_when_none(
        self, order_groups: OrderGroupsResource,
    ) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/create"
        ).mock(return_value=httpx.Response(201, json={"order_group_id": "grp-new"}))

        order_groups.create(contracts_limit=5)

        body = json.loads(route.calls[0].request.content)
        assert "subaccount" not in body

    @respx.mock
    def test_create_400_maps_to_validation_error(
        self, order_groups: OrderGroupsResource,
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/create"
        ).mock(return_value=httpx.Response(400, json={"message": "bad limit"}))

        with pytest.raises(KalshiValidationError):
            order_groups.create(contracts_limit=5)


class TestOrderGroupsMutations:
    @respx.mock
    def test_delete_sends_delete_request(self, order_groups: OrderGroupsResource) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1"
        ).mock(return_value=httpx.Response(200, json={}))
        result = order_groups.delete("grp-1")
        assert result is None
        assert route.called

    @respx.mock
    def test_delete_with_subaccount(self, order_groups: OrderGroupsResource) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1"
        ).mock(return_value=httpx.Response(200, json={}))
        order_groups.delete("grp-1", subaccount=2)
        assert route.calls[0].request.url.params["subaccount"] == "2"

    @respx.mock
    def test_reset_sends_put(self, order_groups: OrderGroupsResource) -> None:
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1/reset"
        ).mock(return_value=httpx.Response(200, json={}))
        result = order_groups.reset("grp-1")
        assert result is None
        assert route.called

    @respx.mock
    def test_trigger_sends_put(self, order_groups: OrderGroupsResource) -> None:
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1/trigger"
        ).mock(return_value=httpx.Response(200, json={}))
        result = order_groups.trigger("grp-1")
        assert result is None
        assert route.called

    @respx.mock
    def test_update_limit_sends_put_with_body(
        self, order_groups: OrderGroupsResource,
    ) -> None:
        import json

        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1/limit"
        ).mock(return_value=httpx.Response(200, json={}))

        order_groups.update_limit("grp-1", contracts_limit=20)

        body = json.loads(route.calls[0].request.content)
        assert body == {"contracts_limit": 20}

    @respx.mock
    def test_update_limit_404(self, order_groups: OrderGroupsResource) -> None:
        respx.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/gone/limit"
        ).mock(return_value=httpx.Response(404, json={"message": "not found"}))
        with pytest.raises(KalshiNotFoundError):
            order_groups.update_limit("gone", contracts_limit=5)


@pytest.mark.asyncio
class TestAsyncOrderGroups:
    async def test_list(
        self, async_order_groups: AsyncOrderGroupsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups"
        ).mock(
            return_value=httpx.Response(200, json={"order_groups": [_MINIMAL_OG]})
        )
        result = await async_order_groups.list()
        assert len(result) == 1
        assert isinstance(result[0], OrderGroup)

    async def test_get(
        self, async_order_groups: AsyncOrderGroupsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1"
        ).mock(
            return_value=httpx.Response(
                200, json={"is_auto_cancel_enabled": True, "orders": []}
            )
        )
        resp = await async_order_groups.get("grp-1")
        assert isinstance(resp, GetOrderGroupResponse)

    async def test_create(
        self, async_order_groups: AsyncOrderGroupsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/create"
        ).mock(return_value=httpx.Response(201, json={"order_group_id": "grp-x"}))
        resp = await async_order_groups.create(contracts_limit=3)
        assert resp.order_group_id == "grp-x"
        assert route.called

    async def test_delete(
        self, async_order_groups: AsyncOrderGroupsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1"
        ).mock(return_value=httpx.Response(200, json={}))
        await async_order_groups.delete("grp-1")
        assert route.called

    async def test_reset(
        self, async_order_groups: AsyncOrderGroupsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1/reset"
        ).mock(return_value=httpx.Response(200, json={}))
        await async_order_groups.reset("grp-1")
        assert route.called

    async def test_trigger(
        self, async_order_groups: AsyncOrderGroupsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1/trigger"
        ).mock(return_value=httpx.Response(200, json={}))
        await async_order_groups.trigger("grp-1")
        assert route.called

    async def test_update_limit(
        self, async_order_groups: AsyncOrderGroupsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/order_groups/grp-1/limit"
        ).mock(return_value=httpx.Response(200, json={}))
        await async_order_groups.update_limit("grp-1", contracts_limit=10)
        body = json.loads(route.calls[0].request.content)
        assert body == {"contracts_limit": 10}
