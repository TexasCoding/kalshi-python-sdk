"""Margin exchange-status channel message models.

``exchange_status`` is sent when trading is paused or resumed exchange-wide,
or when the exchange status changes. Trading messages carry ``trading_active``;
exchange status messages carry ``exchange_active``. Trading is open
exchange-wide only while both flags are true. Per-market halts ride
``market_lifecycle_v2``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MarginExchangeStatusPayload(BaseModel):
    """Payload for ``exchange_status`` (``marginExchangeStatusPayload.msg``).

    ``ts_ms`` is required. ``exchange_active`` and ``trading_active`` are
    optional; a given message typically carries one of them.
    """

    exchange_active: bool | None = None
    trading_active: bool | None = None
    ts_ms: int
    model_config = {"extra": "allow", "populate_by_name": True}


class MarginExchangeStatusMessage(BaseModel):
    """Exchange-wide trading or exchange status change. ``seq`` is required."""

    type: Literal["exchange_status"] = "exchange_status"
    sid: int
    seq: int
    msg: MarginExchangeStatusPayload
    sending_ts_ms: int | None = None
    model_config = {"extra": "allow", "populate_by_name": True}
