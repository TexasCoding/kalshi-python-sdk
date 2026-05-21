"""Historical data models."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, AwareDatetime, BaseModel, Field

from kalshi.models.orders import BookSideLiteral, SideLiteral
from kalshi.types import DollarDecimal, FixedPointCount

# Single-value enum per spec (MveHistoricalFilterQuery). mypy rejects plain
# `str` here even if it holds "exclude" at runtime — pass the literal directly.
MveHistoricalFilterLiteral = Literal["exclude"]
"""Multivariate-event filter for GET /historical/markets. Spec: MveHistoricalFilterQuery."""


class HistoricalCutoff(BaseModel):
    """Timestamps defining the boundary between live and historical data."""

    market_settled_ts: AwareDatetime
    trades_created_ts: AwareDatetime
    orders_updated_ts: AwareDatetime

    model_config = {"extra": "allow"}


class Trade(BaseModel):
    """A public trade on the exchange.

    ``count`` is typed ``FixedPointCount | None`` without ``default=None``
    because the OpenAPI spec (``Trade.required``) marks ``count_fp`` as a
    **required** response key. The ``| None`` admits server-side ``null``
    on rare degenerate trades while a missing key still raises
    ValidationError — schema regression, not a default.
    """

    trade_id: str
    ticker: str
    count: FixedPointCount | None = Field(
        validation_alias=AliasChoices("count_fp", "count"),
    )
    yes_price: DollarDecimal | None = Field(
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    no_price: DollarDecimal | None = Field(
        validation_alias=AliasChoices("no_price_dollars", "no_price"),
    )
    taker_side: str
    created_time: AwareDatetime

    # v3.18.0 backfill (#160). Mirrors Order.outcome_side / book_side from #159
    # — canonical direction encoding superseding the deprecated `taker_side`.
    taker_outcome_side: SideLiteral
    taker_book_side: BookSideLiteral

    model_config = {"extra": "allow", "populate_by_name": True}
