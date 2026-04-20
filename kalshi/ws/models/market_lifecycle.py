"""Market lifecycle v2 channel message models."""
from __future__ import annotations

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
    market_ticker: str | None = None
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
    model_config = {"extra": "allow"}


class MarketLifecycleMessage(BaseModel):
    """Market lifecycle v2 update message. NO required seq."""

    type: str = "market_lifecycle_v2"
    sid: int
    seq: int | None = None
    msg: MarketLifecyclePayload
