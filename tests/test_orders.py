"""Tests for kalshi.resources.orders — Orders resource."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import KalshiConfig
from kalshi.errors import (
    AuthRequiredError,
    KalshiError,
    KalshiNotFoundError,
    KalshiValidationError,
)
from kalshi.models.orders import (
    AmendOrderV2Request,
    BatchCancelOrdersV2Request,
    BatchCancelOrdersV2RequestOrder,
    BatchCreateOrdersV2Request,
    CreateOrderRequest,
    CreateOrderV2Request,
    DecreaseOrderV2Request,
)
from kalshi.resources.orders import OrdersResource
from tests._model_fixtures import fill_dict, order_dict


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
    from kalshi.config import DEMO_BASE_URL, DEMO_WS_URL

    cfg = KalshiConfig(base_url=DEMO_BASE_URL, ws_base_url=DEMO_WS_URL, timeout=5.0, max_retries=0)
    return KalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def unauth_orders(config: KalshiConfig) -> OrdersResource:
    return OrdersResource(SyncTransport(None, config))


_MINIMAL_ORDER = order_dict(order_id="ord-123", ticker="MKT", side="yes", status="resting")


class TestCreateOrderWireShape:
    """v0.8.0: orders.create() builds CreateOrderRequest internally and
    serializes via model_dump. Wire body must not contain phantom `type`
    field; count must serialize as count_fp; new fields reach the wire."""

    def test_no_phantom_type_in_wire(
        self,
        client: KalshiClient,
        respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.post("https://demo-api.kalshi.co/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER})
        )

        client.orders.create(ticker="MKT", side="yes", action="buy", count=1, yes_price=0.5)

        body = json.loads(route.calls[0].request.content)
        assert "type" not in body

    def test_count_fp_not_count_in_wire(
        self,
        client: KalshiClient,
        respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.post("https://demo-api.kalshi.co/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER})
        )

        client.orders.create(ticker="MKT", side="yes", action="buy", yes_price=0.5, count=3)

        body = json.loads(route.calls[0].request.content)
        assert "count_fp" in body
        assert body["count_fp"] == "3"
        assert "count" not in body

    def test_time_in_force_reaches_wire(
        self,
        client: KalshiClient,
        respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.post("https://demo-api.kalshi.co/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER})
        )

        client.orders.create(
            ticker="MKT",
            side="yes",
            action="buy",
            count=1,
            yes_price=0.5,
            time_in_force="fill_or_kill",
        )

        body = json.loads(route.calls[0].request.content)
        assert body["time_in_force"] == "fill_or_kill"

    def test_post_only_reduce_only_reach_wire(
        self,
        client: KalshiClient,
        respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.post("https://demo-api.kalshi.co/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER})
        )

        client.orders.create(
            ticker="MKT",
            side="yes",
            action="buy",
            count=1,
            yes_price=0.5,
            post_only=True,
            reduce_only=False,
        )

        body = json.loads(route.calls[0].request.content)
        assert body["post_only"] is True
        assert body["reduce_only"] is False

    def test_buy_max_cost_int_cents_wire(
        self,
        client: KalshiClient,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Spec says cents. SDK must send int on the wire."""
        import json

        route = respx_mock.post("https://demo-api.kalshi.co/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER})
        )

        client.orders.create(
            ticker="MKT", side="yes", action="buy", count=1, yes_price=0.5, buy_max_cost=500
        )

        body = json.loads(route.calls[0].request.content)
        assert body["buy_max_cost"] == 500
        assert isinstance(body["buy_max_cost"], int)

    def test_subaccount_order_group_cancel_on_pause_stp_wire(
        self,
        client: KalshiClient,
        respx_mock: respx.MockRouter,
    ) -> None:
        import json

        route = respx_mock.post("https://demo-api.kalshi.co/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER})
        )

        client.orders.create(
            ticker="MKT",
            side="yes",
            action="buy",
            count=1,
            yes_price=0.5,
            subaccount=2,
            order_group_id="grp-x",
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
                ticker="MKT",
                side="yes",
                type="market",  # type: ignore[call-arg]
            )

    def test_missing_count_and_action_raises_before_http(
        self,
        client: KalshiClient,
        respx_mock: respx.MockRouter,
    ) -> None:
        """#242: kwarg-form create() with missing ``count`` / ``action`` must raise
        ``TypeError`` BEFORE any HTTP request is dispatched. Pre-#242 the SDK
        silently defaulted to count=1, action="buy" — converting a missing-arg
        bug into a real 1-contract BUY fill (money risk)."""
        route = respx_mock.post("https://demo-api.kalshi.co/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER})
        )

        with pytest.raises(TypeError, match=r"count.*action"):
            client.orders.create(ticker="X", side="yes")
        with pytest.raises(TypeError, match=r"count.*action"):
            client.orders.create(ticker="X", side="yes", action="buy")
        with pytest.raises(TypeError, match=r"count.*action"):
            client.orders.create(ticker="X", side="yes", count=10)

        assert route.call_count == 0

    def test_explicit_count_action_kwargs_still_work(
        self,
        client: KalshiClient,
        respx_mock: respx.MockRouter,
    ) -> None:
        """#242: regression — explicit ``count`` + ``action`` kwargs still build
        and dispatch normally."""
        route = respx_mock.post("https://demo-api.kalshi.co/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER})
        )

        client.orders.create(ticker="X", side="yes", count=10, action="buy", yes_price="0.5")

        assert route.call_count == 1
        body = json.loads(route.calls[0].request.content)
        assert body["count_fp"] == "10"
        assert body["action"] == "buy"
        assert body["yes_price_dollars"] == "0.5"

    def test_request_overload_unaffected_by_242(
        self,
        client: KalshiClient,
        respx_mock: respx.MockRouter,
    ) -> None:
        """#242: the ``request=CreateOrderRequest(...)`` path is unaffected by
        the kwarg-overload guard — the model itself now declares count/action
        required, so a fully-populated request still dispatches."""
        route = respx_mock.post("https://demo-api.kalshi.co/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _MINIMAL_ORDER})
        )

        client.orders.create(
            request=CreateOrderRequest(
                ticker="X",
                side="yes",
                count=Decimal("10"),
                action="buy",
                yes_price=Decimal("0.5"),
            )
        )

        assert route.call_count == 1
        body = json.loads(route.calls[0].request.content)
        assert body["count_fp"] == "10"
        assert body["action"] == "buy"


class TestOrdersCreate:
    @respx.mock
    def test_create_limit_order(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": order_dict(
                        order_id="ord-123",
                        ticker="TEST-MKT",
                        side="yes",
                        status="resting",
                        yes_price_dollars="0.6500",
                        count_fp="10",
                    )
                },
            )
        )
        order = orders.create(ticker="TEST-MKT", side="yes", action="buy", count=10, yes_price=0.65)
        assert order.order_id == "ord-123"
        assert order.yes_price == Decimal("0.6500")
        assert order.count == 10

    @respx.mock
    def test_create_order_no_price(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": order_dict(order_id="ord-456", ticker="TEST-MKT", status="executed")
                },
            )
        )
        order = orders.create(ticker="TEST-MKT", side="yes", action="buy", count=1)
        assert order.order_id == "ord-456"

    @respx.mock
    def test_decimal_price_conversion(self, orders: OrdersResource) -> None:
        route = respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(
                200, json={"order": order_dict(order_id="ord-789", ticker="T")}
            )
        )
        orders.create(ticker="T", side="yes", action="buy", count=1, yes_price=0.65)

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
            orders.create(ticker="INVALID", side="yes", action="buy", count=1)


class TestOrdersGet:
    @respx.mock
    def test_returns_order(self, orders: OrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123").mock(
            return_value=httpx.Response(
                200,
                json={"order": order_dict(order_id="ord-123", ticker="MKT", status="resting")},
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
        route = respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-456").mock(
            return_value=httpx.Response(200, json={})
        )
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
                        order_dict(order_id="ord-1", ticker="A"),
                        order_dict(order_id="ord-2", ticker="B"),
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
    def test_list_accepts_event_ticker_list(self, orders: OrdersResource) -> None:
        """Spec MultipleEventTickerQuery: comma-joined, server caps at 10."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        orders.list(event_ticker=["EVT-A", "EVT-B", "EVT-C"])
        params = dict(route.calls[0].request.url.params)
        # Asserts wire is ?event_ticker=A,B,C (NOT explode:true).
        assert params["event_ticker"] == "EVT-A,EVT-B,EVT-C"

    def test_list_rejects_event_ticker_list_over_spec_max(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match=r"too many tickers: 11 > spec max 10"):
            orders.list(event_ticker=[f"E-{i}" for i in range(11)])

    def test_list_all_rejects_event_ticker_list_over_spec_max(self, orders: OrdersResource) -> None:
        # Eager validation — must fire at call time, not on iteration.
        with pytest.raises(ValueError, match=r"too many tickers"):
            orders.list_all(event_ticker=[f"E-{i}" for i in range(11)])

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
                json={"orders": [order_dict(order_id="ord-x", ticker="MKT-A")], "cursor": ""},
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
                        {
                            "order": order_dict(order_id="b1", ticker="A"),
                            "error": None,
                            "client_order_id": "c1",
                        },
                        {
                            "order": order_dict(order_id="b2", ticker="B"),
                            "error": None,
                            "client_order_id": "c2",
                        },
                    ]
                },
            )
        )
        reqs = [
            CreateOrderRequest(ticker="A", side="yes", action="buy", count=1),
            CreateOrderRequest(ticker="B", side="no", action="buy", count=1),
        ]
        from kalshi.models.orders import BatchCreateOrdersResponse

        result = orders.batch_create(reqs)
        assert isinstance(result, BatchCreateOrdersResponse)
        assert len(result.orders) == 2
        assert result.orders[0].order is not None
        assert result.orders[0].order.order_id == "b1"
        assert result.orders[0].client_order_id == "c1"

    @respx.mock
    def test_batch_create_partial_failure_does_not_crash(self, orders: OrdersResource) -> None:
        """#194: a failed leg returns ``{"order": null, "error": {...}}``.

        The old SDK called ``Order.model_validate(None)`` and tore down the
        whole result; the typed envelope must preserve the per-leg shape.
        """
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orders": [
                        {
                            "order": order_dict(order_id="ok", ticker="A"),
                            "error": None,
                            "client_order_id": "good",
                        },
                        {
                            "order": None,
                            "error": {"code": "bad_price", "message": "rejected"},
                            "client_order_id": "bad",
                        },
                    ]
                },
            )
        )
        result = orders.batch_create(
            [CreateOrderRequest(ticker="A", side="yes", action="buy", count=1)]
        )
        assert len(result.orders) == 2
        assert result.orders[0].order is not None
        assert result.orders[0].error is None
        assert result.orders[1].order is None
        assert result.orders[1].error is not None
        assert result.orders[1].error["code"] == "bad_price"
        assert result.orders[1].client_order_id == "bad"


class TestOrdersFills:
    @respx.mock
    def test_returns_fills(self, orders: OrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fills": [
                        fill_dict(
                            trade_id="t1", order_id="o1", yes_price_dollars="0.5000", count_fp="5"
                        )
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
                        "fills": [fill_dict(trade_id="a", yes_price_dollars="0.50")],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "fills": [fill_dict(trade_id="b", yes_price_dollars="0.60")],
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
                200,
                json={"fills": [fill_dict(trade_id="x", yes_price_dollars="0.5")], "cursor": ""},
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
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-100/amend").mock(
            return_value=httpx.Response(
                200,
                json={
                    "old_order": order_dict(
                        order_id="ord-100",
                        ticker="MKT-A",
                        side="yes",
                        status="resting",
                        yes_price_dollars="0.5000",
                        count_fp="10",
                    ),
                    "order": order_dict(
                        order_id="ord-100",
                        ticker="MKT-A",
                        side="yes",
                        status="resting",
                        yes_price_dollars="0.6000",
                        count_fp="10",
                    ),
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
                    "old_order": order_dict(order_id="ord-200", ticker="T"),
                    "order": order_dict(order_id="ord-200", ticker="T"),
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
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/amend").mock(
            return_value=httpx.Response(404, json={"message": "order not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            orders.amend("fake", ticker="T", side="yes", action="buy", yes_price=0.50)

    @respx.mock
    def test_amend_validation_error(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-300/amend").mock(
            return_value=httpx.Response(400, json={"message": "invalid side"})
        )
        with pytest.raises(KalshiValidationError):
            orders.amend("ord-300", ticker="T", side="invalid", action="buy", yes_price=0.50)

    def test_amend_requires_price_or_count(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match="requires at least one"):
            orders.amend("ord-123", ticker="T", side="yes", action="buy")


class TestOrdersDecrease:
    @respx.mock
    def test_decrease_by(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-400/decrease").mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": order_dict(
                        order_id="ord-400", ticker="MKT-B", status="resting", remaining_count_fp="5"
                    )
                },
            )
        )
        order = orders.decrease("ord-400", reduce_by=5)
        assert order.order_id == "ord-400"
        assert order.remaining_count == Decimal("5")

    @respx.mock
    def test_decrease_to(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-500/decrease").mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": order_dict(
                        order_id="ord-500",
                        ticker="MKT-C",
                        status="cancelled",
                        remaining_count_fp="0",
                    )
                },
            )
        )
        order = orders.decrease("ord-500", reduce_to=0)
        assert order.order_id == "ord-500"
        assert order.remaining_count == Decimal("0")

    @respx.mock
    def test_decrease_not_found(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/decrease").mock(
            return_value=httpx.Response(404, json={"message": "order not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            orders.decrease("fake", reduce_by=1)

    @respx.mock
    def test_decrease_validation_error(self, orders: OrdersResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-600/decrease").mock(
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
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/queue_positions").mock(
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
        ).mock(return_value=httpx.Response(200, json={"queue_positions": []}))
        orders.queue_positions(event_ticker="EVT-1")
        params = dict(route.calls[0].request.url.params)
        assert params["event_ticker"] == "EVT-1"

    @respx.mock
    def test_queue_positions_empty(self, orders: OrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/queue_positions").mock(
            return_value=httpx.Response(200, json={"queue_positions": []})
        )
        positions = orders.queue_positions()
        assert positions == []

    @respx.mock
    def test_queue_positions_with_list_tickers(self, orders: OrdersResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/queue_positions"
        ).mock(return_value=httpx.Response(200, json={"queue_positions": []}))
        orders.queue_positions(market_tickers=["MKT-A", "MKT-B"])
        params = dict(route.calls[0].request.url.params)
        assert params["market_tickers"] == "MKT-A,MKT-B"

    @respx.mock
    def test_queue_position_single(self, orders: OrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-800/queue_position"
        ).mock(return_value=httpx.Response(200, json={"queue_position_fp": "5"}))
        pos = orders.queue_position("ord-800")
        assert pos == Decimal("5")

    @respx.mock
    def test_queue_position_fallback_key(self, orders: OrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-900/queue_position"
        ).mock(return_value=httpx.Response(200, json={"queue_position": "12"}))
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
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/queue_position").mock(
            return_value=httpx.Response(404, json={"message": "order not found"})
        )
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
    def test_wraps_str_ids_into_orders(self, orders: OrdersResource) -> None:
        import json

        route = respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )

        orders.batch_cancel(["ord-1", "ord-2"])

        body = json.loads(route.calls[0].request.content)
        assert "ids" not in body  # deprecated field no longer used
        assert body["orders"] == [
            {"order_id": "ord-1"},
            {"order_id": "ord-2"},
        ]

    @respx.mock
    def test_accepts_typed_order_entries(self, orders: OrdersResource) -> None:
        import json

        from kalshi.models.orders import BatchCancelOrdersRequestOrder

        route = respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )

        orders.batch_cancel(
            [
                BatchCancelOrdersRequestOrder(order_id="ord-1", subaccount=5),
                BatchCancelOrdersRequestOrder(order_id="ord-2"),
            ]
        )

        body = json.loads(route.calls[0].request.content)
        assert body["orders"] == [
            {"order_id": "ord-1", "subaccount": 5},
            {"order_id": "ord-2"},
        ]


class TestBatchCancelRoutesThroughDeleteWithBodyJson:
    """Regression for issue #47 / #223: sync batch_cancel must route through
    the shared ``SyncResource._delete_with_body_json`` bytes helper so retry /
    error-mapping behavior added to the helper applies to the sync path.
    Symmetric with
    ``test_async_orders.py::TestAsyncBatchCancelRoutesThroughDeleteWithBodyJson``.
    """

    @respx.mock
    def test_batch_cancel_uses_delete_with_body_json_helper(
        self,
        orders: OrdersResource,
    ) -> None:
        respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )

        # patch.object + wraps forwards every call to the real method,
        # so the respx mock above still resolves; the spy only records.
        with patch.object(
            orders,
            "_delete_with_body_json",
            wraps=orders._delete_with_body_json,
        ) as spy:
            orders.batch_cancel(["ord-1", "ord-2"])
            spy.assert_called_once()
            args, kwargs = spy.call_args
            assert args == ("/portfolio/orders/batched",)
            # Bytes path: caller passes pre-serialized JSON via ``content=``,
            # NOT a dict via ``json=`` (P4.2).
            assert "json" not in kwargs
            assert isinstance(kwargs["content"], bytes)
            assert json.loads(kwargs["content"]) == {
                "orders": [{"order_id": "ord-1"}, {"order_id": "ord-2"}]
            }

    @respx.mock
    def test_batch_cancel_returns_typed_response_with_reduced_by_fp(
        self, orders: OrdersResource
    ) -> None:
        """#194: response carries per-leg ``reduced_by_fp`` (Decimal,
        load-bearing for risk reconciliation). Previous SDK discarded it.
        """
        respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orders": [
                        {
                            "order_id": "ord-1",
                            "reduced_by_fp": "3",
                            "order": None,
                            "error": None,
                        },
                    ]
                },
            )
        )
        from kalshi.models.orders import BatchCancelOrdersResponse

        result = orders.batch_cancel(["ord-1"])
        assert isinstance(result, BatchCancelOrdersResponse)
        assert len(result.orders) == 1
        assert result.orders[0].order_id == "ord-1"
        assert result.orders[0].reduced_by_fp == Decimal("3")
        assert result.orders[0].error is None

    @respx.mock
    def test_batch_cancel_per_entry_error_surfaced(self, orders: OrdersResource) -> None:
        """#194: per-leg ``error`` is preserved; ``reduced_by_fp`` is ``0``
        when the leg failed.
        """
        respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orders": [
                        {
                            "order_id": "ord-bad",
                            "reduced_by_fp": "0",
                            "order": None,
                            "error": {"code": "not_found", "message": "gone"},
                        },
                    ]
                },
            )
        )
        result = orders.batch_cancel(["ord-bad"])
        assert result.orders[0].reduced_by_fp == Decimal("0")
        assert result.orders[0].error is not None
        assert result.orders[0].error["code"] == "not_found"

    @respx.mock
    def test_batch_cancel_raises_on_204_no_content(self, orders: OrdersResource) -> None:
        """v3.0.0: typed response required — 204 indicates spec drift."""
        respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(204)
        )
        with pytest.raises(KalshiError, match="Expected BatchCancelOrdersResponse"):
            orders.batch_cancel(["ord-1"])

    @respx.mock
    def test_batch_cancel_200_with_empty_body_raises(self, orders: OrdersResource) -> None:
        """Documents an intentional behavior change: the old local helper
        discarded the response, so a hypothetical 200 with an empty body
        would have been silent. The new shared helper parses JSON on
        non-204, so the same case now surfaces as a JSONDecodeError.
        Kalshi's spec returns either 200-with-JSON or 204; this test
        pins the new failure mode rather than letting it regress silently.
        """
        import json as _json

        respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(200)
        )

        with pytest.raises(_json.JSONDecodeError):
            orders.batch_cancel(["ord-1"])


class TestAmendWireShape:
    """v0.8.0: orders.amend() builds AmendOrderRequest internally and
    serializes via model_dump. Price fields must use _dollars suffix;
    count must use count_fp alias; phantom keys must be absent."""

    @respx.mock
    def test_price_serializes_dollars_alias(self, orders: OrdersResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-99/amend"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "old_order": order_dict(order_id="ord-99", ticker="MKT"),
                    "order": order_dict(order_id="ord-99", ticker="MKT"),
                },
            )
        )

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
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "old_order": order_dict(order_id="ord-99", ticker="MKT"),
                    "order": order_dict(order_id="ord-99", ticker="MKT"),
                },
            )
        )

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
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "old_order": order_dict(order_id="ord-99", ticker="MKT"),
                    "order": order_dict(order_id="ord-99", ticker="MKT"),
                },
            )
        )

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
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "old_order": order_dict(order_id="ord-99", ticker="MKT"),
                    "order": order_dict(order_id="ord-99", ticker="MKT"),
                },
            )
        )

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
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": order_dict(
                        order_id="ord-99", ticker="MKT", side="yes", status="resting"
                    ),
                },
            )
        )

        orders.decrease("ord-99", reduce_by=5, subaccount=1)

        body = json.loads(route.calls[0].request.content)
        assert body == {"reduce_by": 5, "subaccount": 1}

    @respx.mock
    def test_reduce_to_body(self, orders: OrdersResource) -> None:
        import json

        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-99/decrease"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "order": order_dict(
                        order_id="ord-99", ticker="MKT", side="yes", status="resting"
                    ),
                },
            )
        )

        orders.decrease("ord-99", reduce_to=2)

        body = json.loads(route.calls[0].request.content)
        assert body == {"reduce_to": 2}


class TestBatchCreateWireShape:
    """v0.8.0: orders.batch_create() wraps via BatchCreateOrdersRequest."""

    @respx.mock
    def test_wraps_orders_key(self, orders: OrdersResource) -> None:
        import json

        route = respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )

        orders.batch_create(
            [
                CreateOrderRequest(ticker="A", side="yes", action="buy", count=1),
                CreateOrderRequest(ticker="B", side="no", action="buy", count=1),
            ]
        )

        body = json.loads(route.calls[0].request.content)
        assert "orders" in body
        assert len(body["orders"]) == 2
        # no phantom top-level keys
        assert set(body.keys()) == {"orders"}


class TestBatchCreateUsesBytesPath:
    """P4.2: batch_create / batch_cancel serialize via model_dump_json directly
    to bytes and hand them to httpx as ``content=`` (not ``json=``). This
    skips one full dict-walk pass on large payloads where the serializer
    cost dominates."""

    @respx.mock
    def test_batch_create_uses_bytes_path(self, orders: OrdersResource) -> None:
        """The transport is called with ``content=bytes`` and the
        Content-Type header is set explicitly (httpx doesn't infer it for
        a raw ``content=`` body)."""
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )

        with patch.object(
            orders._transport,
            "request",
            wraps=orders._transport.request,
        ) as spy:
            orders.batch_create([CreateOrderRequest(ticker="A", side="yes", action="buy", count=1)])
            spy.assert_called_once()
            args, kwargs = spy.call_args
            assert args == ("POST", "/portfolio/orders/batched")
            assert "json" not in kwargs or kwargs.get("json") is None
            assert isinstance(kwargs["content"], bytes)
            assert kwargs["headers"]["Content-Type"] == "application/json"

    @respx.mock
    def test_batch_cancel_uses_bytes_path(self, orders: OrdersResource) -> None:
        """Mirror of ``test_batch_create_uses_bytes_path`` for batch_cancel
        — DELETE-with-body bytes path."""
        respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )

        with patch.object(
            orders._transport,
            "request",
            wraps=orders._transport.request,
        ) as spy:
            orders.batch_cancel(["ord-1"])
            spy.assert_called_once()
            args, kwargs = spy.call_args
            assert args == ("DELETE", "/portfolio/orders/batched")
            assert "json" not in kwargs or kwargs.get("json") is None
            assert isinstance(kwargs["content"], bytes)
            assert kwargs["headers"]["Content-Type"] == "application/json"

    @respx.mock
    def test_batch_create_bytes_path_preserves_decimal_precision(
        self,
        orders: OrdersResource,
    ) -> None:
        """P4.2: the bytes path uses ``model_dump_json`` which round-trips
        Decimals via the configured DollarDecimal serializer. Round-trip
        ``Decimal("0.5600")`` through the wire and confirm the exact
        string is preserved (no float-conversion drift)."""
        route = respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )

        orders.batch_create(
            [
                CreateOrderRequest(
                    ticker="A",
                    side="yes",
                    action="buy",
                    count=10,
                    yes_price=Decimal("0.5600"),
                ),
            ]
        )

        raw = route.calls[0].request.content
        body = json.loads(raw)
        assert body["orders"][0]["yes_price_dollars"] == "0.5600"


# ── V2 event-market orders (spec v3.18.0) ───────────────────


class TestCreateOrderV2:
    @respx.mock
    def test_returns_response(self, orders: OrdersResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders",
        ).mock(
            return_value=httpx.Response(
                201,
                json={
                    "order_id": "ord-v2-1",
                    "client_order_id": "cli-1",
                    "fill_count": "0",
                    "remaining_count": "10",
                    "ts_ms": 1700000000000,
                },
            )
        )
        result = orders.create_v2(
            request=CreateOrderV2Request(
                ticker="MKT-A",
                client_order_id="cli-1",
                side="bid",
                count=Decimal("10"),
                price=Decimal("0.50"),
                time_in_force="good_till_canceled",
                self_trade_prevention_type="taker_at_cross",
            ),
        )
        assert result.order_id == "ord-v2-1"
        assert result.fill_count == Decimal("0")
        assert result.remaining_count == Decimal("10")
        assert route.calls.call_count == 1

    def test_side_must_be_bid_or_ask(self) -> None:
        with pytest.raises(ValueError):
            CreateOrderV2Request(
                ticker="MKT-A",
                client_order_id="cli-1",
                side="yes",  # type: ignore[arg-type]  # invalid for BookSide
                count=Decimal("10"),
                price=Decimal("0.50"),
                time_in_force="good_till_canceled",
                self_trade_prevention_type="taker_at_cross",
            )

    @respx.mock
    def test_serializes_body(self, orders: OrdersResource) -> None:
        """V2 model_dump goes through DollarDecimal/FixedPointCount with
        mode="json" — guard against accidental regression in price/count
        wire shape or by_alias/exclude_none plumbing.
        """
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders",
        ).mock(
            return_value=httpx.Response(
                201,
                json={
                    "order_id": "ord-v2-1",
                    "fill_count": "0",
                    "remaining_count": "10",
                    "ts_ms": 0,
                },
            )
        )
        orders.create_v2(
            request=CreateOrderV2Request(
                ticker="MKT-A",
                client_order_id="cli-1",
                side="bid",
                count=Decimal("10"),
                price=Decimal("0.50"),
                time_in_force="good_till_canceled",
                self_trade_prevention_type="taker_at_cross",
                exchange_index=0,
            ),
        )
        body = json.loads(route.calls[0].request.content)
        # No phantom keys; DollarDecimal serializes as string with mode=json.
        assert body == {
            "ticker": "MKT-A",
            "client_order_id": "cli-1",
            "side": "bid",
            "count": "10",
            "price": "0.50",
            "time_in_force": "good_till_canceled",
            "self_trade_prevention_type": "taker_at_cross",
            "exchange_index": 0,
        }


class TestCancelOrderV2:
    @respx.mock
    def test_returns_response(self, orders: OrdersResource) -> None:
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "order_id": "ord-1",
                    "reduced_by": "5",
                    "ts_ms": 1700000000000,
                },
            )
        )
        result = orders.cancel_v2("ord-1")
        assert result.order_id == "ord-1"
        assert result.reduced_by == Decimal("5")

    @respx.mock
    def test_204_raises(self, orders: OrdersResource) -> None:
        """The V2 endpoint promises a body; 204 No Content is an SDK error."""
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1",
        ).mock(return_value=httpx.Response(204))
        with pytest.raises(KalshiError, match="204 No Content"):
            orders.cancel_v2("ord-1")

    @respx.mock
    def test_passes_query_params(self, orders: OrdersResource) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"order_id": "ord-1", "reduced_by": "0", "ts_ms": 0},
            )
        )
        orders.cancel_v2("ord-1", subaccount=3, exchange_index=0)
        params = dict(route.calls[0].request.url.params)
        assert params["subaccount"] == "3"
        assert params["exchange_index"] == "0"


class TestAmendOrderV2:
    @respx.mock
    def test_returns_response(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1/amend",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"order_id": "ord-1", "ts_ms": 1700000000000},
            )
        )
        result = orders.amend_v2(
            "ord-1",
            request=AmendOrderV2Request(
                ticker="MKT-A",
                side="bid",
                price=Decimal("0.55"),
                count=Decimal("10"),
            ),
        )
        assert result.order_id == "ord-1"

    def test_side_must_be_bid_or_ask(self) -> None:
        with pytest.raises(ValueError):
            AmendOrderV2Request(
                ticker="MKT-A",
                side="yes",  # type: ignore[arg-type]
                price=Decimal("0.55"),
                count=Decimal("10"),
            )

    @respx.mock
    def test_passes_subaccount_query(self, orders: OrdersResource) -> None:
        """Spec puts subaccount in the query, exchange_index in the body.

        Regression guard against the params kwarg being dropped from _post.
        """
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1/amend",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"order_id": "ord-1", "ts_ms": 0},
            )
        )
        orders.amend_v2(
            "ord-1",
            request=AmendOrderV2Request(
                ticker="MKT-A",
                side="bid",
                price=Decimal("0.55"),
                count=Decimal("10"),
                exchange_index=0,
            ),
            subaccount=7,
        )
        request = route.calls[0].request
        assert dict(request.url.params) == {"subaccount": "7"}
        body = json.loads(request.content)
        assert body.get("exchange_index") == 0
        # exchange_index is body-only, must not leak into query
        assert "exchange_index" not in request.url.params


class TestDecreaseOrderV2:
    @respx.mock
    def test_returns_response(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1/decrease",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "order_id": "ord-1",
                    "remaining_count": "5",
                    "ts_ms": 1700000000000,
                },
            )
        )
        result = orders.decrease_v2(
            "ord-1",
            request=DecreaseOrderV2Request(reduce_by=Decimal("2")),
        )
        assert result.remaining_count == Decimal("5")

    def test_xor_rejects_both(self) -> None:
        with pytest.raises(ValueError, match="not both"):
            DecreaseOrderV2Request(
                reduce_by=Decimal("2"),
                reduce_to=Decimal("5"),
            )

    def test_xor_requires_one(self) -> None:
        with pytest.raises(ValueError, match="requires either"):
            DecreaseOrderV2Request()

    @respx.mock
    def test_passes_subaccount_query(self, orders: OrdersResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1/decrease",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"order_id": "ord-1", "remaining_count": "0", "ts_ms": 0},
            )
        )
        orders.decrease_v2(
            "ord-1",
            request=DecreaseOrderV2Request(
                reduce_by=Decimal("2"),
                exchange_index=0,
            ),
            subaccount=4,
        )
        request = route.calls[0].request
        assert dict(request.url.params) == {"subaccount": "4"}
        body = json.loads(request.content)
        assert body.get("exchange_index") == 0


class TestBatchCreateV2:
    @respx.mock
    def test_returns_response(self, orders: OrdersResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/batched",
        ).mock(
            return_value=httpx.Response(
                201,
                json={
                    "orders": [
                        {
                            "order_id": "ord-a",
                            "fill_count": "0",
                            "remaining_count": "10",
                            "ts_ms": 1700000000000,
                        },
                        {"error": {"code": "invalid_market"}},
                    ],
                },
            )
        )
        result = orders.batch_create_v2(
            request=BatchCreateOrdersV2Request(
                orders=[
                    CreateOrderV2Request(
                        ticker="MKT-A",
                        client_order_id="cli-1",
                        side="bid",
                        count=Decimal("10"),
                        price=Decimal("0.50"),
                        time_in_force="good_till_canceled",
                        self_trade_prevention_type="taker_at_cross",
                    ),
                ],
            ),
        )
        assert len(result.orders) == 2
        assert result.orders[0].order_id == "ord-a"
        assert result.orders[1].error == {"code": "invalid_market"}


class TestBatchCancelV2:
    @respx.mock
    def test_sends_body(self, orders: OrdersResource) -> None:
        """Spec says DELETE /portfolio/events/orders/batched carries a JSON
        body. Regression guard against the body silently dropping off the
        request — httpx + the DELETE-with-body helper need to keep this wired.
        """
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/batched",
        ).mock(
            return_value=httpx.Response(200, json={"orders": []}),
        )
        orders.batch_cancel_v2(
            request=BatchCancelOrdersV2Request(
                orders=[
                    BatchCancelOrdersV2RequestOrder(order_id="ord-a", subaccount=3),
                    BatchCancelOrdersV2RequestOrder(order_id="ord-b"),
                ],
            ),
        )
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "orders": [
                {"order_id": "ord-a", "subaccount": 3},
                {"order_id": "ord-b"},
            ],
        }

    @respx.mock
    def test_error_entry_parses(self, orders: OrdersResource) -> None:
        """Per spec, an errored cancel still carries order_id + reduced_by=0
        alongside the error block. Document the spec contract here so we
        catch upstream divergence early.
        """
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/batched",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "orders": [
                        {
                            "order_id": "ord-bad",
                            "reduced_by": "0",
                            "error": {
                                "code": "order_not_found",
                                "message": "no such order",
                            },
                        },
                    ],
                },
            )
        )
        result = orders.batch_cancel_v2(
            request=BatchCancelOrdersV2Request(
                orders=[BatchCancelOrdersV2RequestOrder(order_id="ord-bad")],
            ),
        )
        assert result.orders[0].order_id == "ord-bad"
        assert result.orders[0].reduced_by == Decimal("0")
        assert result.orders[0].error == {
            "code": "order_not_found",
            "message": "no such order",
        }

    @respx.mock
    def test_returns_response(self, orders: OrdersResource) -> None:
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/batched",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "orders": [
                        {
                            "order_id": "ord-a",
                            "reduced_by": "10",
                            "ts_ms": 1700000000000,
                        },
                    ],
                },
            )
        )
        result = orders.batch_cancel_v2(
            request=BatchCancelOrdersV2Request(
                orders=[BatchCancelOrdersV2RequestOrder(order_id="ord-a")],
            ),
        )
        assert result.orders[0].order_id == "ord-a"
        assert result.orders[0].reduced_by == Decimal("10")

    @respx.mock
    def test_204_raises(self, orders: OrdersResource) -> None:
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/batched",
        ).mock(return_value=httpx.Response(204))
        with pytest.raises(KalshiError, match="204 No Content"):
            orders.batch_cancel_v2(
                request=BatchCancelOrdersV2Request(
                    orders=[BatchCancelOrdersV2RequestOrder(order_id="ord-a")],
                ),
            )


class TestV2RequiresAuth:
    """Every V2 method must reject an unauthenticated client before
    issuing the request (matches the V1 cancel/create/etc. tests).
    """

    @pytest.fixture
    def _create_request(self) -> CreateOrderV2Request:
        return CreateOrderV2Request(
            ticker="MKT-A",
            client_order_id="cli-1",
            side="bid",
            count=Decimal("10"),
            price=Decimal("0.50"),
            time_in_force="good_till_canceled",
            self_trade_prevention_type="taker_at_cross",
        )

    def test_create_v2(
        self,
        unauth_orders: OrdersResource,
        _create_request: CreateOrderV2Request,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_orders.create_v2(request=_create_request)

    def test_cancel_v2(self, unauth_orders: OrdersResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_orders.cancel_v2("ord-1")

    def test_amend_v2(self, unauth_orders: OrdersResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_orders.amend_v2(
                "ord-1",
                request=AmendOrderV2Request(
                    ticker="MKT-A",
                    side="bid",
                    price=Decimal("0.55"),
                    count=Decimal("10"),
                ),
            )

    def test_decrease_v2(self, unauth_orders: OrdersResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_orders.decrease_v2(
                "ord-1",
                request=DecreaseOrderV2Request(reduce_by=Decimal("2")),
            )

    def test_batch_create_v2(
        self,
        unauth_orders: OrdersResource,
        _create_request: CreateOrderV2Request,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_orders.batch_create_v2(
                request=BatchCreateOrdersV2Request(orders=[_create_request]),
            )

    def test_batch_cancel_v2(self, unauth_orders: OrdersResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_orders.batch_cancel_v2(
                request=BatchCancelOrdersV2Request(
                    orders=[BatchCancelOrdersV2RequestOrder(order_id="ord-a")],
                ),
            )


class TestPathSegmentEncoding:
    """#211: caller-supplied path segments must be URL-encoded so a
    ticker/order_id containing ``/``, whitespace, or ``..`` cannot
    misroute (silently 404 or hit a different handler).
    """

    @respx.mock
    def test_order_id_with_slash_is_encoded_not_routing_attack(
        self, orders: OrdersResource
    ) -> None:
        # ``/`` is encoded as ``%2F`` so the server receives the encoded
        # segment, never a path-traversal-adjacent URL.
        encoded_path = "https://test.kalshi.com/trade-api/v2/portfolio/orders/%2F..%2Fadmin"
        route = respx.get(encoded_path).mock(
            return_value=httpx.Response(
                200,
                json={"order": order_dict(order_id="o", ticker="M")},
            )
        )
        orders.get("/../admin")
        assert route.called

    @respx.mock
    def test_order_id_with_space_encoded(self, orders: OrdersResource) -> None:
        encoded_path = "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord%20a"
        route = respx.get(encoded_path).mock(
            return_value=httpx.Response(
                200,
                json={"order": order_dict(order_id="o", ticker="M")},
            )
        )
        orders.get("ord a")
        assert route.called

    def test_empty_string_order_id_raises_value_error(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match="order_id must be non-empty"):
            orders.get("")

    def test_whitespace_only_order_id_rejected(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match="order_id must be non-empty"):
            orders.cancel("   ")

    def test_dotdot_order_id_rejected(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match=r"cannot be '\.' or '\.\.'"):
            orders.get("..")

    def test_single_dot_order_id_rejected(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match=r"cannot be '\.' or '\.\.'"):
            orders.get(".")


class TestLimitValidation:
    """#214: client-side spec-bound enforcement avoids a wasted round
    trip and produces a more actionable error than a server 400.
    """

    def test_orders_list_rejects_limit_below_1(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match=r"limit must be in \[1, 1000\]"):
            orders.list(limit=0)

    def test_orders_list_rejects_limit_above_1000(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match=r"limit must be in \[1, 1000\]"):
            orders.list(limit=1001)

    @respx.mock
    def test_orders_list_accepts_limit_at_boundaries(self, orders: OrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        orders.list(limit=1)
        orders.list(limit=1000)

    def test_fills_rejects_limit_above_1000(self, orders: OrdersResource) -> None:
        with pytest.raises(ValueError, match=r"limit must be in \[1, 1000\]"):
            orders.fills(limit=10_000)


class TestCreateOrderRequestLiteralEnforcement:
    """#270 Item 2: V1 CreateOrderRequest narrows enum-style fields to Literals.

    Before this change V1 callers could pass ``side="foo"`` and only fail server-
    side. V2 already enforces literals at construction; aligning V1 closes the
    deprecation-window inconsistency.
    """

    def test_rejects_invalid_side(self) -> None:
        with pytest.raises(ValidationError):
            CreateOrderRequest(ticker="T", side="foo", action="buy", count=Decimal("1"))  # type: ignore[arg-type]

    def test_rejects_invalid_action(self) -> None:
        with pytest.raises(ValidationError):
            CreateOrderRequest(ticker="T", side="yes", action="trade", count=Decimal("1"))  # type: ignore[arg-type]

    def test_rejects_invalid_time_in_force(self) -> None:
        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="T", side="yes", action="buy", count=Decimal("1"),
                time_in_force="forever",  # type: ignore[arg-type]
            )

    def test_rejects_invalid_self_trade_prevention_type(self) -> None:
        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="T", side="yes", action="buy", count=Decimal("1"),
                self_trade_prevention_type="never",  # type: ignore[arg-type]
            )

    def test_accepts_valid_v1_yes_no_side(self) -> None:
        # V1 uses yes/no (NOT bid/ask like V2)
        req = CreateOrderRequest(ticker="T", side="no", action="sell", count=Decimal("1"))
        assert req.side == "no"
        assert req.action == "sell"

