"""Event-related models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel

from kalshi.models.markets import Market
from kalshi.types import MultiplierDecimal, NullableList

EventStatusLiteral = Literal["unopened", "open", "closed", "settled"]
"""Event status filter for GET /events. Spec: GetEvents.status query enum."""


class SettlementSource(BaseModel):
    """A settlement source for an event."""

    url: str | None = None
    name: str | None = None

    model_config = {"extra": "allow"}


class Event(BaseModel):
    """A Kalshi event (container for one or more markets)."""

    event_ticker: str
    series_ticker: str
    title: str
    sub_title: str
    collateral_return_type: str
    mutually_exclusive: bool
    category: str | None = None
    strike_date: AwareDatetime | None = None
    strike_period: str | None = None
    # Spec dropped this field after OpenAPI 3.29.0 content drift; kept optional
    # so existing constructors and older responses still parse.
    available_on_brokers: bool | None = None
    # The live demo server omits `product_metadata` on most events (observed
    # run #26141405845, 2026-05-20). OpenAPI v3.20.0 relaxed it to optional
    # too (#385), so this is no longer a spec deviation — kept nullable to
    # match server reality.
    product_metadata: dict[str, Any] | None = None
    # Spec-required on EventData but `nullable: true` (added to the live
    # v3.21.0 spec post-#449, #451). NullableList coerces a JSON null -> [] so
    # the key-present contract holds while callers always see a list. Same
    # nullable shape as Series.settlement_sources; EventMetadata's is a plain
    # list because its spec field isn't nullable.
    settlement_sources: NullableList[SettlementSource]
    last_updated_ts: AwareDatetime | None = None
    markets: NullableList[Market] = []

    # v3.18.0 backfill (#160). fee_multiplier_override is `type: number,
    # format: double` per spec — Decimal (matches Market.floor_strike /
    # cap_strike precedent for the same wire shape).
    fee_type_override: str | None = None
    fee_multiplier_override: MultiplierDecimal | None = None
    exchange_index: int | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class EventFeeChange(BaseModel):
    """A scheduled event-level fee override (GET /events/fee_changes).

    Event fees layer on top of the parent series' fee structure.
    ``fee_type_override`` and ``fee_multiplier_override`` are both ``None``
    when the override has been cleared (the event falls back to the series
    fee). Both are spec-required keys (``EventFeeChange.required``) but
    nullable — the key must be present; ``None`` is a meaningful "override
    cleared" signal, so neither carries a default.
    """

    id: str
    event_ticker: str
    series_ticker: str
    fee_type_override: str | None
    fee_multiplier_override: MultiplierDecimal | None
    scheduled_ts: AwareDatetime

    model_config = {"extra": "allow"}


class MarketMetadata(BaseModel):
    """Metadata for a market within an event."""

    market_ticker: str
    image_url: str
    color_code: str

    model_config = {"extra": "allow"}


class EventMetadata(BaseModel):
    """Metadata for an event including images and settlement sources."""

    image_url: str
    featured_image_url: str | None = None
    # Spec says `market_details: list[MarketMetadata]` required, but the live
    # demo server sends JSON null for the value (observed run #26141405845).
    # NullableList coerces null -> [] so callers see a stable list type; the
    # spec contract (key present) is still enforced.
    market_details: NullableList[MarketMetadata]
    settlement_sources: list[SettlementSource]

    # v3.18.0 backfill (#160).
    competition: str | None = None
    competition_scope: str | None = None

    model_config = {"extra": "allow"}
