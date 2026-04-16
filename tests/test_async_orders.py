"""Tests for async orders resource — mirrors test_orders.py."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiNotFoundError, KalshiValidationError
from kalshi.models.orders import AmendOrderResponse, CreateOrderRequest
from kalshi.resources.orders import AsyncOrdersResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def orders(
    test_auth: KalshiAuth, config: KalshiConfig
) -> AsyncOrdersResource:
    return AsyncOrdersResource(AsyncTransport(test_auth, config))


@pytest.fixture
def unauth_orders_async(config: KalshiConfig) -> AsyncOrdersResource:
    return AsyncOrdersResource(AsyncTransport(None, config))


class TestAsyncOrdersCreate:
    @respx.mock
    @pytest.mark.asyncio
    async def test_create_limit_order(
        self, orders: AsyncOrdersResource
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(
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
        order = await orders.create(
            ticker="TEST-MKT", side="yes", count=10, yes_price=0.65
        )
        assert order.order_id == "ord-123"
        assert order.yes_price == Decimal("0.6500")
        assert order.count == 10

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_market_order_no_price(
        self, orders: AsyncOrdersResource
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(
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
        order = await orders.create(
            ticker="TEST-MKT", side="yes", type="market"
        )
        assert order.order_id == "ord-456"

    @respx.mock
    @pytest.mark.asyncio
    async def test_decimal_price_conversion(
        self, orders: AsyncOrdersResource
    ) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": {"order_id": "ord-789", "ticker": "T"}
                },
            )
        )
        await orders.create(ticker="T", side="yes", yes_price=0.65)

        body = json.loads(route.calls[0].request.content)
        assert body["yes_price_dollars"] == "0.65"
        assert "yes_price" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_validation_error(
        self, orders: AsyncOrdersResource
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(
            return_value=httpx.Response(
                400, json={"message": "invalid ticker"}
            )
        )
        with pytest.raises(KalshiValidationError):
            await orders.create(ticker="INVALID", side="yes")


class TestAsyncOrdersGet:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_order(
        self, orders: AsyncOrdersResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": {
                        "order_id": "ord-123",
                        "ticker": "MKT",
                        "status": "resting",
                    }
                },
            )
        )
        order = await orders.get("ord-123")
        assert order.order_id == "ord-123"
        assert order.status == "resting"

    @respx.mock
    @pytest.mark.asyncio
    async def test_not_found(
        self, orders: AsyncOrdersResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/fake"
        ).mock(
            return_value=httpx.Response(
                404, json={"message": "order not found"}
            )
        )
        with pytest.raises(KalshiNotFoundError):
            await orders.get("fake")


class TestAsyncOrdersCancel:
    @respx.mock
    @pytest.mark.asyncio
    async def test_cancel_order(
        self, orders: AsyncOrdersResource
    ) -> None:
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123"
        ).mock(return_value=httpx.Response(200, json={}))
        await orders.cancel("ord-123")  # should not raise


class TestAsyncOrdersList:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(
        self, orders: AsyncOrdersResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(
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
        page = await orders.list()
        assert len(page) == 2
        assert page.items[0].order_id == "ord-1"
        assert page.has_next is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_with_filters(
        self, orders: AsyncOrdersResource
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(
            return_value=httpx.Response(
                200, json={"orders": []}
            )
        )
        await orders.list(status="resting", ticker="MKT-A")
        params = dict(route.calls[0].request.url.params)
        assert params["status"] == "resting"
        assert params["ticker"] == "MKT-A"


class TestAsyncOrdersListAll:
    @respx.mock
    @pytest.mark.asyncio
    async def test_auto_paginates(
        self, orders: AsyncOrdersResource
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "orders": [
                            {"order_id": "o1", "ticker": "A"},
                        ],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "orders": [
                            {"order_id": "o2", "ticker": "B"},
                        ],
                        "cursor": None,
                    },
                ),
            ]
        )
        order_ids = [
            o.order_id async for o in orders.list_all()
        ]
        assert order_ids == ["o1", "o2"]
        assert route.call_count == 2


class TestAsyncOrdersBatch:
    @respx.mock
    @pytest.mark.asyncio
    async def test_batch_create(
        self, orders: AsyncOrdersResource
    ) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2"
            "/portfolio/orders/batched"
        ).mock(
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
        result = await orders.batch_create(reqs)
        assert len(result) == 2
        assert result[0].order_id == "b1"

        # Verify serialization uses _dollars alias
        body = json.loads(route.calls[0].request.content)
        for order_body in body["orders"]:
            assert "yes_price" not in order_body

    @respx.mock
    @pytest.mark.asyncio
    async def test_batch_cancel(
        self, orders: AsyncOrdersResource
    ) -> None:
        respx.delete(
            "https://test.kalshi.com/trade-api/v2"
            "/portfolio/orders/batched"
        ).mock(return_value=httpx.Response(200, json={}))
        await orders.batch_cancel(["o1", "o2"])  # should not raise


class TestAsyncOrdersFills:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_fills(
        self, orders: AsyncOrdersResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/fills"
        ).mock(
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
        page = await orders.fills()
        assert len(page) == 1
        assert page.items[0].trade_id == "t1"
        assert page.items[0].yes_price == Decimal("0.5000")

    @respx.mock
    @pytest.mark.asyncio
    async def test_fills_with_filters(
        self, orders: AsyncOrdersResource
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/fills"
        ).mock(
            return_value=httpx.Response(
                200, json={"fills": []}
            )
        )
        await orders.fills(ticker="MKT-A", order_id="ord-1")
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["order_id"] == "ord-1"


class TestAsyncOrdersFillsAll:
    @respx.mock
    @pytest.mark.asyncio
    async def test_auto_paginates(self, orders: AsyncOrdersResource) -> None:
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
        ids = [f.trade_id async for f in orders.fills_all()]
        assert ids == ["a", "b"]


class TestAsyncOrdersAmend:
    @respx.mock
    @pytest.mark.asyncio
    async def test_amend_price(self, orders: AsyncOrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123/amend").mock(
            return_value=httpx.Response(200, json={
                "old_order": {"order_id": "ord-123", "ticker": "T", "yes_price_dollars": "0.5000"},
                "order": {"order_id": "ord-456", "ticker": "T", "yes_price_dollars": "0.6500"},
            })
        )
        result = await orders.amend("ord-123", ticker="T", side="yes", action="buy", yes_price=0.65)
        assert isinstance(result, AmendOrderResponse)
        assert result.order.yes_price == Decimal("0.6500")

    @respx.mock
    @pytest.mark.asyncio
    async def test_amend_not_found(self, orders: AsyncOrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/amend").mock(
            return_value=httpx.Response(404, json={"message": "not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            await orders.amend("fake", ticker="T", side="yes", action="buy", yes_price=0.50)


class TestAsyncOrdersDecrease:
    @respx.mock
    @pytest.mark.asyncio
    async def test_decrease_by(self, orders: AsyncOrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123/decrease").mock(
            return_value=httpx.Response(
                200,
                json={"order": {"order_id": "ord-123", "remaining_count_fp": "5"}},
            )
        )
        order = await orders.decrease("ord-123", reduce_by=5)
        assert order.remaining_count == Decimal("5")

    @respx.mock
    @pytest.mark.asyncio
    async def test_decrease_validation_error(self, orders: AsyncOrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123/decrease").mock(
            return_value=httpx.Response(400, json={"message": "invalid"})
        )
        with pytest.raises(KalshiValidationError):
            await orders.decrease("ord-123", reduce_by=-1)

    @pytest.mark.asyncio
    async def test_decrease_requires_reduce_arg(self, orders: AsyncOrdersResource) -> None:
        with pytest.raises(ValueError, match="requires either reduce_by or reduce_to"):
            await orders.decrease("ord-123")

    @pytest.mark.asyncio
    async def test_decrease_rejects_both_reduce_args(self, orders: AsyncOrdersResource) -> None:
        with pytest.raises(ValueError, match="not both"):
            await orders.decrease("ord-123", reduce_by=5, reduce_to=3)


class TestAsyncOrdersQueuePositions:
    @respx.mock
    @pytest.mark.asyncio
    async def test_queue_positions(self, orders: AsyncOrdersResource) -> None:
        from kalshi.models.orders import OrderQueuePosition
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/queue_positions").mock(
            return_value=httpx.Response(200, json={
                "queue_positions": [
                    {"order_id": "ord-1", "market_ticker": "MKT-A", "queue_position_fp": "42.00"},
                ],
            })
        )
        positions = await orders.queue_positions()
        assert len(positions) == 1
        assert isinstance(positions[0], OrderQueuePosition)

    @respx.mock
    @pytest.mark.asyncio
    async def test_queue_position_single(self, orders: AsyncOrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123/queue_position").mock(
            return_value=httpx.Response(200, json={"queue_position_fp": "15.00"})
        )
        position = await orders.queue_position("ord-123")
        assert position == Decimal("15.00")

    @respx.mock
    @pytest.mark.asyncio
    async def test_queue_position_missing_key_raises(self, orders: AsyncOrdersResource) -> None:
        from kalshi.errors import KalshiError

        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-999/queue_position"
        ).mock(return_value=httpx.Response(200, json={"unexpected_field": "value"}))
        with pytest.raises(KalshiError, match="missing 'queue_position_fp'"):
            await orders.queue_position("ord-999")


class TestAsyncOrdersAuthGuards:
    @pytest.mark.asyncio
    async def test_amend_requires_auth(self, unauth_orders_async: AsyncOrdersResource) -> None:
        from kalshi.errors import AuthRequiredError
        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.amend("ord-123", ticker="T", side="yes", action="buy")

    @pytest.mark.asyncio
    async def test_decrease_requires_auth(self, unauth_orders_async: AsyncOrdersResource) -> None:
        from kalshi.errors import AuthRequiredError
        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.decrease("ord-123", reduce_by=1)

    @pytest.mark.asyncio
    async def test_queue_positions_requires_auth(
        self, unauth_orders_async: AsyncOrdersResource,
    ) -> None:
        from kalshi.errors import AuthRequiredError
        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.queue_positions()

    @pytest.mark.asyncio
    async def test_queue_position_requires_auth(
        self, unauth_orders_async: AsyncOrdersResource,
    ) -> None:
        from kalshi.errors import AuthRequiredError
        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.queue_position("ord-123")
