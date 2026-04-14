"""Order group updates channel message models."""
from __future__ import annotations

from pydantic import BaseModel


class OrderGroupPayload(BaseModel):
    """Payload for order_group_updates messages (private channel)."""

    event_type: str  # created/triggered/reset/deleted/limit_updated
    order_group_id: str
    contracts_limit: str | None = None  # _fp format
    model_config = {"extra": "allow"}


class OrderGroupMessage(BaseModel):
    """Order group update message. HAS required seq (one of only 2 channels)."""

    type: str = "order_group_updates"
    sid: int
    seq: int  # Required — one of few channels with required seq
    msg: OrderGroupPayload
