"""Integration tests for MilestonesResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import KalshiNotFoundError
from kalshi.models.common import Page
from kalshi.models.milestones import Milestone
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register("MilestonesResource", ["get", "list", "list_all"])


@pytest.mark.integration
class TestMilestonesSync:
    def test_list(self, sync_client: KalshiClient) -> None:
        page = sync_client.milestones.list(limit=5)
        assert isinstance(page, Page)
        for ms in page.items:
            assert isinstance(ms, Milestone)
            assert_model_fields(ms)

    def test_list_with_category(self, sync_client: KalshiClient) -> None:
        # Demo accepts `category="Sports"` as input but returns the category
        # lowercased in the response body. Spec example is "Sports" —
        # server-side normalization is the inconsistency. Compare case-
        # insensitively so future case fixes on either side don't regress.
        page = sync_client.milestones.list(limit=3, category="Sports")
        assert isinstance(page, Page)
        for ms in page.items:
            assert ms.category.lower() == "sports"

    def test_list_all(self, sync_client: KalshiClient) -> None:
        for count, ms in enumerate(sync_client.milestones.list_all(limit=3)):
            assert isinstance(ms, Milestone)
            if count >= 2:
                break

    def test_get(self, sync_client: KalshiClient) -> None:
        # Walk list first to find a real milestone id — demo inventory
        # drifts, so hardcoding an id would be brittle.
        page = sync_client.milestones.list(limit=1)
        if not page.items:
            pytest.skip("No milestones on demo server")
        target = page.items[0]
        ms = sync_client.milestones.get(target.id)
        assert isinstance(ms, Milestone)
        assert ms.id == target.id
        assert_model_fields(ms)

    def test_get_bogus_id_raises_404(self, sync_client: KalshiClient) -> None:
        with pytest.raises(KalshiNotFoundError):
            sync_client.milestones.get("bogus-milestone-id-does-not-exist")


@pytest.mark.integration
class TestMilestonesAsync:
    @pytest.mark.asyncio
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.milestones.list(limit=5)
        assert isinstance(page, Page)

    @pytest.mark.asyncio
    async def test_list_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for ms in async_client.milestones.list_all(limit=3):
            assert isinstance(ms, Milestone)
            count += 1
            if count >= 3:
                break

    @pytest.mark.asyncio
    async def test_get(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.milestones.list(limit=1)
        if not page.items:
            pytest.skip("No milestones on demo server")
        ms = await async_client.milestones.get(page.items[0].id)
        assert isinstance(ms, Milestone)
