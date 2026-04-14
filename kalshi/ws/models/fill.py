"""Fill channel message models."""
from __future__ import annotations

from pydantic import BaseModel


class FillPayload(BaseModel):
    """Payload for fill messages (private channel)."""

    trade_id: str
    order_id: str | None = None
    market_ticker: str | None = None
    is_taker: bool | None = None
    side: str | None = None
    yes_price: int | None = None  # cents
    count: str | None = None  # _fp format
    fee_cost: str | None = None  # dollar string
    action: str | None = None  # buy/sell
    ts: int | None = None
    post_position: str | None = None  # _fp format
    purchased_side: str | None = None
    client_order_id: str | None = None
    subaccount: int | None = None
    model_config = {"extra": "allow"}


class FillMessage(BaseModel):
    """Fill update message. NO required seq."""

    type: str = "fill"
    sid: int
    seq: int | None = None
    msg: FillPayload
