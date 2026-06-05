"""Margin order-group lifecycle/limit-update channel message models.

Sequenced channel: ``seq`` is REQUIRED on the envelope (mirrors the
prediction-API ``OrderGroupMessage``). Market spec is ignored for this channel.
``ts_ms`` is the matching-engine epoch-millisecond timestamp.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from kalshi.perps.ws.models._common import OrderGroupEventType
from kalshi.types import FixedPointCount


class OrderGroupUpdatesPayload(BaseModel):
    """Payload for ``order_group_updates`` messages (``orderGroupUpdatesPayload.msg``).

    Required per spec: ``event_type`` (one of ``created``/``triggered``/``reset``/
    ``deleted``/``limit_updated``), ``order_group_id``, and ``ts_ms`` (matching-
    engine epoch ms). ``contracts_limit`` (wire ``contracts_limit_fp``, a 2-decimal
    fixed-point count) is present only for ``created`` and ``limit_updated`` events.
    """

    event_type: OrderGroupEventType
    order_group_id: str
    ts_ms: int
    contracts_limit: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_limit_fp", "contracts_limit"),
    )
    model_config = {"extra": "allow", "populate_by_name": True}


class OrderGroupUpdatesMessage(BaseModel):
    """Order-group lifecycle/limit update. Sequenced channel: ``seq`` REQUIRED."""

    type: Literal["order_group_updates"] = "order_group_updates"
    sid: int
    seq: int
    msg: OrderGroupUpdatesPayload
    model_config = {"extra": "allow", "populate_by_name": True}
