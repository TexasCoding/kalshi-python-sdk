"""Perps (margin) order models — create/get/list/cancel/decrease/amend (#391).

Response models tolerate additive server fields (``extra="allow"``); request
models reject unknown keys (``extra="forbid"``) so a phantom kwarg fails at
construction instead of round-tripping to a server 400.

Wire-name note: unlike the prediction API's V1 order family (``yes_price_dollars``
/ ``count_fp``), the perps order schemas use the *short* keys directly —
``price``, ``count``, ``fill_count``, ``remaining_count`` are the literal wire
names. So no ``validation_alias`` / ``serialization_alias`` is needed here;
verified against ``specs/perps_openapi.yaml`` schemas at lines 1652-1951.

Request prices use :data:`~kalshi.types.OrderPrice` (rejects negatives and
sub-$0.0001-tick precision at construction); response prices use
:data:`~kalshi.types.DollarDecimal` (negatives/precision are legitimate on
fee/fill fields).
"""

from __future__ import annotations

import builtins
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from kalshi.types import DollarDecimal, FixedPointCount, OrderPrice, StrictInt

# ── Literal aliases (fixed-enum kwargs / fields) ─────────────────────────────
# Source of truth: specs/perps_openapi.yaml. Perps order side is bid/ask
# (BookSide), NOT the prediction API's yes/no.

BookSideLiteral = Literal["bid", "ask"]
"""Side of the book. Spec ``BookSide`` (line 2225)."""

TimeInForceLiteral = Literal["fill_or_kill", "good_till_canceled", "immediate_or_cancel"]
"""Order time-in-force. Inline enum on ``CreateMarginOrderRequest.time_in_force`` (line 1686)."""

SelfTradePreventionTypeLiteral = Literal["taker_at_cross", "maker"]
"""Self-trade prevention behavior. Spec ``SelfTradePreventionType`` (line 1578)."""

OrderSourceLiteral = Literal["user", "system"]
"""Order source — user-placed or system (liquidation). Spec ``OrderSource`` (line 2036)."""

OrderReasonLiteral = Literal["liquidation", "take_profit_stop_loss"]
"""Reason for a system-generated order. Spec ``OrderReason`` — present only for
liquidation and take-profit/stop-loss orders."""

LastUpdateReasonLiteral = Literal[
    "",
    "Decrease",
    "Amend",
    "MarginCancel",
    "SelfTradeCancel",
    "ExpiryCancel",
    "Trade",
    "PostOnlyCrossCancel",
]
"""Why an order was last updated. Spec ``LastUpdateReason`` (line 2044).

The empty-string member ``""`` is a real wire value — keep it.
"""


# ── Request models (extra="forbid") ──────────────────────────────────────────


class CreateMarginOrderRequest(BaseModel):
    """Body for ``POST /margin/orders``. Spec ``CreateMarginOrderRequest`` (line 1652).

    ``price``/``count`` wire names match the field names (no ``_dollars``/``_fp``
    suffix), so ``by_alias=True`` is a no-op for them — confirmed against the spec.
    ``subaccount`` is carried in the *body* here (the cancel/decrease/amend
    endpoints route it as a query param instead).
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str
    client_order_id: str
    side: BookSideLiteral
    count: FixedPointCount = Field(gt=0)
    price: OrderPrice
    time_in_force: TimeInForceLiteral
    self_trade_prevention_type: SelfTradePreventionTypeLiteral
    expiration_time: StrictInt | None = None
    post_only: bool | None = None
    cancel_order_on_pause: bool | None = None
    reduce_only: bool | None = None
    subaccount: StrictInt | None = Field(default=None, ge=0)
    order_group_id: str | None = None


class DecreaseMarginOrderRequest(BaseModel):
    """Body for ``POST /margin/orders/{order_id}/decrease``. Spec line 1853.

    Spec marks both fields optional/nullable, but the server requires exactly
    one of ``reduce_by`` / ``reduce_to``. Enforced at construction (mirrors
    :class:`kalshi.models.orders.DecreaseOrderV2Request`). ``subaccount`` is a
    query param on the resource method, not a body field.
    """

    model_config = ConfigDict(extra="forbid")

    # reduce_by is an amount to subtract (must be positive); reduce_to is a
    # target remaining count, where 0 (decrease to nothing) is valid — so it
    # only rejects negatives.
    reduce_by: FixedPointCount | None = Field(default=None, gt=0)
    reduce_to: FixedPointCount | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _enforce_reduce_xor(self) -> DecreaseMarginOrderRequest:
        if self.reduce_by is not None and self.reduce_to is not None:
            raise ValueError(
                "DecreaseMarginOrderRequest accepts reduce_by or reduce_to, not both"
            )
        if self.reduce_by is None and self.reduce_to is None:
            raise ValueError(
                "DecreaseMarginOrderRequest requires either reduce_by or reduce_to"
            )
        return self


class AmendMarginOrderRequest(BaseModel):
    """Body for ``POST /margin/orders/{order_id}/amend`` (spec ``AmendMarginOrderRequest``).

    Amending increases-in-size or price changes forfeit queue position
    (server-side). ``price``/``count`` wire names match the field names.
    ``subaccount`` is a query param on the resource method, not a body field.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str
    side: BookSideLiteral
    price: OrderPrice
    count: FixedPointCount = Field(gt=0)
    client_order_id: str | None = None
    updated_client_order_id: str | None = None


# ── Response models (extra="allow") ──────────────────────────────────────────


class CreateMarginOrderResponse(BaseModel):
    """Response for ``POST /margin/orders``. Spec ``CreateMarginOrderResponse`` (line 1723).

    ``average_fill_price`` / ``average_fee_paid`` are present only when
    ``fill_count > 0``.
    """

    model_config = ConfigDict(extra="allow")

    order_id: str
    fill_count: FixedPointCount
    remaining_count: FixedPointCount
    client_order_id: str | None = None
    average_fill_price: DollarDecimal | None = None
    average_fee_paid: DollarDecimal | None = None


class MarginOrder(BaseModel):
    """A perps (margin) order. Spec ``MarginOrder`` (line 1771).

    Wire field names match the Python names (``price``, ``fill_count``,
    ``remaining_count`` — no ``_dollars``/``_fp`` suffixes), so no
    ``validation_alias`` is needed. ``last_update_reason`` includes the
    empty-string member.
    """

    model_config = ConfigDict(extra="allow")

    order_id: str
    user_id: str
    client_order_id: str
    ticker: str
    side: BookSideLiteral
    last_update_reason: LastUpdateReasonLiteral
    price: DollarDecimal
    fill_count: FixedPointCount
    remaining_count: FixedPointCount
    expiration_time: AwareDatetime | None = None
    created_time: AwareDatetime | None = None
    last_update_time: AwareDatetime | None = None
    self_trade_prevention_type: SelfTradePreventionTypeLiteral | None = None
    cancel_order_on_pause: bool | None = None
    order_group_id: str | None = None
    order_source: OrderSourceLiteral | None = None
    # Spec v3.23.0: present only for system-generated orders (liquidation, TP/SL).
    order_reason: OrderReasonLiteral | None = None


class GetMarginOrderResponse(BaseModel):
    """Response for ``GET /margin/orders/{order_id}``. Spec line 1752."""

    model_config = ConfigDict(extra="allow")

    order: MarginOrder


class GetMarginOrdersResponse(BaseModel):
    """Paginated envelope for ``GET /margin/orders`` and ``GET /margin/fcm/orders``.

    Spec ``GetMarginOrdersResponse`` (line 1759). ``cursor`` drives
    ``list_all()`` / ``list_all_fcm()``.
    """

    model_config = ConfigDict(extra="allow")

    orders: builtins.list[MarginOrder]
    # Spec marks ``cursor`` required, but Kalshi omits the key on the final page
    # (rather than returning ``""``) — a bare ``str`` would crash ``list_all()``
    # on the last page. Optional matches the sibling fills/trades responses.
    cursor: str | None = None


class CancelMarginOrderResponse(BaseModel):
    """Response for ``DELETE /margin/orders/{order_id}``. Spec line 1838.

    ``reduced_by`` is the number of contracts canceled (the remaining count at
    cancellation time).
    """

    model_config = ConfigDict(extra="allow")

    order_id: str
    reduced_by: FixedPointCount
    client_order_id: str | None = None


class DecreaseMarginOrderResponse(BaseModel):
    """Response for ``POST /margin/orders/{order_id}/decrease``. Spec line 1868."""

    model_config = ConfigDict(extra="allow")

    order_id: str
    remaining_count: FixedPointCount
    client_order_id: str | None = None


class AmendMarginOrderResponse(BaseModel):
    """Response for ``POST /margin/orders/{order_id}/amend``. Spec line 1915.

    All fields except ``order_id`` are nullable — the fill/size fields are
    present only when the amend crossed the book or changed the resting size.
    """

    model_config = ConfigDict(extra="allow")

    order_id: str
    client_order_id: str | None = None
    remaining_count: FixedPointCount | None = None
    fill_count: FixedPointCount | None = None
    average_fill_price: DollarDecimal | None = None
    average_fee_paid: DollarDecimal | None = None
