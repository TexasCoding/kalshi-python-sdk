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
from kalshi.models.orders import CreateOrderRequest
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
