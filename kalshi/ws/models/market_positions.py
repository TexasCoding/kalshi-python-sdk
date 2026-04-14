"""Market positions channel message models."""
from __future__ import annotations

from pydantic import BaseModel


class MarketPositionsPayload(BaseModel):
    """Payload for market_positions messages (private channel)."""

    user_id: str | None = None
    market_ticker: str
    position: str | None = None  # _fp format
    position_cost: str | None = None  # dollar string
    realized_pnl: str | None = None  # dollar string
    fees_paid: str | None = None  # dollar string
    position_fee_cost: str | None = None  # dollar string
    volume: str | None = None  # _fp format
    subaccount: int | None = None
    model_config = {"extra": "allow"}


class MarketPositionsMessage(BaseModel):
    """Market positions update message. NO required seq."""

    type: str = "market_positions"
    sid: int
    seq: int | None = None
    msg: MarketPositionsPayload
