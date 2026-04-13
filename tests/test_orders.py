"""Tests for kalshi.resources.orders — Orders resource."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiNotFoundError, KalshiValidationError
from kalshi.models.orders import CreateOrderRequest
from kalshi.resources.orders import OrdersResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def orders(test_auth: KalshiAuth, config: KalshiConfig) -> OrdersResource:
    return OrdersResource(SyncTransport(test_auth, config))


class TestOrdersCreate:
    @respx.mock
    def test_create_limit_order(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": {
                        "order_id": "ord-123",
                        "ticker": "TEST-MKT",
                        "side": "yes",
                        "status": "resting",
                        "yes_price": "0.65",
                        "count": 10,
                    }
                },
            )
        )
        order = orders.create(ticker="TEST-MKT", side="yes", count=10, yes_price=0.65)
        assert order.order_id == "ord-123"
        assert order.yes_price == Decimal("0.65")
        assert order.count == 10

    @respx.mock
    def test_create_market_order_no_price(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": {
                        "order_id": "ord-456",
                        "ticker": "TEST-MKT",
                        "status": "executed",
                    }
                },
            )
        )
        order = orders.create(ticker="TEST-MKT", side="yes", type="market")
        assert order.order_id == "ord-456"

    @respx.mock
    def test_decimal_price_conversion(self, orders: OrdersResource) -> None:
        route = respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(
                200, json={"order": {"order_id": "ord-789", "ticker": "T"}}
            )
        )
        orders.create(ticker="T", side="yes", yes_price=0.65)

        import json
        body = json.loads(route.calls[0].request.content)
        # Must be "0.65" string, not a float
        assert body["yes_price"] == "0.65"

    @respx.mock
    def test_validation_error(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(400, json={"message": "invalid ticker"})
        )
        with pytest.raises(KalshiValidationError):
            orders.create(ticker="INVALID", side="yes")


class TestOrdersGet:
    @respx.mock
    def test_returns_order(self, orders: OrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123").mock(
            return_value=httpx.Response(
                200,
                json={"order": {"order_id": "ord-123", "ticker": "MKT", "status": "resting"}},
            )
        )
        order = orders.get("ord-123")
        assert order.order_id == "ord-123"
        assert order.status == "resting"

    @respx.mock
    def test_not_found(self, orders: OrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/fake").mock(
            return_value=httpx.Response(404, json={"message": "order not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            orders.get("fake")


class TestOrdersCancel:
    @respx.mock
    def test_cancel_order(self, orders: OrdersResource) -> None:
        respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123").mock(
            return_value=httpx.Response(200, json={})
        )
        orders.cancel("ord-123")  # should not raise


class TestOrdersList:
    @respx.mock
    def test_returns_page(self, orders: OrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orders": [
                        {"order_id": "ord-1", "ticker": "A"},
                        {"order_id": "ord-2", "ticker": "B"},
                    ],
                    "cursor": "next",
                },
            )
        )
        page = orders.list()
        assert len(page) == 2
        assert page.items[0].order_id == "ord-1"
        assert page.has_next is True

    @respx.mock
    def test_with_filters(self, orders: OrdersResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        orders.list(status="resting", ticker="MKT-A")
        params = dict(route.calls[0].request.url.params)
        assert params["status"] == "resting"
        assert params["ticker"] == "MKT-A"


class TestOrdersBatch:
    @respx.mock
    def test_batch_create(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orders": [
                        {"order_id": "b1", "ticker": "A"},
                        {"order_id": "b2", "ticker": "B"},
                    ]
                },
            )
        )
        reqs = [
            CreateOrderRequest(ticker="A", side="yes"),
            CreateOrderRequest(ticker="B", side="no"),
        ]
        result = orders.batch_create(reqs)
        assert len(result) == 2
        assert result[0].order_id == "b1"


class TestOrdersFills:
    @respx.mock
    def test_returns_fills(self, orders: OrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fills": [
                        {"trade_id": "t1", "order_id": "o1", "yes_price": "0.50", "count": 5}
                    ]
                },
            )
        )
        page = orders.fills()
        assert len(page) == 1
        assert page.items[0].trade_id == "t1"
        assert page.items[0].yes_price == Decimal("0.50")
