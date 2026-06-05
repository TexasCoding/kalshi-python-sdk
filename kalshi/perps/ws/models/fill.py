"""Margin private fill channel message models (authenticated user fills).

``side`` is ``bid``/``ask`` (:data:`PerpsBookSide`), NOT ``yes``/``no``;
``ts_ms`` is epoch milliseconds.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from kalshi.perps.ws.models._common import PerpsBookSide
from kalshi.types import DollarDecimal, FixedPointCount


class MarginFillPayload(BaseModel):
    """Payload for ``fill`` messages (``marginFillPayload.msg``).

    Required per spec: ``trade_id``/``order_id`` (UUID strings), ``market_ticker``,
    ``is_taker``, ``side`` (``bid``/``ask``), ``ts_ms`` (epoch ms), ``price``
    (dollar-decimal), ``count``/``post_position`` (fixed-point counts), and
    ``fee_cost`` (dollar-decimal). ``client_order_id`` and ``subaccount`` are
    optional.
    """

    trade_id: str
    order_id: str
    market_ticker: str
    is_taker: bool
    side: PerpsBookSide
    ts_ms: int
    price: DollarDecimal
    count: FixedPointCount
    fee_cost: DollarDecimal
    post_position: FixedPointCount
    client_order_id: str | None = None
    subaccount: int | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class MarginFillMessage(BaseModel):
    """Private margin fill update. ``seq`` is NOT required on this channel."""

    type: Literal["fill"] = "fill"
    sid: int
    seq: int | None = None
    msg: MarginFillPayload
    model_config = {"extra": "allow", "populate_by_name": True}
