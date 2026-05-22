"""Orderbook delta and snapshot message models."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, BeforeValidator, Field

from kalshi.types import DollarDecimal, FixedPointCount, _coerce_decimal


def _levels_to_dict(value: Any) -> Any:
    """Collapse the snapshot wire payload into a single dict in one walk.

    The wire format for ``yes_dollars_fp`` / ``no_dollars_fp`` is a list of
    ``[price, count]`` string pairs. Previously the model validated that into
    ``list[tuple[Decimal, Decimal]]`` and ``OrderbookManager`` then called
    ``dict(...)`` on it — a second per-level Python walk that dominated
    snapshot apply cost for deep books (#263).

    Coercing each price/count to ``Decimal`` inline and returning a fully
    typed ``dict[Decimal, Decimal]`` means (a) pydantic-core just bounces
    the already-validated map back without a second walk, and (b)
    ``_apply_snapshot_inplace`` adopts the dict directly with no rebuild.

    Accepts ``None`` (→ empty), an already-built dict (direct constructor /
    re-validation — keys/values still coerced so callers can pass strings),
    or any iterable of 2-element ``(price, count)`` pairs (wire shape).
    """
    if value is None:
        return {}
    coerce = _coerce_decimal
    if isinstance(value, dict):
        # Fast path when keys/values are already Decimal (avoids hashing the
        # same Decimal twice on dict rebuild).
        if all(type(k) is Decimal and type(v) is Decimal for k, v in value.items()):
            return value
        return {coerce(k): coerce(v) for k, v in value.items()}
    out: dict[Decimal, Decimal] = {}
    for row in value:
        price, count = row
        out[coerce(price)] = coerce(count)
    return out


# Field type is ``dict[Decimal, Decimal]`` (not ``dict[DollarDecimal, FixedPointCount]``)
# so pydantic-core does not re-run the per-item ``BeforeValidator(_coerce_decimal)``
# walk on values our ``BeforeValidator`` has already coerced. The on-the-wire
# semantics are unchanged — prices are dollar-decimals, counts are fixed-point
# counts — they are simply both ``Decimal`` once parsed.
PriceCountMap = Annotated[dict[Decimal, Decimal], BeforeValidator(_levels_to_dict)]


class OrderbookSnapshotPayload(BaseModel):
    """Payload for orderbook_snapshot messages.

    Wire format per AsyncAPI spec: ``yes_dollars_fp`` and ``no_dollars_fp`` are
    arrays of ``[price_in_dollars, contract_count_fp]`` string pairs. Each row
    is two JSON strings, e.g. ``["0.5500", "100.00"]``.

    These are validated directly into ``dict[Decimal, Decimal]`` (price ->
    count) in a single walk so ``OrderbookManager._apply_snapshot_inplace``
    can adopt the map with no second iteration (#263).

    Both sides are required (#268): a snapshot envelope missing
    ``yes_dollars_fp`` or ``no_dollars_fp`` is schema drift or a partial
    server response, not "an empty book on that side". Surfacing a
    ``ValidationError`` lets the recv loop's malformed-frame handler
    log it and roll back the seq watermark for #241 rather than silently
    resetting the local book to empty.

    Aliasing note: when delivered through
    :meth:`KalshiWSClient.subscribe_orderbook_delta`, ``yes`` / ``no`` are live
    dicts owned by the :class:`OrderbookManager` after dispatch — they
    mutate on every subsequent delta.
    """

    market_ticker: str
    market_id: str
    yes: PriceCountMap = Field(
        validation_alias=AliasChoices("yes_dollars_fp", "yes"),
    )
    no: PriceCountMap = Field(
        validation_alias=AliasChoices("no_dollars_fp", "no"),
    )
    model_config = {"extra": "allow", "populate_by_name": True}


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
    delta: FixedPointCount = Field(
        validation_alias=AliasChoices("delta_fp", "delta"),
    )
    side: Literal["yes", "no"]
    client_order_id: str | None = None
    subaccount: int | None = None
    ts: str | None = None
    # v0.14+ backfill (#162). ts_ms (Unix ms) supersedes ts (RFC3339).
    ts_ms: int | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class OrderbookSnapshotMessage(BaseModel):
    """Full orderbook snapshot, sent on initial subscribe."""

    type: str = "orderbook_snapshot"
    sid: int
    seq: int
    msg: OrderbookSnapshotPayload
    model_config = {"extra": "allow", "populate_by_name": True}


class OrderbookDeltaMessage(BaseModel):
    """Incremental orderbook update."""

    type: str = "orderbook_delta"
    sid: int
    seq: int
    msg: OrderbookDeltaPayload
    model_config = {"extra": "allow", "populate_by_name": True}
