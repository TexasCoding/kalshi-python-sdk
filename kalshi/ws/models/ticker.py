"""Ticker channel message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field


class TickerPayload(BaseModel):
    """Payload for ticker messages (public channel)."""

    market_ticker: str
    market_id: str | None = None
    yes_bid: int | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_bid_dollars", "yes_bid"),
    )
    yes_ask: int | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_ask_dollars", "yes_ask"),
    )
    no_bid: int | None = None
    no_ask: int | None = None
    volume: str | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_fp", "volume"),
    )  # _fp format
    open_interest: str | None = Field(
        default=None,
        validation_alias=AliasChoices("open_interest_fp", "open_interest"),
    )  # _fp format
    dollar_volume: str | None = None
    dollar_open_interest: str | None = None
    yes_bid_size: str | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_bid_size_fp", "yes_bid_size"),
    )  # _fp format
    yes_ask_size: str | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_ask_size_fp", "yes_ask_size"),
    )  # _fp format
    last_trade_size: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_trade_size_fp", "last_trade_size"),
    )  # _fp format
    ts: int | None = None
    model_config = {"extra": "allow"}


class TickerMessage(BaseModel):
    """Ticker update message. NO required seq."""

    type: str = "ticker"
    sid: int
    seq: int | None = None
    msg: TickerPayload
