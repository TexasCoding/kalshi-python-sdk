"""Search resource — discovery surfaces (tags by category, filters by sport)."""

from __future__ import annotations

from kalshi.models.search import (
    GetFiltersBySportsResponse,
    GetTagsForSeriesCategoriesResponse,
)
from kalshi.resources._base import AsyncResource, SyncResource


class SearchResource(SyncResource):
    """Sync search/discovery API."""

    def tags_by_categories(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetTagsForSeriesCategoriesResponse:
        data = self._get("/search/tags_by_categories", extra_headers=extra_headers)
        return GetTagsForSeriesCategoriesResponse.model_validate(data)

    def filters_by_sport(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetFiltersBySportsResponse:
        data = self._get("/search/filters_by_sport", extra_headers=extra_headers)
        return GetFiltersBySportsResponse.model_validate(data)


class AsyncSearchResource(AsyncResource):
    """Async search/discovery API."""

    async def tags_by_categories(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetTagsForSeriesCategoriesResponse:
        data = await self._get("/search/tags_by_categories", extra_headers=extra_headers)
        return GetTagsForSeriesCategoriesResponse.model_validate(data)

    async def filters_by_sport(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetFiltersBySportsResponse:
        data = await self._get("/search/filters_by_sport", extra_headers=extra_headers)
        return GetFiltersBySportsResponse.model_validate(data)
