"""Tests for async orders resource — mirrors test_orders.py."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport
from kalshi.async_client import AsyncKalshiClient
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


@pytest.fixture
def client(test_auth: KalshiAuth) -> AsyncKalshiClient:
    """AsyncKalshiClient wired to the demo base URL (matches wire-shape test mocks)."""
    from kalshi.config import DEMO_BASE_URL
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, timeout=5.0, max_retries=0)
    return AsyncKalshiClient(auth=test_auth, config=cfg)


_MINIMAL_ORDER = {
    "order_id": "ord-123",
    "ticker": "MKT",
    "side": "yes",
    "status": "resting",
}


class TestCreateOrderWireShapeAsync:
    """v0.8.0: async orders.create() builds CreateOrderRequest internally and
    serializes via model_dump. Wire body must not contain phantom `type`
    field; count must serialize as count_fp; new fields reach the wire."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_phantom_type_in_wire(
        self, client: AsyncKalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        await client.orders.create(ticker="MKT", side="yes", yes_price=0.5)

        body = json.loads(route.calls[0].request.content)
        assert "type" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_count_fp_not_count_in_wire(
        self, client: AsyncKalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        await client.orders.create(ticker="MKT", side="yes", yes_price=0.5, count=3)

        body = json.loads(route.calls[0].request.content)
        assert "count_fp" in body
        assert body["count_fp"] == "3"
        assert "count" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_time_in_force_reaches_wire(
        self, client: AsyncKalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        await client.orders.create(
            ticker="MKT", side="yes", yes_price=0.5,
            time_in_force="fill_or_kill",
        )

        body = json.loads(route.calls[0].request.content)
        assert body["time_in_force"] == "fill_or_kill"

    @respx.mock
    @pytest.mark.asyncio
    async def test_post_only_reduce_only_reach_wire(
        self, client: AsyncKalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        await client.orders.create(
            ticker="MKT", side="yes", yes_price=0.5,
            post_only=True, reduce_only=False,
        )

        body = json.loads(route.calls[0].request.content)
        assert body["post_only"] is True
        assert body["reduce_only"] is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_buy_max_cost_int_cents_wire(
        self, client: AsyncKalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        """Spec says cents. SDK must send int on the wire."""
        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        await client.orders.create(
            ticker="MKT", side="yes", yes_price=0.5, buy_max_cost=500,
        )

        body = json.loads(route.calls[0].request.content)
        assert body["buy_max_cost"] == 500
        assert isinstance(body["buy_max_cost"], int)

    @respx.mock
    @pytest.mark.asyncio
    async def test_subaccount_order_group_cancel_on_pause_stp_wire(
        self, client: AsyncKalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        await client.orders.create(
            ticker="MKT", side="yes", yes_price=0.5,
            subaccount=2, order_group_id="grp-x",
            cancel_order_on_pause=True,
            self_trade_prevention_type="maker",
        )

        body = json.loads(route.calls[0].request.content)
        assert body["subaccount"] == 2
        assert body["order_group_id"] == "grp-x"
        assert body["cancel_order_on_pause"] is True
        assert body["self_trade_prevention_type"] == "maker"

    @pytest.mark.asyncio
    async def test_type_kwarg_removed(self, client: AsyncKalshiClient) -> None:
        """v0.8.0 removed the `type` kwarg from orders.create()."""
        with pytest.raises(TypeError):
            await client.orders.create(
                ticker="MKT", side="yes",
                type="market",  # type: ignore[call-arg]
            )


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
    async def test_create_order_no_price(
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
        order = await orders.create(ticker="TEST-MKT", side="yes")
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

    @respx.mock
    @pytest.mark.asyncio
    async def test_cancel_with_subaccount(
        self, orders: AsyncOrdersResource
    ) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-456"
        ).mock(return_value=httpx.Response(200, json={}))
        await orders.cancel("ord-456", subaccount=42)
        params = dict(route.calls[0].request.url.params)
        assert params["subaccount"] == "42"


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

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_with_all_new_filters(
        self, orders: AsyncOrdersResource
    ) -> None:
        """Consolidated coverage for v0.7.0 ADDs: event_ticker, min_ts, max_ts, subaccount."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"orders": []}))
        await orders.list(
            ticker="MKT-A",
            event_ticker="EVT-X",
            status="resting",
            min_ts=1700000000,
            max_ts=1700099999,
            limit=50,
            cursor="abc",
            subaccount=7,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["status"] == "resting"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["subaccount"] == "7"

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_string_ticker_passes_through(
        self, orders: AsyncOrdersResource
    ) -> None:
        """Regression: empty-string ticker reaches the wire after _params() standardization."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"orders": []}))
        await orders.list(ticker="")
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == ""

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_string_status_passes_through(
        self, orders: AsyncOrdersResource
    ) -> None:
        """Regression: same fix as ticker — empty string status now reaches wire."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"orders": []}))
        await orders.list(status="")
        params = dict(route.calls[0].request.url.params)
        assert params["status"] == ""


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

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_all_with_all_new_filters(
        self, orders: AsyncOrdersResource
    ) -> None:
        """v0.7.0 ADDs on list_all: event_ticker, min_ts, max_ts, subaccount."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"orders": [{"order_id": "ord-x", "ticker": "MKT-A"}], "cursor": ""},
            )
        )
        _ = [o async for o in orders.list_all(
            ticker="MKT-A",
            event_ticker="EVT-X",
            status="resting",
            min_ts=1700000000,
            max_ts=1700099999,
            limit=50,
            subaccount=7,
        )]
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["status"] == "resting"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["subaccount"] == "7"


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

    @respx.mock
    @pytest.mark.asyncio
    async def test_fills_with_all_new_filters(
        self, orders: AsyncOrdersResource
    ) -> None:
        """Consolidated coverage for v0.7.0 ADDs: min_ts, max_ts, subaccount."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/fills"
        ).mock(return_value=httpx.Response(200, json={"fills": []}))
        await orders.fills(
            ticker="MKT-A",
            order_id="ord-1",
            min_ts=1700000000,
            max_ts=1700099999,
            limit=50,
            cursor="abc",
            subaccount=7,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["order_id"] == "ord-1"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["subaccount"] == "7"


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

    @respx.mock
    @pytest.mark.asyncio
    async def test_fills_all_with_all_new_filters(
        self, orders: AsyncOrdersResource
    ) -> None:
        """Consolidated coverage for v0.7.0 ADDs on fills_all: min_ts, max_ts, subaccount."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/fills"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"fills": [{"trade_id": "x", "yes_price_dollars": "0.5"}], "cursor": ""},
            )
        )
        _ = [f async for f in orders.fills_all(
            ticker="MKT-A",
            order_id="ord-1",
            min_ts=1700000000,
            max_ts=1700099999,
            limit=50,
            subaccount=7,
        )]
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["order_id"] == "ord-1"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["subaccount"] == "7"


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

    @respx.mock
    @pytest.mark.asyncio
    async def test_amend_serializes_dollars_and_count(self, orders: AsyncOrdersResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123/amend"
        ).mock(
            return_value=httpx.Response(200, json={
                "old_order": {"order_id": "ord-123", "ticker": "T"},
                "order": {"order_id": "ord-123", "ticker": "T"},
            })
        )
        await orders.amend(
            "ord-123", ticker="T", side="yes", action="buy", yes_price=0.55, count=20
        )
        body = json.loads(route.calls[0].request.content)
        assert body["yes_price_dollars"] == "0.55"
        assert body["count_fp"] == "20"
        assert "yes_price" not in body
        assert "count" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_amend_validation_error(self, orders: AsyncOrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123/amend"
        ).mock(return_value=httpx.Response(400, json={"message": "invalid"}))
        with pytest.raises(KalshiValidationError):
            await orders.amend("ord-123", ticker="T", side="bad", action="buy", yes_price=0.50)

    @pytest.mark.asyncio
    async def test_amend_requires_price_or_count(self, orders: AsyncOrdersResource) -> None:
        with pytest.raises(ValueError, match="requires at least one"):
            await orders.amend("ord-123", ticker="T", side="yes", action="buy")


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

    @respx.mock
    @pytest.mark.asyncio
    async def test_decrease_to(self, orders: AsyncOrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123/decrease"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"order": {"order_id": "ord-123", "remaining_count_fp": "0"}},
            )
        )
        order = await orders.decrease("ord-123", reduce_to=0)
        assert order.remaining_count == Decimal("0")

    @respx.mock
    @pytest.mark.asyncio
    async def test_decrease_not_found(self, orders: AsyncOrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/decrease"
        ).mock(return_value=httpx.Response(404, json={"message": "not found"}))
        with pytest.raises(KalshiNotFoundError):
            await orders.decrease("fake", reduce_by=1)

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
    async def test_queue_positions_with_list_tickers(self, orders: AsyncOrdersResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/queue_positions"
        ).mock(return_value=httpx.Response(200, json={"queue_positions": []}))
        await orders.queue_positions(market_tickers=["MKT-A", "MKT-B"])
        params = dict(route.calls[0].request.url.params)
        assert params["market_tickers"] == "MKT-A,MKT-B"

    @respx.mock
    @pytest.mark.asyncio
    async def test_queue_position_fallback_key(self, orders: AsyncOrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-900/queue_position"
        ).mock(return_value=httpx.Response(200, json={"queue_position": "12"}))
        pos = await orders.queue_position("ord-900")
        assert pos == Decimal("12")

    @respx.mock
    @pytest.mark.asyncio
    async def test_queue_position_not_found(self, orders: AsyncOrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/queue_position"
        ).mock(return_value=httpx.Response(404, json={"message": "not found"}))
        with pytest.raises(KalshiNotFoundError):
            await orders.queue_position("fake")

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


class TestBatchCancelWireShapeAsync:
    @respx.mock
    @pytest.mark.asyncio
    async def test_wraps_str_ids_into_orders(
        self, orders: AsyncOrdersResource
    ) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/batched"
        ).mock(return_value=httpx.Response(200, json={}))

        await orders.batch_cancel(["ord-1", "ord-2"])

        body = json.loads(route.calls[0].request.content)
        assert "ids" not in body  # deprecated field no longer used
        assert "orders" in body
        assert body["orders"] == [
            {"order_id": "ord-1"},
            {"order_id": "ord-2"},
        ]

    @respx.mock
    @pytest.mark.asyncio
    async def test_accepts_typed_order_entries(
        self, orders: AsyncOrdersResource
    ) -> None:
        from kalshi.models.orders import BatchCancelOrdersRequestOrder

        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/batched"
        ).mock(return_value=httpx.Response(200, json={}))

        await orders.batch_cancel([
            BatchCancelOrdersRequestOrder(order_id="ord-1", subaccount=5),
            BatchCancelOrdersRequestOrder(order_id="ord-2"),
        ])

        body = json.loads(route.calls[0].request.content)
        assert body["orders"] == [
            {"order_id": "ord-1", "subaccount": 5},
            {"order_id": "ord-2"},
        ]
