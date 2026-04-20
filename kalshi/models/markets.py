"""Market-related models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal, NullableList


class Market(BaseModel):
    """A Kalshi prediction market.

    Price fields accept both ``_dollars``-suffixed names from the API
    (e.g. ``yes_bid_dollars``) and short names (e.g. ``yes_bid``).
    Volume/count fields accept both ``_fp``-suffixed names and short names.
    """

    ticker: str
    event_ticker: str | None = None
    market_type: str | None = None
    title: str | None = None
    subtitle: str | None = None
    yes_sub_title: str | None = None
    no_sub_title: str | None = None
    status: str | None = None

    # Price fields (FixedPointDollars)
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
    settlement_value: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("settlement_value_dollars", "settlement_value"),
    )
    liquidity: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("liquidity_dollars", "liquidity"),
    )

    # Size/volume fields (FixedPointCount)
    yes_bid_size: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_bid_size_fp", "yes_bid_size"),
    )
    yes_ask_size: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_ask_size_fp", "yes_ask_size"),
    )
    no_bid_size: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_bid_size_fp", "no_bid_size"),
    )
    no_ask_size: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_ask_size_fp", "no_ask_size"),
    )
    volume: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_fp", "volume"),
    )
    volume_24h: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_24h_fp", "volume_24h"),
    )
    open_interest: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("open_interest_fp", "open_interest"),
    )

    # Timestamps
    created_time: datetime | None = None
    updated_time: datetime | None = None
    open_time: datetime | None = None
    close_time: datetime | None = None
    latest_expiration_time: datetime | None = None
    expected_expiration_time: datetime | None = None
    expiration_time: datetime | None = None
    settlement_ts: datetime | None = None
    occurrence_datetime: datetime | None = None

    # Metadata
    settlement_timer_seconds: int | None = None
    result: str | None = None
    can_close_early: bool | None = None
    fractional_trading_enabled: bool | None = None
    expiration_value: str | None = None
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
    yes: NullableList[OrderbookLevel] = []
    no: NullableList[OrderbookLevel] = []


class BidAskDistribution(BaseModel):
    """OHLC data for bid/ask prices within a candlestick period."""

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

    model_config = {"populate_by_name": True}


class PriceDistribution(BaseModel):
    """OHLC data for trade prices within a candlestick period.

    Fields are nullable because there may be no trades in a period.
    """

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

    model_config = {"populate_by_name": True}


class Candlestick(BaseModel):
    """A candlestick data point for a market.

    The API returns nested OHLC objects for yes_bid, yes_ask, and price,
    plus volume and open interest as FixedPointCount strings.
    """

    end_period_ts: int | None = None
    yes_bid: BidAskDistribution | None = None
    yes_ask: BidAskDistribution | None = None
    price: PriceDistribution | None = None
    volume: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_fp", "volume"),
    )
    open_interest: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("open_interest_fp", "open_interest"),
    )

    # Legacy flat fields for backward compat with older API responses
    ticker: str | None = None
    period_start: datetime | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class MarketCandlesticks(BaseModel):
    """Per-market candlestick bundle in a bulk response.

    Spec schema ``MarketCandlesticksResponse`` — wraps a ticker and its
    candlesticks. The outer bulk response is ``{markets: [...]}``.
    """

    market_ticker: str
    # NullableList: Kalshi has returned JSON null for required list fields
    # in other envelopes (v0.9.0 Series fix). Coerce None -> [] to match the
    # pattern used on Orderbook.yes/no and envelope-level list fields.
    candlesticks: NullableList[Candlestick] = []

    model_config = {"extra": "allow"}
