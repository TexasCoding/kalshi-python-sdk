"""Margin public trade channel message models.

Wire-distinct from the prediction-API trade: ``taker_side`` is ``bid``/``ask``
(:data:`PerpsBookSide`), NOT ``yes``/``no``, and ``ts_ms`` is epoch milliseconds.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from kalshi.perps.ws.models._common import PerpsBookSide
from kalshi.types import DollarDecimal, FixedPointCount


class MarginTradePayload(BaseModel):
    """Payload for ``trade`` messages (``marginTradePayload.msg``).

    All fields required per spec. ``trade_id`` is a UUID string; ``price`` is a
    dollar-decimal string; ``count`` is a fixed-point count string;
    ``taker_side`` is ``bid``/``ask``; ``ts_ms`` is epoch milliseconds.
    """

    trade_id: str
    market_ticker: str
    price: DollarDecimal
    count: FixedPointCount
    taker_side: PerpsBookSide
    ts_ms: int
    model_config = {"extra": "allow", "populate_by_name": True}


class MarginTradeMessage(BaseModel):
    """Public margin trade update. ``seq`` is NOT required on this channel."""

    type: Literal["trade"] = "trade"
    sid: int
    seq: int | None = None
    msg: MarginTradePayload
    model_config = {"extra": "allow", "populate_by_name": True}
