"""Incentive programs — market-level liquidity/volume reward programs.

Note on ``period_reward``: spec says "Total reward for the period in
centi-cents". The SDK exposes it as a plain ``int`` (caller converts to
dollars by dividing by 10 000). Fractional values come through
``target_size_fp`` (``FixedPointCount`` string).
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel

from kalshi.types import FixedPointCount, NullableList

IncentiveProgramStatusLiteral = Literal["all", "active", "upcoming", "closed", "paid_out"]
"""Incentive program status filter. Spec: GetIncentivePrograms.status query enum."""

IncentiveProgramTypeLiteral = Literal["all", "liquidity", "volume"]
"""Incentive program type filter. Spec: GetIncentivePrograms.type query enum."""


class IncentiveProgram(BaseModel):
    """A single incentive program rewarding liquidity or volume on a market."""

    id: str
    market_id: str
    market_ticker: str
    series_ticker: str | None = None
    event_ticker: str | None = None
    incentive_type: str  # "liquidity" | "volume"
    start_date: AwareDatetime
    end_date: AwareDatetime
    # Spec: integer (int64), centi-cents. Caller divides by 10000 for dollars.
    period_reward: int
    paid_out: bool
    discount_factor_bps: int | None = None
    target_size_fp: FixedPointCount | None = None

    # v3.18.0 backfill (#160).
    incentive_description: str
    max_reward_per_account: int | None = None

    model_config = {"extra": "allow"}


class GetIncentiveProgramsResponse(BaseModel):
    """Paginated response for GET /incentive_programs.

    Uses ``next_cursor`` (not ``cursor``) as the pagination key — unique
    to this endpoint.
    """

    incentive_programs: NullableList[IncentiveProgram] = []
    next_cursor: str | None = None

    model_config = {"extra": "allow"}


class IncentiveSchedule(BaseModel):
    """Recurring incentive terms for a series, or for one event of a series."""

    series_ticker: str
    series_title: str
    series_category: str
    # Spec-required but empty when the schedule covers the whole series;
    # the server may omit empties.
    event_ticker: str | None = None
    event_title: str | None = None
    incentive_type: str  # "liquidity" | "volume"
    source: str
    # Spec: integer (int64), centi-cents. Same convention as period_reward.
    reward: int
    window_days: int
    discount_factor_bps: int | None = None
    target_size_fp: FixedPointCount | None = None
    ends: AwareDatetime | None = None
    description: str
    all_markets: bool
    posted_ts: AwareDatetime
    updated_ts: AwareDatetime

    model_config = {"extra": "allow"}


class GetIncentiveSchedulesResponse(BaseModel):
    """Response for GET /incentive_schedules."""

    schedules: NullableList[IncentiveSchedule] = []

    model_config = {"extra": "allow"}
