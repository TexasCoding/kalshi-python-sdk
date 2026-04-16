"""User orders channel message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field


class UserOrdersPayload(BaseModel):
    """Payload for user_orders messages (private channel)."""

    order_id: str
    user_id: str | None = None
    ticker: str | None = None
    status: str | None = None  # resting/canceled/executed
    side: str | None = None
    is_yes: bool | None = None
    yes_price: int | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )  # int cents; alias serves contract pipeline
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
    taker_fill_cost: str | None = Field(
        default=None,
        validation_alias=AliasChoices("taker_fill_cost_dollars", "taker_fill_cost"),
    )  # dollar string
    maker_fill_cost: str | None = Field(
        default=None,
        validation_alias=AliasChoices("maker_fill_cost_dollars", "maker_fill_cost"),
    )  # dollar string
    taker_fees: str | None = Field(
        default=None,
        validation_alias=AliasChoices("taker_fees_dollars", "taker_fees"),
    )  # dollar string
    maker_fees: str | None = Field(
        default=None,
        validation_alias=AliasChoices("maker_fees_dollars", "maker_fees"),
    )  # dollar string
    client_order_id: str | None = None
    created_time: str | None = None
    order_group_id: str | None = None
    last_update_time: str | None = None
    expiration_time: str | None = None
    subaccount_number: int | None = None
    model_config = {"extra": "allow"}


class UserOrdersMessage(BaseModel):
    """User orders update message. NO required seq."""

    type: str = "user_orders"
    sid: int
    seq: int | None = None
    msg: UserOrdersPayload
