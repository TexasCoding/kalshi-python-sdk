"""Order-related models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from kalshi.types import DollarDecimal, FixedPointCount

# Literal aliases for fixed-enum kwargs on order resource methods.
# Source of truth: OpenAPI spec v3.13.0 (specs/openapi.yaml).
# The Pydantic request models leave these fields as ``str`` to remain tolerant
# of spec drift; the static-type narrowing happens at the resource-method
# boundary where users actually pass values.
SideLiteral = Literal["yes", "no"]
"""Order side. Spec: CreateOrderRequest.side / AmendOrderRequest.side enum."""

ActionLiteral = Literal["buy", "sell"]
"""Order action. Spec: CreateOrderRequest.action / AmendOrderRequest.action enum."""

TimeInForceLiteral = Literal["fill_or_kill", "good_till_canceled", "immediate_or_cancel"]
"""Order time-in-force. Spec: CreateOrderRequest.time_in_force enum."""

SelfTradePreventionTypeLiteral = Literal["taker_at_cross", "maker"]
"""Self-trade prevention behavior. Spec: SelfTradePreventionType enum."""

OrderStatusLiteral = Literal["resting", "canceled", "executed"]
"""Order status filter for GET /portfolio/orders and /fcm/orders. Spec: OrderStatus enum."""

BookSideLiteral = Literal["bid", "ask"]
"""Side of the book for V2 event-market orders. Spec: BookSide enum."""


class Order(BaseModel):
    """A Kalshi order.

    Price/cost fields accept both ``_dollars``-suffixed names from the API
    (e.g. ``yes_price_dollars``) and short names (e.g. ``yes_price``).
    """

    order_id: str
    ticker: str | None = None
    user_id: str | None = None
    status: str | None = None
    side: str | None = None
    is_yes: bool | None = None
    # Spec field is named ``type`` (enum: limit, market). Renamed to
    # ``order_type`` on the SDK side to avoid shadowing the Python builtin —
    # same rationale as milestone_type / target_type / incentive_type
    # elsewhere. The wire still sends ``type``; validation alias accepts both.
    order_type: str | None = Field(
        default=None,
        validation_alias=AliasChoices("type", "order_type"),
    )
    yes_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    no_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_price_dollars", "no_price"),
    )
    count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("count_fp", "count"),
    )
    initial_count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("initial_count_fp", "initial_count"),
    )
    remaining_count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("remaining_count_fp", "remaining_count"),
    )
    fill_count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("fill_count_fp", "fill_count"),
    )
    taker_fill_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("taker_fill_cost_dollars", "taker_fill_cost"),
    )
    maker_fill_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("maker_fill_cost_dollars", "maker_fill_cost"),
    )
    taker_fees: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("taker_fees_dollars", "taker_fees"),
    )
    maker_fees: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("maker_fees_dollars", "maker_fees"),
    )
    created_time: datetime | None = None
    expiration_time: datetime | None = None
    client_order_id: str | None = None
    subaccount: int | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class Fill(BaseModel):
    """A filled trade.

    Price fields accept both ``_dollars``-suffixed names from the API
    and short names. Count accepts ``_fp``-suffixed name.
    """

    trade_id: str
    fill_id: str | None = None
    order_id: str | None = None
    ticker: str | None = None
    market_ticker: str | None = None
    side: str | None = None
    action: str | None = None
    is_taker: bool | None = None
    count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("count_fp", "count"),
    )
    yes_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    no_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_price_dollars", "no_price"),
    )
    fee_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("fee_cost_dollars", "fee_cost"),
    )
    created_time: datetime | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class CreateOrderRequest(BaseModel):
    """Parameters for creating an order.

    Price fields serialize with ``_dollars`` suffix. ``count`` is a Decimal
    and serializes as ``count_fp`` (FixedPointCount string); the spec
    accepts either ``count`` or ``count_fp`` key, but the SDK commits to
    a single wire shape.

    ``buy_max_cost`` is **integer cents** (per OpenAPI spec: "Maximum
    cost in cents"). Pass e.g. ``500`` for a $5.00 cap, NOT ``5.00``.
    Passing a decimal string like ``"5.00"`` raises ``ValidationError``.

    The SDK previously exposed a ``type: str = "limit"`` field never
    defined in the spec's ``CreateOrderRequest`` schema. v0.8.0 removes
    it. Callers passing ``type="market"`` (or similar) now get a
    ``ValidationError`` at construction time.

    ``action`` defaults to ``"buy"`` — the pre-v0.8.0 default is
    preserved to keep existing call sites working. ``ticker`` and
    ``side`` remain required.

    See ``kalshi.resources.orders.OrdersResource.create`` for the
    user-facing method that builds this model internally.
    """

    ticker: str
    side: str
    action: str = "buy"
    count: FixedPointCount = Field(default=Decimal("1"), serialization_alias="count_fp")
    yes_price: DollarDecimal | None = Field(
        default=None,
        serialization_alias="yes_price_dollars",
    )
    no_price: DollarDecimal | None = Field(
        default=None,
        serialization_alias="no_price_dollars",
    )
    client_order_id: str | None = None
    expiration_ts: int | None = None
    buy_max_cost: int | None = None
    time_in_force: str | None = None
    post_only: bool | None = None
    reduce_only: bool | None = None
    self_trade_prevention_type: str | None = None
    order_group_id: str | None = None
    cancel_order_on_pause: bool | None = None
    subaccount: int | None = None
    exchange_index: int | None = None

    model_config = {"extra": "forbid"}

    @field_validator("buy_max_cost", mode="before")
    @classmethod
    def _reject_decimal_and_float_buy_max_cost(cls, v: object) -> object:
        """Reject Decimal and float inputs on buy_max_cost.

        Spec says integer cents. Accepting Decimal would silently coerce
        callers who pass Decimal('5.00') (expecting $5.00 under the old
        DollarDecimal semantics) into 5 cents — data corruption with no
        error. Reject at the boundary.

        int and int-shaped strings are fine (Pydantic coerces normally).
        """
        if isinstance(v, Decimal):
            raise ValueError(
                "buy_max_cost must be int (cents), not Decimal. "
                "The previous DollarDecimal type was a v0.7.x-and-earlier "
                "bug — spec says integer cents. Pass cents directly "
                "(e.g., 500 for $5.00)."
            )
        if isinstance(v, float):
            raise ValueError(
                "buy_max_cost must be int (cents), not float. "
                "Pass cents directly (e.g., 500 for $5.00)."
            )
        return v


class AmendOrderRequest(BaseModel):
    """Parameters for amending an open order.

    Matches spec ``components.schemas.AmendOrderRequest``. Required fields
    (``ticker``, ``side``, ``action``) mirror the spec's ``required`` list.
    Price fields serialize with ``_dollars`` suffix; ``count`` serializes
    as ``count_fp`` (FixedPointCount).

    Cent-form ``yes_price``/``no_price`` spec properties are NOT on this
    model — redundant with the ``_dollars`` forms. EXCLUSIONS in
    ``tests/_contract_support.py`` records this.

    See ``kalshi.resources.orders.OrdersResource.amend`` — v0.8.0 builds
    this model internally; the public method signature is unchanged.
    """

    ticker: str
    side: str
    action: str
    yes_price: DollarDecimal | None = Field(
        default=None,
        serialization_alias="yes_price_dollars",
    )
    no_price: DollarDecimal | None = Field(
        default=None,
        serialization_alias="no_price_dollars",
    )
    count: FixedPointCount | None = Field(
        default=None,
        serialization_alias="count_fp",
    )
    client_order_id: str | None = None
    updated_client_order_id: str | None = None
    subaccount: int | None = None
    exchange_index: int | None = None

    model_config = {"extra": "forbid"}


class DecreaseOrderRequest(BaseModel):
    """Parameters for decreasing an open order's size.

    Matches spec ``components.schemas.DecreaseOrderRequest``. Spec marks
    all fields optional, but the server rejects an empty body — so the
    model enforces XOR at construction: exactly one of ``reduce_by`` or
    ``reduce_to`` must be set. This matches the method-level guard in
    ``orders.decrease()`` and keeps model-first construction (v0.9)
    fail-fast rather than deferring the error to the HTTP call.

    See ``kalshi.resources.orders.OrdersResource.decrease`` — v0.8.0
    builds this model internally; method signature unchanged.
    """

    reduce_by: int | None = None
    reduce_to: int | None = None
    subaccount: int | None = None
    exchange_index: int | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _enforce_reduce_xor(self) -> DecreaseOrderRequest:
        if self.reduce_by is not None and self.reduce_to is not None:
            raise ValueError(
                "DecreaseOrderRequest accepts reduce_by or reduce_to, not both"
            )
        if self.reduce_by is None and self.reduce_to is None:
            raise ValueError(
                "DecreaseOrderRequest requires either reduce_by or reduce_to"
            )
        return self


class BatchCreateOrdersRequest(BaseModel):
    """Wrapper for the ``POST /portfolio/orders/batched`` request body.

    Matches spec ``components.schemas.BatchCreateOrdersRequest``: a single
    ``orders`` key holding a list of ``CreateOrderRequest`` entries. Each
    nested entry inherits ``extra="forbid"`` from ``CreateOrderRequest``
    itself, so phantom fields in items fail at construction time.

    See ``kalshi.resources.orders.OrdersResource.batch_create`` — v0.8.0
    wraps this model internally; method signature unchanged.
    """

    orders: list[CreateOrderRequest]

    model_config = {"extra": "forbid"}


class BatchCancelOrdersRequestOrder(BaseModel):
    """A single cancellation entry in a batch cancel request.

    Matches spec ``components.schemas.BatchCancelOrdersRequestOrder``.
    Required: ``order_id``. Optional: ``subaccount`` (defaults to 0,
    primary subaccount).
    """

    order_id: str
    subaccount: int | None = None
    exchange_index: int | None = None

    model_config = {"extra": "forbid"}


class BatchCancelOrdersRequest(BaseModel):
    """Wrapper for the ``DELETE /portfolio/orders/batched`` request body.

    Matches spec ``components.schemas.BatchCancelOrdersRequest``. Spec
    defines two fields: the preferred ``orders`` (list of
    ``BatchCancelOrdersRequestOrder``) and the deprecated ``ids`` (list
    of string order IDs). SDK v0.8.0 commits to emitting ``orders`` only.

    The previous SDK sent the deprecated ``ids`` field — BREAKING change
    at the wire level as of v0.8.0. Users calling the public
    ``batch_cancel(orders=[...])`` method are unaffected.

    See ``kalshi.resources.orders.OrdersResource.batch_cancel``.
    """

    orders: list[BatchCancelOrdersRequestOrder]

    model_config = {"extra": "forbid"}


class AmendOrderResponse(BaseModel):
    """Response from amending an order — contains both pre and post-amendment orders."""

    old_order: Order
    order: Order

    model_config = {"extra": "allow"}


class OrderQueuePosition(BaseModel):
    """Queue position for a single resting order."""

    order_id: str
    market_ticker: str
    queue_position: FixedPointCount = Field(
        validation_alias=AliasChoices("queue_position_fp", "queue_position"),
    )

    model_config = {"extra": "allow", "populate_by_name": True}


# ---------------------------------------------------------------------------
# V2 event-market order models (spec v3.18.0). The legacy /portfolio/orders
# endpoints will be deprecated no earlier than May 6, 2026; the V2 family
# uses single-book bid/ask sides and fixed-point dollar prices.
# ---------------------------------------------------------------------------


class CreateOrderV2Request(BaseModel):
    """Body for POST /portfolio/events/orders.

    Differences from v1 ``CreateOrderRequest`` worth knowing:

    - ``side`` is ``BookSideLiteral`` (``bid``/``ask``), not ``yes``/``no``.
      V2 narrows the type on the model itself since there is no kwarg
      overload at the resource-method boundary (see model_only V2 surface).
    - ``client_order_id`` is **required** in V2, unlike V1 where it is
      optional. The server uses it for idempotency in V2.
    - Price is a single ``price: FixedPointDollars`` field rather than the
      paired ``yes_price`` / ``no_price`` from V1.
    """

    ticker: str
    client_order_id: str
    side: BookSideLiteral
    count: FixedPointCount
    price: DollarDecimal
    time_in_force: TimeInForceLiteral
    self_trade_prevention_type: SelfTradePreventionTypeLiteral
    expiration_time: int | None = None
    post_only: bool | None = None
    cancel_order_on_pause: bool | None = None
    reduce_only: bool | None = None
    subaccount: int | None = Field(default=None, ge=0, le=32)
    order_group_id: str | None = None
    exchange_index: int | None = None

    model_config = {"extra": "forbid"}


class CreateOrderV2Response(BaseModel):
    """Response from POST /portfolio/events/orders."""

    order_id: str
    fill_count: FixedPointCount
    remaining_count: FixedPointCount
    ts_ms: int
    client_order_id: str | None = None
    average_fill_price: DollarDecimal | None = None
    average_fee_paid: DollarDecimal | None = None

    model_config = {"extra": "allow"}


class CancelOrderV2Response(BaseModel):
    """Response from DELETE /portfolio/events/orders/{order_id}."""

    order_id: str
    reduced_by: FixedPointCount
    ts_ms: int
    client_order_id: str | None = None

    model_config = {"extra": "allow"}


class DecreaseOrderV2Request(BaseModel):
    """Body for POST /portfolio/events/orders/{order_id}/decrease.

    Spec marks all fields optional but server requires exactly one of
    ``reduce_by`` or ``reduce_to``. Enforced at construction.
    """

    reduce_by: FixedPointCount | None = None
    reduce_to: FixedPointCount | None = None
    exchange_index: int | None = None

    model_config = {"extra": "forbid"}

    # DecreaseOrderV2Request has no subaccount field — the V2 spec routes
    # that as a query param on the resource method, not on the request body.

    @model_validator(mode="after")
    def _enforce_reduce_xor(self) -> DecreaseOrderV2Request:
        if self.reduce_by is not None and self.reduce_to is not None:
            raise ValueError(
                "DecreaseOrderV2Request accepts reduce_by or reduce_to, not both"
            )
        if self.reduce_by is None and self.reduce_to is None:
            raise ValueError(
                "DecreaseOrderV2Request requires either reduce_by or reduce_to"
            )
        return self


class DecreaseOrderV2Response(BaseModel):
    """Response from POST /portfolio/events/orders/{order_id}/decrease."""

    order_id: str
    remaining_count: FixedPointCount
    ts_ms: int
    client_order_id: str | None = None

    model_config = {"extra": "allow"}


class AmendOrderV2Request(BaseModel):
    """Body for POST /portfolio/events/orders/{order_id}/amend."""

    ticker: str
    side: BookSideLiteral
    price: DollarDecimal
    count: FixedPointCount
    client_order_id: str | None = None
    updated_client_order_id: str | None = None
    exchange_index: int | None = None

    model_config = {"extra": "forbid"}


class AmendOrderV2Response(BaseModel):
    """Response from POST /portfolio/events/orders/{order_id}/amend."""

    order_id: str
    ts_ms: int
    client_order_id: str | None = None
    remaining_count: FixedPointCount | None = None
    fill_count: FixedPointCount | None = None
    average_fill_price: DollarDecimal | None = None
    average_fee_paid: DollarDecimal | None = None

    model_config = {"extra": "allow"}


class BatchCreateOrdersV2Request(BaseModel):
    """Body for POST /portfolio/events/orders/batched."""

    orders: list[CreateOrderV2Request]

    model_config = {"extra": "forbid"}


class BatchCreateOrdersV2ResponseEntry(BaseModel):
    """Single entry in BatchCreateOrdersV2Response — may carry an error per-order."""

    order_id: str | None = None
    client_order_id: str | None = None
    fill_count: FixedPointCount | None = None
    remaining_count: FixedPointCount | None = None
    average_fill_price: DollarDecimal | None = None
    average_fee_paid: DollarDecimal | None = None
    ts_ms: int | None = None
    error: dict[str, object] | None = None

    model_config = {"extra": "allow"}


class BatchCreateOrdersV2Response(BaseModel):
    """Response from POST /portfolio/events/orders/batched."""

    orders: list[BatchCreateOrdersV2ResponseEntry]

    model_config = {"extra": "allow"}


class BatchCancelOrdersV2RequestOrder(BaseModel):
    """Single entry in BatchCancelOrdersV2Request.orders."""

    order_id: str
    subaccount: int | None = Field(default=None, ge=0, le=32)
    exchange_index: int | None = None

    model_config = {"extra": "forbid"}


class BatchCancelOrdersV2Request(BaseModel):
    """Body for DELETE /portfolio/events/orders/batched."""

    orders: list[BatchCancelOrdersV2RequestOrder]

    model_config = {"extra": "forbid"}


class BatchCancelOrdersV2ResponseEntry(BaseModel):
    """Single entry in BatchCancelOrdersV2Response — may carry an error per-order.

    Spec invariant (v3.18.0): when ``error`` is null, ``reduced_by`` is the
    count canceled (possibly ``0``). When ``error`` is set, ``reduced_by``
    is still required and is ``0``. Both fields are marked ``required`` in
    the spec; the model validator below makes the invariant explicit so a
    non-conforming response surfaces a clear error rather than a generic
    ``ValidationError`` deep inside Pydantic.
    """

    order_id: str
    reduced_by: FixedPointCount | None = None
    client_order_id: str | None = None
    ts_ms: int | None = None
    error: dict[str, object] | None = None

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def _enforce_reduced_by_present(self) -> BatchCancelOrdersV2ResponseEntry:
        # Spec requires reduced_by on every entry, including errored ones
        # (where it is 0). If a future upstream change starts omitting it,
        # raise a descriptive error rather than letting downstream code see
        # `None` and silently misbehave.
        if self.reduced_by is None:
            raise ValueError(
                "BatchCancelOrdersV2ResponseEntry.reduced_by missing — "
                "spec v3.18.0 requires it on every entry (zero on error). "
                "Server may have diverged from spec; file with Kalshi."
            )
        return self


class BatchCancelOrdersV2Response(BaseModel):
    """Response from DELETE /portfolio/events/orders/batched."""

    orders: list[BatchCancelOrdersV2ResponseEntry]

    model_config = {"extra": "allow"}
