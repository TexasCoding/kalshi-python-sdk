"""Trade channel message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal


class TradePayload(BaseModel):
    """Payload for trade messages (public channel).

    Wire format per AsyncAPI spec: ``yes_price_dollars`` / ``no_price_dollars``
    are dollar-decimal strings; ``count_fp`` is a fixed-point count string;
    ``ts`` is an integer Unix timestamp (seconds).
    """

    trade_id: str
    market_ticker: str
    yes_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    no_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_price_dollars", "no_price"),
    )
    count: str | None = Field(
        default=None,
        validation_alias=AliasChoices("count_fp", "count"),
    )  # _fp format
    taker_side: str | None = None
    ts: int | None = None
    model_config = {"extra": "allow"}


class TradeMessage(BaseModel):
    """Trade update message. NO required seq."""

    type: str = "trade"
    sid: int
    seq: int | None = None
    msg: TradePayload
