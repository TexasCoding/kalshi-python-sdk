"""Margin market lifecycle channel message models.

``market_lifecycle_v2`` reports activation and deactivation of every margin
market. ``market_ticker`` filters are not supported. ``seq`` is required on
the envelope; ``sending_ts_ms`` is an optional epoch-millisecond send time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from kalshi.perps.ws.models._common import MarginMarketLifecycleEventType


class MarginMarketLifecycleV2Payload(BaseModel):
    """Payload for ``market_lifecycle_v2`` (``marginMarketLifecycleV2Payload.msg``).

    All three fields are required: ``market_ticker``, ``event_type``
    (``activated`` / ``deactivated``), and ``is_deactivated``.
    """

    market_ticker: str
    event_type: MarginMarketLifecycleEventType
    is_deactivated: bool
    model_config = {"extra": "allow", "populate_by_name": True}


class MarginMarketLifecycleV2Message(BaseModel):
    """Market activation or deactivation. ``seq`` is required; not gap-tracked."""

    type: Literal["market_lifecycle_v2"] = "market_lifecycle_v2"
    sid: int
    seq: int
    msg: MarginMarketLifecycleV2Payload
    sending_ts_ms: int | None = None
    model_config = {"extra": "allow", "populate_by_name": True}
