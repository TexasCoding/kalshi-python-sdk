"""Orderbook delta and snapshot message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field


class OrderbookSnapshotPayload(BaseModel):
    """Payload for orderbook_snapshot messages."""

    market_ticker: str
    market_id: str
    yes: list[list[int]] = Field(
        default=[],
        validation_alias=AliasChoices("yes_dollars_fp", "yes"),
    )
    no: list[list[int]] = Field(
        default=[],
        validation_alias=AliasChoices("no_dollars_fp", "no"),
    )
    model_config = {"extra": "allow"}


class OrderbookDeltaPayload(BaseModel):
    """Payload for orderbook_delta messages."""

    market_ticker: str
    market_id: str
    price: int = Field(
        validation_alias=AliasChoices("price_dollars", "price"),
    )
    delta: int = Field(
        validation_alias=AliasChoices("delta_fp", "delta"),
    )
    side: str
    client_order_id: str | None = None
    subaccount: int | None = None
    ts: int | None = None
    model_config = {"extra": "allow"}


class OrderbookSnapshotMessage(BaseModel):
    """Full orderbook snapshot, sent on initial subscribe."""
    type: str = "orderbook_snapshot"
    sid: int
    seq: int
    msg: OrderbookSnapshotPayload


class OrderbookDeltaMessage(BaseModel):
    """Incremental orderbook update."""
    type: str = "orderbook_delta"
    sid: int
    seq: int
    msg: OrderbookDeltaPayload
