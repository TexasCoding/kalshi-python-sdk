"""Tests for kalshi.resources.order_groups — Order Groups resource."""

from __future__ import annotations

from decimal import Decimal

import httpx  # noqa: F401
import pytest
import respx  # noqa: F401

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
    CreateOrderGroupResponse,
    GetOrderGroupResponse,
    OrderGroup,
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
