"""Series-related models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from kalshi.models.markets import Candlestick
from kalshi.types import DollarDecimal

# Fee type constants (use str fields, not StrEnum, for forward-compat)
FEE_TYPE_QUADRATIC = "quadratic"
FEE_TYPE_QUADRATIC_WITH_MAKER_FEES = "quadratic_with_maker_fees"
FEE_TYPE_FLAT = "flat"


class Series(BaseModel):
    """A Kalshi series (template for recurring events)."""

    ticker: str
    frequency: str
    title: str
    category: str
    tags: list[str] = []
    settlement_sources: list[dict[str, Any]] = []
    contract_url: str = ""
    contract_terms_url: str = ""
    product_metadata: dict[str, Any] | None = None
    fee_type: str = ""
    fee_multiplier: float = 0.0
    additional_prohibitions: list[str] = []
    volume: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_fp", "volume"),
    )
    last_updated_ts: datetime | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class SeriesFeeChange(BaseModel):
    """A scheduled fee change for a series."""

    id: str
    series_ticker: str
    fee_type: str
    fee_multiplier: float
    scheduled_ts: datetime | None = None

    model_config = {"extra": "allow"}


class EventCandlesticks(BaseModel):
    """Event-level candlestick data spanning multiple markets.

    Unlike market candlesticks (flat list for one market), event candlesticks
    return a nested structure: one candlestick list per market in the event.
    """

    market_tickers: list[str] = []
    market_candlesticks: list[list[Candlestick]] = []
    adjusted_end_ts: int = 0

    model_config = {"extra": "allow"}


class PercentilePoint(BaseModel):
    """A single forecast value at a given percentile."""

    percentile: int
    raw_numerical_forecast: float
    numerical_forecast: float
    formatted_forecast: str

    model_config = {"extra": "allow"}


class ForecastPercentilesPoint(BaseModel):
    """A forecast data point with percentile breakdowns."""

    event_ticker: str
    end_period_ts: int
    period_interval: int
    percentile_points: list[PercentilePoint] = []

    model_config = {"extra": "allow"}
