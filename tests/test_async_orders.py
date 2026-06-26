"""Tests for async orders resource — mirrors test_orders.py."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport
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
from kalshi.resources.orders import AsyncOrdersResource
from tests._model_fixtures import fill_dict, order_dict


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def orders(test_auth: KalshiAuth, config: KalshiConfig) -> AsyncOrdersResource:
    return AsyncOrdersResource(AsyncTransport(test_auth, config))


@pytest.fixture
def unauth_orders_async(config: KalshiConfig) -> AsyncOrdersResource:
    return AsyncOrdersResource(AsyncTransport(None, config))


class TestAsyncOrdersGet:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_order(self, orders: AsyncOrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123").mock(
            return_value=httpx.Response(
                200,
                json={"order": order_dict(order_id="ord-123", ticker="MKT", status="resting")},
            )
        )
        order = await orders.get("ord-123")
        assert order.order_id == "ord-123"
        assert order.status == "resting"

    @respx.mock
    @pytest.mark.asyncio
    async def test_not_found(self, orders: AsyncOrdersResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/fake").mock(
            return_value=httpx.Response(404, json={"message": "order not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            await orders.get("fake")


class TestAsyncOrdersList:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(self, orders: AsyncOrdersResource) -> None:
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
        page = await orders.list()
        assert len(page) == 2
        assert page.items[0].order_id == "ord-1"
        assert page.has_next is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_with_filters(self, orders: AsyncOrdersResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        await orders.list(status="resting", ticker="MKT-A")
        params = dict(route.calls[0].request.url.params)
        assert params["status"] == "resting"
        assert params["ticker"] == "MKT-A"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_with_all_new_filters(self, orders: AsyncOrdersResource) -> None:
        """Consolidated coverage for v0.7.0 ADDs: event_ticker, min_ts, max_ts, subaccount."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
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
    async def test_empty_string_ticker_passes_through(self, orders: AsyncOrdersResource) -> None:
        """Regression: empty-string ticker reaches the wire after _params() standardization."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        await orders.list(ticker="")
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == ""

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_string_status_passes_through(self, orders: AsyncOrdersResource) -> None:
        """Regression: same fix as ticker — empty string status now reaches wire."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        await orders.list(status="")
        params = dict(route.calls[0].request.url.params)
        assert params["status"] == ""


class TestAsyncOrdersListAll:
    @respx.mock
    @pytest.mark.asyncio
    async def test_auto_paginates(self, orders: AsyncOrdersResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "orders": [
                            order_dict(order_id="o1", ticker="A"),
                        ],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "orders": [
                            order_dict(order_id="o2", ticker="B"),
                        ],
                        "cursor": None,
                    },
                ),
            ]
        )
        order_ids = [o.order_id async for o in orders.list_all()]
        assert order_ids == ["o1", "o2"]
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_all_with_all_new_filters(self, orders: AsyncOrdersResource) -> None:
        """v0.7.0 ADDs on list_all: event_ticker, min_ts, max_ts, subaccount."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(
                200,
                json={"orders": [order_dict(order_id="ord-x", ticker="MKT-A")], "cursor": ""},
            )
        )
        _ = [
            o
            async for o in orders.list_all(
                ticker="MKT-A",
                event_ticker="EVT-X",
                status="resting",
                min_ts=1700000000,
                max_ts=1700099999,
                limit=50,
                subaccount=7,
            )
        ]
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["status"] == "resting"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["subaccount"] == "7"


class TestAsyncOrdersFills:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_fills(self, orders: AsyncOrdersResource) -> None:
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
        page = await orders.fills()
        assert len(page) == 1
        assert page.items[0].trade_id == "t1"
        assert page.items[0].yes_price == Decimal("0.5000")

    @respx.mock
    @pytest.mark.asyncio
    async def test_fills_with_filters(self, orders: AsyncOrdersResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(200, json={"fills": []})
        )
        await orders.fills(ticker="MKT-A", order_id="ord-1")
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["order_id"] == "ord-1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_fills_with_all_new_filters(self, orders: AsyncOrdersResource) -> None:
        """Consolidated coverage for v0.7.0 ADDs: min_ts, max_ts, subaccount."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(200, json={"fills": []})
        )
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
        ids = [f.trade_id async for f in orders.fills_all()]
        assert ids == ["a", "b"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_fills_all_with_all_new_filters(self, orders: AsyncOrdersResource) -> None:
        """Consolidated coverage for v0.7.0 ADDs on fills_all: min_ts, max_ts, subaccount."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(
                200,
                json={"fills": [fill_dict(trade_id="x", yes_price_dollars="0.5")], "cursor": ""},
            )
        )
        _ = [
            f
            async for f in orders.fills_all(
                ticker="MKT-A",
                order_id="ord-1",
                min_ts=1700000000,
                max_ts=1700099999,
                limit=50,
                subaccount=7,
            )
        ]
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["order_id"] == "ord-1"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["subaccount"] == "7"


class TestAsyncOrdersQueuePositions:
    @respx.mock
    @pytest.mark.asyncio
    async def test_queue_positions(self, orders: AsyncOrdersResource) -> None:
        from kalshi.models.orders import OrderQueuePosition

        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/queue_positions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "queue_positions": [
                        {
                            "order_id": "ord-1",
                            "market_ticker": "MKT-A",
                            "queue_position_fp": "42.00",
                        },
                    ],
                },
            )
        )
        positions = await orders.queue_positions()
        assert len(positions) == 1
        assert isinstance(positions[0], OrderQueuePosition)

    @respx.mock
    @pytest.mark.asyncio
    async def test_queue_position_single(self, orders: AsyncOrdersResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-123/queue_position"
        ).mock(return_value=httpx.Response(200, json={"queue_position_fp": "15.00"}))
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
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/orders/fake/queue_position").mock(
            return_value=httpx.Response(404, json={"message": "not found"})
        )
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
    async def test_queue_positions_requires_auth(
        self,
        unauth_orders_async: AsyncOrdersResource,
    ) -> None:
        from kalshi.errors import AuthRequiredError

        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.queue_positions()

    @pytest.mark.asyncio
    async def test_queue_position_requires_auth(
        self,
        unauth_orders_async: AsyncOrdersResource,
    ) -> None:
        from kalshi.errors import AuthRequiredError

        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.queue_position("ord-123")


# ── V2 event-market orders (spec v3.18.0) ───────────────────


class TestAsyncCreateOrderV2:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_response(
        self,
        orders: AsyncOrdersResource,
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders",
        ).mock(
            return_value=httpx.Response(
                201,
                json={
                    "order_id": "ord-v2-1",
                    "fill_count": "0",
                    "remaining_count": "10",
                    "ts_ms": 1700000000000,
                },
            )
        )
        result = await orders.create_v2(
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

    @respx.mock
    @pytest.mark.asyncio
    async def test_serializes_body(
        self,
        orders: AsyncOrdersResource,
    ) -> None:
        """Async parity with TestCreateOrderV2.test_serializes_body —
        guards DollarDecimal / FixedPointCount mode="json" serialization
        on the async dispatch path.
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
        await orders.create_v2(
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


class TestAsyncCancelOrderV2:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_response(
        self,
        orders: AsyncOrdersResource,
    ) -> None:
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
        result = await orders.cancel_v2("ord-1")
        assert result.reduced_by == Decimal("5")

    @respx.mock
    @pytest.mark.asyncio
    async def test_204_raises(self, orders: AsyncOrdersResource) -> None:
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1",
        ).mock(return_value=httpx.Response(204))
        with pytest.raises(KalshiError, match="204 No Content"):
            await orders.cancel_v2("ord-1")

    @respx.mock
    @pytest.mark.asyncio
    async def test_passes_query_params(
        self,
        orders: AsyncOrdersResource,
    ) -> None:
        """Async parity with sync TestCancelOrderV2.test_passes_query_params:
        cancel_v2 routes BOTH subaccount and exchange_index to query params
        (unlike amend_v2/decrease_v2 where exchange_index is body).
        """
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"order_id": "ord-1", "reduced_by": "0", "ts_ms": 0},
            )
        )
        await orders.cancel_v2("ord-1", subaccount=3, exchange_index=0)
        params = dict(route.calls[0].request.url.params)
        assert params["subaccount"] == "3"
        assert params["exchange_index"] == "0"


class TestAsyncAmendOrderV2:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_response(
        self,
        orders: AsyncOrdersResource,
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1/amend",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"order_id": "ord-1", "ts_ms": 1700000000000},
            )
        )
        result = await orders.amend_v2(
            "ord-1",
            request=AmendOrderV2Request(
                ticker="MKT-A",
                side="ask",
                price=Decimal("0.55"),
                count=Decimal("10"),
            ),
        )
        assert result.order_id == "ord-1"


class TestAsyncDecreaseOrderV2:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_response(
        self,
        orders: AsyncOrdersResource,
    ) -> None:
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
        result = await orders.decrease_v2(
            "ord-1",
            request=DecreaseOrderV2Request(reduce_to=Decimal("5")),
        )
        assert result.remaining_count == Decimal("5")


class TestAsyncBatchCreateV2:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_response(
        self,
        orders: AsyncOrdersResource,
    ) -> None:
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
                    ],
                },
            )
        )
        result = await orders.batch_create_v2(
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
        assert result.orders[0].order_id == "ord-a"


class TestAsyncBatchCancelV2:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_response(
        self,
        orders: AsyncOrdersResource,
    ) -> None:
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
        result = await orders.batch_cancel_v2(
            request=BatchCancelOrdersV2Request(
                orders=[BatchCancelOrdersV2RequestOrder(order_id="ord-a")],
            ),
        )
        assert result.orders[0].reduced_by == Decimal("10")

    @respx.mock
    @pytest.mark.asyncio
    async def test_204_raises(self, orders: AsyncOrdersResource) -> None:
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/batched",
        ).mock(return_value=httpx.Response(204))
        with pytest.raises(KalshiError, match="204 No Content"):
            await orders.batch_cancel_v2(
                request=BatchCancelOrdersV2Request(
                    orders=[BatchCancelOrdersV2RequestOrder(order_id="ord-a")],
                ),
            )


class TestIssue329AsyncBatchV2BytesFastPath:
    """Async mirror of test_orders' TestIssue329BatchV2BytesFastPath — V2 batch
    endpoints must route through the bytes fast-path helpers (#223, #329).
    """

    @pytest.mark.asyncio
    async def test_issue_329_v2_batch_create_uses_bytes_fast_path(
        self, orders: AsyncOrdersResource,
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
            AsyncOrdersResource,
            "_post_json",
            new=AsyncMock(return_value={"orders": []}),
        ) as post_json, patch.object(
            AsyncOrdersResource, "_post", new=AsyncMock(),
        ) as post_dict:
            await orders.batch_create_v2(request=request)
        post_dict.assert_not_called()
        assert post_json.call_count == 1
        kwargs = post_json.call_args.kwargs
        assert "json" not in kwargs
        body = kwargs["content"]
        assert isinstance(body, bytes)
        assert json.loads(body) == request.model_dump(
            exclude_none=True, by_alias=True, mode="json",
        )

    @pytest.mark.asyncio
    async def test_issue_329_v2_batch_cancel_uses_bytes_fast_path(
        self, orders: AsyncOrdersResource,
    ) -> None:
        request = BatchCancelOrdersV2Request(
            orders=[BatchCancelOrdersV2RequestOrder(order_id="ord-a")],
        )
        with patch.object(
            AsyncOrdersResource,
            "_delete_with_body_json",
            new=AsyncMock(return_value={"orders": []}),
        ) as del_json, patch.object(
            AsyncOrdersResource, "_delete_with_body", new=AsyncMock(),
        ) as del_dict:
            await orders.batch_cancel_v2(request=request)
        del_dict.assert_not_called()
        assert del_json.call_count == 1
        kwargs = del_json.call_args.kwargs
        assert "json" not in kwargs
        body = kwargs["content"]
        assert isinstance(body, bytes)
        assert json.loads(body) == request.model_dump(
            exclude_none=True, by_alias=True, mode="json",
        )


class TestAsyncAmendDecreaseV2QueryParams:
    """Regression guard: subaccount must reach the query string (not the body)
    on both amend_v2 and decrease_v2 — exchange_index stays in the body.
    """

    @respx.mock
    @pytest.mark.asyncio
    async def test_amend_v2(self, orders: AsyncOrdersResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1/amend",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"order_id": "ord-1", "ts_ms": 0},
            )
        )
        await orders.amend_v2(
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

    @respx.mock
    @pytest.mark.asyncio
    async def test_decrease_v2(self, orders: AsyncOrdersResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/events/orders/ord-1/decrease",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"order_id": "ord-1", "remaining_count": "0", "ts_ms": 0},
            )
        )
        await orders.decrease_v2(
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
        assert "exchange_index" not in request.url.params


class TestAsyncV2RequiresAuth:
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

    @pytest.mark.asyncio
    async def test_create_v2(
        self,
        unauth_orders_async: AsyncOrdersResource,
        _create_request: CreateOrderV2Request,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.create_v2(request=_create_request)

    @pytest.mark.asyncio
    async def test_cancel_v2(
        self,
        unauth_orders_async: AsyncOrdersResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.cancel_v2("ord-1")

    @pytest.mark.asyncio
    async def test_amend_v2(
        self,
        unauth_orders_async: AsyncOrdersResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.amend_v2(
                "ord-1",
                request=AmendOrderV2Request(
                    ticker="MKT-A",
                    side="bid",
                    price=Decimal("0.55"),
                    count=Decimal("10"),
                ),
            )

    @pytest.mark.asyncio
    async def test_decrease_v2(
        self,
        unauth_orders_async: AsyncOrdersResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.decrease_v2(
                "ord-1",
                request=DecreaseOrderV2Request(reduce_by=Decimal("2")),
            )

    @pytest.mark.asyncio
    async def test_batch_create_v2(
        self,
        unauth_orders_async: AsyncOrdersResource,
        _create_request: CreateOrderV2Request,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.batch_create_v2(
                request=BatchCreateOrdersV2Request(orders=[_create_request]),
            )

    @pytest.mark.asyncio
    async def test_batch_cancel_v2(
        self,
        unauth_orders_async: AsyncOrdersResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_orders_async.batch_cancel_v2(
                request=BatchCancelOrdersV2Request(
                    orders=[BatchCancelOrdersV2RequestOrder(order_id="ord-a")],
                ),
            )


# ── Issue #351: deprecated forwarders for fills on AsyncOrdersResource ───────


class TestIssue351AsyncOrdersFillsDeprecated:
    @respx.mock
    @pytest.mark.asyncio
    async def test_issue_351_orders_fills_emits_deprecation_warning(
        self, orders: AsyncOrdersResource
    ) -> None:
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
        with pytest.warns(DeprecationWarning, match=r"AsyncOrdersResource\.fills") as record:
            page = await orders.fills()
        assert len(page) == 1
        assert page.items[0].trade_id == "t1"
        assert len([w for w in record if issubclass(w.category, DeprecationWarning)]) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_issue_351_orders_fills_all_emits_deprecation_warning(
        self, orders: AsyncOrdersResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fills": [fill_dict(trade_id="a", yes_price_dollars="0.5")],
                    "cursor": "",
                },
            )
        )
        with pytest.warns(
            DeprecationWarning, match=r"AsyncOrdersResource\.fills_all"
        ) as record:
            ids = [f.trade_id async for f in orders.fills_all()]
        assert ids == ["a"]
        assert len([w for w in record if issubclass(w.category, DeprecationWarning)]) == 1
