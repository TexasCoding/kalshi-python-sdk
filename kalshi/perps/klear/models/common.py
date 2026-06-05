"""Shared Klear (SCM) models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Error(BaseModel):
    """Spec ``Error`` — a structured Klear API error body.

    The transport's ``_map_error`` already reads ``message`` / ``details`` to
    build the SDK exception hierarchy; this typed model is provided for callers
    that want structured access. ``code`` and ``message`` are spec-required.
    """

    model_config = ConfigDict(extra="allow")

    code: str
    message: str
    details: str | None = None
    service: str | None = None
