"""Tests for kalshi.resources.search — tags_by_categories + filters_by_sport."""

from __future__ import annotations

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.resources.search import AsyncSearchResource, SearchResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def search(test_auth: KalshiAuth, config: KalshiConfig) -> SearchResource:
    return SearchResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_search(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> AsyncSearchResource:
    return AsyncSearchResource(AsyncTransport(test_auth, config))


class TestTagsByCategories:
    @respx.mock
    def test_returns_mapping(self, search: SearchResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/search/tags_by_categories",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "tags_by_categories": {
                        "Sports": ["NFL", "NBA"],
                        "Politics": ["Elections"],
                    }
                },
            )
        )
        result = search.tags_by_categories()
        assert result.tags_by_categories["Sports"] == ["NFL", "NBA"]
        assert result.tags_by_categories["Politics"] == ["Elections"]

    @respx.mock
    def test_empty(self, search: SearchResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/search/tags_by_categories",
        ).mock(
            return_value=httpx.Response(
                200, json={"tags_by_categories": {}},
            )
        )
        result = search.tags_by_categories()
        assert result.tags_by_categories == {}


class TestFiltersBySport:
    @respx.mock
    def test_returns_filters(self, search: SearchResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/search/filters_by_sport",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "filters_by_sports": {
                        "basketball": {
                            "scopes": ["player", "team"],
                            "competitions": {
                                "NBA": {"scopes": ["playoffs", "regular"]},
                            },
                        },
                    },
                    "sport_ordering": ["basketball", "football"],
                },
            )
        )
        result = search.filters_by_sport()
        bb = result.filters_by_sports["basketball"]
        assert bb.scopes == ["player", "team"]
        assert bb.competitions["NBA"].scopes == ["playoffs", "regular"]
        assert result.sport_ordering == ["basketball", "football"]

    @respx.mock
    def test_empty(self, search: SearchResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/search/filters_by_sport",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"filters_by_sports": {}, "sport_ordering": []},
            )
        )
        result = search.filters_by_sport()
        assert result.filters_by_sports == {}
        assert result.sport_ordering == []


class TestAsyncSearch:
    @respx.mock
    @pytest.mark.asyncio
    async def test_tags(self, async_search: AsyncSearchResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/search/tags_by_categories",
        ).mock(
            return_value=httpx.Response(
                200, json={"tags_by_categories": {"Sports": ["NFL"]}},
            )
        )
        result = await async_search.tags_by_categories()
        assert result.tags_by_categories["Sports"] == ["NFL"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_filters(self, async_search: AsyncSearchResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/search/filters_by_sport",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"filters_by_sports": {}, "sport_ordering": []},
            )
        )
        result = await async_search.filters_by_sport()
        assert result.sport_ordering == []
