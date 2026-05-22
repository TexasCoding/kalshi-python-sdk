"""Ticker channel message models."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal, FixedPointCount


class TickerPayload(BaseModel):
    """Payload for ticker messages (public channel).

    Wire format per AsyncAPI spec: ``yes_bid_dollars`` / ``yes_ask_dollars`` are
    dollar-decimal strings; ``ts`` is an integer Unix timestamp (seconds);
    ``_fp`` fields are fixed-point count strings.
    """

    market_ticker: str
    market_id: str
    yes_bid: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_bid_dollars", "yes_bid"),
    )
    yes_ask: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_ask_dollars", "yes_ask"),
    )
    no_bid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_bid_dollars", "no_bid"),
    )
    no_ask: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_ask_dollars", "no_ask"),
    )
    volume: FixedPointCount = Field(
        validation_alias=AliasChoices("volume_fp", "volume"),
    )
    open_interest: FixedPointCount = Field(
        validation_alias=AliasChoices("open_interest_fp", "open_interest"),
    )
    dollar_volume: DollarDecimal
    dollar_open_interest: DollarDecimal
    yes_bid_size: FixedPointCount = Field(
        validation_alias=AliasChoices("yes_bid_size_fp", "yes_bid_size"),
    )
    yes_ask_size: FixedPointCount = Field(
        validation_alias=AliasChoices("yes_ask_size_fp", "yes_ask_size"),
    )
    last_trade_size: FixedPointCount = Field(
        validation_alias=AliasChoices("last_trade_size_fp", "last_trade_size"),
    )
    ts: int
    # v0.14+ backfill (#162). Spec promotes ts_ms (Unix ms) as the primary
    # timestamp; ts (seconds) stays for compat. Do NOT auto-convert.
    price: DollarDecimal = Field(
        validation_alias=AliasChoices("price_dollars", "price"),
    )
    ts_ms: int
    model_config = {"extra": "allow", "populate_by_name": True}


class TickerMessage(BaseModel):
    """Ticker update message. NO required seq."""

    type: Literal["ticker"] = "ticker"
    sid: int
    seq: int | None = None
    msg: TickerPayload
    model_config = {"extra": "allow", "populate_by_name": True}
