"""Tests for kalshi.resources.incentive_programs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiServerError
from kalshi.models.incentive_programs import IncentiveProgram, IncentiveSchedule
from kalshi.resources.incentive_programs import (
    AsyncIncentiveProgramsResource,
    IncentiveProgramsResource,
)
from tests._model_fixtures import incentive_program_dict


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def resource(
    test_auth: KalshiAuth,
    config: KalshiConfig,
) -> IncentiveProgramsResource:
    return IncentiveProgramsResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_resource(
    test_auth: KalshiAuth,
    config: KalshiConfig,
) -> AsyncIncentiveProgramsResource:
    return AsyncIncentiveProgramsResource(AsyncTransport(test_auth, config))


_SAMPLE_PROGRAM = incentive_program_dict(
    id="prog-1",
    market_id="mkt-abc",
    market_ticker="TEST-MKT",
    incentive_type="liquidity",
    start_date="2026-04-01T00:00:00Z",
    end_date="2026-04-30T23:59:59Z",
    period_reward=1_000_000,  # centi-cents
    paid_out=False,
    discount_factor_bps=25,
    target_size_fp="100.5000",
)

_BASE = "https://test.kalshi.com/trade-api/v2"

_SAMPLE_SCHEDULE = {
    "series_ticker": "KXHIGHNY",
    "series_title": "Highest temperature in NYC",
    "series_category": "Climate and Weather",
    "event_ticker": "KXHIGHNY-24JAN01",
    "event_title": "Highest temperature in NYC on Jan 1",
    "incentive_type": "liquidity",
    "source": "weather-liquidity",
    "reward": 1_000_000,
    "window_days": 7,
    "discount_factor_bps": 25,
    "target_size_fp": "100.00",
    "ends": "2026-12-31T00:00:00Z",
    "description": "Weekly liquidity on NYC high-temp markets",
    "all_markets": True,
    "posted_ts": "2026-01-01T00:00:00Z",
    "updated_ts": "2026-01-02T12:00:00Z",
}

_SAMPLE_SCHEDULE_OPEN_ENDED = {
    **_SAMPLE_SCHEDULE,
    "series_ticker": "KXBTC",
    "event_ticker": None,
    "event_title": None,
    "incentive_type": "volume",
    "ends": None,
    "target_size_fp": None,
    "discount_factor_bps": None,
    "all_markets": False,
}


class TestList:
    @respx.mock
    def test_returns_page(self, resource: IncentiveProgramsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "incentive_programs": [_SAMPLE_PROGRAM],
                    "next_cursor": "page-2",
                },
            )
        )
        page = resource.list()
        assert len(page.items) == 1
        prog = page.items[0]
        assert prog.id == "prog-1"
        assert prog.incentive_type == "liquidity"
        assert prog.period_reward == 1_000_000
        assert prog.paid_out is False
        assert prog.target_size_fp == Decimal("100.5000")
        assert page.cursor == "page-2"
        assert page.has_next

    @respx.mock
    def test_no_next_cursor(self, resource: IncentiveProgramsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"incentive_programs": [_SAMPLE_PROGRAM]},
            )
        )
        page = resource.list()
        assert page.cursor is None
        assert not page.has_next

    @respx.mock
    def test_forwards_filters(self, resource: IncentiveProgramsResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"incentive_programs": []},
            )
        )
        resource.list(status="active", incentive_type="volume", limit=50)
        assert route.called
        url = route.calls.last.request.url
        assert url.params["status"] == "active"
        # Wire key is `type`, SDK kwarg is `incentive_type`
        assert url.params["type"] == "volume"
        assert url.params["limit"] == "50"
        assert "series_ticker" not in url.params
        assert "event_ticker" not in url.params

    @respx.mock
    def test_forwards_series_and_event_ticker(
        self,
        resource: IncentiveProgramsResource,
    ) -> None:
        route = respx.get(f"{_BASE}/incentive_programs").mock(
            return_value=httpx.Response(200, json={"incentive_programs": []})
        )
        resource.list(series_ticker="KXHIGHNY", event_ticker="KXHIGHNY-24")
        url = route.calls.last.request.url
        assert url.params["series_ticker"] == "KXHIGHNY"
        assert url.params["event_ticker"] == "KXHIGHNY-24"

    @respx.mock
    def test_null_target_size_fp(
        self,
        resource: IncentiveProgramsResource,
    ) -> None:
        prog = {**_SAMPLE_PROGRAM, "target_size_fp": None, "discount_factor_bps": None}
        respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"incentive_programs": [prog]},
            )
        )
        page = resource.list()
        assert page.items[0].target_size_fp is None
        assert page.items[0].discount_factor_bps is None


class TestListAll:
    @respx.mock
    def test_paginates_next_cursor(
        self,
        resource: IncentiveProgramsResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "incentive_programs": [_SAMPLE_PROGRAM],
                        "next_cursor": "page-2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "incentive_programs": [
                            {**_SAMPLE_PROGRAM, "id": "prog-2"},
                        ],
                    },
                ),
            ],
        )
        items = list(resource.list_all(limit=1))
        assert len(items) == 2
        assert items[0].id == "prog-1"
        assert items[1].id == "prog-2"
        assert route.call_count == 2
        # Second call must send cursor=page-2
        assert route.calls[1].request.url.params["cursor"] == "page-2"

    @respx.mock
    def test_forwards_series_and_event_ticker(
        self,
        resource: IncentiveProgramsResource,
    ) -> None:
        route = respx.get(f"{_BASE}/incentive_programs").mock(
            return_value=httpx.Response(200, json={"incentive_programs": []})
        )
        list(resource.list_all(series_ticker="KXHIGHNY", event_ticker="KXHIGHNY-24"))
        url = route.calls.last.request.url
        assert url.params["series_ticker"] == "KXHIGHNY"
        assert url.params["event_ticker"] == "KXHIGHNY-24"

    @respx.mock
    def test_omits_unset_tickers(
        self,
        resource: IncentiveProgramsResource,
    ) -> None:
        route = respx.get(f"{_BASE}/incentive_programs").mock(
            return_value=httpx.Response(200, json={"incentive_programs": []})
        )
        list(resource.list_all())
        url = route.calls.last.request.url
        assert "series_ticker" not in url.params
        assert "event_ticker" not in url.params


class TestAsync:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list(
        self,
        async_resource: AsyncIncentiveProgramsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"incentive_programs": [_SAMPLE_PROGRAM]},
            )
        )
        page = await async_resource.list()
        assert page.items[0].id == "prog-1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_forwards_filters(
        self,
        async_resource: AsyncIncentiveProgramsResource,
    ) -> None:
        """Regression guard: SDK kwarg `incentive_type` must serialize to wire `type`."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"incentive_programs": []},
            )
        )
        await async_resource.list(
            status="active",
            incentive_type="volume",
            limit=50,
        )
        assert route.called
        url = route.calls.last.request.url
        assert url.params["type"] == "volume"
        assert url.params["status"] == "active"
        assert url.params["limit"] == "50"
        assert "series_ticker" not in url.params
        assert "event_ticker" not in url.params

    @respx.mock
    @pytest.mark.asyncio
    async def test_forwards_series_and_event_ticker(
        self,
        async_resource: AsyncIncentiveProgramsResource,
    ) -> None:
        route = respx.get(f"{_BASE}/incentive_programs").mock(
            return_value=httpx.Response(200, json={"incentive_programs": []})
        )
        await async_resource.list(
            series_ticker="KXHIGHNY",
            event_ticker="KXHIGHNY-24",
        )
        url = route.calls.last.request.url
        assert url.params["series_ticker"] == "KXHIGHNY"
        assert url.params["event_ticker"] == "KXHIGHNY-24"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_all_forwards_tickers(
        self,
        async_resource: AsyncIncentiveProgramsResource,
    ) -> None:
        route = respx.get(f"{_BASE}/incentive_programs").mock(
            return_value=httpx.Response(200, json={"incentive_programs": []})
        )
        [item async for item in async_resource.list_all(series_ticker="KXHIGHNY")]
        url = route.calls.last.request.url
        assert url.params["series_ticker"] == "KXHIGHNY"
        assert "event_ticker" not in url.params

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_all(
        self,
        async_resource: AsyncIncentiveProgramsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"incentive_programs": [_SAMPLE_PROGRAM]},
            )
        )
        items = [item async for item in async_resource.list_all()]
        assert len(items) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_paginates_next_cursor(
        self,
        async_resource: AsyncIncentiveProgramsResource,
    ) -> None:
        """next_cursor (not cursor) drives async pagination for this endpoint."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "incentive_programs": [_SAMPLE_PROGRAM],
                        "next_cursor": "page-2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "incentive_programs": [
                            {**_SAMPLE_PROGRAM, "id": "prog-2"},
                        ],
                    },
                ),
            ],
        )
        items = [item async for item in async_resource.list_all(limit=1)]
        assert len(items) == 2
        assert items[0].id == "prog-1"
        assert items[1].id == "prog-2"
        assert route.call_count == 2
        assert route.calls[1].request.url.params["cursor"] == "page-2"


class TestIncentiveProgramTickers:
    def test_parses_series_and_event_ticker(self) -> None:
        prog = IncentiveProgram.model_validate(
            incentive_program_dict(
                series_ticker="KXHIGHNY",
                event_ticker="KXHIGHNY-24",
            )
        )
        assert prog.series_ticker == "KXHIGHNY"
        assert prog.event_ticker == "KXHIGHNY-24"

    def test_parses_without_tickers(self) -> None:
        prog = IncentiveProgram.model_validate(incentive_program_dict())
        assert prog.series_ticker is None
        assert prog.event_ticker is None


class TestListSchedules:
    @respx.mock
    def test_happy_path(self, resource: IncentiveProgramsResource) -> None:
        route = respx.get(f"{_BASE}/incentive_schedules").mock(
            return_value=httpx.Response(
                200,
                json={"schedules": [_SAMPLE_SCHEDULE, _SAMPLE_SCHEDULE_OPEN_ENDED]},
            )
        )
        schedules = resource.list_schedules()
        assert route.calls[0].request.method == "GET"
        assert str(route.calls[0].request.url) == f"{_BASE}/incentive_schedules"
        assert len(schedules) == 2
        first = schedules[0]
        assert first.series_ticker == "KXHIGHNY"
        assert first.series_title == "Highest temperature in NYC"
        assert first.series_category == "Climate and Weather"
        assert first.event_ticker == "KXHIGHNY-24JAN01"
        assert first.event_title == "Highest temperature in NYC on Jan 1"
        assert first.incentive_type == "liquidity"
        assert first.source == "weather-liquidity"
        assert first.reward == 1_000_000
        assert first.window_days == 7
        assert first.discount_factor_bps == 25
        assert first.target_size_fp == Decimal("100.00")
        assert isinstance(first.target_size_fp, Decimal)
        assert isinstance(first.ends, datetime)
        assert first.ends.tzinfo is not None
        assert first.ends.year == 2026
        assert first.all_markets is True
        assert isinstance(first.posted_ts, datetime)
        assert first.posted_ts.tzinfo is not None
        assert isinstance(first.updated_ts, datetime)
        assert first.updated_ts.tzinfo is not None
        second = schedules[1]
        assert second.ends is None
        assert second.event_ticker is None
        assert second.event_title is None
        assert second.target_size_fp is None
        assert second.all_markets is False

    @respx.mock
    def test_empty_list(self, resource: IncentiveProgramsResource) -> None:
        respx.get(f"{_BASE}/incentive_schedules").mock(
            return_value=httpx.Response(200, json={"schedules": []})
        )
        assert resource.list_schedules() == []

    @respx.mock
    def test_null_schedules_coerced_to_empty(
        self, resource: IncentiveProgramsResource
    ) -> None:
        respx.get(f"{_BASE}/incentive_schedules").mock(
            return_value=httpx.Response(200, json={"schedules": None})
        )
        assert resource.list_schedules() == []

    @respx.mock
    def test_missing_schedules_coerced_to_empty(
        self, resource: IncentiveProgramsResource
    ) -> None:
        respx.get(f"{_BASE}/incentive_schedules").mock(
            return_value=httpx.Response(200, json={})
        )
        assert resource.list_schedules() == []

    @respx.mock
    def test_omitted_event_fields_are_none(
        self, resource: IncentiveProgramsResource
    ) -> None:
        payload = {
            k: v
            for k, v in _SAMPLE_SCHEDULE.items()
            if k not in ("event_ticker", "event_title")
        }
        respx.get(f"{_BASE}/incentive_schedules").mock(
            return_value=httpx.Response(200, json={"schedules": [payload]})
        )
        schedule = resource.list_schedules()[0]
        assert schedule.event_ticker is None
        assert schedule.event_title is None

    def test_omitted_event_fields_parse_on_model(self) -> None:
        payload = {
            k: v
            for k, v in _SAMPLE_SCHEDULE.items()
            if k not in ("event_ticker", "event_title")
        }
        schedule = IncentiveSchedule.model_validate(payload)
        assert schedule.event_ticker is None
        assert schedule.event_title is None

    @respx.mock
    def test_server_error(self, resource: IncentiveProgramsResource) -> None:
        respx.get(f"{_BASE}/incentive_schedules").mock(
            return_value=httpx.Response(500, json={"error": {"code": "internal"}})
        )
        with pytest.raises(KalshiServerError):
            resource.list_schedules()

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_happy_path(
        self, async_resource: AsyncIncentiveProgramsResource
    ) -> None:
        route = respx.get(f"{_BASE}/incentive_schedules").mock(
            return_value=httpx.Response(
                200, json={"schedules": [_SAMPLE_SCHEDULE]}
            )
        )
        schedules = await async_resource.list_schedules()
        assert route.calls[0].request.method == "GET"
        assert len(schedules) == 1
        assert schedules[0].target_size_fp == Decimal("100.00")
        assert isinstance(schedules[0].posted_ts, datetime)
        assert schedules[0].posted_ts.tzinfo is not None

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_null_and_empty(
        self, async_resource: AsyncIncentiveProgramsResource
    ) -> None:
        respx.get(f"{_BASE}/incentive_schedules").mock(
            return_value=httpx.Response(200, json={"schedules": None})
        )
        assert await async_resource.list_schedules() == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_omitted_event_fields(
        self, async_resource: AsyncIncentiveProgramsResource
    ) -> None:
        payload = {
            k: v
            for k, v in _SAMPLE_SCHEDULE.items()
            if k not in ("event_ticker", "event_title")
        }
        respx.get(f"{_BASE}/incentive_schedules").mock(
            return_value=httpx.Response(200, json={"schedules": [payload]})
        )
        schedule = (await async_resource.list_schedules())[0]
        assert schedule.event_ticker is None
        assert schedule.event_title is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_server_error(
        self, async_resource: AsyncIncentiveProgramsResource
    ) -> None:
        respx.get(f"{_BASE}/incentive_schedules").mock(
            return_value=httpx.Response(500, json={"error": {"code": "internal"}})
        )
        with pytest.raises(KalshiServerError):
            await async_resource.list_schedules()
