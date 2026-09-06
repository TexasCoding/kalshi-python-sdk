"""Live data models — real-time event state keyed by milestone.

``LiveData.details`` is deliberately a loose ``dict[str, Any]``: the spec
marks it ``additionalProperties: true`` with no fixed schema because the
shape varies per milestone ``type`` (e.g., football vs. political race).
``GetGameStatsResponse.pbp`` (play-by-play) is similarly loose — each
period/event is a free-form object.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from kalshi.types import NullableList


class LiveData(BaseModel):
    """Live-data payload for a specific milestone."""

    type: str
    details: dict[str, Any]
    milestone_id: str

    model_config = {"extra": "allow"}


class EventLiveData(BaseModel):
    """Live-data payload keyed by event ticker (not milestone).

    Spec ``EventLiveData`` (OpenAPI 3.27.0) — used for event-keyed series such as
    crypto price charts, commodity timeseries, and weather observations.
    ``type`` names the schema of ``details``. Unlike :class:`LiveData`, there is
    no ``milestone_id``.
    """

    type: str
    details: dict[str, Any]
    is_historical: bool | None = None
    default_range: str | None = None
    range_options: list[str] | None = None

    model_config = {"extra": "allow"}


class GetLiveDataResponse(BaseModel):
    """Response from GET /live_data/milestone/{milestone_id}."""

    live_data: LiveData

    model_config = {"extra": "allow"}


class GetEventLiveDataResponse(BaseModel):
    """Response from GET /live_data/events/{event_ticker}."""

    live_data: EventLiveData

    model_config = {"extra": "allow"}


class GetLiveDatasResponse(BaseModel):
    """Response from GET /live_data/batch — multiple milestones at once."""

    live_datas: NullableList[LiveData] = []

    model_config = {"extra": "allow"}


class PlayByPlayPeriod(BaseModel):
    """A single period within a game's play-by-play.

    ``events`` is a loose list of free-form objects (spec has no fixed
    event schema) because each sport emits different event shapes.
    ``NullableList`` coerces server-returned null to [] (Kalshi has
    historically sent null for required list fields).
    """

    events: NullableList[dict[str, Any]] = []

    model_config = {"extra": "allow"}


class PlayByPlay(BaseModel):
    """Play-by-play data organized by period."""

    periods: NullableList[PlayByPlayPeriod] = []

    model_config = {"extra": "allow"}


class WeatherIndexStationReading(BaseModel):
    """Per-station audit reading on a weather-index point (``detailed=true``)."""

    station_id: str
    code: str
    source: str | None = None
    temp_f: float | None = None
    obs_time_ms: int | None = None
    received_at_ms: int | None = None
    primary_code: str | None = None

    model_config = {"extra": "allow"}


class WeatherIndexPoint(BaseModel):
    """One minute of a published weather index."""

    t: int
    status: str
    v: float | None = None
    contributors: int | None = None
    stations: list[WeatherIndexStationReading] | None = None
    # Present only on labelled historical-backfill points (not settlement-eligible).
    receipt_basis: str | None = None

    model_config = {"extra": "allow"}


class GetWeatherIndexResponse(BaseModel):
    """Response from GET /live_data/weather/{city}."""

    city: str
    units: str
    timeseries: list[WeatherIndexPoint]
    config_version: str | None = None

    model_config = {"extra": "allow"}


class WeatherIndexCalibrationStation(BaseModel):
    """One configured member station on a weather-index calibration record."""

    station_id: str
    weight: float
    offset_c: float
    update_note: str | None = None

    model_config = {"extra": "allow"}


class WeatherIndexCalibration(BaseModel):
    """One published weather-index configuration, effective from ``effective_at_ms``."""

    config_version: str
    effective_at_ms: int
    city_reference_c: float
    stations: list[WeatherIndexCalibrationStation]
    published_at_ms: int | None = None
    change_reason: str | None = None
    calibration_window_start_ms: int | None = None
    calibration_window_end_ms: int | None = None

    model_config = {"extra": "allow"}


class GetWeatherIndexCalibrationsResponse(BaseModel):
    """Response from GET /live_data/weather/{city}/calibrations."""

    city: str
    units: str
    calibrations: list[WeatherIndexCalibration]

    model_config = {"extra": "allow"}


class GetGameStatsResponse(BaseModel):
    """Response from GET /live_data/milestone/{milestone_id}/game_stats.

    ``pbp`` is ``None`` for unsupported milestone types or milestones
    without a Sportradar ID (spec: "Returns null for unsupported milestone
    types or milestones without a Sportradar ID").
    """

    pbp: PlayByPlay | None = None

    model_config = {"extra": "allow"}
