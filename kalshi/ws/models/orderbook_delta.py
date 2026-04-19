"""Orderbook delta and snapshot message models."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal


class OrderbookSnapshotPayload(BaseModel):
    """Payload for orderbook_snapshot messages.

    Wire format per AsyncAPI spec: ``yes_dollars_fp`` and ``no_dollars_fp`` are
    arrays of ``[price_in_dollars, contract_count_fp]`` string pairs. Each row
    is two JSON strings, e.g. ``["0.5500", "100.00"]``. Consumers should parse
    both elements as :class:`decimal.Decimal`.
    """

    market_ticker: str
    market_id: str
    yes: list[list[str]] = Field(
        default=[],
        validation_alias=AliasChoices("yes_dollars_fp", "yes"),
    )
    no: list[list[str]] = Field(
        default=[],
        validation_alias=AliasChoices("no_dollars_fp", "no"),
    )
    model_config = {"extra": "allow"}


class OrderbookDeltaPayload(BaseModel):
    """Payload for orderbook_delta messages.

    Wire format per AsyncAPI spec and confirmed on demo: ``price_dollars`` is
    a dollar-decimal string (e.g. ``"0.0200"``), ``delta_fp`` is a fixed-point
    count string (e.g. ``"10.00"``, may be negative), ``ts`` is an RFC3339
    timestamp string (e.g. ``"2026-04-19T18:43:37.662364Z"``).
    """

    market_ticker: str
    market_id: str
    price: DollarDecimal = Field(
        validation_alias=AliasChoices("price_dollars", "price"),
    )
    delta: str = Field(
        validation_alias=AliasChoices("delta_fp", "delta"),
    )
    side: str
    client_order_id: str | None = None
    subaccount: int | None = None
    ts: str | None = None
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
