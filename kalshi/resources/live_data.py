"""Live data resource — real-time event state tied to a milestone.

The ``/live_data/{type}/milestone/{milestone_id}`` endpoint is the legacy
shape (requires a ``type`` path param); prefer ``get`` (which hits
``/live_data/milestone/{milestone_id}``) for new code.
"""

from __future__ import annotations

import builtins

from kalshi.models.live_data import (
    EventLiveData,
    GetEventLiveDataResponse,
    GetGameStatsResponse,
    GetLiveDataResponse,
    GetLiveDatasResponse,
    GetWeatherIndexResponse,
    LiveData,
)
from kalshi.resources._base import AsyncResource, SyncResource, _bool_param, _params, _seg

_MAX_BATCH = 100


class LiveDataResource(SyncResource):
    """Sync live-data API — public, no auth required per spec."""

    def get(
        self,
        milestone_id: str,
        *,
        include_player_stats: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LiveData:
        params = _params(
            include_player_stats=_bool_param(include_player_stats),
        )
        data = self._get(
            f"/live_data/milestone/{_seg(milestone_id, name='milestone_id')}",
            params=params,
            extra_headers=extra_headers,
        )
        return GetLiveDataResponse.model_validate(data).live_data

    def get_event(
        self,
        event_ticker: str,
        *,
        range: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> EventLiveData:
        """``GET /live_data/events/{event_ticker}`` — event-keyed live data.

        Serves crypto price charts, commodity timeseries, weather observations,
        and similar event-scoped payloads. Optional ``range`` is a chart-window
        hint (e.g. ``15min``, ``1h``, ``1d``) when the underlying type supports it.
        """
        params = _params(range=range)
        data = self._get(
            f"/live_data/events/{_seg(event_ticker, name='event_ticker')}",
            params=params,
            extra_headers=extra_headers,
        )
        return GetEventLiveDataResponse.model_validate(data).live_data

    def get_typed(
        self,
        milestone_type: str,
        milestone_id: str,
        *,
        include_player_stats: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LiveData:
        """Legacy ``/live_data/{type}/milestone/{milestone_id}`` URL form.

        Despite the name, ``get_typed`` is **not** a more-strongly-typed
        variant of :meth:`get`: both return the same :class:`LiveData`
        model with the same annotations. The only difference is the URL
        — ``get_typed`` hits the legacy path that embeds the milestone
        ``{type}`` segment, while :meth:`get` hits the canonical
        ``/live_data/milestone/{milestone_id}``. The ``_typed`` suffix
        refers to the typed URL form, not to Python typing.

        ``milestone_type`` populates the ``{type}`` path segment. Named
        ``milestone_type`` (not ``type``) to avoid shadowing the Python
        built-in.

        Prefer :meth:`get`. The spec marks this endpoint as the legacy
        form retained for backward compatibility.
        """
        params = _params(
            include_player_stats=_bool_param(include_player_stats),
        )
        data = self._get(
            f"/live_data/{_seg(milestone_type, name='milestone_type')}/milestone/{_seg(milestone_id, name='milestone_id')}",  # noqa: E501
            params=params,
            extra_headers=extra_headers,
        )
        return GetLiveDataResponse.model_validate(data).live_data

    def batch(
        self,
        *,
        milestone_ids: builtins.list[str],
        include_player_stats: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[LiveData]:
        """Fetch up to 100 milestones in one call.

        Spec requires at least one milestone id (max 100). ``milestone_ids``
        wire format is ``?milestone_ids=a&milestone_ids=b`` (spec
        ``style: form, explode: true``) — httpx serializes list values
        that way by default.
        """
        if not milestone_ids:
            raise ValueError("milestone_ids must be a non-empty list")
        if len(milestone_ids) > _MAX_BATCH:
            raise ValueError(
                f"milestone_ids accepts at most {_MAX_BATCH} entries per spec "
                f"(got {len(milestone_ids)})"
            )
        params = _params(
            milestone_ids=milestone_ids,
            include_player_stats=_bool_param(include_player_stats),
        )
        data = self._get("/live_data/batch", params=params, extra_headers=extra_headers)
        return GetLiveDatasResponse.model_validate(data).live_datas

    def game_stats(
        self, milestone_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetGameStatsResponse:
        """Play-by-play stats. Returns ``pbp=None`` for unsupported sports."""
        data = self._get(
            f"/live_data/milestone/{_seg(milestone_id, name='milestone_id')}/game_stats",
            extra_headers=extra_headers,
        )
        return GetGameStatsResponse.model_validate(data)

    def weather(
        self,
        city: str,
        *,
        from_ts: int | None = None,
        to: int | None = None,
        last_sec: int | None = None,
        detailed: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetWeatherIndexResponse:
        """``GET /live_data/weather/{city}`` — published weather index timeseries.

        ``from_ts`` is the spec ``from`` query (unix milliseconds). Named
        ``from_ts`` to avoid the Python keyword; the wire key is still
        ``from``. Mutually exclusive with ``last_sec`` per spec.
        """
        params = _params(
            to=to,
            last_sec=last_sec,
            detailed=_bool_param(detailed),
        )
        if from_ts is not None:
            params["from"] = from_ts
        data = self._get(
            f"/live_data/weather/{_seg(city, name='city')}",
            params=params,
            extra_headers=extra_headers,
        )
        return GetWeatherIndexResponse.model_validate(data)


class AsyncLiveDataResource(AsyncResource):
    """Async live-data API."""

    async def get(
        self,
        milestone_id: str,
        *,
        include_player_stats: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LiveData:
        params = _params(
            include_player_stats=_bool_param(include_player_stats),
        )
        data = await self._get(
            f"/live_data/milestone/{_seg(milestone_id, name='milestone_id')}",
            params=params,
            extra_headers=extra_headers,
        )
        return GetLiveDataResponse.model_validate(data).live_data

    async def get_event(
        self,
        event_ticker: str,
        *,
        range: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> EventLiveData:
        """``GET /live_data/events/{event_ticker}`` — event-keyed live data.

        Async counterpart of :meth:`LiveDataResource.get_event`.
        """
        params = _params(range=range)
        data = await self._get(
            f"/live_data/events/{_seg(event_ticker, name='event_ticker')}",
            params=params,
            extra_headers=extra_headers,
        )
        return GetEventLiveDataResponse.model_validate(data).live_data

    async def get_typed(
        self,
        milestone_type: str,
        milestone_id: str,
        *,
        include_player_stats: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LiveData:
        """Legacy ``/live_data/{type}/milestone/{milestone_id}`` URL form.

        Despite the name, ``get_typed`` is **not** a more-strongly-typed
        variant of :meth:`get`: both return the same :class:`LiveData`
        model with the same annotations. The only difference is the URL
        — ``get_typed`` hits the legacy path that embeds the milestone
        ``{type}`` segment, while :meth:`get` hits the canonical
        ``/live_data/milestone/{milestone_id}``. The ``_typed`` suffix
        refers to the typed URL form, not to Python typing.

        ``milestone_type`` populates the ``{type}`` path segment. Named
        ``milestone_type`` (not ``type``) to avoid shadowing the Python
        built-in.

        Prefer :meth:`get`. The spec marks this endpoint as the legacy
        form retained for backward compatibility.
        """
        params = _params(
            include_player_stats=_bool_param(include_player_stats),
        )
        data = await self._get(
            f"/live_data/{_seg(milestone_type, name='milestone_type')}/milestone/{_seg(milestone_id, name='milestone_id')}",  # noqa: E501
            params=params,
            extra_headers=extra_headers,
        )
        return GetLiveDataResponse.model_validate(data).live_data

    async def batch(
        self,
        *,
        milestone_ids: builtins.list[str],
        include_player_stats: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[LiveData]:
        """Fetch up to 100 milestones in one call.

        Spec requires at least one milestone id (max 100). ``milestone_ids``
        wire format is ``?milestone_ids=a&milestone_ids=b`` (spec
        ``style: form, explode: true``) — httpx serializes list values
        that way by default.
        """
        if not milestone_ids:
            raise ValueError("milestone_ids must be a non-empty list")
        if len(milestone_ids) > _MAX_BATCH:
            raise ValueError(
                f"milestone_ids accepts at most {_MAX_BATCH} entries per spec "
                f"(got {len(milestone_ids)})"
            )
        params = _params(
            milestone_ids=milestone_ids,
            include_player_stats=_bool_param(include_player_stats),
        )
        data = await self._get("/live_data/batch", params=params, extra_headers=extra_headers)
        return GetLiveDatasResponse.model_validate(data).live_datas

    async def game_stats(
        self, milestone_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetGameStatsResponse:
        """Play-by-play stats. Returns ``pbp=None`` for unsupported sports."""
        data = await self._get(
            f"/live_data/milestone/{_seg(milestone_id, name='milestone_id')}/game_stats",
            extra_headers=extra_headers,
        )
        return GetGameStatsResponse.model_validate(data)

    async def weather(
        self,
        city: str,
        *,
        from_ts: int | None = None,
        to: int | None = None,
        last_sec: int | None = None,
        detailed: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetWeatherIndexResponse:
        """Async :meth:`LiveDataResource.weather`."""
        params = _params(
            to=to,
            last_sec=last_sec,
            detailed=_bool_param(detailed),
        )
        if from_ts is not None:
            params["from"] = from_ts
        data = await self._get(
            f"/live_data/weather/{_seg(city, name='city')}",
            params=params,
            extra_headers=extra_headers,
        )
        return GetWeatherIndexResponse.model_validate(data)
