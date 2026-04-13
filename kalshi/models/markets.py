"""Market-related models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from kalshi.types import DollarDecimal


class Market(BaseModel):
    """A Kalshi prediction market."""

    ticker: str
    event_ticker: str | None = None
    title: str | None = None
    subtitle: str | None = None
    status: str | None = None
    yes_bid: DollarDecimal | None = None
    yes_ask: DollarDecimal | None = None
    no_bid: DollarDecimal | None = None
    no_ask: DollarDecimal | None = None
    last_price: DollarDecimal | None = None
    volume: int | None = None
    volume_24h: int | None = None
    open_interest: int | None = None
    open_time: datetime | None = None
    close_time: datetime | None = None
    result: str | None = None
    can_close_early: bool | None = None
    expiration_time: datetime | None = None
    category: str | None = None
    risk_limit_cents: int | None = None
    strike_type: str | None = None
    floor_strike: Decimal | None = None
    cap_strike: Decimal | None = None
    rules_primary: str | None = None
    rules_secondary: str | None = None

    model_config = {"extra": "allow"}


class OrderbookLevel(BaseModel):
    """A single price level in the orderbook."""

    price: DollarDecimal
    quantity: int


class Orderbook(BaseModel):
    """Orderbook for a market."""

    ticker: str
    yes: list[OrderbookLevel] = []
    no: list[OrderbookLevel] = []


class Candlestick(BaseModel):
    """A candlestick (OHLCV) data point."""

    ticker: str | None = None
    period_start: datetime | None = None
    open: DollarDecimal | None = None
    high: DollarDecimal | None = None
    low: DollarDecimal | None = None
    close: DollarDecimal | None = None
    volume: int | None = None
    open_interest: int | None = None
