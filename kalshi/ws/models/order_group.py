"""Order group updates channel message models."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import FixedPointCount


class OrderGroupPayload(BaseModel):
    """Payload for order_group_updates messages (private channel)."""

    event_type: str  # created/triggered/reset/deleted/limit_updated
    order_group_id: str
    contracts_limit: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_limit_fp", "contracts_limit"),
    )  # _fp format — coerced to Decimal per #225/#230 invariant
    # v0.14+ backfill (#162). Matching engine timestamp in Unix ms.
    ts_ms: int
    model_config = {"extra": "allow", "populate_by_name": True}


class OrderGroupMessage(BaseModel):
    """Order group update message. HAS required seq (one of only 2 channels)."""

    type: str = "order_group_updates"
    sid: int
    seq: int  # Required — one of few channels with required seq
    msg: OrderGroupPayload
    model_config = {"extra": "allow", "populate_by_name": True}
