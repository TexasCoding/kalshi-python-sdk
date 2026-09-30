"""Perps (margin) funding models — rate estimate, historical rates, premium index, payment history.

Response models for the four read-only perps **funding** endpoints (#395):

- :class:`MarginFundingRate` — a single applied historical funding rate.
- :class:`MarginFundingHistoryEntry` — one row of the authenticated user's
  per-payment funding history (the rate joined with the realized payment).
- :class:`MarginFundingRateEstimate` — the current in-progress rate estimate.
- :class:`MarginPremiumIndexPoint` — one per-second informational premium index.

Field-type rules (verified against ``specs/perps_openapi.yaml``):

- ``funding_rate`` is ``type: number, format: double`` and is **not** a price —
  it uses :data:`~kalshi.types.MultiplierDecimal` (exact ``Decimal``,
  string-serialized), matching the perps WS ticker's ``funding_rate``, NOT
  :data:`~kalshi.types.DollarDecimal`.
- ``mark_price`` / ``funding_amount`` are ``$ref FixedPointDollars`` strings →
  :data:`~kalshi.types.DollarDecimal`.
- ``quantity`` is ``$ref FixedPointCount`` → :data:`~kalshi.types.FixedPointCount`.
- ``funding_time`` / ``computed_time`` / ``next_funding_time`` /
  ``premium_index_ts`` / ``second_ts`` are RFC3339 ``format: date-time`` REST
  timestamps → :class:`~pydantic.AwareDatetime` (NOT ``_ms`` epoch ints).
- ``premium_index`` is a signed decimal fraction (spec ``type: string``) →
  :data:`~kalshi.types.MultiplierDecimal`.

These are response models only — this issue has no request bodies, so every
model uses ``extra="allow"`` (tolerate additive server fields) and never
``extra="forbid"``.
"""

from __future__ import annotations

from pydantic import AliasChoices, AwareDatetime, BaseModel, Field

from kalshi.types import (
    DollarDecimal,
    FixedPointCount,
    MultiplierDecimal,
    NullableList,
)


class MarginFundingRate(BaseModel):
    """Spec ``MarginFundingRate`` — a single applied historical funding rate.

    All four properties are spec-required (``market_ticker``, ``funding_time``,
    ``funding_rate``, ``mark_price``).
    """

    model_config = {"extra": "allow", "populate_by_name": True}

    market_ticker: str
    funding_time: AwareDatetime
    funding_rate: MultiplierDecimal
    mark_price: DollarDecimal = Field(
        validation_alias=AliasChoices("mark_price_dollars", "mark_price"),
    )


class MarginFundingHistoryEntry(BaseModel):
    """Spec ``MarginFundingHistoryEntry`` — one realized funding payment.

    All seven properties are spec-required. ``subaccount_number`` is marked
    ``required`` **and** ``nullable: true`` in the spec, so it is typed
    ``int | None`` with **no default** — a missing key still raises
    ``ValidationError`` while an explicit ``null`` is tolerated (same pattern as
    :class:`kalshi.models.historical.Trade.count`). ``0`` = primary subaccount.
    """

    model_config = {"extra": "allow", "populate_by_name": True}

    market_ticker: str
    funding_time: AwareDatetime
    funding_rate: MultiplierDecimal
    mark_price: DollarDecimal = Field(
        validation_alias=AliasChoices("mark_price_dollars", "mark_price"),
    )
    # Positive = received, negative = paid (per spec).
    funding_amount: DollarDecimal = Field(
        validation_alias=AliasChoices("funding_amount_dollars", "funding_amount"),
    )
    quantity: FixedPointCount = Field(
        validation_alias=AliasChoices("quantity_fp", "quantity"),
    )
    # Spec-required + nullable: no default so a missing key raises
    # ValidationError, while an explicit null is tolerated.
    subaccount_number: int | None


class MarginFundingRateEstimate(BaseModel):
    """Spec ``GetMarginFundingRateEstimateResponse`` — the in-progress rate estimate.

    The SDK returns the estimate object directly (the resource validates the
    response body), so the model drops the ``GetMargin...Response`` wrapper name.
    Only ``next_funding_time`` is spec-required; every other field is optional.
    """

    model_config = {"extra": "allow", "populate_by_name": True}

    market_ticker: str | None = None
    computed_time: AwareDatetime | None = None
    funding_rate: MultiplierDecimal | None = None
    mark_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("mark_price_dollars", "mark_price"),
    )
    next_funding_time: AwareDatetime
    # Final-second premium captured with this estimate. Omitted when that
    # second has no available premium (spec optional).
    premium_index: MultiplierDecimal | None = None
    premium_index_ts: AwareDatetime | None = None


class MarginPremiumIndexPoint(BaseModel):
    """Spec ``MarginPremiumIndexPoint`` — one per-second informational premium.

    Both properties are spec-required. ``premium_index`` is a signed decimal
    fraction of the index price (``"0"`` when no premium was measurable), not
    basis points. Informational only — it may not match the premium used in
    the actual funding calculation.
    """

    model_config = {"extra": "allow", "populate_by_name": True}

    second_ts: AwareDatetime
    premium_index: MultiplierDecimal


class GetMarginPremiumIndexResponse(BaseModel):
    """Spec ``GetMarginPremiumIndexResponse`` — premium-index envelope.

    ``points`` is spec-required and uses
    :data:`~kalshi.types.NullableList`: a missing key raises ``ValidationError``
    (surfacing drift), while a ``null`` array coerces to ``[]``.
    """

    points: NullableList[MarginPremiumIndexPoint]

    model_config = {"extra": "allow"}


class GetMarginHistoricalFundingRatesResponse(BaseModel):
    """Spec ``GetMarginHistoricalFundingRatesResponse`` — historical-rates envelope.

    ``funding_rates`` is spec-required and uses
    :data:`~kalshi.types.NullableList`: a missing key raises ``ValidationError``
    (surfacing drift), while a ``null`` array coerces to ``[]``.
    """

    funding_rates: NullableList[MarginFundingRate]

    model_config = {"extra": "allow"}


class GetMarginFundingHistoryResponse(BaseModel):
    """Spec ``GetMarginFundingHistoryResponse`` — funding-payment-history envelope.

    ``funding_history`` is spec-required (NullableList: missing key -> error,
    ``null`` -> ``[]``).
    """

    funding_history: NullableList[MarginFundingHistoryEntry]

    model_config = {"extra": "allow"}
