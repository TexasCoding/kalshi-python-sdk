"""Margin orderbook snapshot + delta channel message models.

Wire-distinct from the prediction-API orderbook (``kalshi/ws/models/
orderbook_delta.py``): perps book sides are ``bid``/``ask`` (NOT ``yes``/
``no``), snapshot levels are ``priceLevelDollarsCountFp`` =
``[price_in_dollars, contract_count_fp]`` string pairs under ``bid``/``ask``
arrays, and the delta carries a single-sided ``price``/``delta``/``side`` plus
an epoch-ms ``ts_ms`` (NOT an RFC3339 ``ts``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field

from kalshi.perps.ws.models._common import (
    PerpsBookSide,
    PerpsLastUpdateReason,
)
from kalshi.types import DollarDecimal, FixedPointCount, _coerce_decimal


def _levels_to_dict(value: Any) -> Any:
    """Collapse the snapshot wire payload into a ``dict[Decimal, Decimal]``.

    The wire format for ``bid`` / ``ask`` is a list of ``[price, count]``
    string pairs (``priceLevelDollarsCountFp``). Coercing each price/count to
    ``Decimal`` inline and returning a fully typed ``dict[Decimal, Decimal]``
    means (a) pydantic-core just bounces the already-validated map back without
    a second walk, and (b) :meth:`PerpsOrderbookManager._apply_snapshot_inplace`
    adopts the dict directly with no rebuild. Mirrors the prediction-API
    ``_levels_to_dict`` (#263).

    Accepts ``None`` (→ empty — perps allows a partial book, see the payload
    docstring), an already-built dict (re-validation), or any iterable of
    2-element ``(price, count)`` pairs (wire shape).
    """
    if value is None:
        return {}
    coerce = _coerce_decimal
    if isinstance(value, dict):
        if all(type(k) is Decimal and type(v) is Decimal for k, v in value.items()):
            return value
        return {coerce(k): coerce(v) for k, v in value.items()}
    out: dict[Decimal, Decimal] = {}
    try:
        for row in value:
            price, count = row
            out[coerce(price)] = coerce(count)
    except (TypeError, ValueError, ArithmeticError) as exc:
        # Re-raise as ValueError so pydantic surfaces a ValidationError (a raw
        # decimal.InvalidOperation / TypeError would escape model_validate).
        raise ValueError(f"malformed orderbook level data: {exc}") from exc
    return out


# Field type is ``dict[Decimal, Decimal]`` (not ``dict[DollarDecimal,
# FixedPointCount]``) so pydantic-core does not re-run the per-item coercion
# walk on values our ``BeforeValidator`` has already coerced. On-the-wire
# semantics: prices are dollar-decimals, counts are fixed-point counts — both
# land as ``Decimal``. Mirrors ``kalshi.ws.models.orderbook_delta.PriceCountMap``.
PriceCountMap = Annotated[dict[Decimal, Decimal], BeforeValidator(_levels_to_dict)]


class MarginOrderbookSnapshotPayload(BaseModel):
    """Payload for ``orderbook_snapshot`` messages (``marginOrderbookSnapshotPayload.msg``).

    Wire format: ``bid`` and ``ask`` are arrays of ``[price_in_dollars,
    contract_count_fp]`` string pairs (``priceLevelDollarsCountFp``). Each row
    collapses into ``dict[Decimal, Decimal]`` (price -> count) in a single walk
    so :class:`~kalshi.perps.ws.orderbook.PerpsOrderbookManager` adopts the map
    with no second iteration.

    Partial-book note: unlike the prediction-API snapshot (#268, where BOTH
    sides are required), the perps spec does NOT mark ``bid``/``ask`` as
    ``required`` on ``msg``. Each side therefore defaults to an empty map when
    omitted — a snapshot with one side absent is a legitimate one-sided book,
    not schema drift.

    Aliasing: the wire names ``bid``/``ask`` already match the short names, so
    there is no ``_dollars``/``_fp`` suffix mismatch to alias.
    """

    market_ticker: str
    bid: PriceCountMap = Field(default_factory=dict)
    ask: PriceCountMap = Field(default_factory=dict)
    model_config = {"extra": "allow", "populate_by_name": True}


class MarginOrderbookDeltaPayload(BaseModel):
    """Payload for ``orderbook_delta`` messages (``marginOrderbookDeltaPayload.msg``).

    Single-sided incremental update. ``price`` is a dollar-decimal string,
    ``delta`` is a fixed-point count string (may be negative), ``side`` is
    ``bid``/``ask``. ``ts_ms`` is epoch milliseconds (``int``), NOT RFC3339.
    """

    market_ticker: str
    price: DollarDecimal
    delta: FixedPointCount
    side: PerpsBookSide
    last_update_reason: PerpsLastUpdateReason | None = None
    client_order_id: str | None = None
    subaccount: int | None = None
    ts_ms: int | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class MarginOrderbookSnapshotMessage(BaseModel):
    """Full margin orderbook snapshot, sent first on an ``orderbook_delta`` subscribe.

    Sequenced channel: ``seq`` is REQUIRED.
    """

    type: Literal["orderbook_snapshot"] = "orderbook_snapshot"
    sid: int
    seq: int
    msg: MarginOrderbookSnapshotPayload
    model_config = {"extra": "allow", "populate_by_name": True}


class MarginOrderbookDeltaMessage(BaseModel):
    """Incremental margin orderbook update. Sequenced channel: ``seq`` REQUIRED."""

    type: Literal["orderbook_delta"] = "orderbook_delta"
    sid: int
    seq: int
    msg: MarginOrderbookDeltaPayload
    model_config = {"extra": "allow", "populate_by_name": True}
