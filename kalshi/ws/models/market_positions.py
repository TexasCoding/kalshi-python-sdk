"""Market positions channel message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field


class MarketPositionsPayload(BaseModel):
    """Payload for market_positions messages (private channel)."""

    user_id: str | None = None
    market_ticker: str
    position: str | None = Field(
        default=None,
        validation_alias=AliasChoices("position_fp", "position"),
    )  # _fp format
    position_cost: str | None = Field(
        default=None,
        validation_alias=AliasChoices("position_cost_dollars", "position_cost"),
    )  # dollar string
    realized_pnl: str | None = Field(
        default=None,
        validation_alias=AliasChoices("realized_pnl_dollars", "realized_pnl"),
    )  # dollar string
    fees_paid: str | None = Field(
        default=None,
        validation_alias=AliasChoices("fees_paid_dollars", "fees_paid"),
    )  # dollar string
    position_fee_cost: str | None = Field(
        default=None,
        validation_alias=AliasChoices("position_fee_cost_dollars", "position_fee_cost"),
    )  # dollar string
    volume: str | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_fp", "volume"),
    )  # _fp format
    subaccount: int | None = None
    model_config = {"extra": "allow"}


class MarketPositionsMessage(BaseModel):
    """Market positions update message. NO required seq."""

    type: str = "market_positions"
    sid: int
    seq: int | None = None
    msg: MarketPositionsPayload
