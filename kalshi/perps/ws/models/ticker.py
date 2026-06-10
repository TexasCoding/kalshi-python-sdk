"""Margin ticker channel message models.

Perps-unique: the ticker payload carries a ``funding_rate`` (perps funding) and
``reference_price`` / ``settlement_mark_price`` / ``liquidation_mark_price``
mark-price objects — none of which exist on the prediction-API ticker. Prices
are single-sided (``price`` / ``bid`` / ``ask``), NOT ``yes_``/``no_``-prefixed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal, FixedPointCount, MultiplierDecimal


class FundingRate(BaseModel):
    """Perps funding-rate object (``fundingRate`` schema).

    ``rate`` is wire ``type: number, format: double``; typed
    :data:`~kalshi.types.MultiplierDecimal` (not bare ``float``) to avoid
    binary-float drift per the #225 invariant — the same handling
    ``Series.fee_multiplier`` uses. ``next_funding_time_ms`` and ``ts_ms`` are
    epoch milliseconds (``int``).
    """

    rate: MultiplierDecimal
    next_funding_time_ms: int
    ts_ms: int
    model_config = {"extra": "allow", "populate_by_name": True}


class TickerPrice(BaseModel):
    """A reference/mark price point (``tickerPrice`` schema).

    ``price`` is a USD fixed-point decimal string (4 decimals); ``ts_ms`` is
    epoch milliseconds (``int``).
    """

    price: DollarDecimal
    ts_ms: int
    model_config = {"extra": "allow", "populate_by_name": True}


class MarginTickerPayload(BaseModel):
    """Payload for ``ticker`` messages (``marginTickerPayload.msg``).

    Single-sided prices (``price``/``bid``/``ask``) — no ``yes_``/``no_``
    prefixes, unlike the prediction-API ticker. ``*_size_fp`` size fields are
    aliased to short names; the ``volume``/``volume_24h``/``open_interest``
    fields are bare strings on the wire (no ``_fp`` suffix) but are fixed-point
    counts, so they are typed :data:`~kalshi.types.FixedPointCount` with no
    alias. The mark-price + funding-rate fields are optional.
    """

    market_ticker: str
    price: DollarDecimal
    bid: DollarDecimal
    ask: DollarDecimal
    bid_size: FixedPointCount = Field(
        validation_alias=AliasChoices("bid_size_fp", "bid_size"),
    )
    ask_size: FixedPointCount = Field(
        validation_alias=AliasChoices("ask_size_fp", "ask_size"),
    )
    last_trade_size: FixedPointCount = Field(
        validation_alias=AliasChoices("last_trade_size_fp", "last_trade_size"),
    )
    volume: FixedPointCount
    volume_24h: FixedPointCount
    open_interest: FixedPointCount
    # Notional dollar values. The AsyncAPI marks these required, but they are
    # newly added on a *live* streaming channel — modeling them optional avoids
    # breaking an entire ticker subscription if a server omits them mid-rollout
    # (the WS payload-drift guard checks name coverage, not required-ness, and
    # the REST ``MarginMarket`` models the same fields optional). Short Python
    # names accept the ``_dollars``-suffixed wire keys.
    volume_notional_value: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_notional_value_dollars", "volume_notional_value"),
    )
    volume_24h_notional_value: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "volume_24h_notional_value_dollars", "volume_24h_notional_value"
        ),
    )
    open_interest_notional_value: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "open_interest_notional_value_dollars", "open_interest_notional_value"
        ),
    )
    reference_price: TickerPrice | None = None
    settlement_mark_price: TickerPrice | None = None
    liquidation_mark_price: TickerPrice | None = None
    funding_rate: FundingRate | None = None
    ts_ms: int
    model_config = {"extra": "allow", "populate_by_name": True}


class MarginTickerMessage(BaseModel):
    """Margin ticker update. ``seq`` is NOT required on this channel."""

    type: Literal["ticker"] = "ticker"
    sid: int
    seq: int | None = None
    msg: MarginTickerPayload
    model_config = {"extra": "allow", "populate_by_name": True}
