"""User orders channel message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal


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
    user_id: str | None = None
    ticker: str | None = None
    status: str | None = None  # resting/canceled/executed
    side: str | None = None
    is_yes: bool | None = None
    yes_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    fill_count: str | None = Field(
        default=None,
        validation_alias=AliasChoices("fill_count_fp", "fill_count"),
    )  # _fp format
    remaining_count: str | None = Field(
        default=None,
        validation_alias=AliasChoices("remaining_count_fp", "remaining_count"),
    )  # _fp format
    initial_count: str | None = Field(
        default=None,
        validation_alias=AliasChoices("initial_count_fp", "initial_count"),
    )  # _fp format
    taker_fill_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("taker_fill_cost_dollars", "taker_fill_cost"),
    )
    maker_fill_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("maker_fill_cost_dollars", "maker_fill_cost"),
    )
    taker_fees: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("taker_fees_dollars", "taker_fees"),
    )
    maker_fees: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("maker_fees_dollars", "maker_fees"),
    )
    client_order_id: str | None = None
    created_time: str | None = None
    order_group_id: str | None = None
    last_update_time: str | None = None
    expiration_time: str | None = None
    subaccount_number: int | None = None
    model_config = {"extra": "allow"}


class UserOrdersMessage(BaseModel):
    """User orders update message. NO required seq."""

    type: str = "user_order"
    sid: int
    seq: int | None = None
    msg: UserOrdersPayload
