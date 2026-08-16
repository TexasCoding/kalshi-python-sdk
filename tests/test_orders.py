"""Tests for kalshi.resources.orders — Orders resource."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
import respx

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import (
    AuthRequiredError,
    KalshiError,
    KalshiNotFoundError,
)
from kalshi.models.orders import (
    AmendOrderV2Request,
    BatchCancelOrdersV2Request,
    BatchCancelOrdersV2RequestOrder,
    BatchCreateOrdersV2Request,
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
def unauth_orders(config: KalshiConfig) -> OrdersResource:
    return OrdersResource(SyncTransport(None, config))


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
            exchange_index=0,
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
        assert params["exchange_index"] == "0"

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
                exchange_index=1,
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
        assert params["exchange_index"] == "1"


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
            exchange_index=0,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["order_id"] == "ord-1"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["subaccount"] == "7"
        assert params["exchange_index"] == "0"


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
                exchange_index=2,
            )
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["order_id"] == "ord-1"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["subaccount"] == "7"
        assert params["exchange_index"] == "2"


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
    def test_queue_positions_requires_auth(self, unauth_orders: OrdersResource) -> None:
        from kalshi.errors import AuthRequiredError

        with pytest.raises(AuthRequiredError):
            unauth_orders.queue_positions()

    def test_queue_position_requires_auth(self, unauth_orders: OrdersResource) -> None:
        from kalshi.errors import AuthRequiredError

        with pytest.raises(AuthRequiredError):
            unauth_orders.queue_position("ord-123")


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

    @respx.mock
    def test_market_ticker_with_auto_exchange_index(
        self, orders: OrdersResource,
    ) -> None:
        """Spec 3.27.0: market_ticker required when exchange_index is -1."""
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
                exchange_index=-1,
                market_ticker="MKT-A",
            ),
        )
        body = json.loads(route.calls[0].request.content)
        assert body["exchange_index"] == -1
        assert body["market_ticker"] == "MKT-A"


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
    def test_auto_route_exchange_index_minus_one(self, orders: OrdersResource) -> None:
        """Spec v3.22.0: exchange_index=-1 auto-routes by market_ticker. The
        model must accept -1 (no ge=0 floor) and emit market_ticker so the
        auto-route contract is usable.
        """
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/batched",
        ).mock(return_value=httpx.Response(200, json={"orders": []}))
        orders.batch_cancel_v2(
            request=BatchCancelOrdersV2Request(
                orders=[
                    BatchCancelOrdersV2RequestOrder(
                        order_id="ord-a", exchange_index=-1, market_ticker="MKT-A",
                    ),
                ],
            ),
        )
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "orders": [{"order_id": "ord-a", "exchange_index": -1, "market_ticker": "MKT-A"}],
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


class TestIssue329BatchV2BytesFastPath:
    """V2 batch endpoints must route through the v2.4 #223 bytes fast-path
    (``_post_json`` / ``_delete_with_body_json`` with ``content=<bytes>``),
    not the dict-walk slow path (``_post`` / ``_delete_with_body`` with
    ``json=<dict>``). See issues #223 and #329.

    We assert by patching the transport-helper layer: the fast-path helpers
    forward ``content=`` bytes; the slow-path helpers forward ``json=``.
    """

    def test_issue_329_v2_batch_create_uses_bytes_fast_path(
        self, orders: OrdersResource,
    ) -> None:
        request = BatchCreateOrdersV2Request(
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
        )
        with patch.object(
            OrdersResource, "_post_json", return_value={"orders": []},
        ) as post_json, patch.object(OrdersResource, "_post") as post_dict:
            orders.batch_create_v2(request=request)
        post_dict.assert_not_called()
        assert post_json.call_count == 1
        kwargs = post_json.call_args.kwargs
        assert "json" not in kwargs
        body = kwargs["content"]
        assert isinstance(body, bytes)
        assert json.loads(body) == request.model_dump(
            exclude_none=True, by_alias=True, mode="json",
        )

    def test_issue_329_v2_batch_cancel_uses_bytes_fast_path(
        self, orders: OrdersResource,
    ) -> None:
        request = BatchCancelOrdersV2Request(
            orders=[BatchCancelOrdersV2RequestOrder(order_id="ord-a")],
        )
        with patch.object(
            OrdersResource, "_delete_with_body_json", return_value={"orders": []},
        ) as del_json, patch.object(OrdersResource, "_delete_with_body") as del_dict:
            orders.batch_cancel_v2(request=request)
        del_dict.assert_not_called()
        assert del_json.call_count == 1
        kwargs = del_json.call_args.kwargs
        assert "json" not in kwargs
        body = kwargs["content"]
        assert isinstance(body, bytes)
        assert json.loads(body) == request.model_dump(
            exclude_none=True, by_alias=True, mode="json",
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
            orders.get("   ")

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


class TestIssue351OrdersFillsDeprecated:
    @respx.mock
    def test_issue_351_orders_fills_emits_deprecation_warning(
        self, orders: OrdersResource
    ) -> None:
        """Old location still works and emits exactly one DeprecationWarning per call."""
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fills": [
                        fill_dict(
                            trade_id="t1", order_id="o1", yes_price_dollars="0.5", count_fp="5"
                        )
                    ],
                    "cursor": "",
                },
            )
        )
        with pytest.warns(DeprecationWarning, match=r"OrdersResource\.fills") as record:
            page = orders.fills()
        assert len(page) == 1
        assert page.items[0].trade_id == "t1"
        assert len([w for w in record if issubclass(w.category, DeprecationWarning)]) == 1

    @respx.mock
    def test_issue_351_orders_fills_all_emits_deprecation_warning(
        self, orders: OrdersResource
    ) -> None:
        """Iterator forwarder still works and emits exactly one DeprecationWarning per call."""
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fills": [fill_dict(trade_id="a", yes_price_dollars="0.5")],
                    "cursor": "",
                },
            )
        )
        with pytest.warns(DeprecationWarning, match=r"OrdersResource\.fills_all") as record:
            ids = [f.trade_id for f in orders.fills_all()]
        assert ids == ["a"]
        assert len([w for w in record if issubclass(w.category, DeprecationWarning)]) == 1
