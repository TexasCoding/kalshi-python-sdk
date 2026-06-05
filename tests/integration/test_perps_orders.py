"""Integration tests for the perps (margin) orders resource — live demo.

Covers ``create`` / ``get`` / ``list`` / ``cancel``. Order-mutating tests place a
RESTING (non-marketable, far-from-market) ``bid`` so it never fills, then cancel
it inline; the session-end ``cleanup_perps_orders`` sweep (conftest) is the
backstop, matching on the ``PERPS_TEST_RUN_ID``-tagged ``client_order_id``.

All perps order endpoints are auth-gated and require a margin-enabled account, so
each test guards with ``skip_if_not_margin_enabled`` (the demo must also expose a
margin market, guarded by the ``perps_market_ticker`` fixture).
"""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest

from kalshi.perps.async_client import AsyncPerpsClient
from kalshi.perps.client import PerpsClient
from kalshi.perps.models.orders import (
    CreateMarginOrderResponse,
    GetMarginOrdersResponse,
    MarginOrder,
)
from tests.integration.conftest import skip_if_not_margin_enabled
from tests.integration.coverage_harness import register_perps
from tests.integration.helpers import await_resource, wait_for_resource

logger = logging.getLogger(__name__)

register_perps(
    "MarginOrdersResource",
    [
        "amend",
        "cancel",
        "create",
        "decrease",
        "get",
        "list",
        "list_all",
        "list_all_fcm",
        "list_fcm",
    ],
)

# A resting bid far below any plausible market price. Perps prices are dollars
# (not the binary [0, 1]); $0.0001 is the minimum positive tick and is virtually
# guaranteed to rest rather than cross.
_RESTING_PRICE = "0.0001"


@pytest.mark.integration
class TestPerpsOrdersSync:
    def test_list(self, perps_sync_client: PerpsClient) -> None:
        skip_if_not_margin_enabled(perps_sync_client)
        resp = perps_sync_client.orders.list(limit=5)
        assert isinstance(resp, GetMarginOrdersResponse)
        for order in resp.orders:
            assert isinstance(order, MarginOrder)
            assert order.order_id

    def test_create_get_cancel(
        self,
        perps_sync_client: PerpsClient,
        perps_market_ticker: str,
        perps_test_run_id: str,
    ) -> None:
        """Create a resting margin bid, retrieve it, then cancel it."""
        skip_if_not_margin_enabled(perps_sync_client)
        client_order_id = f"{perps_test_run_id}-create"

        created = perps_sync_client.orders.create(
            ticker=perps_market_ticker,
            client_order_id=client_order_id,
            side="bid",
            count=1,
            price=_RESTING_PRICE,
            time_in_force="good_till_canceled",
            self_trade_prevention_type="taker_at_cross",
        )
        assert isinstance(created, CreateMarginOrderResponse)
        assert created.order_id

        try:
            order = wait_for_resource(
                lambda: perps_sync_client.orders.get(created.order_id),
            )
            assert isinstance(order, MarginOrder)
            assert order.order_id == created.order_id
            assert isinstance(order.price, Decimal)
        finally:
            try:
                perps_sync_client.orders.cancel(created.order_id)
            except Exception:
                logger.warning(
                    "Failed to cancel perps order %s in teardown", created.order_id
                )


@pytest.mark.integration
class TestPerpsOrdersAsync:
    async def test_list(self, perps_async_client: AsyncPerpsClient) -> None:
        if not perps_async_client.is_authenticated:
            pytest.skip("Perps client unauthenticated")
        if not (await perps_async_client.exchange.enabled()).enabled:
            pytest.skip("Demo account is not margin-enabled")
        resp = await perps_async_client.orders.list(limit=5)
        assert isinstance(resp, GetMarginOrdersResponse)
        for order in resp.orders:
            assert isinstance(order, MarginOrder)

    async def test_create_get_cancel(
        self,
        perps_async_client: AsyncPerpsClient,
        perps_test_run_id: str,
    ) -> None:
        """Async: create a resting margin bid, retrieve it, cancel it."""
        if not perps_async_client.is_authenticated:
            pytest.skip("Perps client unauthenticated")
        if not (await perps_async_client.exchange.enabled()).enabled:
            pytest.skip("Demo account is not margin-enabled")
        markets = await perps_async_client.markets.list()
        if not markets:
            pytest.skip("No margin markets on demo server")
        ticker = markets[0].ticker
        client_order_id = f"{perps_test_run_id}-async-create"

        created = await perps_async_client.orders.create(
            ticker=ticker,
            client_order_id=client_order_id,
            side="bid",
            count=1,
            price=_RESTING_PRICE,
            time_in_force="good_till_canceled",
            self_trade_prevention_type="taker_at_cross",
        )
        assert isinstance(created, CreateMarginOrderResponse)
        assert created.order_id

        try:
            order = await await_resource(
                lambda: perps_async_client.orders.get(created.order_id),
            )
            assert isinstance(order, MarginOrder)
            assert order.order_id == created.order_id
        finally:
            try:
                await perps_async_client.orders.cancel(created.order_id)
            except Exception:
                logger.warning(
                    "Failed to cancel async perps order %s", created.order_id
                )
