"""Historical data models."""

from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal


class HistoricalCutoff(BaseModel):
    """Timestamps defining the boundary between live and historical data."""

    market_settled_ts: datetime
    trades_created_ts: datetime
    orders_updated_ts: datetime

    model_config = {"extra": "allow"}


class Trade(BaseModel):
    """A public trade on the exchange."""

    trade_id: str
    ticker: str | None = None
    count: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("count_fp", "count"),
    )
    yes_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    no_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_price_dollars", "no_price"),
    )
    taker_side: str | None = None
    created_time: datetime | None = None

    model_config = {"extra": "allow", "populate_by_name": True}
