"""Event-related models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from kalshi.models.markets import Market


class Event(BaseModel):
    """A Kalshi event (container for one or more markets)."""

    event_ticker: str
    series_ticker: str | None = None
    title: str | None = None
    sub_title: str | None = None
    collateral_return_type: str | None = None
    mutually_exclusive: bool | None = None
    category: str | None = None
    strike_date: datetime | None = None
    strike_period: str | None = None
    available_on_brokers: bool | None = None
    product_metadata: dict[str, Any] | None = None
    last_updated_ts: datetime | None = None
    markets: list[Market] | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class MarketMetadata(BaseModel):
    """Metadata for a market within an event."""

    market_ticker: str
    image_url: str | None = None
    color_code: str | None = None

    model_config = {"extra": "allow"}


class SettlementSource(BaseModel):
    """A settlement source for an event."""

    url: str | None = None
    name: str | None = None

    model_config = {"extra": "allow"}


class EventMetadata(BaseModel):
    """Metadata for an event including images and settlement sources."""

    image_url: str | None = None
    featured_image_url: str | None = None
    market_details: list[MarketMetadata] | None = None
    settlement_sources: list[SettlementSource] | None = None

    model_config = {"extra": "allow"}
