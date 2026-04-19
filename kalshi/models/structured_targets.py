"""Structured targets — external entities (players, teams, etc.) markets anchor to.

Unlike most spec schemas, every ``StructuredTarget`` field is optional per
spec — Kalshi returns partial records depending on the target type. The
SDK mirrors that: all fields default to ``None`` / ``{}``.

``details`` is flexible JSON (``additionalProperties: true``) whose keys
depend on ``type`` (e.g., a ``basketball_player`` carries different keys
than a ``horse_race_entry``). Consumers are expected to branch on ``type``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from kalshi.types import NullableList


class StructuredTarget(BaseModel):
    """An external entity a market can be structured against."""

    id: str | None = None
    name: str | None = None
    type: str | None = None
    details: dict[str, Any] = {}
    source_id: str | None = None
    source_ids: dict[str, str] | None = None
    last_updated_ts: datetime | None = None

    model_config = {"extra": "allow"}


class GetStructuredTargetsResponse(BaseModel):
    """Paginated response for GET /structured_targets."""

    structured_targets: NullableList[StructuredTarget] = []
    cursor: str | None = None

    model_config = {"extra": "allow"}


class GetStructuredTargetResponse(BaseModel):
    """Response for GET /structured_targets/{id}."""

    structured_target: StructuredTarget | None = None

    model_config = {"extra": "allow"}
