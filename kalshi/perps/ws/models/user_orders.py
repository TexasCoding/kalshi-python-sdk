"""Margin private user-order channel message models (order create/update).

The subscribe channel is ``user_orders`` but the message envelope ``type`` is
``user_order`` (singular) per spec — the dispatcher registers under
``user_order``. The order identifier field is ``ticker`` (NOT ``market_ticker``);
``side`` is ``bid``/``ask`` (:data:`PerpsBookSide`); all timestamps are
``*_ts_ms`` epoch milliseconds.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from kalshi.perps.ws.models._common import (
    PerpsBookSide,
    PerpsOrderSource,
    PerpsSelfTradePreventionType,
)
from kalshi.types import DollarDecimal, FixedPointCount


class MarginUserOrderPayload(BaseModel):
    """Payload for ``user_order`` messages (``marginUserOrderPayload.msg``).

    Required per spec: ``order_id``/``user_id`` (UUID strings), ``client_order_id``,
    ``ticker`` (note: ``ticker``, NOT ``market_ticker``), ``side`` (``bid``/
    ``ask``), ``price`` (dollar-decimal), ``fill_count``/``remaining_count``
    (fixed-point counts), ``created_ts_ms`` (epoch ms), and ``order_source``
    (``user``/``system``). The remaining fields — STP type, order-group id, and
    the ``*_ts_ms`` timestamps — are optional.
    """

    order_id: str
    user_id: str
    client_order_id: str
    ticker: str
    side: PerpsBookSide
    price: DollarDecimal
    fill_count: FixedPointCount
    remaining_count: FixedPointCount
    created_ts_ms: int
    order_source: PerpsOrderSource
    self_trade_prevention_type: PerpsSelfTradePreventionType | None = None
    order_group_id: str | None = None
    expiration_ts_ms: int | None = None
    last_updated_ts_ms: int | None = None
    subaccount_number: int | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class MarginUserOrderMessage(BaseModel):
    """Private margin order create/update. ``seq`` is NOT required on this channel.

    Envelope ``type`` is ``user_order`` (singular) even though the subscribe
    channel name is ``user_orders``.
    """

    type: Literal["user_order"] = "user_order"
    sid: int
    seq: int | None = None
    msg: MarginUserOrderPayload
    model_config = {"extra": "allow", "populate_by_name": True}
