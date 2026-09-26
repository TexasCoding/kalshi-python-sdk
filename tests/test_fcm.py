"""Tests for kalshi.resources.fcm — FCM orders + positions."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import AuthRequiredError, KalshiAuthError
from kalshi.resources.fcm import AsyncFcmResource, FcmResource
from tests._model_fixtures import market_position_dict, order_dict


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def fcm(test_auth: KalshiAuth, config: KalshiConfig) -> FcmResource:
    return FcmResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_fcm(
    test_auth: KalshiAuth,
    config: KalshiConfig,
) -> AsyncFcmResource:
    return AsyncFcmResource(AsyncTransport(test_auth, config))


@pytest.fixture
def unauth_fcm(config: KalshiConfig) -> FcmResource:
    return FcmResource(SyncTransport(None, config))


class TestOrders:
    @respx.mock
    def test_returns_page(self, fcm: FcmResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/fcm/orders").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orders": [
                        order_dict(
                            order_id="ord-1",
                            user_id="user-1",
                            client_order_id="client-1",
                            ticker="TEST-MKT",
                            side="yes",
                            action="buy",
                            type="limit",
                            status="resting",
                            yes_price_dollars="0.55",
                        ),
                    ],
                    "cursor": "",
                },
            )
        )
        page = fcm.orders(subtrader_id="sub-1")
        assert len(page.items) == 1
        assert page.items[0].order_id == "ord-1"

    @respx.mock
    def test_forwards_filters(self, fcm: FcmResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/fcm/orders",
        ).mock(return_value=httpx.Response(200, json={"orders": []}))
        fcm.orders(
            subtrader_id="sub-1",
            ticker="TEST-MKT",
            event_ticker="TEST-EVT",
            status="resting",
            min_ts=1000,
            max_ts=2000,
            limit=50,
        )
        assert route.called
        url = route.calls.last.request.url
        assert url.params["subtrader_id"] == "sub-1"
        assert url.params["ticker"] == "TEST-MKT"
        assert url.params["event_ticker"] == "TEST-EVT"
        assert url.params["status"] == "resting"
        assert url.params["limit"] == "50"

    @respx.mock
    def test_client_order_ids_without_subtrader(self, fcm: FcmResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/fcm/orders",
        ).mock(return_value=httpx.Response(200, json={"orders": []}))
        fcm.orders(client_order_ids=["a", "b"])
        assert route.calls.last.request.url.params["client_order_ids"] == "a,b"
        assert "subtrader_id" not in route.calls.last.request.url.params

    def test_requires_subtrader_or_client_order_ids(self, fcm: FcmResource) -> None:
        with pytest.raises(ValueError, match="subtrader_id or client_order_ids"):
            fcm.orders()

    def test_client_order_ids_cap(self, fcm: FcmResource) -> None:
        with pytest.raises(ValueError, match="at most 100"):
            fcm.orders(client_order_ids=[f"id-{i}" for i in range(101)])

    def test_requires_auth(self, unauth_fcm: FcmResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_fcm.orders(subtrader_id="sub-1")

    @respx.mock
    def test_server_rejects_auth(self, fcm: FcmResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/fcm/orders").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        with pytest.raises(KalshiAuthError):
            fcm.orders(subtrader_id="sub-1")


class TestPositions:
    @respx.mock
    def test_returns_positions(self, fcm: FcmResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/fcm/positions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_positions": [],
                    "event_positions": [],
                    "cursor": "",
                },
            )
        )
        result = fcm.positions(subtrader_id="sub-1")
        assert result.market_positions == []
        assert result.event_positions == []

    @respx.mock
    def test_forwards_filters(self, fcm: FcmResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/fcm/positions",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"market_positions": [], "event_positions": []},
            )
        )
        fcm.positions(
            subtrader_id="sub-1",
            ticker="TEST-MKT",
            event_ticker="TEST-EVT",
            count_filter="position",
            settlement_status="unsettled",
            limit=100,
        )
        assert route.called
        url = route.calls.last.request.url
        assert url.params["subtrader_id"] == "sub-1"
        assert url.params["ticker"] == "TEST-MKT"
        assert url.params["count_filter"] == "position"
        assert url.params["settlement_status"] == "unsettled"

    def test_requires_auth(self, unauth_fcm: FcmResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_fcm.positions(subtrader_id="sub-1")


class TestPositionsAll:
    @respx.mock
    def test_positions_all_paginates(self, fcm: FcmResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/fcm/positions").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "market_positions": [
                            market_position_dict(ticker="A"),
                            market_position_dict(ticker="B"),
                        ],
                        "event_positions": [],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "market_positions": [market_position_dict(ticker="C")],
                        "event_positions": [],
                        "cursor": "",
                    },
                ),
            ]
        )
        tickers = [p.ticker for p in fcm.positions_all(subtrader_id="sub-1")]
        assert tickers == ["A", "B", "C"]

    @respx.mock
    def test_positions_all_forwards_filters(self, fcm: FcmResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/fcm/positions").mock(
            return_value=httpx.Response(
                200, json={"market_positions": [], "event_positions": [], "cursor": ""}
            )
        )
        list(
            fcm.positions_all(
                subtrader_id="sub-1",
                ticker="MKT-A",
                event_ticker="EVT-X",
                count_filter="position",
                settlement_status="unsettled",
                limit=50,
            )
        )
        url = route.calls.last.request.url
        assert url.params["subtrader_id"] == "sub-1"
        assert url.params["ticker"] == "MKT-A"
        assert url.params["event_ticker"] == "EVT-X"
        assert url.params["settlement_status"] == "unsettled"
        assert "cursor" not in url.params

    def test_positions_all_requires_auth(self, unauth_fcm: FcmResource) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_fcm.positions_all(subtrader_id="sub-1"))


class TestAsyncFcm:
    @respx.mock
    @pytest.mark.asyncio
    async def test_orders(self, async_fcm: AsyncFcmResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/fcm/orders").mock(
            return_value=httpx.Response(200, json={"orders": [], "cursor": ""})
        )
        page = await async_fcm.orders(subtrader_id="sub-1")
        assert page.items == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_positions(self, async_fcm: AsyncFcmResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/fcm/positions").mock(
            return_value=httpx.Response(
                200,
                json={"market_positions": [], "event_positions": []},
            )
        )
        result = await async_fcm.positions(subtrader_id="sub-1")
        assert result.market_positions == []


class TestAsyncFcmPositionsAll:
    @pytest.mark.asyncio
    @respx.mock
    async def test_positions_all_paginates(self, async_fcm: AsyncFcmResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/fcm/positions").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "market_positions": [market_position_dict(ticker="A")],
                        "event_positions": [],
                        "cursor": "next",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "market_positions": [market_position_dict(ticker="B")],
                        "event_positions": [],
                        "cursor": "",
                    },
                ),
            ]
        )
        tickers = [p.ticker async for p in async_fcm.positions_all(subtrader_id="sub-1")]
        assert tickers == ["A", "B"]


class TestFcmSubtraders:
    @respx.mock
    def test_list_subtraders(self, fcm: FcmResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/fcm/subtraders").mock(
            return_value=httpx.Response(
                200,
                json={
                    "subtraders": [
                        {
                            "subtrader_id": "acct_desk1",
                            "exchange_indices": [0],
                            "trading_blocked": False,
                            "fcm_trading_blocked": False,
                            "propagation_pending": False,
                        }
                    ]
                },
            )
        )
        resp = fcm.list_subtraders()
        assert resp.subtraders[0].subtrader_id == "acct_desk1"

    @respx.mock
    def test_create_subtrader(self, fcm: FcmResource) -> None:
        route = respx.post("https://test.kalshi.com/trade-api/v2/fcm/subtraders").mock(
            return_value=httpx.Response(200, json={"subtrader_id": "acct_desk1"})
        )
        resp = fcm.create_subtrader(subtrader_suffix="desk1")
        assert resp.subtrader_id == "acct_desk1"
        assert json.loads(route.calls[0].request.content) == {"subtrader_suffix": "desk1"}

    def test_create_subtrader_requires_suffix(self, fcm: FcmResource) -> None:
        with pytest.raises(TypeError, match="create_subtrader"):
            fcm.create_subtrader()  # type: ignore[call-overload]

    @respx.mock
    def test_blocked_categories_roundtrip(self, fcm: FcmResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/fcm/subtraders/blocked_categories").mock(
            return_value=httpx.Response(200, json={"categories": ["Politics"]})
        )
        got = fcm.blocked_categories(subtrader_id="acct_desk1")
        assert got.categories == ["Politics"]
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/fcm/subtraders/blocked_categories"
        ).mock(return_value=httpx.Response(200, json={"categories": ["Politics", "Sports"]}))
        updated = fcm.update_blocked_categories(
            subtrader_id="acct_desk1", category="Sports", blocked=True
        )
        assert updated.categories == ["Politics", "Sports"]
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "subtrader_id": "acct_desk1",
            "category": "Sports",
            "blocked": True,
        }

    @respx.mock
    def test_event_contract_daily_cap_roundtrip(self, fcm: FcmResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/fcm/subtraders/event_contract_daily_cap"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "subtrader_id": "acct_desk1",
                    "limit": "10000.0000",
                    "executed_utilization": "100.0000",
                    "resting_order_utilization": "50.0000",
                    "pending_order_utilization": "25.0000",
                    "cap_date": "2026-09-20",
                },
            )
        )
        got = fcm.event_contract_daily_cap(subtrader_id="acct_desk1")
        assert got.limit == Decimal("10000.0000")
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/fcm/subtraders/event_contract_daily_cap"
        ).mock(return_value=httpx.Response(200, json={}))
        fcm.update_event_contract_daily_cap(subtrader_id="acct_desk1", limit="5000.00")
        assert json.loads(route.calls[0].request.content) == {
            "subtrader_id": "acct_desk1",
            "limit": "5000.00",
        }
        delete = respx.delete(
            "https://test.kalshi.com/trade-api/v2/fcm/subtraders/event_contract_daily_cap"
        ).mock(return_value=httpx.Response(200, json={}))
        fcm.delete_event_contract_daily_cap(subtrader_id="acct_desk1")
        assert dict(delete.calls[0].request.url.params)["subtrader_id"] == "acct_desk1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_list_and_create(self, async_fcm: AsyncFcmResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/fcm/subtraders").mock(
            return_value=httpx.Response(200, json={"subtraders": []})
        )
        respx.post("https://test.kalshi.com/trade-api/v2/fcm/subtraders").mock(
            return_value=httpx.Response(200, json={"subtrader_id": "acct_a"})
        )
        listed = await async_fcm.list_subtraders()
        created = await async_fcm.create_subtrader(subtrader_suffix="a")
        assert listed.subtraders == []
        assert created.subtrader_id == "acct_a"


_FILL = {
    "fill_id": "fill-1",
    "exchange_index": 0,
    "ticker": "TEST-MKT",
    "taker_outcome_side": "yes",
    "count_fp": "2.00",
    "yes_price_dollars": "0.5600",
    "created_time": "2026-04-12T12:00:00Z",
    "maker_order_id": "maker-1",
    "maker_subtrader_id": "acct_maker",
    "maker_fee_cost": "0.0100",
    "taker_order_id": "taker-1",
    "taker_subtrader_id": "acct_taker",
    "taker_fee_cost": "0.0200",
}

_FCM = "https://test.kalshi.com/trade-api/v2"


class TestFills:
    @respx.mock
    def test_returns_fills(self, fcm: FcmResource) -> None:
        route = respx.get(f"{_FCM}/fcm/fills").mock(
            return_value=httpx.Response(200, json={"fills": [_FILL], "cursor": "p2"})
        )
        resp = fcm.fills(min_ts=100, max_ts=200, cursor="p1")
        params = dict(route.calls[0].request.url.params)
        assert params == {"min_ts": "100", "max_ts": "200", "cursor": "p1"}
        assert len(resp.fills) == 1
        fill = resp.fills[0]
        assert fill.fill_id == "fill-1"
        assert fill.count == Decimal("2.00")
        assert fill.yes_price == Decimal("0.5600")
        assert fill.taker_outcome_side == "yes"
        assert fill.maker_fee_cost == Decimal("0.0100")
        assert fill.taker_fee_cost == Decimal("0.0200")
        assert resp.cursor == "p2"

    @respx.mock
    def test_optional_fields_omitted(self, fcm: FcmResource) -> None:
        respx.get(f"{_FCM}/fcm/fills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fills": [
                        {
                            "fill_id": "fill-2",
                            "exchange_index": 1,
                            "ticker": "TEST-MKT",
                            "taker_outcome_side": "no",
                            "count_fp": "1.00",
                            "yes_price_dollars": "0.1000",
                        }
                    ],
                    "cursor": "",
                },
            )
        )
        resp = fcm.fills()
        fill = resp.fills[0]
        assert fill.maker_order_id is None
        assert fill.maker_fee_cost is None
        assert fill.taker_fee_cost is None
        assert fill.created_time is None
        assert resp.cursor == ""
        assert fill.count == Decimal("1.00")

    def test_requires_auth(self, unauth_fcm: FcmResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_fcm.fills()

    @respx.mock
    def test_server_401(self, fcm: FcmResource) -> None:
        respx.get(f"{_FCM}/fcm/fills").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        with pytest.raises(KalshiAuthError):
            fcm.fills()

    @respx.mock
    def test_fills_all_paginates(self, fcm: FcmResource) -> None:
        respx.get(f"{_FCM}/fcm/fills").mock(
            side_effect=[
                httpx.Response(200, json={"fills": [_FILL], "cursor": "p2"}),
                httpx.Response(
                    200,
                    json={
                        "fills": [{**_FILL, "fill_id": "fill-2"}],
                        "cursor": "",
                    },
                ),
            ]
        )
        ids = [fill.fill_id for fill in fcm.fills_all(min_ts=5, max_pages=5)]
        assert ids == ["fill-1", "fill-2"]

    def test_fills_all_requires_auth(self, unauth_fcm: FcmResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_fcm.fills_all()

    def test_fills_all_rejects_zero_max_pages(self, fcm: FcmResource) -> None:
        with pytest.raises(ValueError, match="max_pages"):
            fcm.fills_all(max_pages=0)

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_fills(self, async_fcm: AsyncFcmResource) -> None:
        route = respx.get(f"{_FCM}/fcm/fills").mock(
            return_value=httpx.Response(200, json={"fills": [_FILL], "cursor": ""})
        )
        resp = await async_fcm.fills(max_ts=9)
        assert dict(route.calls[0].request.url.params) == {"max_ts": "9"}
        assert resp.fills[0].yes_price == Decimal("0.5600")

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_fills_all(self, async_fcm: AsyncFcmResource) -> None:
        respx.get(f"{_FCM}/fcm/fills").mock(
            return_value=httpx.Response(200, json={"fills": [_FILL], "cursor": ""})
        )
        ids = [fill.fill_id async for fill in async_fcm.fills_all()]
        assert ids == ["fill-1"]
