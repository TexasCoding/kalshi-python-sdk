"""User orders channel message models."""
from __future__ import annotations

from pydantic import BaseModel


class UserOrdersPayload(BaseModel):
    """Payload for user_orders messages (private channel)."""

    order_id: str
    user_id: str | None = None
    ticker: str | None = None
    status: str | None = None  # resting/canceled/executed
    side: str | None = None
    is_yes: bool | None = None
    yes_price: int | None = None  # cents
    fill_count: str | None = None  # _fp format
    remaining_count: str | None = None  # _fp format
    initial_count: str | None = None  # _fp format
    taker_fill_cost: str | None = None  # dollar string
    maker_fill_cost: str | None = None  # dollar string
    taker_fees: str | None = None  # dollar string
    maker_fees: str | None = None  # dollar string
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
