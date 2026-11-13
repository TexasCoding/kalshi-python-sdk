"""Tests for concert cancellation market endpoints on MarketsResource (#582)."""

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
    KalshiRateLimitError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.models.markets import CreateConcertCancellationMarketRequest
from kalshi.resources.markets import AsyncMarketsResource, MarketsResource

BASE = "https://test.kalshi.com/trade-api/v2"

_CREATE_KWARGS: dict[str, object] = {
    "jambase_event_id": "jambase:16543035",
    "scheduled_date": "2026-11-20",
    "cover": "postponed",
}

_CREATE_BODY = {
    "jambase_event_id": "jambase:16543035",
    "scheduled_date": "2026-11-20",
    "cover": "postponed",
}

_CREATE_RESPONSE = {
    "cover": "postponed",
    "event_ticker": "KXRFQCONCERTP-JB16543035-26NOV20",
    "market_ticker": "KXRFQCONCERTP-JB16543035-26NOV20-PPD",
    "created": True,
}

_CONCERT = {
    "jambase_event_id": "jambase:16543035",
    "name": "Artist at Venue",
    "lineup": ["Artist"],
    "venue_name": "Madison Square Garden",
    "timezone": "America/New_York",
    "scheduled_date": "2026-11-20",
    "markets": [
        {
            "cover": "postponed",
            "event_ticker": "KXRFQCONCERTP-JB16543035-26NOV20",
            "market_ticker": "KXRFQCONCERTP-JB16543035-26NOV20-PPD",
        }
    ],
}

_AVAIL_RESPONSE = {
    "enabled": True,
    "covers": ["postponed", "cancelled", "either"],
    "max_days_ahead": 60,
    "metros": [
        {
            "id": "jambase:1",
            "name": "New York",
            "latitude": 40.7128,
            "longitude": -74.006,
            "upcoming_shows": 12,
        }
    ],
}

_CONCERTS_RESPONSE = {
    "concerts": [_CONCERT],
    "page": 1,
    "total_pages": 3,
}

_SEARCH_RESPONSE = {
    "concerts": [_CONCERT],
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


class TestCreateConcertCancellationMarket:
    @respx.mock
    def test_happy_path(self, markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        resp = markets.create_concert_cancellation_market(**_CREATE_KWARGS)
        assert route.calls[0].request.method == "POST"
        assert str(route.calls[0].request.url) == f"{BASE}/concert_cancellation_markets"
        body = json.loads(route.calls[0].request.content)
        assert body == _CREATE_BODY
        assert resp.cover == "postponed"
        assert resp.event_ticker == _CREATE_RESPONSE["event_ticker"]
        assert resp.market_ticker == _CREATE_RESPONSE["market_ticker"]
        assert resp.created is True

    @respx.mock
    def test_request_model_form(self, markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        req = CreateConcertCancellationMarketRequest(**_CREATE_KWARGS)
        resp = markets.create_concert_cancellation_market(request=req)
        assert json.loads(route.calls[0].request.content) == _CREATE_BODY
        assert resp.created is True

    def test_request_and_kwargs_exclusive(self, markets: MarketsResource) -> None:
        req = CreateConcertCancellationMarketRequest(**_CREATE_KWARGS)
        with pytest.raises(TypeError, match="not both"):
            markets.create_concert_cancellation_market(request=req, cover="cancelled")

    def test_missing_required_kwargs(self, markets: MarketsResource) -> None:
        with pytest.raises(TypeError, match="create_concert_cancellation_market"):
            markets.create_concert_cancellation_market()  # type: ignore[call-overload]

    def test_extra_field_rejected_by_forbid(self) -> None:
        with pytest.raises(ValidationError):
            CreateConcertCancellationMarketRequest(
                **_CREATE_KWARGS,
                extra_field="nope",  # type: ignore[call-arg]
            )

    def test_requires_auth(self, unauth_markets: MarketsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_markets.create_concert_cancellation_market(**_CREATE_KWARGS)

    @respx.mock
    def test_409_concert_cancellation_market_unavailable(self, markets: MarketsResource) -> None:
        respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(
                409,
                json={"error": {"code": "concert_cancellation_market_unavailable"}},
            )
        )
        with pytest.raises(KalshiConflictError):
            markets.create_concert_cancellation_market(**_CREATE_KWARGS)

    @respx.mock
    def test_429_rate_limit(self, markets: MarketsResource) -> None:
        respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"code": "concert_cancellation_market_limit_exceeded"}},
            )
        )
        with pytest.raises(KalshiRateLimitError):
            markets.create_concert_cancellation_market(**_CREATE_KWARGS)

    @respx.mock
    def test_400_validation_error(self, markets: MarketsResource) -> None:
        respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": "invalid_parameters"}},
            )
        )
        with pytest.raises(KalshiValidationError):
            markets.create_concert_cancellation_market(**_CREATE_KWARGS)

    @respx.mock
    def test_not_retried_on_503(self, retrying_markets: MarketsResource) -> None:
        route = respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            retrying_markets.create_concert_cancellation_market(**_CREATE_KWARGS)
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_happy_path(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        resp = await async_markets.create_concert_cancellation_market(**_CREATE_KWARGS)
        assert route.calls[0].request.method == "POST"
        body = json.loads(route.calls[0].request.content)
        assert body == _CREATE_BODY
        assert resp.created is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_request_model_form(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(200, json=_CREATE_RESPONSE)
        )
        req = CreateConcertCancellationMarketRequest(**_CREATE_KWARGS)
        await async_markets.create_concert_cancellation_market(request=req)
        assert json.loads(route.calls[0].request.content) == _CREATE_BODY

    @pytest.mark.asyncio
    async def test_async_request_and_kwargs_exclusive(
        self, async_markets: AsyncMarketsResource
    ) -> None:
        req = CreateConcertCancellationMarketRequest(**_CREATE_KWARGS)
        with pytest.raises(TypeError, match="not both"):
            await async_markets.create_concert_cancellation_market(request=req, cover="cancelled")

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_409(self, async_markets: AsyncMarketsResource) -> None:
        respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(
                409,
                json={"error": {"code": "concert_cancellation_market_unavailable"}},
            )
        )
        with pytest.raises(KalshiConflictError):
            await async_markets.create_concert_cancellation_market(**_CREATE_KWARGS)

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_429(self, async_markets: AsyncMarketsResource) -> None:
        respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"code": "concert_cancellation_market_limit_exceeded"}},
            )
        )
        with pytest.raises(KalshiRateLimitError):
            await async_markets.create_concert_cancellation_market(**_CREATE_KWARGS)

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_400(self, async_markets: AsyncMarketsResource) -> None:
        respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": "invalid_parameters"}},
            )
        )
        with pytest.raises(KalshiValidationError):
            await async_markets.create_concert_cancellation_market(**_CREATE_KWARGS)

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
        route = respx.post(f"{BASE}/concert_cancellation_markets").mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            await retrying.create_concert_cancellation_market(**_CREATE_KWARGS)
        assert route.call_count == 1


class TestConcertCancellationAvailability:
    @respx.mock
    def test_happy_path(self, markets: MarketsResource) -> None:
        route = respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(200, json=_AVAIL_RESPONSE)
        )
        resp = markets.concert_cancellation_availability()
        assert route.calls[0].request.method == "GET"
        assert (
            str(route.calls[0].request.url) == f"{BASE}/concert_cancellation_markets/availability"
        )
        assert "date_from" not in route.calls[0].request.url.params
        assert "date_to" not in route.calls[0].request.url.params
        assert resp.enabled is True
        assert resp.covers == ["postponed", "cancelled", "either"]
        assert resp.max_days_ahead == 60
        assert len(resp.metros) == 1
        assert resp.metros[0].id == "jambase:1"
        assert resp.metros[0].name == "New York"
        assert resp.metros[0].latitude == 40.7128
        assert resp.metros[0].upcoming_shows == 12

    @respx.mock
    def test_optional_query_params_sent_when_set(self, markets: MarketsResource) -> None:
        route = respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(200, json=_AVAIL_RESPONSE)
        )
        markets.concert_cancellation_availability(date_from="2026-11-20", date_to="2026-12-01")
        params = dict(route.calls[0].request.url.params)
        assert params == {"date_from": "2026-11-20", "date_to": "2026-12-01"}

    @respx.mock
    def test_empty_lists(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(
                200,
                json={"enabled": False, "covers": [], "max_days_ahead": 0, "metros": []},
            )
        )
        resp = markets.concert_cancellation_availability()
        assert resp.enabled is False
        assert resp.covers == []
        assert resp.metros == []

    @respx.mock
    def test_null_lists_coerced_to_empty(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(
                200,
                json={
                    "enabled": True,
                    "covers": None,
                    "max_days_ahead": 30,
                    "metros": None,
                },
            )
        )
        resp = markets.concert_cancellation_availability()
        assert resp.covers == []
        assert resp.metros == []

    @respx.mock
    def test_works_without_auth(self, unauth_markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(200, json=_AVAIL_RESPONSE)
        )
        resp = unauth_markets.concert_cancellation_availability()
        assert resp.enabled is True

    @respx.mock
    def test_400_validation_error(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            markets.concert_cancellation_availability()

    @respx.mock
    def test_429_rate_limit(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(429, json={"error": {"code": "too_many_requests"}})
        )
        with pytest.raises(KalshiRateLimitError):
            markets.concert_cancellation_availability()

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_happy_path(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(200, json=_AVAIL_RESPONSE)
        )
        resp = await async_markets.concert_cancellation_availability()
        assert route.calls[0].request.method == "GET"
        assert "date_from" not in route.calls[0].request.url.params
        assert resp.enabled is True
        assert resp.metros[0].id == "jambase:1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_optional_query_params(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(200, json=_AVAIL_RESPONSE)
        )
        await async_markets.concert_cancellation_availability(date_from="2026-11-20")
        params = dict(route.calls[0].request.url.params)
        assert params == {"date_from": "2026-11-20"}
        assert "date_to" not in params

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_empty_lists(self, async_markets: AsyncMarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(
                200,
                json={"enabled": False, "covers": [], "max_days_ahead": 0, "metros": []},
            )
        )
        resp = await async_markets.concert_cancellation_availability()
        assert resp.enabled is False
        assert resp.covers == []
        assert resp.metros == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_400(self, async_markets: AsyncMarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/availability").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            await async_markets.concert_cancellation_availability()


class TestListConcerts:
    @respx.mock
    def test_happy_path(self, markets: MarketsResource) -> None:
        route = respx.get(f"{BASE}/concert_cancellation_markets/concerts").mock(
            return_value=httpx.Response(200, json=_CONCERTS_RESPONSE)
        )
        resp = markets.list_concerts(metro_id="jambase:1")
        assert route.calls[0].request.method == "GET"
        params = dict(route.calls[0].request.url.params)
        assert params == {"metro_id": "jambase:1"}
        assert resp.page == 1
        assert resp.total_pages == 3
        assert len(resp.concerts) == 1
        concert = resp.concerts[0]
        assert concert.jambase_event_id == "jambase:16543035"
        assert concert.name == "Artist at Venue"
        assert concert.lineup == ["Artist"]
        assert concert.markets[0].cover == "postponed"
        assert concert.start_time is None

    @respx.mock
    def test_optional_query_params_sent_when_set(self, markets: MarketsResource) -> None:
        route = respx.get(f"{BASE}/concert_cancellation_markets/concerts").mock(
            return_value=httpx.Response(200, json=_CONCERTS_RESPONSE)
        )
        markets.list_concerts(
            metro_id="jambase:1",
            date_from="2026-11-20",
            date_to="2026-12-01",
            page=2,
        )
        params = dict(route.calls[0].request.url.params)
        assert params == {
            "metro_id": "jambase:1",
            "date_from": "2026-11-20",
            "date_to": "2026-12-01",
            "page": "2",
        }

    def test_missing_required_kwargs(self, markets: MarketsResource) -> None:
        with pytest.raises(TypeError, match="metro_id"):
            markets.list_concerts()  # type: ignore[call-arg]

    def test_requires_auth(self, unauth_markets: MarketsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_markets.list_concerts(metro_id="jambase:1")

    @respx.mock
    def test_null_lists_coerced_to_empty(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/concerts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "concerts": [
                        {
                            "jambase_event_id": "jambase:1",
                            "name": "Show",
                            "lineup": None,
                            "venue_name": "Venue",
                            "timezone": "America/New_York",
                            "scheduled_date": "2026-11-20",
                            "markets": None,
                        }
                    ],
                    "page": 1,
                    "total_pages": 1,
                },
            )
        )
        resp = markets.list_concerts(metro_id="jambase:1")
        assert resp.concerts[0].lineup == []
        assert resp.concerts[0].markets == []

    @respx.mock
    def test_null_concerts_coerced_to_empty(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/concerts").mock(
            return_value=httpx.Response(
                200, json={"concerts": None, "page": 1, "total_pages": 0}
            )
        )
        resp = markets.list_concerts(metro_id="jambase:1")
        assert resp.concerts == []

    @respx.mock
    def test_400_validation_error(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/concerts").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            markets.list_concerts(metro_id="jambase:1")

    @respx.mock
    def test_429_rate_limit(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/concerts").mock(
            return_value=httpx.Response(429, json={"error": {"code": "too_many_requests"}})
        )
        with pytest.raises(KalshiRateLimitError):
            markets.list_concerts(metro_id="jambase:1")

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_happy_path(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.get(f"{BASE}/concert_cancellation_markets/concerts").mock(
            return_value=httpx.Response(200, json=_CONCERTS_RESPONSE)
        )
        resp = await async_markets.list_concerts(metro_id="jambase:1")
        assert route.calls[0].request.method == "GET"
        params = dict(route.calls[0].request.url.params)
        assert params == {"metro_id": "jambase:1"}
        assert resp.concerts[0].venue_name == "Madison Square Garden"

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_optional_query_params(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.get(f"{BASE}/concert_cancellation_markets/concerts").mock(
            return_value=httpx.Response(200, json=_CONCERTS_RESPONSE)
        )
        await async_markets.list_concerts(metro_id="jambase:1", page=2)
        params = dict(route.calls[0].request.url.params)
        assert params == {"metro_id": "jambase:1", "page": "2"}

    @pytest.mark.asyncio
    async def test_async_requires_auth(self, config: KalshiConfig) -> None:
        unauth = AsyncMarketsResource(AsyncTransport(None, config))
        with pytest.raises(AuthRequiredError):
            await unauth.list_concerts(metro_id="jambase:1")

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_400(self, async_markets: AsyncMarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/concerts").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            await async_markets.list_concerts(metro_id="jambase:1")


class TestSearchConcerts:
    @respx.mock
    def test_happy_path(self, markets: MarketsResource) -> None:
        route = respx.get(f"{BASE}/concert_cancellation_markets/concerts/search").mock(
            return_value=httpx.Response(200, json=_SEARCH_RESPONSE)
        )
        resp = markets.search_concerts(q="Artist")
        assert route.calls[0].request.method == "GET"
        params = dict(route.calls[0].request.url.params)
        assert params == {"q": "Artist"}
        assert len(resp.concerts) == 1
        assert resp.concerts[0].name == "Artist at Venue"

    def test_missing_required_kwargs(self, markets: MarketsResource) -> None:
        with pytest.raises(TypeError, match="search_concerts"):
            markets.search_concerts()  # type: ignore[call-arg]

    def test_requires_auth(self, unauth_markets: MarketsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_markets.search_concerts(q="Artist")

    @respx.mock
    def test_null_lists_coerced_to_empty(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/concerts/search").mock(
            return_value=httpx.Response(200, json={"concerts": None})
        )
        resp = markets.search_concerts(q="Artist")
        assert resp.concerts == []

    @respx.mock
    def test_400_validation_error(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/concerts/search").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            markets.search_concerts(q="Artist")

    @respx.mock
    def test_429_rate_limit(self, markets: MarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/concerts/search").mock(
            return_value=httpx.Response(
                429, json={"error": {"code": "concert_search_limit_exceeded"}}
            )
        )
        with pytest.raises(KalshiRateLimitError):
            markets.search_concerts(q="Artist")

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_happy_path(self, async_markets: AsyncMarketsResource) -> None:
        route = respx.get(f"{BASE}/concert_cancellation_markets/concerts/search").mock(
            return_value=httpx.Response(200, json=_SEARCH_RESPONSE)
        )
        resp = await async_markets.search_concerts(q="Artist")
        assert route.calls[0].request.method == "GET"
        params = dict(route.calls[0].request.url.params)
        assert params == {"q": "Artist"}
        assert resp.concerts[0].jambase_event_id == "jambase:16543035"

    @pytest.mark.asyncio
    async def test_async_requires_auth(self, config: KalshiConfig) -> None:
        unauth = AsyncMarketsResource(AsyncTransport(None, config))
        with pytest.raises(AuthRequiredError):
            await unauth.search_concerts(q="Artist")

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_400(self, async_markets: AsyncMarketsResource) -> None:
        respx.get(f"{BASE}/concert_cancellation_markets/concerts/search").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            await async_markets.search_concerts(q="Artist")
