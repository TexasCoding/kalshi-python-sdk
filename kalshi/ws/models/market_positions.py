"""Market positions channel message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal


class MarketPositionsPayload(BaseModel):
    """Payload for market_positions messages (private channel).

    Dollar-denominated fields use :data:`DollarDecimal` per the CLAUDE.md
    convention. ``position`` is a fixed-point contract count (string).
    """

    user_id: str | None = None
    market_ticker: str
    position: str | None = Field(
        default=None,
        validation_alias=AliasChoices("position_fp", "position"),
    )  # _fp format
    position_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("position_cost_dollars", "position_cost"),
    )
    realized_pnl: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("realized_pnl_dollars", "realized_pnl"),
    )
    fees_paid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("fees_paid_dollars", "fees_paid"),
    )
    position_fee_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("position_fee_cost_dollars", "position_fee_cost"),
    )
    volume: str | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_fp", "volume"),
    )  # _fp format
    subaccount: int | None = None
    model_config = {"extra": "allow"}


class MarketPositionsMessage(BaseModel):
    """Market positions update message. NO required seq."""

    type: str = "market_position"
    sid: int
    seq: int | None = None
    msg: MarketPositionsPayload
