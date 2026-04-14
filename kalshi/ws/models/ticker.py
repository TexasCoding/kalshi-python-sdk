"""Ticker channel message models."""
from __future__ import annotations

from pydantic import BaseModel


class TickerPayload(BaseModel):
    """Payload for ticker messages (public channel)."""

    market_ticker: str
    market_id: str | None = None
    yes_bid: int | None = None
    yes_ask: int | None = None
    no_bid: int | None = None
    no_ask: int | None = None
    volume: str | None = None  # _fp format
    open_interest: str | None = None  # _fp format
    dollar_volume: str | None = None
    dollar_open_interest: str | None = None
    yes_bid_size: str | None = None  # _fp format
    yes_ask_size: str | None = None  # _fp format
    last_trade_size: str | None = None  # _fp format
    ts: int | None = None
    model_config = {"extra": "allow"}


class TickerMessage(BaseModel):
    """Ticker update message. NO required seq."""

    type: str = "ticker"
    sid: int
    seq: int | None = None
    msg: TickerPayload
