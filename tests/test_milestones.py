"""Tests for kalshi.resources.milestones."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiNotFoundError
from kalshi.models.milestones import Milestone
from kalshi.resources.milestones import (
    AsyncMilestonesResource,
    MilestonesResource,
)


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def milestones(test_auth: KalshiAuth, config: KalshiConfig) -> MilestonesResource:
    return MilestonesResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_milestones(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> AsyncMilestonesResource:
    return AsyncMilestonesResource(AsyncTransport(test_auth, config))


_MS_JSON = {
    "id": "ms-1",
    "category": "Sports",
    "type": "football_game",
    "start_date": "2026-09-01T18:00:00Z",
    "related_event_tickers": ["NFL-W1-PHI-NE"],
    "title": "PHI at NE",
    "notification_message": "Game starts soon",
    "details": {"home": "NE", "away": "PHI"},
    "primary_event_tickers": ["NFL-W1-PHI-NE"],
    "last_updated_ts": "2026-08-30T12:00:00Z",
}


class TestMilestoneModel:
    def test_parses_required_fields(self) -> None:
        ms = Milestone.model_validate(_MS_JSON)
        assert ms.id == "ms-1"
        assert ms.category == "Sports"
        assert ms.type == "football_game"
        assert ms.start_date == datetime(2026, 9, 1, 18, 0, tzinfo=UTC)
        assert ms.details == {"home": "NE", "away": "PHI"}

    def test_end_date_optional(self) -> None:
        ms = Milestone.model_validate({**_MS_JSON, "end_date": None})
        assert ms.end_date is None

    def test_source_ids_dict(self) -> None:
        ms = Milestone.model_validate(
            {**_MS_JSON, "source_ids": {"sportradar": "sr-123", "optacode": "o-9"}},
        )
        assert ms.source_ids == {"sportradar": "sr-123", "optacode": "o-9"}


class TestMilestonesList:
    @respx.mock
    def test_list_returns_page(self, milestones: MilestonesResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/milestones").mock(
            return_value=httpx.Response(
                200, json={"milestones": [_MS_JSON], "cursor": "next"},
            ),
        )
        page = milestones.list(limit=50)
        assert len(page.items) == 1
        assert page.cursor == "next"

    @respx.mock
    def test_list_sends_filters(self, milestones: MilestonesResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/milestones").mock(
            return_value=httpx.Response(200, json={"milestones": [], "cursor": ""}),
        )
        milestones.list(
            limit=100,
            category="Sports",
            competition="Pro Football",
            type="football_game",
            minimum_start_date=datetime(2026, 9, 1, tzinfo=UTC),
            min_updated_ts=1_700_000_000,
        )
        q = dict(route.calls[0].request.url.params)
        assert q["limit"] == "100"
        assert q["category"] == "Sports"
        assert q["competition"] == "Pro Football"
        assert q["type"] == "football_game"
        assert q["min_updated_ts"] == "1700000000"
        assert q["minimum_start_date"].startswith("2026-09-01")

    @respx.mock
    def test_list_accepts_iso_string(
        self, milestones: MilestonesResource,
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/milestones").mock(
            return_value=httpx.Response(200, json={"milestones": [], "cursor": ""}),
        )
        milestones.list(limit=25, minimum_start_date="2026-09-01T00:00:00Z")
        q = dict(route.calls[0].request.url.params)
        assert q["minimum_start_date"] == "2026-09-01T00:00:00Z"

    @respx.mock
    def test_list_coerces_naive_datetime_to_utc(
        self, milestones: MilestonesResource,
    ) -> None:
        # Naive datetime has no tzinfo. Without coercion, .isoformat() would
        # emit "2026-09-01T00:00:00" (no offset), which isn't RFC3339 and can
        # be silently interpreted in the server's local timezone.
        from datetime import datetime as _dt
        route = respx.get("https://test.kalshi.com/trade-api/v2/milestones").mock(
            return_value=httpx.Response(200, json={"milestones": [], "cursor": ""}),
        )
        milestones.list(limit=25, minimum_start_date=_dt(2026, 9, 1, 0, 0, 0))
        q = dict(route.calls[0].request.url.params)
        # Coerced to UTC: "+00:00" suffix.
        assert q["minimum_start_date"] == "2026-09-01T00:00:00+00:00"

    @respx.mock
    def test_list_all_paginates(
        self, milestones: MilestonesResource,
    ) -> None:
        page1 = {"milestones": [_MS_JSON], "cursor": "p2"}
        page2 = {
            "milestones": [{**_MS_JSON, "id": "ms-2"}],
            "cursor": "",
        }
        route = respx.get("https://test.kalshi.com/trade-api/v2/milestones").mock(
            side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)],
        )
        items = list(milestones.list_all(limit=1))
        assert [i.id for i in items] == ["ms-1", "ms-2"]
        assert route.call_count == 2


class TestMilestonesGet:
    @respx.mock
    def test_get_returns_milestone(
        self, milestones: MilestonesResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/milestones/ms-1",
        ).mock(return_value=httpx.Response(200, json={"milestone": _MS_JSON}))
        ms = milestones.get("ms-1")
        assert ms.id == "ms-1"

    @respx.mock
    def test_get_404_maps(self, milestones: MilestonesResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/milestones/nope",
        ).mock(return_value=httpx.Response(404, json={"message": "not found"}))
        with pytest.raises(KalshiNotFoundError):
            milestones.get("nope")


class TestAsyncMilestones:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list(
        self, async_milestones: AsyncMilestonesResource,
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/milestones").mock(
            return_value=httpx.Response(
                200, json={"milestones": [_MS_JSON], "cursor": ""},
            ),
        )
        page = await async_milestones.list(limit=50)
        assert len(page.items) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_get(
        self, async_milestones: AsyncMilestonesResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/milestones/ms-1",
        ).mock(return_value=httpx.Response(200, json={"milestone": _MS_JSON}))
        ms = await async_milestones.get("ms-1")
        assert ms.id == "ms-1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_all_paginates(
        self, async_milestones: AsyncMilestonesResource,
    ) -> None:
        page1 = {"milestones": [_MS_JSON], "cursor": "p2"}
        page2 = {"milestones": [{**_MS_JSON, "id": "ms-9"}], "cursor": ""}
        respx.get("https://test.kalshi.com/trade-api/v2/milestones").mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ],
        )
        items = [m async for m in async_milestones.list_all(limit=1)]
        assert [i.id for i in items] == ["ms-1", "ms-9"]
