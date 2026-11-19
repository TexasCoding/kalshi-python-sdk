"""Tests for flight disruption market endpoints on MarketsResource (#586)."""

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
    KalshiNotFoundError,
    KalshiRateLimitError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.models.markets import CreateFlightDisruptionMarketRequest
from kalshi.resources.markets import AsyncMarketsResource, MarketsResource

BASE = "https://test.kalshi.com/trade-api/v2"

_CREATE_KWARGS: dict[str, object] = {
    "carrier": "AA",
    "flight_number": "100",
    "departure_airport": "JFK",
    "arrival_airport": "LHR",
    "scheduled_date": "2026-11-25",
    "cover": "cancelled",
}

_CREATE_BODY = {
    "carrier": "AA",
    "flight_number": "100",
    "departure_airport": "JFK",
    "arrival_airport": "LHR",
    "scheduled_date": "2026-11-25",
    "cover": "cancelled",
}

_CREATE_RESPONSE = {
    "cover": "cancelled",
    "event_ticker": "KXRFQFLIGHTC-AA100-JFKLHR-26NOV25",
    "market_ticker": "KXRFQFLIGHTC-AA100-JFKLHR-26NOV25-CXL",
    "created": True,
}

_DELAY_KWARGS: dict[str, object] = {
    **_CREATE_KWARGS,
    "cover": "delayed",
    "delay_basis": "departure",
    "delay_minutes": 120,
}

_DELAY_BODY = {
    **_CREATE_BODY,
    "cover": "delayed",
    "delay_basis": "departure",
    "delay_minutes": 120,
}

_DELAY_RESPONSE = {
    "cover": "delayed",
    "delay_basis": "departure",
    "delay_minutes": 120,
    "event_ticker": "KXRFQFLIGHTD-AA100-JFKLHR-26NOV25",
    "market_ticker": "KXRFQFLIGHTD-AA100-JFKLHR-26NOV25-DEP120",
    "created": True,
}

_FLIGHT = {
    "carrier": "AA",
    "flight_number": "100",
    "airline_name": "American Airlines",
    "departure_airport": "JFK",
    "departure_airport_name": "John F. Kennedy International",
    "departure_city": "New York",
    "departure_country": "US",
    "departure_timezone": "America/New_York",
    "arrival_airport": "LHR",
    "arrival_airport_name": "London Heathrow",
    "arrival_city": "London",
    "arrival_country": "GB",
    "arrival_timezone": "Europe/London",
    "scheduled_date": "2026-11-25",
    "scheduled_departure": "2026-11-25T10:00:00Z",
    "scheduled_arrival": "2026-11-25T22:00:00Z",
    "close_time": "2026-11-25T10:00:00Z",
    "settle_after": "2026-11-25T22:00:00Z",
    "events": [
        {
            "cover": "cancelled",
            "series_ticker": "KXRFQFLIGHTC",
            "event_ticker": "KXRFQFLIGHTC-AA100-JFKLHR-26NOV25",
            "market_ticker": "KXRFQFLIGHTC-AA100-JFKLHR-26NOV25-CXL",
        }
    ],
}

_AVAIL_RESPONSE = {
    "enabled": True,
    "covers": ["cancelled", "delayed", "either"],
    "delay_bases": ["departure", "arrival"],
    "delay_step_minutes": 30,
    "max_delay_minutes": 360,
    "max_days_ahead": 30,
    "min_lead_minutes": 60,
    "departure_countries": ["US"],
}

_FLIGHTS_RESPONSE = {
    "flights": [_FLIGHT],
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


class TestCreateFlightDisruptionMarket:
    @respx.mock
    def test_happy_path(self, markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        resp = markets.create_flight_disruption_market(**_CREATE_KWARGS)
        assert route.calls[0].request.method == "POST"
        assert str(route.calls[0].request.url) == f"{BASE}/flight_disruption_markets"
        body = json.loads(route.calls[0].request.content)
        assert body == _CREATE_BODY
        assert "delay_basis" not in body
        assert "delay_minutes" not in body
        assert resp.cover == "cancelled"
        assert resp.event_ticker == _CREATE_RESPONSE["event_ticker"]
        assert resp.market_ticker == _CREATE_RESPONSE["market_ticker"]
        assert resp.created is True
        assert resp.delay_basis is None
        assert resp.delay_minutes is None

    @respx.mock
    def test_delay_optionals_sent_when_set(self, markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(200, json=_DELAY_RESPONSE)
        )
        resp = markets.create_flight_disruption_market(**_DELAY_KWARGS)
        body = json.loads(route.calls[0].request.content)
        assert body == _DELAY_BODY
        assert resp.cover == "delayed"
        assert resp.delay_basis == "departure"
        assert resp.delay_minutes == 120

    @respx.mock
    def test_request_model_form(self, markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        req = CreateFlightDisruptionMarketRequest(**_CREATE_KWARGS)
        resp = markets.create_flight_disruption_market(request=req)
        assert json.loads(route.calls[0].request.content) == _CREATE_BODY
        assert resp.created is True

    @respx.mock
    def test_request_model_form_with_delay(self, markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(200, json=_DELAY_RESPONSE)
        )
        req = CreateFlightDisruptionMarketRequest(**_DELAY_KWARGS)
        markets.create_flight_disruption_market(request=req)
        assert json.loads(route.calls[0].request.content) == _DELAY_BODY

    def test_request_and_kwargs_exclusive(self, markets: MarketsResource) -> None:
        req = CreateFlightDisruptionMarketRequest(**_CREATE_KWARGS)
        with pytest.raises(TypeError, match="not both"):
            markets.create_flight_disruption_market(request=req, cover="delayed")

    def test_missing_required_kwargs(self, markets: MarketsResource) -> None:
        with pytest.raises(TypeError, match="create_flight_disruption_market"):
            markets.create_flight_disruption_market()  # type: ignore[call-overload]

    def test_extra_field_rejected_by_forbid(self) -> None:
        with pytest.raises(ValidationError):
            CreateFlightDisruptionMarketRequest(
                **_CREATE_KWARGS,
                extra_field="nope",  # type: ignore[call-arg]
            )

    def test_requires_auth(self, unauth_markets: MarketsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_markets.create_flight_disruption_market(**_CREATE_KWARGS)

    @respx.mock
    def test_400_validation_error(self, markets: MarketsResource) -> None:
        respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": "invalid_parameters"}},
            )
        )
        with pytest.raises(KalshiValidationError):
            markets.create_flight_disruption_market(**_CREATE_KWARGS)

    @respx.mock
    def test_404_not_found(self, markets: MarketsResource) -> None:
        respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(404, json={"error": {"code": "not_found"}})
        )
        with pytest.raises(KalshiNotFoundError):
            markets.create_flight_disruption_market(**_CREATE_KWARGS)

    @respx.mock
    def test_409_flight_disruption_market_unavailable(self, markets: MarketsResource) -> None:
        respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(
                409,
                json={"error": {"code": "flight_disruption_market_unavailable"}},
            )
        )
        with pytest.raises(KalshiConflictError):
            markets.create_flight_disruption_market(**_CREATE_KWARGS)

    @respx.mock
    def test_429_rate_limit(self, markets: MarketsResource) -> None:
        respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"code": "flight_disruption_market_limit_exceeded"}},
            )
        )
        with pytest.raises(KalshiRateLimitError):
            markets.create_flight_disruption_market(**_CREATE_KWARGS)

    @respx.mock
    def test_not_retried_on_503(self, retrying_markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            retrying_markets.create_flight_disruption_market(**_CREATE_KWARGS)
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_happy_path(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        resp = await async_markets.create_flight_disruption_market(**_CREATE_KWARGS)
        assert route.calls[0].request.method == "POST"
        body = json.loads(route.calls[0].request.content)
        assert body == _CREATE_BODY
        assert "delay_basis" not in body
        assert resp.created is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_delay_optionals_sent_when_set(
        self, async_markets: AsyncMarketsResource
    ) -> None:
        route = respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(200, json=_DELAY_RESPONSE)
        )
        await async_markets.create_flight_disruption_market(**_DELAY_KWARGS)
        assert json.loads(route.calls[0].request.content) == _DELAY_BODY

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_request_model_form(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        req = CreateFlightDisruptionMarketRequest(**_CREATE_KWARGS)
        await async_markets.create_flight_disruption_market(request=req)
        assert json.loads(route.calls[0].request.content) == _CREATE_BODY

    @pytest.mark.asyncio
    async def test_async_request_and_kwargs_exclusive(
        self, async_markets: AsyncMarketsResource
    ) -> None:
        req = CreateFlightDisruptionMarketRequest(**_CREATE_KWARGS)
        with pytest.raises(TypeError, match="not both"):
            await async_markets.create_flight_disruption_market(request=req, cover="delayed")

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_400(self, async_markets: AsyncMarketsResource) -> None:
        respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": "invalid_parameters"}},
            )
        )
        with pytest.raises(KalshiValidationError):
            await async_markets.create_flight_disruption_market(**_CREATE_KWARGS)

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_404(self, async_markets: AsyncMarketsResource) -> None:
        respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(404, json={"error": {"code": "not_found"}})
        )
        with pytest.raises(KalshiNotFoundError):
            await async_markets.create_flight_disruption_market(**_CREATE_KWARGS)

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_409(self, async_markets: AsyncMarketsResource) -> None:
        respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(
                409,
                json={"error": {"code": "flight_disruption_market_unavailable"}},
            )
        )
        with pytest.raises(KalshiConflictError):
            await async_markets.create_flight_disruption_market(**_CREATE_KWARGS)

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_429(self, async_markets: AsyncMarketsResource) -> None:
        respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"code": "flight_disruption_market_limit_exceeded"}},
            )
        )
        with pytest.raises(KalshiRateLimitError):
            await async_markets.create_flight_disruption_market(**_CREATE_KWARGS)

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
        route = respx.post(f"{BASE}/flight_disruption_markets").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            await retrying.create_flight_disruption_market(**_CREATE_KWARGS)
        assert route.call_count == 1


class TestFlightDisruptionAvailability:
    @respx.mock
    def test_happy_path(self, markets: MarketsResource) -> None:
        route = respx.get(f"{BASE}/flight_disruption_markets/availability").mock(
            return_value=httpx.Response(200, json=_AVAIL_RESPONSE)
        )
        resp = markets.flight_disruption_availability()
        assert route.calls[0].request.method == "GET"
        assert str(route.calls[0].request.url) == f"{BASE}/flight_disruption_markets/availability"
        assert resp.enabled is True
        assert resp.covers == ["cancelled", "delayed", "either"]
        assert resp.delay_bases == ["departure", "arrival"]
        assert resp.delay_step_minutes == 30
        assert resp.max_delay_minutes == 360
        assert resp.max_days_ahead == 30
        assert resp.min_lead_minutes == 60
        assert resp.departure_countries == ["US"]

    @respx.mock
    def test_empty_lists(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/availability").mock(
            return_value=httpx.Response(
                200,
                json={
                    "enabled": False,
                    "covers": [],
                    "delay_bases": [],
                    "delay_step_minutes": 30,
                    "max_delay_minutes": 360,
                    "max_days_ahead": 0,
                    "min_lead_minutes": 0,
                    "departure_countries": [],
                },
            )
        )
        resp = markets.flight_disruption_availability()
        assert resp.enabled is False
        assert resp.covers == []
        assert resp.delay_bases == []
        assert resp.departure_countries == []

    @respx.mock
    def test_null_lists_coerced_to_empty(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/availability").mock(
            return_value=httpx.Response(
                200,
                json={
                    "enabled": True,
                    "covers": None,
                    "delay_bases": None,
                    "delay_step_minutes": 30,
                    "max_delay_minutes": 360,
                    "max_days_ahead": 30,
                    "min_lead_minutes": 60,
                    "departure_countries": None,
                },
            )
        )
        resp = markets.flight_disruption_availability()
        assert resp.covers == []
        assert resp.delay_bases == []
        assert resp.departure_countries == []

    @respx.mock
    def test_works_without_auth(self, unauth_markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/availability").mock(
            return_value=httpx.Response(200, json=_AVAIL_RESPONSE)
        )
        resp = unauth_markets.flight_disruption_availability()
        assert resp.enabled is True

    @respx.mock
    def test_400_validation_error(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/availability").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            markets.flight_disruption_availability()

    @respx.mock
    def test_429_rate_limit(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/availability").mock(
            return_value=httpx.Response(429, json={"error": {"code": "too_many_requests"}})
        )
        with pytest.raises(KalshiRateLimitError):
            markets.flight_disruption_availability()

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_happy_path(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.get(f"{BASE}/flight_disruption_markets/availability").mock(
            return_value=httpx.Response(200, json=_AVAIL_RESPONSE)
        )
        resp = await async_markets.flight_disruption_availability()
        assert route.calls[0].request.method == "GET"
        assert resp.enabled is True
        assert resp.covers[0] == "cancelled"

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_empty_lists(self, async_markets: AsyncMarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/availability").mock(
            return_value=httpx.Response(
                200,
                json={
                    "enabled": False,
                    "covers": [],
                    "delay_bases": [],
                    "delay_step_minutes": 30,
                    "max_delay_minutes": 360,
                    "max_days_ahead": 0,
                    "min_lead_minutes": 0,
                    "departure_countries": [],
                },
            )
        )
        resp = await async_markets.flight_disruption_availability()
        assert resp.enabled is False
        assert resp.covers == []
        assert resp.delay_bases == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_400(self, async_markets: AsyncMarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/availability").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            await async_markets.flight_disruption_availability()


class TestListFlights:
    @respx.mock
    def test_happy_path(self, markets: MarketsResource) -> None:
        route = respx.get(f"{BASE}/flight_disruption_markets/flights").mock(
            return_value=httpx.Response(200, json=_FLIGHTS_RESPONSE)
        )
        resp = markets.list_flights(carrier="AA", flight_number="100", date="2026-11-25")
        assert route.calls[0].request.method == "GET"
        params = dict(route.calls[0].request.url.params)
        assert params == {"carrier": "AA", "flight_number": "100", "date": "2026-11-25"}
        assert len(resp.flights) == 1
        flight = resp.flights[0]
        assert flight.carrier == "AA"
        assert flight.flight_number == "100"
        assert flight.departure_airport == "JFK"
        assert flight.arrival_airport == "LHR"
        assert flight.scheduled_date == "2026-11-25"
        assert flight.airline_name == "American Airlines"
        assert flight.events[0].cover == "cancelled"
        assert flight.events[0].series_ticker == "KXRFQFLIGHTC"
        assert flight.events[0].market_ticker == "KXRFQFLIGHTC-AA100-JFKLHR-26NOV25-CXL"
        assert flight.scheduled_departure is not None
        assert flight.requested_carrier is None

    def test_missing_required_kwargs(self, markets: MarketsResource) -> None:
        with pytest.raises(TypeError, match="list_flights"):
            markets.list_flights()  # type: ignore[call-arg]

    def test_requires_auth(self, unauth_markets: MarketsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_markets.list_flights(carrier="AA", flight_number="100", date="2026-11-25")

    @respx.mock
    def test_null_lists_coerced_to_empty(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/flights").mock(
            return_value=httpx.Response(
                200,
                json={
                    "flights": [
                        {
                            "carrier": "AA",
                            "flight_number": "100",
                            "departure_airport": "JFK",
                            "arrival_airport": "LHR",
                            "scheduled_date": "2026-11-25",
                            "events": None,
                        }
                    ]
                },
            )
        )
        resp = markets.list_flights(carrier="AA", flight_number="100", date="2026-11-25")
        assert resp.flights[0].events == []

    @respx.mock
    def test_null_flights_coerced_to_empty(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/flights").mock(
            return_value=httpx.Response(200, json={"flights": None})
        )
        resp = markets.list_flights(carrier="AA", flight_number="100", date="2026-11-25")
        assert resp.flights == []

    @respx.mock
    def test_400_validation_error(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/flights").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            markets.list_flights(carrier="AA", flight_number="100", date="2026-11-25")

    @respx.mock
    def test_404_not_found(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/flights").mock(
            return_value=httpx.Response(404, json={"error": {"code": "not_found"}})
        )
        with pytest.raises(KalshiNotFoundError):
            markets.list_flights(carrier="AA", flight_number="100", date="2026-11-25")

    @respx.mock
    def test_409_conflict(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/flights").mock(
            return_value=httpx.Response(409, json={"error": {"code": "conflict"}})
        )
        with pytest.raises(KalshiConflictError):
            markets.list_flights(carrier="AA", flight_number="100", date="2026-11-25")

    @respx.mock
    def test_429_rate_limit(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/flights").mock(
            return_value=httpx.Response(
                429, json={"error": {"code": "flight_lookup_limit_exceeded"}}
            )
        )
        with pytest.raises(KalshiRateLimitError):
            markets.list_flights(carrier="AA", flight_number="100", date="2026-11-25")

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_happy_path(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.get(f"{BASE}/flight_disruption_markets/flights").mock(
            return_value=httpx.Response(200, json=_FLIGHTS_RESPONSE)
        )
        resp = await async_markets.list_flights(
            carrier="AA", flight_number="100", date="2026-11-25"
        )
        assert route.calls[0].request.method == "GET"
        params = dict(route.calls[0].request.url.params)
        assert params == {"carrier": "AA", "flight_number": "100", "date": "2026-11-25"}
        assert resp.flights[0].departure_airport == "JFK"

    @pytest.mark.asyncio
    async def test_async_requires_auth(self, config: KalshiConfig) -> None:
        unauth = AsyncMarketsResource(AsyncTransport(None, config))
        with pytest.raises(AuthRequiredError):
            await unauth.list_flights(carrier="AA", flight_number="100", date="2026-11-25")

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_400(self, async_markets: AsyncMarketsResource) -> None:
        respx.get(f"{BASE}/flight_disruption_markets/flights").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            await async_markets.list_flights(carrier="AA", flight_number="100", date="2026-11-25")
