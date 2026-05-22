"""User orders channel message models."""
from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, AwareDatetime, BaseModel, Field

from kalshi.models.orders import (
    BookSideLiteral,
    SelfTradePreventionTypeLiteral,
    SideLiteral,
)
from kalshi.types import DollarDecimal, FixedPointCount


class UserOrdersPayload(BaseModel):
    """Payload for user_orders messages (private channel).

    Wire format captured on demo 2026-04-19: ``yes_price_dollars`` is a dollar
    string with up to 4 decimals (``"0.0100"``); ``*_fp`` counts are 2-decimal
    fixed-point strings; ``taker_fill_cost_dollars`` / ``maker_fill_cost_dollars``
    / ``taker_fees_dollars`` / ``maker_fees_dollars`` are dollar strings with
    up to 6 decimals. All stored as :class:`decimal.Decimal` via
    :data:`DollarDecimal`.
    """

    order_id: str
    user_id: str
    ticker: str
    status: str  # resting/canceled/executed
    side: str
    is_yes: bool
    yes_price: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    fill_count: FixedPointCount = Field(
        validation_alias=AliasChoices("fill_count_fp", "fill_count"),
    )
    remaining_count: FixedPointCount = Field(
        validation_alias=AliasChoices("remaining_count_fp", "remaining_count"),
    )
    initial_count: FixedPointCount = Field(
        validation_alias=AliasChoices("initial_count_fp", "initial_count"),
    )
    taker_fill_cost: DollarDecimal = Field(
        validation_alias=AliasChoices("taker_fill_cost_dollars", "taker_fill_cost"),
    )
    maker_fill_cost: DollarDecimal = Field(
        validation_alias=AliasChoices("maker_fill_cost_dollars", "maker_fill_cost"),
    )
    taker_fees: DollarDecimal = Field(
        validation_alias=AliasChoices("taker_fees_dollars", "taker_fees"),
    )
    maker_fees: DollarDecimal = Field(
        validation_alias=AliasChoices("maker_fees_dollars", "maker_fees"),
    )
    client_order_id: str
    created_time: AwareDatetime
    order_group_id: str | None = None
    last_update_time: AwareDatetime | None = None
    expiration_time: AwareDatetime | None = None
    subaccount_number: int | None = None
    # v0.14+ backfill (#162). outcome_side/book_side/self_trade_prevention_type
    # mirror Order from #159. *_ts_ms (Unix ms) supersede the *_time RFC3339
    # siblings — both stay; do NOT auto-convert.
    outcome_side: SideLiteral
    book_side: BookSideLiteral
    self_trade_prevention_type: SelfTradePreventionTypeLiteral | None = None
    created_ts_ms: int
    last_updated_ts_ms: int | None = None
    expiration_ts_ms: int | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class UserOrdersMessage(BaseModel):
    """User orders update message. NO required seq."""

    type: Literal["user_order"] = "user_order"
    sid: int
    seq: int | None = None
    msg: UserOrdersPayload
    model_config = {"extra": "allow", "populate_by_name": True}
