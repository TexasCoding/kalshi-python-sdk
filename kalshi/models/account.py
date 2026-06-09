"""Account-scoped models — API tier limits, etc."""

from __future__ import annotations

from pydantic import BaseModel

from kalshi.types import NullableList


class RateLimit(BaseModel):
    """Per-direction (read/write) token-bucket rate limit.

    The server enforces a token bucket per direction: ``bucket_capacity``
    tokens are allowed in a burst; ``refill_rate`` tokens are added per
    second up to the cap. Requests above the cap return 429.
    """

    bucket_capacity: int
    refill_rate: int

    model_config = {"extra": "allow"}


class EndpointTokenCost(BaseModel):
    """Configured token cost for a single API endpoint."""

    method: str
    path: str
    cost: int

    model_config = {"extra": "allow"}


class AccountEndpointCosts(BaseModel):
    """Response from GET /account/endpoint_costs.

    Lists API v2 endpoints whose configured token cost differs from
    ``default_cost``. Endpoints using the default are omitted.
    """

    default_cost: int
    endpoint_costs: list[EndpointTokenCost]

    model_config = {"extra": "allow"}


class ApiUsageLevelGrant(BaseModel):
    """One API usage-level grant for a single exchange lane.

    Spec ``ApiUsageLevelGrant``. Each grant applies to its ``exchange_instance``
    (``event_contract`` or ``margined``); ``level`` is the usage level it confers
    (e.g. ``premier``/``paragon``/``prime``). ``source`` records how it was
    created (``volume`` for trading-volume earned, ``manual`` for Kalshi-assigned).
    ``expires_ts`` is a Unix-seconds expiry, absent (``None``) for permanent grants.
    """

    exchange_instance: str
    level: str
    source: str
    expires_ts: int | None = None

    model_config = {"extra": "allow"}


class AccountApiLimits(BaseModel):
    """Rate limits associated with the authenticated user's API tier.

    NOTE: The published OpenAPI spec (v3.13.0) declares ``read_limit`` and
    ``write_limit`` as ints, but the live server returns nested token-bucket
    objects under ``read`` and ``write``. The SDK matches the server. If the
    spec is corrected upstream, the contract-drift test will flag it.

    ``grants`` lists the caller's active usage-level grants across exchange
    lanes; ``usage_tier`` is the effective tier reported by this endpoint.
    """

    usage_tier: str
    read: RateLimit
    write: RateLimit
    grants: NullableList[ApiUsageLevelGrant]

    model_config = {"extra": "allow"}
