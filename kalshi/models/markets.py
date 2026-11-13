"""Market-related models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, AwareDatetime, BaseModel, Field

from kalshi.types import DollarDecimal, FixedPointCount, NullableList

MarketStatusLiteral = Literal["unopened", "open", "paused", "closed", "settled"]
"""Market status filter for GET /markets. Spec: MarketStatusQuery enum."""

MveFilterLiteral = Literal["only", "exclude"]
"""Multivariate-event filter for GET /markets. Spec: MveFilterQuery enum."""


class Market(BaseModel):
    """A Kalshi prediction market.

    Price fields accept both ``_dollars``-suffixed names from the API
    (e.g. ``yes_bid_dollars``) and short names (e.g. ``yes_bid``).
    Volume/count fields accept both ``_fp``-suffixed names and short names.
    """

    ticker: str
    event_ticker: str
    market_type: str
    title: str | None = None
    subtitle: str | None = None
    yes_sub_title: str
    no_sub_title: str
    status: str

    # Price fields (FixedPointDollars)
    yes_bid: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_bid_dollars", "yes_bid"),
    )
    yes_ask: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_ask_dollars", "yes_ask"),
    )
    no_bid: DollarDecimal = Field(
        validation_alias=AliasChoices("no_bid_dollars", "no_bid"),
    )
    no_ask: DollarDecimal = Field(
        validation_alias=AliasChoices("no_ask_dollars", "no_ask"),
    )
    last_price: DollarDecimal = Field(
        validation_alias=AliasChoices("last_price_dollars", "last_price"),
    )
    previous_yes_bid: DollarDecimal = Field(
        validation_alias=AliasChoices("previous_yes_bid_dollars", "previous_yes_bid"),
    )
    previous_yes_ask: DollarDecimal = Field(
        validation_alias=AliasChoices("previous_yes_ask_dollars", "previous_yes_ask"),
    )
    previous_price: DollarDecimal = Field(
        validation_alias=AliasChoices("previous_price_dollars", "previous_price"),
    )
    notional_value: DollarDecimal = Field(
        validation_alias=AliasChoices("notional_value_dollars", "notional_value"),
    )
    settlement_value: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("settlement_value_dollars", "settlement_value"),
    )
    liquidity: DollarDecimal = Field(
        validation_alias=AliasChoices("liquidity_dollars", "liquidity"),
    )

    # Size/volume fields (FixedPointCount)
    yes_bid_size: FixedPointCount = Field(
        validation_alias=AliasChoices("yes_bid_size_fp", "yes_bid_size"),
    )
    yes_ask_size: FixedPointCount = Field(
        validation_alias=AliasChoices("yes_ask_size_fp", "yes_ask_size"),
    )
    no_bid_size: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("no_bid_size_fp", "no_bid_size"),
    )
    no_ask_size: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("no_ask_size_fp", "no_ask_size"),
    )
    volume: FixedPointCount = Field(
        validation_alias=AliasChoices("volume_fp", "volume"),
    )
    volume_24h: FixedPointCount = Field(
        validation_alias=AliasChoices("volume_24h_fp", "volume_24h"),
    )
    open_interest: FixedPointCount = Field(
        validation_alias=AliasChoices("open_interest_fp", "open_interest"),
    )

    # Timestamps
    created_time: AwareDatetime
    updated_time: AwareDatetime
    open_time: AwareDatetime
    close_time: AwareDatetime
    latest_expiration_time: AwareDatetime
    expected_expiration_time: AwareDatetime | None = None
    expiration_time: AwareDatetime | None = None
    settlement_ts: AwareDatetime | None = None
    # ``floor`` markets may also send settlement_floor_dollars.
    settlement_bounds_type: Literal["default", "floor"]
    settlement_floor: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("settlement_floor_dollars", "settlement_floor"),
    )
    occurrence_datetime: AwareDatetime | None = None

    # Metadata
    settlement_timer_seconds: int
    result: str
    can_close_early: bool
    # Spec 3.23.0 dropped this field from the Market schema (previously required).
    # Optional/defensive: older servers still emit it; newer ones may omit it, so
    # a bare ``bool`` would hard-fail Market parsing if it disappears.
    fractional_trading_enabled: bool | None = None
    expiration_value: str
    category: str | None = None
    risk_limit_cents: int | None = None
    strike_type: str | None = None
    floor_strike: DollarDecimal | None = None
    cap_strike: DollarDecimal | None = None
    rules_primary: str
    rules_secondary: str

    # v3.18.0 backfill (#159). mve_selected_legs is list[MveSelectedLeg] and
    # price_ranges is list[PriceRange] on the wire — kept as list[dict] here;
    # no nested model classes yet (separable polish).
    custom_strike: dict[str, Any] | None = None
    early_close_condition: str | None = None
    exchange_index: int | None = None
    fee_waiver_expiration_time: AwareDatetime | None = None
    functional_strike: str | None = None
    is_provisional: bool | None = None
    mve_collection_ticker: str | None = None
    mve_selected_legs: list[dict[str, Any]] | None = None
    price_level_structure: str
    price_ranges: NullableList[dict[str, Any]]
    primary_participant_key: str | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class OrderbookLevel(BaseModel):
    """A single price level in the orderbook.

    Quantity is FixedPointCount — fractional contract counts are sent as
    FixedPointCount strings like ``"100.50"`` from the API.
    """

    price: DollarDecimal
    quantity: FixedPointCount

    model_config = {"extra": "allow"}


class Orderbook(BaseModel):
    """Orderbook for a market."""

    ticker: str
    yes: NullableList[OrderbookLevel] = []
    no: NullableList[OrderbookLevel] = []

    model_config = {"extra": "allow"}


class BidAskDistribution(BaseModel):
    """OHLC data for bid/ask prices within a candlestick period."""

    open: DollarDecimal = Field(
        validation_alias=AliasChoices("open_dollars", "open"),
    )
    high: DollarDecimal = Field(
        validation_alias=AliasChoices("high_dollars", "high"),
    )
    low: DollarDecimal = Field(
        validation_alias=AliasChoices("low_dollars", "low"),
    )
    close: DollarDecimal = Field(
        validation_alias=AliasChoices("close_dollars", "close"),
    )

    model_config = {"extra": "allow", "populate_by_name": True}


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
    # v3.18.0 spec additions (#171). All four nullable per spec since the
    # candlestick window may contain no trades.
    mean: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("mean_dollars", "mean"),
    )
    previous: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("previous_dollars", "previous"),
    )
    min: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("min_dollars", "min"),
    )
    max: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("max_dollars", "max"),
    )

    model_config = {"extra": "allow", "populate_by_name": True}


class Candlestick(BaseModel):
    """A candlestick data point for a market.

    The API returns nested OHLC objects for yes_bid, yes_ask, and price,
    plus volume and open interest as FixedPointCount strings.
    """

    end_period_ts: int
    yes_bid: BidAskDistribution
    yes_ask: BidAskDistribution
    price: PriceDistribution
    volume: FixedPointCount = Field(
        validation_alias=AliasChoices("volume_fp", "volume"),
    )
    open_interest: FixedPointCount = Field(
        validation_alias=AliasChoices("open_interest_fp", "open_interest"),
    )

    # Legacy flat fields for backward compat with older API responses
    ticker: str | None = None
    period_start: AwareDatetime | None = None

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
    candlesticks: NullableList[Candlestick]

    model_config = {"extra": "allow"}


class GetMarketCandlesticksResponse(BaseModel):
    """Spec ``GetMarketCandlesticksResponse`` — single-market candlesticks envelope.

    ``ticker`` and ``candlesticks`` are spec-required. ``candlesticks`` uses
    :data:`~kalshi.types.NullableList` so a **missing** key hard-fails (surfacing
    spec drift instead of silently returning ``[]``) while a ``null`` value —
    Kalshi's observed "empty-as-null" convention — coerces to ``[]`` (the prior
    ``data.get(...)`` extraction would ``TypeError`` on a null array).
    """

    ticker: str
    candlesticks: NullableList[Candlestick]

    model_config = {"extra": "allow"}


class BatchGetMarketCandlesticksResponse(BaseModel):
    """Spec ``BatchGetMarketCandlesticksResponse`` — bulk-candlesticks envelope.

    ``markets`` is spec-required (NullableList: missing key -> error, null -> []).
    """

    markets: NullableList[MarketCandlesticks]

    model_config = {"extra": "allow"}


class GetMarketOrderbooksResponse(BaseModel):
    """Spec ``GetMarketOrderbooksResponse`` — bulk-orderbooks envelope.

    ``orderbooks`` is spec-required (NullableList: missing key -> error, null ->
    []). Items stay raw dicts — the resource transforms each via
    ``_orderbook_from_item`` (the yes/no FixedPoint parsing it already owns).
    """

    orderbooks: NullableList[dict[str, Any]]

    model_config = {"extra": "allow"}


WeatherPointVariableLiteral = Literal["precip_hours", "precip_total", "max_temp", "min_temp"]
"""What a weather point market measures. Spec: WeatherPointVariable enum."""


class CreateWeatherPointMarketRequest(BaseModel):
    """Body for POST /weather_point_markets.

    Matches spec ``components.schemas.CreateWeatherPointMarketRequest``.
    Required: ``latitude``, ``longitude``, ``variable``, ``strike_type``,
    ``date``, ``start_hour``, ``end_hour``, ``timezone``. Optional:
    ``floor_value``, ``cap_value``.
    """

    latitude: float
    longitude: float
    variable: WeatherPointVariableLiteral
    strike_type: Literal["greater", "less", "between"]
    date: str
    start_hour: int
    end_hour: int
    timezone: str
    floor_value: int | None = None
    cap_value: int | None = None

    model_config = {"extra": "forbid"}


class CreateWeatherPointMarketResponse(BaseModel):
    """Response from POST /weather_point_markets."""

    event_ticker: str
    market_ticker: str
    created: bool
    latitude: float
    longitude: float

    model_config = {"extra": "allow"}


class WeatherPointDomain(BaseModel):
    """A NOAA MRMS domain a weather-point location may lie in."""

    name: str
    north: float
    south: float
    west: float
    east: float

    model_config = {"extra": "allow"}


class WeatherPointVariableAvailability(BaseModel):
    """Where new markets of one weather-point variable may be created."""

    variable: WeatherPointVariableLiteral
    domains: NullableList[str]

    model_config = {"extra": "allow"}


class GetWeatherPointAvailabilityResponse(BaseModel):
    """Response from GET /weather_point_markets/availability."""

    enabled: bool
    domains: NullableList[WeatherPointDomain]
    variables: NullableList[WeatherPointVariableAvailability]

    model_config = {"extra": "allow"}


ConcertCoverLiteral = Literal["postponed", "cancelled", "either"]
"""What a concert cancellation market pays on. Spec: ConcertCover enum."""


class CreateConcertCancellationMarketRequest(BaseModel):
    """Body for POST /concert_cancellation_markets.

    Matches spec ``components.schemas.CreateConcertCancellationMarketRequest``.
    Required: ``jambase_event_id``, ``scheduled_date`` (YYYY-MM-DD), ``cover``.
    """

    jambase_event_id: str
    scheduled_date: str
    cover: ConcertCoverLiteral

    model_config = {"extra": "forbid"}


class CreateConcertCancellationMarketResponse(BaseModel):
    """Response from POST /concert_cancellation_markets."""

    cover: ConcertCoverLiteral
    event_ticker: str
    market_ticker: str
    created: bool

    model_config = {"extra": "allow"}


class ConcertMetro(BaseModel):
    """A metro whose concerts ``GET /concert_cancellation_markets/concerts`` lists."""

    id: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    upcoming_shows: int

    model_config = {"extra": "allow"}


class GetConcertCancellationAvailabilityResponse(BaseModel):
    """Response from GET /concert_cancellation_markets/availability."""

    enabled: bool
    covers: NullableList[ConcertCoverLiteral]
    max_days_ahead: int
    metros: NullableList[ConcertMetro]

    model_config = {"extra": "allow"}


class ConcertMarket(BaseModel):
    """Event and market tickers a show has or would get for one cover."""

    cover: ConcertCoverLiteral
    event_ticker: str
    market_ticker: str

    model_config = {"extra": "allow"}


class Concert(BaseModel):
    """A concert listing that a cancellation market can still be created for."""

    jambase_event_id: str
    name: str
    lineup: NullableList[str]
    venue_name: str
    timezone: str
    scheduled_date: str
    markets: NullableList[ConcertMarket]
    headliner: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    start_time: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    url: str | None = None

    model_config = {"extra": "allow"}


class GetConcertsResponse(BaseModel):
    """Response from GET /concert_cancellation_markets/concerts."""

    concerts: NullableList[Concert]
    page: int
    total_pages: int

    model_config = {"extra": "allow"}


class SearchConcertsResponse(BaseModel):
    """Response from GET /concert_cancellation_markets/concerts/search."""

    concerts: NullableList[Concert]

    model_config = {"extra": "allow"}
