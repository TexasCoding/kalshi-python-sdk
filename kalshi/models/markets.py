"""Market-related models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal


class Market(BaseModel):
    """A Kalshi prediction market.

    Price fields accept both ``_dollars``-suffixed names from the API
    (e.g. ``yes_bid_dollars``) and short names (e.g. ``yes_bid``).
    """

    ticker: str
    event_ticker: str | None = None
    title: str | None = None
    subtitle: str | None = None
    status: str | None = None
    yes_bid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_bid_dollars", "yes_bid"),
    )
    yes_ask: DollarDecimal | None = Field(
        default=None,
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
    last_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("last_price_dollars", "last_price"),
    )
    previous_yes_bid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("previous_yes_bid_dollars", "previous_yes_bid"),
    )
    previous_yes_ask: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("previous_yes_ask_dollars", "previous_yes_ask"),
    )
    previous_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("previous_price_dollars", "previous_price"),
    )
    notional_value: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("notional_value_dollars", "notional_value"),
    )
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

    model_config = {"extra": "allow", "populate_by_name": True}


class OrderbookLevel(BaseModel):
    """A single price level in the orderbook.

    Quantity is DollarDecimal to support fractional contracts
    (FixedPointCount strings like ``"100.50"`` from the API).
    """

    price: DollarDecimal
    quantity: DollarDecimal


class Orderbook(BaseModel):
    """Orderbook for a market."""

    ticker: str
    yes: list[OrderbookLevel] = []
    no: list[OrderbookLevel] = []


class Candlestick(BaseModel):
    """A candlestick (OHLCV) data point.

    OHLC fields accept both ``_dollars``-suffixed names from the API
    and short names.
    """

    ticker: str | None = None
    period_start: datetime | None = None
    open: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("open_dollars", "open"),
    )
    high: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("high_dollars", "high"),
    )
    low: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("low_dollars", "low"),
    )
    close: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("close_dollars", "close"),
    )
    volume: int | None = None
    open_interest: int | None = None

    model_config = {"populate_by_name": True}
