"""Tests for the perps (margin) orders resource (#391).

Concrete-module imports only (``kalshi.perps.models.orders`` /
``kalshi.perps.resources.orders``) — the ``kalshi.perps`` package ``__init__``
exports are wired during integration, after this resource lands.
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi.errors import (
    AuthRequiredError,
    KalshiConflictError,
    KalshiNotFoundError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.models.orders import (
    AmendMarginOrderRequest,
    CreateMarginOrderRequest,
    DecreaseMarginOrderRequest,
    GetMarginOrdersResponse,
    MarginOrder,
)

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


def _order_dict(**overrides: object) -> dict[str, object]:
    """A minimal valid MarginOrder wire dict (required fields per spec)."""
    base: dict[str, object] = {
        "order_id": "ord-1",
        "user_id": "usr-1",
        "client_order_id": "cid-1",
        "ticker": "BTC-PERP",
        "side": "bid",
        "last_update_reason": "",
        "price": "0.5600",
        "fill_count": "0.00",
        "remaining_count": "100.00",
    }
    base.update(overrides)
    return base


# ── create ───────────────────────────────────────────────────────────────────


class TestCreate:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(
                201,
                json={
                    "order_id": "ord-9",
                    "fill_count": "3.00",
                    "remaining_count": "97.00",
                    "client_order_id": "cid-9",
                    "average_fill_price": "0.5600",
                    "average_fee_paid": "0.0100",
                },
            )
        )
        resp = perps_client.orders.create(
            ticker="BTC-PERP",
            client_order_id="cid-9",
            side="bid",
            count="100",
            price="0.56",
            time_in_force="good_till_canceled",
            self_trade_prevention_type="taker_at_cross",
        )
        assert resp.order_id == "ord-9"
        assert resp.fill_count == Decimal("3.00")
        assert isinstance(resp.fill_count, Decimal)
        assert resp.remaining_count == Decimal("97.00")
        assert resp.average_fill_price == Decimal("0.5600")

        body = json.loads(route.calls[0].request.content)
        assert body["client_order_id"] == "cid-9"
        assert body["side"] == "bid"
        assert body["price"] == "0.56"  # OrderPrice serializes to a fixed-point string
        assert body["count"] == "100"
        # wire names are the short keys, not _dollars/_fp suffixed
        assert "price_dollars" not in body
        assert "count_fp" not in body

    @respx.mock
    def test_conflict_maps(self, perps_client: PerpsClient) -> None:
        respx.post(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(409, json={"error": {"code": "duplicate"}})
        )
        with pytest.raises(KalshiConflictError):
            perps_client.orders.create(
                ticker="BTC-PERP",
                client_order_id="cid-9",
                side="bid",
                count="100",
                price="0.56",
                time_in_force="good_till_canceled",
                self_trade_prevention_type="taker_at_cross",
            )

    def test_missing_required_field_raises_before_http(self, perps_client: PerpsClient) -> None:
        # time_in_force / self_trade_prevention_type omitted -> TypeError, no HTTP.
        with pytest.raises(TypeError):
            perps_client.orders.create(
                ticker="BTC-PERP",
                client_order_id="cid-9",
                side="bid",
                count="100",
                price="0.56",
            )

    def test_phantom_kwarg_rejected_by_forbid(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginOrderRequest(
                ticker="BTC-PERP",
                client_order_id="cid-9",
                side="bid",
                count="100",
                price="0.56",
                time_in_force="good_till_canceled",
                self_trade_prevention_type="taker_at_cross",
                phantom="x",  # type: ignore[call-arg]
            )

    def test_negative_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginOrderRequest(
                ticker="BTC-PERP",
                client_order_id="cid-9",
                side="bid",
                count="100",
                price="-0.56",
                time_in_force="good_till_canceled",
                self_trade_prevention_type="taker_at_cross",
            )

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.post(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(201, json={})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.orders.create(
                ticker="BTC-PERP",
                client_order_id="cid-9",
                side="bid",
                count="100",
                price="0.56",
                time_in_force="good_till_canceled",
                self_trade_prevention_type="taker_at_cross",
            )
        assert not route.called
        client.close()

    @respx.mock
    def test_not_retried_on_503(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            perps_client.orders.create(
                ticker="BTC-PERP",
                client_order_id="cid-9",
                side="bid",
                count="100",
                price="0.56",
                time_in_force="good_till_canceled",
                self_trade_prevention_type="taker_at_cross",
            )
        assert route.call_count == 1  # POST is never retried

    @respx.mock
    def test_request_model_path(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(
                201,
                json={"order_id": "ord-9", "fill_count": "0.00", "remaining_count": "100.00"},
            )
        )
        perps_client.orders.create(
            request=CreateMarginOrderRequest(
                ticker="BTC-PERP",
                client_order_id="cid-9",
                side="ask",
                count="100",
                price="0.56",
                time_in_force="immediate_or_cancel",
                self_trade_prevention_type="maker",
                subaccount=2,
            )
        )
        body = json.loads(route.calls[0].request.content)
        assert body["subaccount"] == 2
        assert body["side"] == "ask"

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.post(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(
                201,
                json={"order_id": "ord-9", "fill_count": "0.00", "remaining_count": "100.00"},
            )
        )
        resp = await async_perps_client.orders.create(
            ticker="BTC-PERP",
            client_order_id="cid-9",
            side="bid",
            count="100",
            price="0.56",
            time_in_force="good_till_canceled",
            self_trade_prevention_type="taker_at_cross",
        )
        assert resp.remaining_count == Decimal("100.00")
        await async_perps_client.close()


# ── get ──────────────────────────────────────────────────────────────────────


class TestGet:
    @respx.mock
    def test_happy_unwraps_order(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/orders/ord-1").mock(
            return_value=httpx.Response(200, json={"order": _order_dict()})
        )
        order = perps_client.orders.get("ord-1")
        assert isinstance(order, MarginOrder)
        assert order.order_id == "ord-1"
        assert order.price == Decimal("0.5600")
        assert isinstance(order.price, Decimal)
        # empty-string last_update_reason is a real enum value
        assert order.last_update_reason == ""

    @respx.mock
    def test_not_found(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/orders/missing").mock(
            return_value=httpx.Response(404, json={"error": {"code": "not_found"}})
        )
        with pytest.raises(KalshiNotFoundError):
            perps_client.orders.get("missing")

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/orders/ord-1").mock(
            return_value=httpx.Response(200, json={"order": _order_dict()})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.orders.get("ord-1")
        assert not route.called
        client.close()

    @respx.mock
    async def test_async(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/orders/ord-1").mock(
            return_value=httpx.Response(200, json={"order": _order_dict(side="ask")})
        )
        order = await async_perps_client.orders.get("ord-1")
        assert order.side == "ask"
        await async_perps_client.close()


# ── list / list_all ──────────────────────────────────────────────────────────


class TestList:
    @respx.mock
    def test_happy_envelope(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(
                200, json={"orders": [_order_dict(), _order_dict(order_id="ord-2")], "cursor": "c2"}
            )
        )
        resp = perps_client.orders.list(ticker="BTC-PERP", status="resting", limit=50)
        assert isinstance(resp, GetMarginOrdersResponse)
        assert len(resp.orders) == 2
        assert resp.cursor == "c2"
        q = dict(route.calls[0].request.url.params)
        assert q["ticker"] == "BTC-PERP"
        assert q["status"] == "resting"
        assert q["limit"] == "50"

    @respx.mock
    def test_subaccount_param_only_when_passed(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(200, json={"orders": [], "cursor": ""})
        )
        perps_client.orders.list()
        assert "subaccount" not in dict(route.calls[0].request.url.params)
        perps_client.orders.list(subaccount=0)
        assert dict(route.calls[1].request.url.params)["subaccount"] == "0"

    def test_limit_out_of_range_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValueError):
            perps_client.orders.list(limit=0)
        with pytest.raises(ValueError):
            perps_client.orders.list(limit=1001)

    @respx.mock
    def test_list_all_walks_two_pages(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/orders").mock(
            side_effect=[
                httpx.Response(200, json={"orders": [_order_dict()], "cursor": "c2"}),
                httpx.Response(
                    200, json={"orders": [_order_dict(order_id="ord-2")], "cursor": ""}
                ),
            ]
        )
        orders = list(perps_client.orders.list_all(ticker="BTC-PERP"))
        assert [o.order_id for o in orders] == ["ord-1", "ord-2"]

    @respx.mock
    def test_list_all_max_pages_caps(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(200, json={"orders": [_order_dict()], "cursor": "next"})
        )
        orders = list(perps_client.orders.list_all(max_pages=1))
        assert len(orders) == 1
        assert route.call_count == 1

    @respx.mock
    async def test_async_list_all(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/orders").mock(
            side_effect=[
                httpx.Response(200, json={"orders": [_order_dict()], "cursor": "c2"}),
                httpx.Response(
                    200, json={"orders": [_order_dict(order_id="ord-2")], "cursor": ""}
                ),
            ]
        )
        seen = [o.order_id async for o in async_perps_client.orders.list_all()]
        assert seen == ["ord-1", "ord-2"]
        await async_perps_client.close()


# ── cancel ───────────────────────────────────────────────────────────────────


class TestCancel:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/orders/ord-1").mock(
            return_value=httpx.Response(
                200, json={"order_id": "ord-1", "reduced_by": "100.00", "client_order_id": "cid-1"}
            )
        )
        resp = perps_client.orders.cancel("ord-1")
        assert resp.order_id == "ord-1"
        assert resp.reduced_by == Decimal("100.00")
        assert isinstance(resp.reduced_by, Decimal)
        assert "subaccount" not in dict(route.calls[0].request.url.params)

    @respx.mock
    def test_subaccount_param_emitted(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/orders/ord-1").mock(
            return_value=httpx.Response(200, json={"order_id": "ord-1", "reduced_by": "0.00"})
        )
        perps_client.orders.cancel("ord-1", subaccount=3)
        assert dict(route.calls[0].request.url.params)["subaccount"] == "3"

    @respx.mock
    def test_not_found(self, perps_client: PerpsClient) -> None:
        respx.delete(f"{BASE}/margin/orders/missing").mock(
            return_value=httpx.Response(404, json={"error": {"code": "not_found"}})
        )
        with pytest.raises(KalshiNotFoundError):
            perps_client.orders.cancel("missing")

    @respx.mock
    def test_not_retried_on_503(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/orders/ord-1").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            perps_client.orders.cancel("ord-1")
        assert route.call_count == 1  # DELETE is never retried

    @respx.mock
    async def test_async(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.delete(f"{BASE}/margin/orders/ord-1").mock(
            return_value=httpx.Response(200, json={"order_id": "ord-1", "reduced_by": "5.00"})
        )
        resp = await async_perps_client.orders.cancel("ord-1")
        assert resp.reduced_by == Decimal("5.00")
        await async_perps_client.close()


class TestCancelAll:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(204)
        )
        assert perps_client.orders.cancel_all() is None
        assert route.called
        assert "subaccount" not in dict(route.calls[0].request.url.params)

    @respx.mock
    def test_subaccount_param(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(204)
        )
        perps_client.orders.cancel_all(subaccount=4)
        assert dict(route.calls[0].request.url.params)["subaccount"] == "4"

    @respx.mock
    def test_not_retried_on_503(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/orders").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            perps_client.orders.cancel_all()
        assert route.call_count == 1

    def test_unauthenticated_raises(self) -> None:
        client = PerpsClient(config=PerpsConfig.demo(max_retries=0))
        with pytest.raises(AuthRequiredError):
            client.orders.cancel_all()


# ── decrease ─────────────────────────────────────────────────────────────────


class TestDecrease:
    @respx.mock
    def test_happy_reduce_by(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/orders/ord-1/decrease").mock(
            return_value=httpx.Response(
                200, json={"order_id": "ord-1", "remaining_count": "90.00"}
            )
        )
        resp = perps_client.orders.decrease("ord-1", reduce_by="10")
        assert resp.remaining_count == Decimal("90.00")
        body = json.loads(route.calls[0].request.content)
        assert body == {"reduce_by": "10"}

    @respx.mock
    def test_happy_reduce_to(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/orders/ord-1/decrease").mock(
            return_value=httpx.Response(
                200, json={"order_id": "ord-1", "remaining_count": "50.00"}
            )
        )
        perps_client.orders.decrease("ord-1", reduce_to="50", subaccount=1)
        body = json.loads(route.calls[0].request.content)
        assert body == {"reduce_to": "50"}
        assert dict(route.calls[0].request.url.params)["subaccount"] == "1"

    def test_both_set_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValidationError):
            perps_client.orders.decrease("ord-1", reduce_by="10", reduce_to="50")

    def test_neither_set_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValidationError):
            perps_client.orders.decrease("ord-1")

    @respx.mock
    def test_not_retried_on_503(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/orders/ord-1/decrease").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            perps_client.orders.decrease("ord-1", reduce_by="10")
        assert route.call_count == 1

    @respx.mock
    async def test_async(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.post(f"{BASE}/margin/orders/ord-1/decrease").mock(
            return_value=httpx.Response(
                200, json={"order_id": "ord-1", "remaining_count": "0.00"}
            )
        )
        resp = await async_perps_client.orders.decrease(
            "ord-1", request=DecreaseMarginOrderRequest(reduce_to="0")
        )
        assert resp.remaining_count == Decimal("0.00")
        await async_perps_client.close()


# ── amend ────────────────────────────────────────────────────────────────────


class TestAmend:
    @respx.mock
    def test_happy_nullable_fields_absent(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/orders/ord-1/amend").mock(
            return_value=httpx.Response(200, json={"order_id": "ord-1"})
        )
        resp = perps_client.orders.amend(
            "ord-1", ticker="BTC-PERP", side="bid", price="0.57", count="80"
        )
        assert resp.order_id == "ord-1"
        assert resp.fill_count is None
        assert resp.average_fill_price is None
        body = json.loads(route.calls[0].request.content)
        assert body["price"] == "0.57"
        assert body["count"] == "80"
        assert body["side"] == "bid"

    @respx.mock
    def test_happy_with_fills(self, perps_client: PerpsClient) -> None:
        respx.post(f"{BASE}/margin/orders/ord-1/amend").mock(
            return_value=httpx.Response(
                200,
                json={
                    "order_id": "ord-1",
                    "remaining_count": "30.00",
                    "fill_count": "50.00",
                    "average_fill_price": "0.5700",
                },
            )
        )
        resp = perps_client.orders.amend(
            "ord-1", ticker="BTC-PERP", side="bid", price="0.57", count="80", subaccount=2
        )
        assert resp.fill_count == Decimal("50.00")
        assert resp.average_fill_price == Decimal("0.5700")

    @respx.mock
    def test_subaccount_query_param(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/orders/ord-1/amend").mock(
            return_value=httpx.Response(200, json={"order_id": "ord-1"})
        )
        perps_client.orders.amend(
            "ord-1", ticker="BTC-PERP", side="ask", price="0.40", count="10", subaccount=4
        )
        assert dict(route.calls[0].request.url.params)["subaccount"] == "4"

    @respx.mock
    def test_bad_request_maps(self, perps_client: PerpsClient) -> None:
        respx.post(f"{BASE}/margin/orders/ord-1/amend").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad"}})
        )
        with pytest.raises(KalshiValidationError):
            perps_client.orders.amend(
                "ord-1", ticker="BTC-PERP", side="bid", price="0.57", count="80"
            )

    def test_missing_required_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError):
            perps_client.orders.amend("ord-1", ticker="BTC-PERP", side="bid")

    @respx.mock
    def test_not_retried_on_503(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/orders/ord-1/amend").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            perps_client.orders.amend(
                "ord-1", ticker="BTC-PERP", side="bid", price="0.57", count="80"
            )
        assert route.call_count == 1

    @respx.mock
    async def test_async(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.post(f"{BASE}/margin/orders/ord-1/amend").mock(
            return_value=httpx.Response(200, json={"order_id": "ord-1"})
        )
        resp = await async_perps_client.orders.amend(
            "ord-1",
            request=AmendMarginOrderRequest(
                ticker="BTC-PERP", side="bid", price="0.57", count="80"
            ),
        )
        assert resp.order_id == "ord-1"
        await async_perps_client.close()


# ── list_fcm / list_all_fcm (soft-deprecated; path removed from perps OpenAPI) ──


class TestListFcm:
    @respx.mock
    def test_happy_subtrader_in_query(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fcm/orders").mock(
            return_value=httpx.Response(200, json={"orders": [_order_dict()], "cursor": ""})
        )
        with pytest.warns(DeprecationWarning, match=r"list_fcm"):
            resp = perps_client.orders.list_fcm(subtrader_id="sub-7", ticker="BTC-PERP")
        assert isinstance(resp, GetMarginOrdersResponse)
        q = dict(route.calls[0].request.url.params)
        assert q["subtrader_id"] == "sub-7"
        assert q["ticker"] == "BTC-PERP"
        # FCM endpoint has no subaccount param
        assert "subaccount" not in q

    def test_missing_subtrader_id_is_type_error(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError):
            perps_client.orders.list_fcm()  # type: ignore[call-arg]

    @respx.mock
    def test_list_all_fcm_walks_pages(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fcm/orders").mock(
            side_effect=[
                httpx.Response(200, json={"orders": [_order_dict()], "cursor": "c2"}),
                httpx.Response(
                    200, json={"orders": [_order_dict(order_id="ord-2")], "cursor": ""}
                ),
            ]
        )
        with pytest.warns(DeprecationWarning, match=r"list_all_fcm|list_fcm"):
            orders = list(perps_client.orders.list_all_fcm(subtrader_id="sub-7"))
        assert [o.order_id for o in orders] == ["ord-1", "ord-2"]
        for call in route.calls:
            assert "subaccount" not in dict(call.request.url.params)

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/fcm/orders").mock(
            return_value=httpx.Response(200, json={"orders": [], "cursor": ""})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with (
            pytest.warns(DeprecationWarning, match=r"list_fcm"),
            pytest.raises(AuthRequiredError),
        ):
            client.orders.list_fcm(subtrader_id="sub-7")
        assert not route.called
        client.close()

    @respx.mock
    async def test_async_list_all_fcm(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/fcm/orders").mock(
            return_value=httpx.Response(200, json={"orders": [_order_dict()], "cursor": ""})
        )
        with pytest.warns(DeprecationWarning, match=r"list_all_fcm|list_fcm"):
            seen = [
                o.order_id
                async for o in async_perps_client.orders.list_all_fcm(subtrader_id="sub-7")
            ]
        assert seen == ["ord-1"]
        await async_perps_client.close()
