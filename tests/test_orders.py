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
                        "yes_price_dollars": "0.6500",
                        "count": 10,
                    }
                },
            )
        )
        order = orders.create(ticker="TEST-MKT", side="yes", count=10, yes_price=0.65)
        assert order.order_id == "ord-123"
        assert order.yes_price == Decimal("0.6500")
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
        # Must be sent as yes_price_dollars (FixedPointDollars string)
        assert body["yes_price_dollars"] == "0.65"
        assert "yes_price" not in body

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
                        {
                            "trade_id": "t1",
                            "order_id": "o1",
                            "yes_price_dollars": "0.5000",
                            "count": 5,
                        }
                    ]
                },
            )
        )
        page = orders.fills()
        assert len(page) == 1
        assert page.items[0].trade_id == "t1"
        assert page.items[0].yes_price == Decimal("0.5000")


class TestOrdersFillsAll:
    @respx.mock
    def test_auto_paginates(self, orders: OrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "fills": [{"trade_id": "a", "yes_price_dollars": "0.50"}],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "fills": [{"trade_id": "b", "yes_price_dollars": "0.60"}],
                        "cursor": "",
                    },
                ),
            ]
        )
        ids = [f.trade_id for f in orders.fills_all()]
        assert ids == ["a", "b"]


class TestOrdersAmend:
    @respx.mock
    def test_amend_price(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-100/amend"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "old_order": {
                        "order_id": "ord-100",
                        "ticker": "MKT-A",
                        "side": "yes",
                        "status": "resting",
                        "yes_price_dollars": "0.5000",
                        "count": 10,
                    },
                    "order": {
                        "order_id": "ord-100",
                        "ticker": "MKT-A",
                        "side": "yes",
                        "status": "resting",
                        "yes_price_dollars": "0.6000",
                        "count": 10,
                    },
                },
            )
        )
        result = orders.amend(
            "ord-100",
            ticker="MKT-A",
            side="yes",
            action="buy",
            yes_price=0.60,
        )
        assert result.old_order.yes_price == Decimal("0.5000")
        assert result.order.yes_price == Decimal("0.6000")
        assert result.order.order_id == "ord-100"

    @respx.mock
    def test_amend_serializes_dollars_and_count(self, orders: OrdersResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-200/amend"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "old_order": {"order_id": "ord-200", "ticker": "T"},
                    "order": {"order_id": "ord-200", "ticker": "T"},
                },
            )
        )
        orders.amend(
            "ord-200",
            ticker="T",
            side="yes",
            action="buy",
            yes_price=0.55,
            count=20,
        )

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["yes_price_dollars"] == "0.55"
        assert body["count_fp"] == "20"
        assert "yes_price" not in body
        assert "count" not in body

    @respx.mock
    def test_amend_not_found(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/amend"
        ).mock(return_value=httpx.Response(404, json={"message": "order not found"}))
        with pytest.raises(KalshiNotFoundError):
            orders.amend("fake", ticker="T", side="yes", action="buy")

    @respx.mock
    def test_amend_validation_error(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-300/amend"
        ).mock(return_value=httpx.Response(400, json={"message": "invalid side"}))
        with pytest.raises(KalshiValidationError):
            orders.amend("ord-300", ticker="T", side="invalid", action="buy")


class TestOrdersDecrease:
    @respx.mock
    def test_decrease_by(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-400/decrease"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": {
                        "order_id": "ord-400",
                        "ticker": "MKT-B",
                        "status": "resting",
                        "remaining_count_fp": "5",
                    }
                },
            )
        )
        order = orders.decrease("ord-400", reduce_by=5)
        assert order.order_id == "ord-400"
        assert order.remaining_count == Decimal("5")

    @respx.mock
    def test_decrease_to(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-500/decrease"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": {
                        "order_id": "ord-500",
                        "ticker": "MKT-C",
                        "status": "cancelled",
                        "remaining_count_fp": "0",
                    }
                },
            )
        )
        order = orders.decrease("ord-500", reduce_to=0)
        assert order.order_id == "ord-500"
        assert order.remaining_count == Decimal("0")

    @respx.mock
    def test_decrease_not_found(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/decrease"
        ).mock(return_value=httpx.Response(404, json={"message": "order not found"}))
        with pytest.raises(KalshiNotFoundError):
            orders.decrease("fake", reduce_by=1)

    @respx.mock
    def test_decrease_validation_error(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-600/decrease"
        ).mock(
            return_value=httpx.Response(400, json={"message": "reduce_by must be > 0"})
        )
        with pytest.raises(KalshiValidationError):
            orders.decrease("ord-600", reduce_by=-1)


class TestOrdersQueuePositions:
    @respx.mock
    def test_queue_positions(self, orders: OrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/queue_positions"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "queue_positions": [
                        {
                            "order_id": "ord-700",
                            "market_ticker": "MKT-D",
                            "queue_position_fp": "3",
                        },
                        {
                            "order_id": "ord-701",
                            "market_ticker": "MKT-D",
                            "queue_position_fp": "7",
                        },
                    ]
                },
            )
        )
        positions = orders.queue_positions()
        assert len(positions) == 2
        assert positions[0].order_id == "ord-700"
        assert positions[0].queue_position == Decimal("3")
        assert positions[1].queue_position == Decimal("7")

    @respx.mock
    def test_queue_positions_with_filter(self, orders: OrdersResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/queue_positions"
        ).mock(
            return_value=httpx.Response(200, json={"queue_positions": []})
        )
        orders.queue_positions(event_ticker="EVT-1")
        params = dict(route.calls[0].request.url.params)
        assert params["event_ticker"] == "EVT-1"

    @respx.mock
    def test_queue_positions_empty(self, orders: OrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/queue_positions"
        ).mock(return_value=httpx.Response(200, json={"queue_positions": []}))
        positions = orders.queue_positions()
        assert positions == []

    @respx.mock
    def test_queue_position_single(self, orders: OrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-800/queue_position"
        ).mock(
            return_value=httpx.Response(
                200, json={"queue_position_fp": "5"}
            )
        )
        pos = orders.queue_position("ord-800")
        assert pos == Decimal("5")

    @respx.mock
    def test_queue_position_not_found(self, orders: OrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/queue_position"
        ).mock(return_value=httpx.Response(404, json={"message": "order not found"}))
        with pytest.raises(KalshiNotFoundError):
            orders.queue_position("fake")
