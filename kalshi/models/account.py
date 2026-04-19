"""Account-scoped models — API tier limits, etc."""

from __future__ import annotations

from pydantic import BaseModel


class AccountApiLimits(BaseModel):
    """Rate limits associated with the authenticated user's API tier.

    ``read_limit`` and ``write_limit`` are requests-per-second ceilings
    the server will enforce before returning 429. ``usage_tier`` is a
    human-readable label (e.g., ``standard``, ``elevated``).
    """

    usage_tier: str
    read_limit: int
    write_limit: int

    model_config = {"extra": "allow"}
