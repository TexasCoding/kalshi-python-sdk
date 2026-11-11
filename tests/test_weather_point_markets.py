"""Tests for weather point market endpoints on MarketsResource (#578)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import (
    AuthRequiredError,
    KalshiConflictError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.models.markets import CreateWeatherPointMarketRequest
from kalshi.resources.markets import AsyncMarketsResource, MarketsResource

BASE = "https://test.kalshi.com/trade-api/v2"

_CREATE_KWARGS: dict[str, object] = {
    "latitude": 0.0,
    "longitude": -73.965,
    "variable": "precip_hours",
    "strike_type": "greater",
    "date": "2026-11-11",
    "start_hour": 0,
    "end_hour": 24,
    "timezone": "America/New_York",
}

_CREATE_BODY = {
    "latitude": 0.0,
    "longitude": -73.965,
    "variable": "precip_hours",
    "strike_type": "greater",
    "date": "2026-11-11",
    "start_hour": 0,
    "end_hour": 24,
    "timezone": "America/New_York",
}

_CREATE_RESPONSE = {
    "event_ticker": "KXRFQ-E",
    "market_ticker": "KXRFQRAINHOURS-00000N73965W-26NOV1100Z-24H-G2",
    "created": True,
    "latitude": 0.0,
    "longitude": -73.965,
}

_AVAIL_RESPONSE = {
    "enabled": True,
    "domains": [
        {"name": "conus", "north": 49.0, "south": 24.0, "west": -125.0, "east": -66.0},
    ],
    "variables": [
        {"variable": "precip_hours", "domains": ["conus"]},
    ],
}


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url=BASE,
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def markets(test_auth: KalshiAuth, config: KalshiConfig) -> MarketsResource:
    return MarketsResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_markets(test_auth: KalshiAuth, config: KalshiConfig) -> AsyncMarketsResource:
    return AsyncMarketsResource(AsyncTransport(test_auth, config))


@pytest.fixture
def unauth_markets(config: KalshiConfig) -> MarketsResource:
    return MarketsResource(SyncTransport(None, config))


@pytest.fixture
def retrying_markets(test_auth: KalshiAuth) -> MarketsResource:
    return MarketsResource(
        SyncTransport(
            test_auth,
            KalshiConfig(
                base_url=BASE,
                timeout=5.0,
                max_retries=2,
                retry_base_delay=0.01,
                retry_max_delay=0.05,
            ),
        )
    )


class TestCreateWeatherPointMarket:
    @respx.mock
    def test_happy_path(self, markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/weather_point_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        resp = markets.create_weather_point_market(**_CREATE_KWARGS)
        assert route.calls[0].request.method == "POST"
        assert str(route.calls[0].request.url) == f"{BASE}/weather_point_markets"
        body = json.loads(route.calls[0].request.content)
        assert body == _CREATE_BODY
        assert "floor_value" not in body
        assert "cap_value" not in body
        assert body["latitude"] == 0.0
        assert resp.event_ticker == "KXRFQ-E"
        assert resp.market_ticker == _CREATE_RESPONSE["market_ticker"]
        assert resp.created is True
        assert resp.latitude == 0.0
        assert resp.longitude == -73.965

    @respx.mock
    def test_request_model_form(self, markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/weather_point_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        req = CreateWeatherPointMarketRequest(**_CREATE_KWARGS)
        resp = markets.create_weather_point_market(request=req)
        assert json.loads(route.calls[0].request.content) == _CREATE_BODY
        assert resp.created is True

    def test_request_and_kwargs_exclusive(self, markets: MarketsResource) -> None:
        req = CreateWeatherPointMarketRequest(**_CREATE_KWARGS)
        with pytest.raises(TypeError, match="not both"):
            markets.create_weather_point_market(request=req, latitude=40.785)

    def test_missing_required_kwargs(self, markets: MarketsResource) -> None:
        with pytest.raises(TypeError, match="create_weather_point_market"):
            markets.create_weather_point_market()  # type: ignore[call-overload]

    def test_extra_field_rejected_by_forbid(self) -> None:
        with pytest.raises(ValidationError):
            CreateWeatherPointMarketRequest(
                **_CREATE_KWARGS,
                extra_field="nope",  # type: ignore[call-arg]
            )

    def test_requires_auth(self, unauth_markets: MarketsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_markets.create_weather_point_market(**_CREATE_KWARGS)

    @respx.mock
    def test_409_weather_point_market_unavailable(self, markets: MarketsResource) -> None:
        respx.post(f"{BASE}/weather_point_markets").mock(
            return_value=httpx.Response(
                409,
                json={"error": {"code": "weather_point_market_unavailable"}},
            )
        )
        with pytest.raises(KalshiConflictError):
            markets.create_weather_point_market(**_CREATE_KWARGS)

    @respx.mock
    def test_400_validation_error(self, markets: MarketsResource) -> None:
        respx.post(f"{BASE}/weather_point_markets").mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": "invalid_parameters"}},
            )
        )
        with pytest.raises(KalshiValidationError):
            markets.create_weather_point_market(**_CREATE_KWARGS)

    @respx.mock
    def test_not_retried_on_503(self, retrying_markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/weather_point_markets").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            retrying_markets.create_weather_point_market(**_CREATE_KWARGS)
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_happy_path(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.post(f"{BASE}/weather_point_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        resp = await async_markets.create_weather_point_market(**_CREATE_KWARGS)
        assert route.calls[0].request.method == "POST"
        body = json.loads(route.calls[0].request.content)
        assert body == _CREATE_BODY
        assert "floor_value" not in body
        assert body["latitude"] == 0.0
        assert resp.created is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_request_model_form(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.post(f"{BASE}/weather_point_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        req = CreateWeatherPointMarketRequest(**_CREATE_KWARGS)
        await async_markets.create_weather_point_market(request=req)
        assert json.loads(route.calls[0].request.content) == _CREATE_BODY

    @pytest.mark.asyncio
    async def test_async_request_and_kwargs_exclusive(
        self, async_markets: AsyncMarketsResource
    ) -> None:
        req = CreateWeatherPointMarketRequest(**_CREATE_KWARGS)
        with pytest.raises(TypeError, match="not both"):
            await async_markets.create_weather_point_market(request=req, latitude=40.785)

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_409(self, async_markets: AsyncMarketsResource) -> None:
        respx.post(f"{BASE}/weather_point_markets").mock(
            return_value=httpx.Response(
                409,
                json={"error": {"code": "weather_point_market_unavailable"}},
            )
        )
        with pytest.raises(KalshiConflictError):
            await async_markets.create_weather_point_market(**_CREATE_KWARGS)

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_400(self, async_markets: AsyncMarketsResource) -> None:
        respx.post(f"{BASE}/weather_point_markets").mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": "invalid_parameters"}},
            )
        )
        with pytest.raises(KalshiValidationError):
            await async_markets.create_weather_point_market(**_CREATE_KWARGS)

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_not_retried_on_503(self, test_auth: KalshiAuth) -> None:
        retrying = AsyncMarketsResource(
            AsyncTransport(
                test_auth,
                KalshiConfig(
                    base_url=BASE,
                    timeout=5.0,
                    max_retries=2,
                    retry_base_delay=0.01,
                    retry_max_delay=0.05,
                ),
            )
        )
        route = respx.post(f"{BASE}/weather_point_markets").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            await retrying.create_weather_point_market(**_CREATE_KWARGS)
        assert route.call_count == 1


class TestWeatherPointAvailability:
    @respx.mock
    def test_happy_path(self, markets: MarketsResource) -> None:
        route = respx.get(f"{BASE}/weather_point_markets/availability").mock(
            return_value=httpx.Response(200, json=_AVAIL_RESPONSE)
        )
        resp = markets.weather_point_availability()
        assert route.calls[0].request.method == "GET"
        assert str(route.calls[0].request.url) == f"{BASE}/weather_point_markets/availability"
        assert resp.enabled is True
        assert len(resp.domains) == 1
        assert resp.domains[0].name == "conus"
        assert resp.domains[0].north == 49.0
        assert resp.variables[0].variable == "precip_hours"
        assert resp.variables[0].domains == ["conus"]

    @respx.mock
    def test_empty_lists(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/weather_point_markets/availability").mock(
            return_value=httpx.Response(
                200, json={"enabled": False, "domains": [], "variables": []}
            )
        )
        resp = markets.weather_point_availability()
        assert resp.enabled is False
        assert resp.domains == []
        assert resp.variables == []

    @respx.mock
    def test_null_lists_coerced_to_empty(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/weather_point_markets/availability").mock(
            return_value=httpx.Response(
                200,
                json={
                    "enabled": True,
                    "domains": None,
                    "variables": [{"variable": "max_temp", "domains": None}],
                },
            )
        )
        resp = markets.weather_point_availability()
        assert resp.domains == []
        assert resp.variables[0].domains == []

    @respx.mock
    def test_400_validation_error(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/weather_point_markets/availability").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            markets.weather_point_availability()

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_happy_path(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.get(f"{BASE}/weather_point_markets/availability").mock(
            return_value=httpx.Response(200, json=_AVAIL_RESPONSE)
        )
        resp = await async_markets.weather_point_availability()
        assert route.calls[0].request.method == "GET"
        assert resp.enabled is True
        assert resp.domains[0].name == "conus"

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_empty_lists(self, async_markets: AsyncMarketsResource) -> None:
        respx.get(f"{BASE}/weather_point_markets/availability").mock(
            return_value=httpx.Response(
                200, json={"enabled": False, "domains": [], "variables": []}
            )
        )
        resp = await async_markets.weather_point_availability()
        assert resp.enabled is False
        assert resp.domains == []
        assert resp.variables == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_400(self, async_markets: AsyncMarketsResource) -> None:
        respx.get(f"{BASE}/weather_point_markets/availability").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            await async_markets.weather_point_availability()
