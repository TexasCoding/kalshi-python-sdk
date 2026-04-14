"""Integration tests for OrdersResource — mutable operations."""

from __future__ import annotations

import logging

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.common import Page
from kalshi.models.orders import CreateOrderRequest, Fill, Order
from kalshi.types import to_decimal
from tests.integration.assertions import assert_model_fields
from tests.integration.conftest import skip_if_low_balance
from tests.integration.coverage_harness import register

logger = logging.getLogger(__name__)

register(
    "OrdersResource",
    [
        "batch_cancel",
        "batch_create",
        "cancel",
        "create",
        "fills",
        "fills_all",
        "get",
        "list",
        "list_all",
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

    def test_create_get_cancel(
        self,
        sync_client: KalshiClient,
        demo_market_ticker: str,
        non_marketable_price: str,
        demo_balance_cents: int,
        test_run_id: str,
    ) -> None:
        """Create an order, retrieve it, then cancel it."""
        skip_if_low_balance(demo_balance_cents)
        client_order_id = f"{test_run_id}-create"

        order = sync_client.orders.create(
            ticker=demo_market_ticker,
            side="yes",
            type="limit",
            action="buy",
            count=1,
            yes_price=non_marketable_price,
            client_order_id=client_order_id,
        )
        assert isinstance(order, Order)
        assert_model_fields(order)
        assert order.order_id

        try:
            retrieved = sync_client.orders.get(order.order_id)
            assert isinstance(retrieved, Order)
            assert_model_fields(retrieved)
            assert retrieved.order_id == order.order_id
        finally:
            try:
                sync_client.orders.cancel(order.order_id)
            except Exception:
                logger.warning("Failed to cancel order %s in teardown", order.order_id)

    def test_batch_create_cancel(
        self,
        sync_client: KalshiClient,
        demo_market_ticker: str,
        non_marketable_price: str,
        demo_balance_cents: int,
        test_run_id: str,
    ) -> None:
        """Batch create orders, then batch cancel them."""
        skip_if_low_balance(demo_balance_cents)

        requests = [
            CreateOrderRequest(
                ticker=demo_market_ticker,
                side="yes",
                type="limit",
                action="buy",
                count=to_decimal(1),
                yes_price=to_decimal(non_marketable_price),
                client_order_id=f"{test_run_id}-batch-{i}",
            )
            for i in range(2)
        ]

        orders = sync_client.orders.batch_create(requests)
        assert isinstance(orders, list)
        assert len(orders) > 0
        for o in orders:
            assert isinstance(o, Order)
            assert_model_fields(o)

        order_ids = [o.order_id for o in orders]
        try:
            sync_client.orders.batch_cancel(order_ids)
        except Exception:
            # Clean up individually if batch cancel fails
            for oid in order_ids:
                try:
                    sync_client.orders.cancel(oid)
                except Exception:
                    logger.warning("Failed to cancel order %s in batch teardown", oid)


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

    async def test_create_get_cancel(
        self,
        async_client: AsyncKalshiClient,
        demo_market_ticker: str,
        non_marketable_price: str,
        demo_balance_cents: int,
        test_run_id: str,
    ) -> None:
        """Async: create, retrieve, cancel."""
        skip_if_low_balance(demo_balance_cents)
        client_order_id = f"{test_run_id}-async-create"

        order = await async_client.orders.create(
            ticker=demo_market_ticker,
            side="yes",
            type="limit",
            action="buy",
            count=1,
            yes_price=non_marketable_price,
            client_order_id=client_order_id,
        )
        assert isinstance(order, Order)
        assert_model_fields(order)
        assert order.order_id

        try:
            retrieved = await async_client.orders.get(order.order_id)
            assert isinstance(retrieved, Order)
            assert_model_fields(retrieved)
            assert retrieved.order_id == order.order_id
        finally:
            try:
                await async_client.orders.cancel(order.order_id)
            except Exception:
                logger.warning("Failed to cancel async order %s", order.order_id)

    async def test_batch_create_cancel(
        self,
        async_client: AsyncKalshiClient,
        demo_market_ticker: str,
        non_marketable_price: str,
        demo_balance_cents: int,
        test_run_id: str,
    ) -> None:
        """Async: batch create, then batch cancel."""
        skip_if_low_balance(demo_balance_cents)

        requests = [
            CreateOrderRequest(
                ticker=demo_market_ticker,
                side="yes",
                type="limit",
                action="buy",
                count=to_decimal(1),
                yes_price=to_decimal(non_marketable_price),
                client_order_id=f"{test_run_id}-async-batch-{i}",
            )
            for i in range(2)
        ]

        orders = await async_client.orders.batch_create(requests)
        assert isinstance(orders, list)
        assert len(orders) > 0
        for o in orders:
            assert isinstance(o, Order)
            assert_model_fields(o)

        order_ids = [o.order_id for o in orders]
        try:
            await async_client.orders.batch_cancel(order_ids)
        except Exception:
            for oid in order_ids:
                try:
                    await async_client.orders.cancel(oid)
                except Exception:
                    logger.warning("Failed to cancel async order %s", oid)
