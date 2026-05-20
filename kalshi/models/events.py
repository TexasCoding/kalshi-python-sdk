"""Event-related models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from kalshi.models.markets import Market
from kalshi.types import NullableList

EventStatusLiteral = Literal["unopened", "open", "closed", "settled"]
"""Event status filter for GET /events. Spec: GetEvents.status query enum."""


class Event(BaseModel):
    """A Kalshi event (container for one or more markets)."""

    event_ticker: str
    series_ticker: str
    title: str
    sub_title: str
    collateral_return_type: str
    mutually_exclusive: bool
    category: str | None = None
    strike_date: datetime | None = None
    strike_period: str | None = None
    available_on_brokers: bool
    # Spec marks `product_metadata` required, but the live demo server omits
    # it on most events (observed run #26141405845, 2026-05-20). Recorded in
    # tests/_contract_support.py EXCLUSIONS as `server_omits_despite_required`.
    product_metadata: dict[str, Any] | None = None
    last_updated_ts: datetime | None = None
    markets: NullableList[Market] = []

    # v3.18.0 backfill (#160). fee_multiplier_override is `type: number,
    # format: double` per spec — Decimal (matches Market.floor_strike /
    # cap_strike precedent for the same wire shape).
    fee_type_override: str | None = None
    fee_multiplier_override: Decimal | None = None
    exchange_index: int | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class MarketMetadata(BaseModel):
    """Metadata for a market within an event."""

    market_ticker: str
    image_url: str
    color_code: str

    model_config = {"extra": "allow"}


class SettlementSource(BaseModel):
    """A settlement source for an event."""

    url: str | None = None
    name: str | None = None

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
