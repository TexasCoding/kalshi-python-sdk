"""Account-scoped models — API tier limits, etc."""

from __future__ import annotations

from pydantic import BaseModel


class RateLimit(BaseModel):
    """Per-direction (read/write) token-bucket rate limit.

    The server enforces a token bucket per direction: ``bucket_capacity``
    tokens are allowed in a burst; ``refill_rate`` tokens are added per
    second up to the cap. Requests above the cap return 429.
    """

    bucket_capacity: int
    refill_rate: int

    model_config = {"extra": "allow"}


class AccountApiLimits(BaseModel):
    """Rate limits associated with the authenticated user's API tier.

    NOTE: The published OpenAPI spec (v3.13.0) declares ``read_limit`` and
    ``write_limit`` as ints, but the live server returns nested token-bucket
    objects under ``read`` and ``write``. The SDK matches the server. If the
    spec is corrected upstream, the contract-drift test will flag it.
    """

    usage_tier: str
    read: RateLimit
    write: RateLimit

    model_config = {"extra": "allow"}
