"""Historical data models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from kalshi.models.orders import BookSideLiteral, SideLiteral
from kalshi.types import DollarDecimal, FixedPointCount

# Single-value enum per spec (MveHistoricalFilterQuery). mypy rejects plain
# `str` here even if it holds "exclude" at runtime — pass the literal directly.
MveHistoricalFilterLiteral = Literal["exclude"]
"""Multivariate-event filter for GET /historical/markets. Spec: MveHistoricalFilterQuery."""


class HistoricalCutoff(BaseModel):
    """Timestamps defining the boundary between live and historical data."""

    market_settled_ts: datetime
    trades_created_ts: datetime
    orders_updated_ts: datetime

    model_config = {"extra": "allow"}


class Trade(BaseModel):
    """A public trade on the exchange."""

    trade_id: str
    ticker: str | None = None
    count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("count_fp", "count"),
    )
    yes_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    no_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_price_dollars", "no_price"),
    )
    taker_side: str | None = None
    created_time: datetime | None = None

    # v3.18.0 backfill (#160). Mirrors Order.outcome_side / book_side from #159
    # — canonical direction encoding superseding the deprecated `taker_side`.
    taker_outcome_side: SideLiteral | None = None
    taker_book_side: BookSideLiteral | None = None

    model_config = {"extra": "allow", "populate_by_name": True}
