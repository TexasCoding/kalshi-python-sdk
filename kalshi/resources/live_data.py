"""Live data resource — real-time event state tied to a milestone.

The ``/live_data/{type}/milestone/{milestone_id}`` endpoint is the legacy
shape (requires a ``type`` path param); prefer ``get`` (which hits
``/live_data/milestone/{milestone_id}``) for new code.
"""

from __future__ import annotations

import builtins

from kalshi.models.live_data import (
    GetGameStatsResponse,
    GetLiveDataResponse,
    GetLiveDatasResponse,
    LiveData,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


class LiveDataResource(SyncResource):
    """Sync live-data API — public, no auth required per spec."""

    def get(
        self,
        milestone_id: str,
        *,
        include_player_stats: bool | None = None,
    ) -> LiveData:
        params = _params(
            include_player_stats="true" if include_player_stats else None,
        )
        data = self._get(
            f"/live_data/milestone/{milestone_id}",
            params=params,
        )
        return GetLiveDataResponse.model_validate(data).live_data

    def get_typed(
        self,
        type: str,
        milestone_id: str,
        *,
        include_player_stats: bool | None = None,
    ) -> LiveData:
        """Legacy ``/live_data/{type}/milestone/{milestone_id}`` shape.

        Prefer :meth:`get`. The spec marks this endpoint as the legacy
        form retained for backward compatibility.
        """
        params = _params(
            include_player_stats="true" if include_player_stats else None,
        )
        data = self._get(
            f"/live_data/{type}/milestone/{milestone_id}",
            params=params,
        )
        return GetLiveDataResponse.model_validate(data).live_data

    def batch(
        self,
        *,
        milestone_ids: builtins.list[str],
        include_player_stats: bool | None = None,
    ) -> builtins.list[LiveData]:
        """Fetch up to 100 milestones in one call.

        ``milestone_ids`` wire format is ``?milestone_ids=a&milestone_ids=b``
        (spec ``style: form, explode: true``) — httpx serializes list values
        that way by default.
        """
        params = _params(
            milestone_ids=milestone_ids,
            include_player_stats="true" if include_player_stats else None,
        )
        data = self._get("/live_data/batch", params=params)
        return GetLiveDatasResponse.model_validate(data).live_datas

    def game_stats(self, milestone_id: str) -> GetGameStatsResponse:
        """Play-by-play stats. Returns ``pbp=None`` for unsupported sports."""
        data = self._get(f"/live_data/milestone/{milestone_id}/game_stats")
        return GetGameStatsResponse.model_validate(data)


class AsyncLiveDataResource(AsyncResource):
    """Async live-data API."""

    async def get(
        self,
        milestone_id: str,
        *,
        include_player_stats: bool | None = None,
    ) -> LiveData:
        params = _params(
            include_player_stats="true" if include_player_stats else None,
        )
        data = await self._get(
            f"/live_data/milestone/{milestone_id}",
            params=params,
        )
        return GetLiveDataResponse.model_validate(data).live_data

    async def get_typed(
        self,
        type: str,
        milestone_id: str,
        *,
        include_player_stats: bool | None = None,
    ) -> LiveData:
        params = _params(
            include_player_stats="true" if include_player_stats else None,
        )
        data = await self._get(
            f"/live_data/{type}/milestone/{milestone_id}",
            params=params,
        )
        return GetLiveDataResponse.model_validate(data).live_data

    async def batch(
        self,
        *,
        milestone_ids: builtins.list[str],
        include_player_stats: bool | None = None,
    ) -> builtins.list[LiveData]:
        params = _params(
            milestone_ids=milestone_ids,
            include_player_stats="true" if include_player_stats else None,
        )
        data = await self._get("/live_data/batch", params=params)
        return GetLiveDatasResponse.model_validate(data).live_datas

    async def game_stats(self, milestone_id: str) -> GetGameStatsResponse:
        data = await self._get(f"/live_data/milestone/{milestone_id}/game_stats")
        return GetGameStatsResponse.model_validate(data)
