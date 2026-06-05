"""Perps (margin) markets models — markets, orderbook, candlesticks (#390).

Response models for the read-only margin market-data endpoints. Mirrors the
alias style of :mod:`kalshi.models.markets` (short Python field names + accept
both ``_dollars``/``_fp``-suffixed and bare wire names). Margin price fields are
``FixedPointDollars`` → :data:`~kalshi.types.DollarDecimal`; counts are
``FixedPointCount`` → :data:`~kalshi.types.FixedPointCount`.

Note: REST timestamps in this slice (``end_period_ts``) are Unix epoch **seconds**
integers (spec ``type: integer, format: int64``) — kept as bare ``int``, not
``AwareDatetime``.

The orderbook side is ``bids``/``asks`` (margin), **not** the prediction API's
``yes``/``no``; each level is a 2-tuple ``[price_dollars, contract_count_fp]``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal, FixedPointCount, MultiplierDecimal, NullableList

MarginMarketStatusLiteral = Literal["inactive", "active", "closed"]
"""Status filter for GET /margin/markets and ``MarginMarket.status``.

Spec schema ``MarginMarketStatus`` (``type: string``). Defined here as a
``Literal`` for the query-param signature; the ``StrEnum`` form lives in
:mod:`kalshi.perps.models.common` as :class:`~kalshi.perps.models.common.MarginMarketStatus`.
"""


class MarginMarket(BaseModel):
    """Spec ``MarginMarket`` — a margin market with trading stats.

    Price fields are ``FixedPointDollars`` strings (e.g. ``"0.5600"``); count
    fields are ``FixedPointCount`` strings. ``contract_size`` is a 6-decimal
    fixed-point dollar-style string (spec ``type: string``). ``_fp``-suffixed
    validation aliases on volume/count fields accept both the bare names the
    spec emits and the forward-compatible ``_fp`` form.
    """

    ticker: str
    title: str
    status: MarginMarketStatusLiteral
    contract_size: DollarDecimal
    tick_size: DollarDecimal
    fractional_trading_enabled: bool

    leverage_estimate: MultiplierDecimal | None = None
    price: DollarDecimal | None = None
    bid: DollarDecimal | None = None
    ask: DollarDecimal | None = None
    volume: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_fp", "volume"),
    )
    volume_24h: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_24h_fp", "volume_24h"),
    )
    open_interest: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("open_interest_fp", "open_interest"),
    )

    model_config = {"extra": "allow", "populate_by_name": True}


class MarginOrderbookLevel(BaseModel):
    """A single margin orderbook price level.

    Parsed from spec ``PriceLevelDollarsCountFp`` — a positional 2-tuple
    ``[price_dollars, contract_count_fp]``. Element 0 is the price in dollars,
    element 1 is the contract quantity (NOT a price).
    """

    price: DollarDecimal
    quantity: FixedPointCount

    model_config = {"extra": "allow"}


class MarginOrderbook(BaseModel):
    """Margin orderbook for a market (spec ``MarginOrderbookCount``).

    ``ticker`` is injected by the resource from the path arg (not on the wire).
    ``bids``/``asks`` tolerate a server-returned null via :data:`NullableList`.
    """

    ticker: str
    bids: NullableList[MarginOrderbookLevel] = []
    asks: NullableList[MarginOrderbookLevel] = []

    model_config = {"extra": "allow"}


class BidAskDistributionHistorical(BaseModel):
    """Spec ``BidAskDistributionHistorical`` — OHLC for quoted bid/ask prices.

    All four fields are required and non-null per spec.
    """

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


class PriceDistributionHistorical(BaseModel):
    """Spec ``PriceDistributionHistorical`` — OHLC for executed trade prices.

    Every field is ``nullable: true`` in the spec (values are JSON ``null`` when
    no trades occurred in the period), so all are ``DollarDecimal | None``. This
    margin schema has only these 6 fields — no ``min``/``max`` (those exist only
    on the public ``PriceDistribution``).
    """

    # Spec marks all 6 ``required`` AND ``nullable`` — the keys are present but
    # the values are JSON ``null`` when no trades occurred. Modeled as
    # required-key / nullable-value (no default) so required-drift stays aligned.
    open: DollarDecimal | None = Field(validation_alias=AliasChoices("open_dollars", "open"))
    high: DollarDecimal | None = Field(validation_alias=AliasChoices("high_dollars", "high"))
    low: DollarDecimal | None = Field(validation_alias=AliasChoices("low_dollars", "low"))
    close: DollarDecimal | None = Field(validation_alias=AliasChoices("close_dollars", "close"))
    mean: DollarDecimal | None = Field(validation_alias=AliasChoices("mean_dollars", "mean"))
    previous: DollarDecimal | None = Field(
        validation_alias=AliasChoices("previous_dollars", "previous")
    )

    model_config = {"extra": "allow", "populate_by_name": True}


class MarginMarketCandlestick(BaseModel):
    """Spec ``MarginMarketCandlestick`` — a margin candlestick data point.

    Uses ``bid``/``ask`` (margin) nested OHLC objects instead of the public
    ``yes_bid``/``yes_ask``. ``end_period_ts`` is a Unix-seconds int64.
    """

    end_period_ts: int
    bid: BidAskDistributionHistorical
    ask: BidAskDistributionHistorical
    price: PriceDistributionHistorical
    volume: FixedPointCount = Field(
        validation_alias=AliasChoices("volume_fp", "volume"),
    )
    open_interest: FixedPointCount = Field(
        validation_alias=AliasChoices("open_interest_fp", "open_interest"),
    )

    model_config = {"extra": "allow", "populate_by_name": True}


class GetMarginMarketsResponse(BaseModel):
    """Spec ``GetMarginMarketsResponse`` — the ``GET /margin/markets`` envelope.

    ``markets`` is spec-required and uses :data:`~kalshi.types.NullableList`: a
    **missing** key raises ``ValidationError`` (surfacing spec drift instead of a
    silent ``[]``), while a ``null`` array coerces to ``[]`` (Kalshi's
    empty-as-null convention). Mirrors the prediction-API list envelopes.
    """

    markets: NullableList[MarginMarket]

    model_config = {"extra": "allow"}


class GetMarginMarketCandlesticksResponse(BaseModel):
    """Spec ``GetMarginMarketCandlesticksResponse`` — the candlesticks envelope.

    Both ``ticker`` and ``candlesticks`` are spec-required. Validating the
    envelope keeps the required ``ticker`` from being silently dropped; the
    ``candlesticks`` array uses :data:`~kalshi.types.NullableList` (missing key
    -> error, ``null`` -> ``[]``).
    """

    ticker: str
    candlesticks: NullableList[MarginMarketCandlestick]

    model_config = {"extra": "allow"}
