"""Integration tests for OrderGroupsResource — list/get/create/delete/reset/trigger/update_limit."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import KalshiNotFoundError
from kalshi.models.order_groups import (
    CreateOrderGroupResponse,
    GetOrderGroupResponse,
    OrderGroup,
)
from tests.integration.assertions import assert_model_fields
from tests.integration.conftest import skip_if_low_balance
from tests.integration.coverage_harness import register

logger = logging.getLogger(__name__)

register(
    "OrderGroupsResource",
    [
        "create",
        "delete",
        "get",
        "list",
        "reset",
        "trigger",
        "update_limit",
    ],
)


@pytest.fixture
def ephemeral_group(
    sync_client: KalshiClient,
    demo_balance_cents: int,
) -> Iterator[str]:
    """Create an order group for the test and clean it up afterward.

    Demo balance floor: 100 cents.
    """
    skip_if_low_balance(demo_balance_cents, threshold_cents=100)
    resp = sync_client.order_groups.create(contracts_limit=1)
    group_id = resp.order_group_id
    try:
        yield group_id
    finally:
        try:
            sync_client.order_groups.delete(group_id)
        except Exception:
            logger.warning("cleanup: failed to delete order group %s", group_id)


@pytest.mark.integration
class TestOrderGroupsSync:
    def test_list(self, sync_client: KalshiClient) -> None:
        groups = sync_client.order_groups.list()
        assert isinstance(groups, list)
        for g in groups:
            assert isinstance(g, OrderGroup)
            assert_model_fields(g)

    def test_create_and_get(
        self, sync_client: KalshiClient, ephemeral_group: str,
    ) -> None:
        resp = sync_client.order_groups.get(ephemeral_group)
        assert isinstance(resp, GetOrderGroupResponse)
        assert_model_fields(resp)

    def test_update_limit(
        self, sync_client: KalshiClient, ephemeral_group: str,
    ) -> None:
        sync_client.order_groups.update_limit(ephemeral_group, contracts_limit=5)
        resp = sync_client.order_groups.get(ephemeral_group)
        # Server may normalize the limit — just assert round-trip works
        assert resp.contracts_limit is not None

    def test_trigger_then_reset(
        self, sync_client: KalshiClient, ephemeral_group: str,
    ) -> None:
        sync_client.order_groups.trigger(ephemeral_group)
        sync_client.order_groups.reset(ephemeral_group)
        # Both returning without exception is the assertion.

    def test_delete(
        self, sync_client: KalshiClient, demo_balance_cents: int,
    ) -> None:
        skip_if_low_balance(demo_balance_cents, threshold_cents=100)
        resp = sync_client.order_groups.create(contracts_limit=1)
        sync_client.order_groups.delete(resp.order_group_id)
        # Follow-up GET should 404
        with pytest.raises(KalshiNotFoundError):
            sync_client.order_groups.get(resp.order_group_id)


@pytest.mark.integration
class TestOrderGroupsAsync:
    @pytest.mark.asyncio
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        groups = await async_client.order_groups.list()
        assert isinstance(groups, list)
        for g in groups:
            assert isinstance(g, OrderGroup)

    @pytest.mark.asyncio
    async def test_create_get_delete(
        self, async_client: AsyncKalshiClient, demo_balance_cents: int,
    ) -> None:

        skip_if_low_balance(demo_balance_cents, threshold_cents=100)
        resp = await async_client.order_groups.create(contracts_limit=1)
        assert isinstance(resp, CreateOrderGroupResponse)
        try:
            # Demo server may need a moment to propagate the new group.
            await asyncio.sleep(0.5)
            got = await async_client.order_groups.get(resp.order_group_id)
            assert isinstance(got, GetOrderGroupResponse)
        finally:
            await async_client.order_groups.delete(resp.order_group_id)

    @pytest.mark.asyncio
    async def test_reset_and_trigger(
        self, async_client: AsyncKalshiClient, demo_balance_cents: int,
    ) -> None:
        skip_if_low_balance(demo_balance_cents, threshold_cents=100)
        resp = await async_client.order_groups.create(contracts_limit=1)
        try:
            await async_client.order_groups.trigger(resp.order_group_id)
            await async_client.order_groups.reset(resp.order_group_id)
        finally:
            await async_client.order_groups.delete(resp.order_group_id)

    @pytest.mark.asyncio
    async def test_update_limit(
        self, async_client: AsyncKalshiClient, demo_balance_cents: int,
    ) -> None:
        skip_if_low_balance(demo_balance_cents, threshold_cents=100)
        resp = await async_client.order_groups.create(contracts_limit=1)
        try:
            await async_client.order_groups.update_limit(
                resp.order_group_id, contracts_limit=5,
            )
        finally:
            await async_client.order_groups.delete(resp.order_group_id)
