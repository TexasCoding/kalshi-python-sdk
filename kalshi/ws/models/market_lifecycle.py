"""Market lifecycle v2 channel message models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from kalshi.types import DollarDecimal


class MarketLifecyclePayload(BaseModel):
    """Payload for market_lifecycle_v2 messages (public channel).

    Discriminated by event_type field. Conditional fields depend on event_type:
    - created/activated: open_ts, close_ts, title, subtitle, series_ticker
    - determined: result, determination_ts
    - settled: settlement_value, settled_ts
    - deactivated: is_deactivated
    """

    event_type: str  # created/activated/deactivated/close_date_updated/determined/settled/etc
    # #172: tightened; all observed lifecycle event_types carry market_ticker.
    market_ticker: str
    event_ticker: str | None = None
    # Conditional fields depending on event_type
    open_ts: int | None = None
    close_ts: int | None = None
    result: str | None = None
    determination_ts: int | None = None
    settlement_value: DollarDecimal | None = None
    settled_ts: int | None = None
    is_deactivated: bool | None = None
    fractional_trading_enabled: bool | None = None
    title: str | None = None
    subtitle: str | None = None
    series_ticker: str | None = None

    # v0.14+ backfill (#162). additional_metadata is emitted for `created`
    # events; floor_strike/yes_sub_title for `metadata_updated`;
    # price_level_structure for `price_level_structure_updated` (or `created`).
    additional_metadata: dict[str, Any] | None = None
    floor_strike: DollarDecimal | None = None
    price_level_structure: str | None = None
    yes_sub_title: str | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class MarketLifecycleMessage(BaseModel):
    """Market lifecycle v2 update message. NO required seq."""

    type: Literal["market_lifecycle_v2"] = "market_lifecycle_v2"
    sid: int
    seq: int | None = None
    msg: MarketLifecyclePayload
    model_config = {"extra": "allow", "populate_by_name": True}
