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


class GetLiveDataResponse(BaseModel):
    """Response from GET /live_data/milestone/{milestone_id}."""

    live_data: LiveData

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


class GetGameStatsResponse(BaseModel):
    """Response from GET /live_data/milestone/{milestone_id}/game_stats.

    ``pbp`` is ``None`` for unsupported milestone types or milestones
    without a Sportradar ID (spec: "Returns null for unsupported milestone
    types or milestones without a Sportradar ID").
    """

    pbp: PlayByPlay | None = None

    model_config = {"extra": "allow"}
