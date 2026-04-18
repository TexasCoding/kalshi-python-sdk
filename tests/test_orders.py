"""Tests for kalshi.resources.orders — Orders resource."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
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


@pytest.fixture
def client(test_auth: KalshiAuth) -> KalshiClient:
    """KalshiClient wired to the demo base URL (matches wire-shape test mocks)."""
    from kalshi.config import DEMO_BASE_URL
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, timeout=5.0, max_retries=0)
    return KalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def unauth_orders(config: KalshiConfig) -> OrdersResource:
    return OrdersResource(SyncTransport(None, config))


_MINIMAL_ORDER = {
    "order_id": "ord-123",
    "ticker": "MKT",
    "side": "yes",
    "status": "resting",
}


class TestCreateOrderWireShape:
    """v0.8.0: orders.create() builds CreateOrderRequest internally and
    serializes via model_dump. Wire body must not contain phantom `type`
    field; count must serialize as count_fp; new fields reach the wire."""

    def test_no_phantom_type_in_wire(
        self, client: KalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        client.orders.create(ticker="MKT", side="yes", yes_price=0.5)

        body = json.loads(route.calls[0].request.content)
        assert "type" not in body

    def test_count_fp_not_count_in_wire(
        self, client: KalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        client.orders.create(ticker="MKT", side="yes", yes_price=0.5, count=3)

        body = json.loads(route.calls[0].request.content)
        assert "count_fp" in body
        assert body["count_fp"] == "3"
        assert "count" not in body

    def test_time_in_force_reaches_wire(
        self, client: KalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        client.orders.create(
            ticker="MKT", side="yes", yes_price=0.5,
            time_in_force="fill_or_kill",
        )

        body = json.loads(route.calls[0].request.content)
        assert body["time_in_force"] == "fill_or_kill"

    def test_post_only_reduce_only_reach_wire(
        self, client: KalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        client.orders.create(
            ticker="MKT", side="yes", yes_price=0.5,
            post_only=True, reduce_only=False,
        )

        body = json.loads(route.calls[0].request.content)
        assert body["post_only"] is True
        assert body["reduce_only"] is False

    def test_buy_max_cost_int_cents_wire(
        self, client: KalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        """Spec says cents. SDK must send int on the wire."""
        import json

        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        client.orders.create(ticker="MKT", side="yes", yes_price=0.5, buy_max_cost=500)

        body = json.loads(route.calls[0].request.content)
        assert body["buy_max_cost"] == 500
        assert isinstance(body["buy_max_cost"], int)

    def test_subaccount_order_group_cancel_on_pause_stp_wire(
        self, client: KalshiClient, respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.post(
            "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER}))

        client.orders.create(
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

    def test_type_kwarg_removed(self, client: KalshiClient) -> None:
        """v0.8.0 removed the `type` kwarg from orders.create()."""
        with pytest.raises(TypeError):
            client.orders.create(
                ticker="MKT", side="yes",
                type="market",  # type: ignore[call-arg]
            )


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
    def test_create_order_no_price(self, orders: OrdersResource) -> None:
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
        order = orders.create(ticker="TEST-MKT", side="yes")
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

    @respx.mock
    def test_cancel_with_subaccount(self, orders: OrdersResource) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-456"
        ).mock(return_value=httpx.Response(200, json={}))
        orders.cancel("ord-456", subaccount=42)
        params = dict(route.calls[0].request.url.params)
        assert params["subaccount"] == "42"


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

    @respx.mock
    def test_list_with_all_new_filters(self, orders: OrdersResource) -> None:
        """Consolidated coverage for v0.7.0 ADDs: event_ticker, min_ts, max_ts, subaccount."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        orders.list(
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
    def test_empty_string_ticker_passes_through(self, orders: OrdersResource) -> None:
        """Regression: pre-v0.7.0 the `if ticker:` truthiness check silently dropped
        empty strings. After _params() standardization, empty string reaches the wire."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        orders.list(ticker="")
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == ""

    @respx.mock
    def test_empty_string_status_passes_through(self, orders: OrdersResource) -> None:
        """Regression: same fix as ticker — empty string status now reaches wire."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        orders.list(status="")
        params = dict(route.calls[0].request.url.params)
        assert params["status"] == ""


class TestOrdersListAll:
    @respx.mock
    def test_list_all_with_all_new_filters(self, orders: OrdersResource) -> None:
        """v0.7.0 ADDs on list_all: event_ticker, min_ts, max_ts, subaccount."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(
                200,
                json={"orders": [{"order_id": "ord-x", "ticker": "MKT-A"}], "cursor": ""},
            )
        )
        list(
            orders.list_all(
                ticker="MKT-A",
                event_ticker="EVT-X",
                status="resting",
                min_ts=1700000000,
                max_ts=1700099999,
                limit=50,
                subaccount=7,
            )
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["status"] == "resting"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["subaccount"] == "7"


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

    @respx.mock
    def test_fills_with_all_new_filters(self, orders: OrdersResource) -> None:
        """Consolidated coverage for v0.7.0 ADDs: min_ts, max_ts, subaccount."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(200, json={"fills": []})
        )
        orders.fills(
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

    @respx.mock
    def test_fills_all_with_all_new_filters(self, orders: OrdersResource) -> None:
        """Consolidated coverage for v0.7.0 ADDs on fills_all: min_ts, max_ts, subaccount."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(
                200, json={"fills": [{"trade_id": "x", "yes_price_dollars": "0.5"}], "cursor": ""}
            )
        )
        list(
            orders.fills_all(
                ticker="MKT-A",
                order_id="ord-1",
                min_ts=1700000000,
                max_ts=1700099999,
                limit=50,
                subaccount=7,
            )
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["order_id"] == "ord-1"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["subaccount"] == "7"


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
            orders.amend("fake", ticker="T", side="yes", action="buy", yes_price=0.50)

    @respx.mock
    def test_amend_validation_error(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-300/amend"
        ).mock(return_value=httpx.Response(400, json={"message": "invalid side"}))
        with pytest.raises(KalshiValidationError):
            orders.amend("ord-300", ticker="T", side="invalid", action="buy", yes_price=0.50)

    def test_amend_requires_price_or_count(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match="requires at least one"):
            orders.amend("ord-123", ticker="T", side="yes", action="buy")


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

    def test_decrease_requires_reduce_arg(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match="requires either reduce_by or reduce_to"):
            orders.decrease("ord-123")

    def test_decrease_rejects_both_reduce_args(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match="not both"):
            orders.decrease("ord-123", reduce_by=5, reduce_to=3)


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
    def test_queue_positions_with_list_tickers(self, orders: OrdersResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/queue_positions"
        ).mock(
            return_value=httpx.Response(200, json={"queue_positions": []})
        )
        orders.queue_positions(market_tickers=["MKT-A", "MKT-B"])
        params = dict(route.calls[0].request.url.params)
        assert params["market_tickers"] == "MKT-A,MKT-B"

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
    def test_queue_position_fallback_key(self, orders: OrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-900/queue_position"
        ).mock(
            return_value=httpx.Response(
                200, json={"queue_position": "12"}
            )
        )
        pos = orders.queue_position("ord-900")
        assert pos == Decimal("12")

    @respx.mock
    def test_queue_position_missing_key_raises(self, orders: OrdersResource) -> None:
        from kalshi.errors import KalshiError

        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-999/queue_position"
        ).mock(return_value=httpx.Response(200, json={"unexpected_field": "value"}))
        with pytest.raises(KalshiError, match="missing 'queue_position_fp'"):
            orders.queue_position("ord-999")

    @respx.mock
    def test_queue_position_not_found(self, orders: OrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/queue_position"
        ).mock(return_value=httpx.Response(404, json={"message": "order not found"}))
        with pytest.raises(KalshiNotFoundError):
            orders.queue_position("fake")


class TestOrdersAuthGuards:
    def test_amend_requires_auth(self, unauth_orders: OrdersResource) -> None:
        from kalshi.errors import AuthRequiredError
        with pytest.raises(AuthRequiredError):
            unauth_orders.amend("ord-123", ticker="T", side="yes", action="buy")

    def test_decrease_requires_auth(self, unauth_orders: OrdersResource) -> None:
        from kalshi.errors import AuthRequiredError
        with pytest.raises(AuthRequiredError):
            unauth_orders.decrease("ord-123", reduce_by=1)

    def test_queue_positions_requires_auth(self, unauth_orders: OrdersResource) -> None:
        from kalshi.errors import AuthRequiredError
        with pytest.raises(AuthRequiredError):
            unauth_orders.queue_positions()

    def test_queue_position_requires_auth(self, unauth_orders: OrdersResource) -> None:
        from kalshi.errors import AuthRequiredError
        with pytest.raises(AuthRequiredError):
            unauth_orders.queue_position("ord-123")


class TestBatchCancelWireShape:
    @respx.mock
    def test_wraps_str_ids_into_orders(
        self, orders: OrdersResource
    ) -> None:
        import json

        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/batched"
        ).mock(return_value=httpx.Response(200, json={}))

        orders.batch_cancel(["ord-1", "ord-2"])

        body = json.loads(route.calls[0].request.content)
        assert "ids" not in body  # deprecated field no longer used
        assert "orders" in body
        assert body["orders"] == [
            {"order_id": "ord-1"},
            {"order_id": "ord-2"},
        ]

    @respx.mock
    def test_accepts_typed_order_entries(
        self, orders: OrdersResource
    ) -> None:
        import json

        from kalshi.models.orders import BatchCancelOrdersRequestOrder

        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/batched"
        ).mock(return_value=httpx.Response(200, json={}))

        orders.batch_cancel([
            BatchCancelOrdersRequestOrder(order_id="ord-1", subaccount=5),
            BatchCancelOrdersRequestOrder(order_id="ord-2"),
        ])

        body = json.loads(route.calls[0].request.content)
        assert body["orders"] == [
            {"order_id": "ord-1", "subaccount": 5},
            {"order_id": "ord-2"},
        ]


class TestAmendWireShape:
    """v0.8.0: orders.amend() builds AmendOrderRequest internally and
    serializes via model_dump. Price fields must use _dollars suffix;
    count must use count_fp alias; phantom keys must be absent."""

    @respx.mock
    def test_price_serializes_dollars_alias(self, orders: OrdersResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-99/amend"
        ).mock(return_value=httpx.Response(200, json={
            "old_order": {"order_id": "ord-99", "ticker": "MKT"},
            "order": {"order_id": "ord-99", "ticker": "MKT"},
        }))

        orders.amend(
            "ord-99",
            ticker="MKT",
            side="yes",
            action="buy",
            yes_price="0.55",
        )

        body = json.loads(route.calls[0].request.content)
        assert body["yes_price_dollars"] == "0.55"
        assert "yes_price" not in body

    @respx.mock
    def test_count_serializes_fp_alias(self, orders: OrdersResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-99/amend"
        ).mock(return_value=httpx.Response(200, json={
            "old_order": {"order_id": "ord-99", "ticker": "MKT"},
            "order": {"order_id": "ord-99", "ticker": "MKT"},
        }))

        orders.amend(
            "ord-99",
            ticker="MKT",
            side="yes",
            action="buy",
            count=3,
        )

        body = json.loads(route.calls[0].request.content)
        assert body["count_fp"] == "3"
        assert "count" not in body

    @respx.mock
    def test_required_and_optional_fields(self, orders: OrdersResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-99/amend"
        ).mock(return_value=httpx.Response(200, json={
            "old_order": {"order_id": "ord-99", "ticker": "MKT"},
            "order": {"order_id": "ord-99", "ticker": "MKT"},
        }))

        orders.amend(
            "ord-99",
            ticker="MKT",
            side="yes",
            action="buy",
            yes_price="0.55",
            count=3,
            subaccount=2,
            client_order_id="c-old",
            updated_client_order_id="c-new",
        )

        body = json.loads(route.calls[0].request.content)
        assert body["ticker"] == "MKT"
        assert body["side"] == "yes"
        assert body["action"] == "buy"
        assert body["yes_price_dollars"] == "0.55"
        assert body["count_fp"] == "3"
        assert body["subaccount"] == 2
        assert body["client_order_id"] == "c-old"
        assert body["updated_client_order_id"] == "c-new"
        # no phantom keys
        assert "yes_price" not in body
        assert "no_price" not in body
        assert "count" not in body

    @respx.mock
    def test_no_price_absent_when_not_passed(self, orders: OrdersResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-99/amend"
        ).mock(return_value=httpx.Response(200, json={
            "old_order": {"order_id": "ord-99", "ticker": "MKT"},
            "order": {"order_id": "ord-99", "ticker": "MKT"},
        }))

        orders.amend(
            "ord-99",
            ticker="MKT",
            side="no",
            action="buy",
            no_price="0.45",
        )

        body = json.loads(route.calls[0].request.content)
        assert body["no_price_dollars"] == "0.45"
        assert "no_price" not in body
        assert "yes_price_dollars" not in body
        assert "count_fp" not in body


class TestDecreaseWireShape:
    """v0.8.0: orders.decrease() builds DecreaseOrderRequest internally."""

    @respx.mock
    def test_reduce_by_body(self, orders: OrdersResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-99/decrease"
        ).mock(return_value=httpx.Response(200, json={
            "order": {"order_id": "ord-99", "ticker": "MKT", "side": "yes", "status": "resting"},
        }))

        orders.decrease("ord-99", reduce_by=5, subaccount=1)

        body = json.loads(route.calls[0].request.content)
        assert body == {"reduce_by": 5, "subaccount": 1}

    @respx.mock
    def test_reduce_to_body(self, orders: OrdersResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-99/decrease"
        ).mock(return_value=httpx.Response(200, json={
            "order": {"order_id": "ord-99", "ticker": "MKT", "side": "yes", "status": "resting"},
        }))

        orders.decrease("ord-99", reduce_to=2)

        body = json.loads(route.calls[0].request.content)
        assert body == {"reduce_to": 2}


class TestBatchCreateWireShape:
    """v0.8.0: orders.batch_create() wraps via BatchCreateOrdersRequest."""

    @respx.mock
    def test_wraps_orders_key(self, orders: OrdersResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/batched"
        ).mock(return_value=httpx.Response(200, json={"orders": []}))

        orders.batch_create([
            CreateOrderRequest(ticker="A", side="yes"),
            CreateOrderRequest(ticker="B", side="no"),
        ])

        body = json.loads(route.calls[0].request.content)
        assert "orders" in body
        assert len(body["orders"]) == 2
        # no phantom top-level keys
        assert set(body.keys()) == {"orders"}
