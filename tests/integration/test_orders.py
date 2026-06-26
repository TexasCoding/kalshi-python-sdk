"""Integration tests for OrdersResource — mutable operations."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.common import Page
from kalshi.models.orders import Fill, Order
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register(
    "OrdersResource",
    [
        "amend_v2",
        "batch_cancel_v2",
        "batch_create_v2",
        "cancel_v2",
        "create_v2",
        "decrease_v2",
        "fills",
        "fills_all",
        "get",
        "list",
        "list_all",
        "queue_position",
        "queue_positions",
    ],
)


@pytest.mark.integration
class TestOrdersSync:
    def test_list(self, sync_client: KalshiClient) -> None:
        page = sync_client.orders.list(limit=5)
        assert isinstance(page, Page)
        for item in page.items:
            assert isinstance(item, Order)
            assert_model_fields(item)

    def test_list_all(self, sync_client: KalshiClient) -> None:
        for count, order in enumerate(sync_client.orders.list_all(limit=2)):
            assert isinstance(order, Order)
            assert_model_fields(order)

            if count >= 2:
                break

    def test_fills(self, sync_client: KalshiClient) -> None:
        page = sync_client.orders.fills(limit=5)
        assert isinstance(page, Page)
        for item in page.items:
            assert isinstance(item, Fill)
            assert_model_fields(item)

    def test_fills_all(self, sync_client: KalshiClient) -> None:
        for count, fill in enumerate(sync_client.orders.fills_all(limit=2)):
            assert isinstance(fill, Fill)
            assert_model_fields(fill)

            if count >= 2:
                break


@pytest.mark.integration
class TestOrdersAsync:
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.orders.list(limit=5)
        assert isinstance(page, Page)
        for item in page.items:
            assert isinstance(item, Order)
            assert_model_fields(item)

    async def test_list_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for order in async_client.orders.list_all(limit=2):
            assert isinstance(order, Order)
            assert_model_fields(order)
            count += 1
            if count >= 3:
                break

    async def test_fills(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.orders.fills(limit=5)
        assert isinstance(page, Page)
        for item in page.items:
            assert isinstance(item, Fill)
            assert_model_fields(item)

    async def test_fills_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for fill in async_client.orders.fills_all(limit=2):
            assert isinstance(fill, Fill)
            assert_model_fields(fill)
            count += 1
            if count >= 3:
                break
