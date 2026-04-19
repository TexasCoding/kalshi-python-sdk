"""Integration tests for LiveDataResource.

All live-data endpoints are keyed by milestone_id, so tests discover a
live milestone from /milestones first. Without an active milestone on
demo, the live-data endpoints 404 — tests skip cleanly in that case.
"""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import KalshiError, KalshiNotFoundError
from kalshi.models.live_data import (
    GetGameStatsResponse,
    LiveData,
)
from kalshi.models.milestones import Milestone
from tests.integration.coverage_harness import register

register("LiveDataResource", ["batch", "game_stats", "get", "get_typed"])


@pytest.fixture(scope="session")
def live_milestone(sync_client: KalshiClient) -> Milestone:
    """Find a milestone with a live-data feed on demo.

    Not every milestone has a corresponding live-data payload. We try
    .get() on each until one returns 200, then cache the hit for all
    live-data tests in the session.
    """
    page = sync_client.milestones.list(limit=20)
    if not page.items:
        pytest.skip("No milestones on demo server")
    for ms in page.items:
        try:
            sync_client.live_data.get(ms.id)
            return ms
        except (KalshiNotFoundError, KalshiError):
            continue
    pytest.skip("No milestone on demo has an accessible live_data feed")


@pytest.mark.integration
class TestLiveDataSync:
    def test_get(
        self, sync_client: KalshiClient, live_milestone: Milestone,
    ) -> None:
        ld = sync_client.live_data.get(live_milestone.id)
        assert isinstance(ld, LiveData)
        assert ld.milestone_id == live_milestone.id

    def test_get_404_for_bogus_milestone(
        self, sync_client: KalshiClient,
    ) -> None:
        with pytest.raises(KalshiError):
            sync_client.live_data.get("bogus-milestone-id")

    def test_get_typed(
        self, sync_client: KalshiClient, live_milestone: Milestone,
    ) -> None:
        # Legacy endpoint takes the type from the milestone itself.
        ld = sync_client.live_data.get_typed(
            live_milestone.type, live_milestone.id,
        )
        assert isinstance(ld, LiveData)
        assert ld.milestone_id == live_milestone.id

    def test_batch(
        self, sync_client: KalshiClient, live_milestone: Milestone,
    ) -> None:
        items = sync_client.live_data.batch(milestone_ids=[live_milestone.id])
        assert isinstance(items, list)
        # Demo may return fewer entries than requested (some ids have no
        # feed), so only assert that what comes back parses.
        for ld in items:
            assert isinstance(ld, LiveData)

    def test_game_stats(
        self, sync_client: KalshiClient, live_milestone: Milestone,
    ) -> None:
        # Game stats returns pbp=None for unsupported sports — that's
        # still a successful response.
        resp = sync_client.live_data.game_stats(live_milestone.id)
        assert isinstance(resp, GetGameStatsResponse)


@pytest.mark.integration
class TestLiveDataAsync:
    @pytest.mark.asyncio
    async def test_get(
        self,
        async_client: AsyncKalshiClient,
        live_milestone: Milestone,
    ) -> None:
        ld = await async_client.live_data.get(live_milestone.id)
        assert isinstance(ld, LiveData)

    @pytest.mark.asyncio
    async def test_batch(
        self,
        async_client: AsyncKalshiClient,
        live_milestone: Milestone,
    ) -> None:
        items = await async_client.live_data.batch(
            milestone_ids=[live_milestone.id],
        )
        assert isinstance(items, list)

    @pytest.mark.asyncio
    async def test_game_stats(
        self,
        async_client: AsyncKalshiClient,
        live_milestone: Milestone,
    ) -> None:
        resp = await async_client.live_data.game_stats(live_milestone.id)
        assert isinstance(resp, GetGameStatsResponse)
