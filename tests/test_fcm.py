"""Tests for kalshi.resources.fcm — FCM orders + positions."""

from __future__ import annotations

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import AuthRequiredError, KalshiAuthError
from kalshi.resources.fcm import AsyncFcmResource, FcmResource


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
    test_auth: KalshiAuth, config: KalshiConfig,
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
                        {
                            "order_id": "ord-1",
                            "user_id": "user-1",
                            "client_order_id": "client-1",
                            "ticker": "TEST-MKT",
                            "side": "yes",
                            "action": "buy",
                            "type": "limit",
                            "status": "resting",
                            "yes_price_dollars": "0.55",
                        },
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
                200, json={"market_positions": [], "event_positions": []},
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
                200, json={"market_positions": [], "event_positions": []},
            )
        )
        result = await async_fcm.positions(subtrader_id="sub-1")
        assert result.market_positions == []
