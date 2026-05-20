"""Trade channel message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.models.orders import BookSideLiteral, SideLiteral
from kalshi.types import DollarDecimal


class TradePayload(BaseModel):
    """Payload for trade messages (public channel).

    Wire format per AsyncAPI spec: ``yes_price_dollars`` / ``no_price_dollars``
    are dollar-decimal strings; ``count_fp`` is a fixed-point count string;
    ``ts`` is an integer Unix timestamp (seconds).
    """

    trade_id: str
    market_ticker: str
    yes_price: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    no_price: DollarDecimal = Field(
        validation_alias=AliasChoices("no_price_dollars", "no_price"),
    )
    count: str = Field(
        validation_alias=AliasChoices("count_fp", "count"),
    )  # _fp format
    taker_side: str
    ts: int
    # v0.14+ backfill (#162). taker_outcome_side/taker_book_side are the
    # canonical direction encoding; ts_ms supersedes ts. taker_side stays.
    taker_outcome_side: SideLiteral
    taker_book_side: BookSideLiteral
    ts_ms: int
    model_config = {"extra": "allow"}


class TradeMessage(BaseModel):
    """Trade update message. NO required seq."""

    type: str = "trade"
    sid: int
    seq: int | None = None
    msg: TradePayload
    model_config = {"extra": "allow"}
