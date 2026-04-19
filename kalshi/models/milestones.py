"""Milestone models — structured markers for sports/elections/crypto events.

Milestones anchor live-data feeds (see :mod:`kalshi.models.live_data`).
Each milestone has a ``type`` (e.g., ``football_game``, ``political_race``)
that determines what the ``details`` object contains. ``last_updated_ts``
and ``start_date`` are ISO ``date-time`` strings per spec (unlike
subaccount timestamps which are Unix ints).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from kalshi.types import NullableList


class Milestone(BaseModel):
    """A structured event milestone (game, race, tournament, etc.)."""

    id: str
    category: str
    type: str
    start_date: datetime
    end_date: datetime | None = None
    # Spec marks these required but Kalshi has historically returned JSON null
    # for required list fields (see v0.9.0 fix for Series.tags). NullableList
    # coerces None -> [] so demo/prod inconsistencies don't break parsing.
    related_event_tickers: NullableList[str] = []
    title: str
    notification_message: str
    source_id: str | None = None
    source_ids: dict[str, str] | None = None
    details: dict[str, Any] = {}
    primary_event_tickers: NullableList[str] = []
    last_updated_ts: datetime

    model_config = {"extra": "allow"}


class GetMilestoneResponse(BaseModel):
    """Response from GET /milestones/{milestone_id}."""

    milestone: Milestone

    model_config = {"extra": "allow"}


class GetMilestonesResponse(BaseModel):
    """Response from GET /milestones — paginated list."""

    milestones: list[Milestone]
    cursor: str | None = None

    model_config = {"extra": "allow"}
