"""Fill channel message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.models.orders import BookSideLiteral, SideLiteral
from kalshi.types import DollarDecimal


class FillPayload(BaseModel):
    """Payload for fill messages (private channel).

    Wire format per AsyncAPI spec: ``yes_price_dollars`` is a dollar-decimal
    string; ``count_fp`` / ``post_position_fp`` are fixed-point count strings;
    ``fee_cost`` is a dollar-decimal string; ``ts`` is an integer Unix
    timestamp (seconds).
    """

    trade_id: str
    order_id: str | None = None
    market_ticker: str | None = None
    is_taker: bool | None = None
    side: str | None = None
    yes_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    count: str | None = Field(
        default=None,
        validation_alias=AliasChoices("count_fp", "count"),
    )  # _fp format
    fee_cost: DollarDecimal | None = None
    action: str | None = None  # buy/sell
    ts: int | None = None
    post_position: str | None = Field(
        default=None,
        validation_alias=AliasChoices("post_position_fp", "post_position"),
    )  # _fp format
    purchased_side: str | None = None
    client_order_id: str | None = None
    subaccount: int | None = None
    # v0.14+ backfill (#162). outcome_side/book_side are the canonical
    # direction encoding; ts_ms supersedes ts. action/side stay for compat.
    outcome_side: SideLiteral | None = None
    book_side: BookSideLiteral | None = None
    ts_ms: int | None = None
    model_config = {"extra": "allow"}


class FillMessage(BaseModel):
    """Fill update message. NO required seq."""

    type: str = "fill"
    sid: int
    seq: int | None = None
    msg: FillPayload
    model_config = {"extra": "allow"}
