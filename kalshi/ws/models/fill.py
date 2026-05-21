"""Fill channel message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.models.orders import BookSideLiteral, SideLiteral
from kalshi.types import DollarDecimal, FixedPointCount


class FillPayload(BaseModel):
    """Payload for fill messages (private channel).

    Wire format per AsyncAPI spec: ``yes_price_dollars`` is a dollar-decimal
    string; ``count_fp`` / ``post_position_fp`` are fixed-point count strings;
    ``fee_cost`` is a dollar-decimal string; ``ts`` is an integer Unix
    timestamp (seconds).
    """

    trade_id: str
    order_id: str
    market_ticker: str
    is_taker: bool
    side: str
    yes_price: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    count: FixedPointCount = Field(
        validation_alias=AliasChoices("count_fp", "count"),
    )
    fee_cost: DollarDecimal
    action: str  # buy/sell
    ts: int
    post_position: FixedPointCount = Field(
        validation_alias=AliasChoices("post_position_fp", "post_position"),
    )
    purchased_side: str
    client_order_id: str | None = None
    subaccount: int | None = None
    # v0.14+ backfill (#162). outcome_side/book_side are the canonical
    # direction encoding; ts_ms supersedes ts. action/side stay for compat.
    outcome_side: SideLiteral
    book_side: BookSideLiteral
    ts_ms: int
    model_config = {"extra": "allow"}


class FillMessage(BaseModel):
    """Fill update message. NO required seq."""

    type: str = "fill"
    sid: int
    seq: int | None = None
    msg: FillPayload
    model_config = {"extra": "allow"}
