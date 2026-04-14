"""Trade channel message models."""
from __future__ import annotations

from pydantic import BaseModel


class TradePayload(BaseModel):
    """Payload for trade messages (public channel)."""

    trade_id: str
    market_ticker: str
    yes_price: int | None = None  # cents
    no_price: int | None = None  # cents
    count: str | None = None  # _fp format
    taker_side: str | None = None
    ts: int | None = None
    model_config = {"extra": "allow"}


class TradeMessage(BaseModel):
    """Trade update message. NO required seq."""

    type: str = "trade"
    sid: int
    seq: int | None = None
    msg: TradePayload
