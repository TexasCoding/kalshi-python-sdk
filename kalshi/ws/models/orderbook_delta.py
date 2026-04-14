"""Orderbook delta and snapshot message models."""
from __future__ import annotations

from pydantic import BaseModel


class OrderbookSnapshotPayload(BaseModel):
    """Payload for orderbook_snapshot messages."""
    market_ticker: str
    market_id: str
    yes: list[list[int]] = []
    no: list[list[int]] = []


class OrderbookDeltaPayload(BaseModel):
    """Payload for orderbook_delta messages."""
    market_ticker: str
    market_id: str
    price: int
    delta: int
    side: str
    client_order_id: str | None = None
    subaccount: int | None = None
    ts: int | None = None


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
