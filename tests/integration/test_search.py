"""Integration tests for SearchResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.search import (
    GetFiltersBySportsResponse,
    GetTagsForSeriesCategoriesResponse,
)
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register("SearchResource", ["filters_by_sport", "tags_by_categories"])


@pytest.mark.integration
class TestSearchSync:
    def test_tags_by_categories(self, sync_client: KalshiClient) -> None:
        result = sync_client.search.tags_by_categories()
        assert isinstance(result, GetTagsForSeriesCategoriesResponse)
        assert_model_fields(result)
        assert isinstance(result.tags_by_categories, dict)

    def test_filters_by_sport(self, sync_client: KalshiClient) -> None:
        result = sync_client.search.filters_by_sport()
        assert isinstance(result, GetFiltersBySportsResponse)
        assert_model_fields(result)
        assert isinstance(result.sport_ordering, list)


@pytest.mark.integration
class TestSearchAsync:
    async def test_tags_by_categories(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        result = await async_client.search.tags_by_categories()
        assert isinstance(result, GetTagsForSeriesCategoriesResponse)

    async def test_filters_by_sport(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        result = await async_client.search.filters_by_sport()
        assert isinstance(result, GetFiltersBySportsResponse)
