"""Order-related models."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, AwareDatetime, BaseModel, Field, model_validator

from kalshi.types import DollarDecimal, FixedPointCount, OrderPrice, StrictInt

# Literal aliases for fixed-enum fields on the order models.
# Source of truth: OpenAPI spec (specs/openapi.yaml). Narrowed types make a
# typo fail at construction rather than as a 400 from the server.
SideLiteral = Literal["yes", "no"]
"""Outcome side. Spec: Order.outcome_side / Fill.outcome_side enum."""

TimeInForceLiteral = Literal["fill_or_kill", "good_till_canceled", "immediate_or_cancel"]
"""Order time-in-force. Spec: CreateOrderV2Request.time_in_force enum."""

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
    ticker: str
    user_id: str
    status: str
    side: str
    is_yes: bool | None = None
    # Spec field is named ``type`` (enum: limit, market). Renamed to
    # ``order_type`` on the SDK side to avoid shadowing the Python builtin —
    # same rationale as milestone_type / target_type / incentive_type
    # elsewhere. The wire still sends ``type``; validation alias accepts both.
    order_type: str = Field(
        validation_alias=AliasChoices("type", "order_type"),
    )
    yes_price: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    no_price: DollarDecimal = Field(
        validation_alias=AliasChoices("no_price_dollars", "no_price"),
    )
    count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("count_fp", "count"),
    )
    initial_count: FixedPointCount = Field(
        validation_alias=AliasChoices("initial_count_fp", "initial_count"),
    )
    remaining_count: FixedPointCount = Field(
        validation_alias=AliasChoices("remaining_count_fp", "remaining_count"),
    )
    fill_count: FixedPointCount = Field(
        validation_alias=AliasChoices("fill_count_fp", "fill_count"),
    )
    taker_fill_cost: DollarDecimal = Field(
        validation_alias=AliasChoices("taker_fill_cost_dollars", "taker_fill_cost"),
    )
    maker_fill_cost: DollarDecimal = Field(
        validation_alias=AliasChoices("maker_fill_cost_dollars", "maker_fill_cost"),
    )
    taker_fees: DollarDecimal = Field(
        validation_alias=AliasChoices("taker_fees_dollars", "taker_fees"),
    )
    maker_fees: DollarDecimal = Field(
        validation_alias=AliasChoices("maker_fees_dollars", "maker_fees"),
    )
    created_time: AwareDatetime | None = None
    expiration_time: AwareDatetime | None = None
    client_order_id: str
    subaccount: int | None = None

    # v3.18.0 backfill (#159). outcome_side/book_side are the canonical
    # direction encoding going forward; deprecated action/side/is_yes stay
    # for back-compat. subaccount_number is distinct from subaccount.
    outcome_side: SideLiteral
    book_side: BookSideLiteral
    last_update_time: AwareDatetime | None = None
    self_trade_prevention_type: SelfTradePreventionTypeLiteral | None = None
    order_group_id: str | None = None
    cancel_order_on_pause: bool | None = None
    subaccount_number: int | None = None
    exchange_index: int | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class Fill(BaseModel):
    """A filled trade.

    Price fields accept both ``_dollars``-suffixed names from the API
    and short names. Count accepts ``_fp``-suffixed name.
    """

    trade_id: str
    fill_id: str
    order_id: str
    ticker: str
    market_ticker: str
    side: str
    action: str
    is_taker: bool
    count: FixedPointCount = Field(
        validation_alias=AliasChoices("count_fp", "count"),
    )
    yes_price: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    no_price: DollarDecimal = Field(
        validation_alias=AliasChoices("no_price_dollars", "no_price"),
    )
    fee_cost: DollarDecimal = Field(
        validation_alias=AliasChoices("fee_cost_dollars", "fee_cost"),
    )
    created_time: AwareDatetime | None = None

    # v3.18.0 backfill (#159). ts is Unix-ms int per spec — distinct from
    # the typed created_time: datetime; do NOT coerce.
    outcome_side: SideLiteral
    book_side: BookSideLiteral
    subaccount_number: int | None = None
    ts: int | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


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
    """Body for POST /portfolio/events/orders — the event-market order API.

    Notable shape:

    - ``side`` is ``BookSideLiteral`` (``bid``/``ask``). V2 narrows the type on
      the model itself since there is no kwarg overload at the resource-method
      boundary (the V2 surface is model-only).
    - ``client_order_id`` is **required** by this model because the server uses
      it for idempotency on V2 orders. (OpenAPI v3.20.0 relaxed it to optional
      server-side, but the SDK keeps it required by design so every V2 order is
      idempotent.)
    - Price is a single ``price`` field (dollars).
    """

    ticker: str
    client_order_id: str
    side: BookSideLiteral
    count: FixedPointCount
    price: OrderPrice
    time_in_force: TimeInForceLiteral
    self_trade_prevention_type: SelfTradePreventionTypeLiteral
    expiration_time: StrictInt | None = None
    post_only: bool | None = None
    cancel_order_on_pause: bool | None = None
    reduce_only: bool | None = None
    subaccount: StrictInt | None = Field(default=None, ge=0)
    order_group_id: str | None = None
    exchange_index: StrictInt | None = Field(default=None, ge=0)

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

    ``market_ticker`` (OpenAPI 3.27.0) is required when ``exchange_index`` is
    ``-1`` (auto-route by ticker), matching cancel/batch-cancel.
    """

    reduce_by: FixedPointCount | None = None
    reduce_to: FixedPointCount | None = None
    # No ``ge=0``: ExchangeIndex permits ``-1`` to auto-route by market ticker.
    exchange_index: StrictInt | None = None
    market_ticker: str | None = None

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
    price: OrderPrice
    count: FixedPointCount
    client_order_id: str | None = None
    updated_client_order_id: str | None = None
    exchange_index: StrictInt | None = None

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
    """Single entry in BatchCreateOrdersV2Response — may carry an error per-order.

    All fields are optional because each entry can be either a success
    (``order_id`` + ``fill_count`` + ``remaining_count`` + ``ts_ms`` set)
    or an error (only ``error`` set, others omitted). Note this differs
    from :class:`CreateOrderV2Response` where ``ts_ms`` is required —
    that response is for a single order which either succeeds with a
    timestamp or raises an HTTP error, never a per-entry error block.
    """

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
    subaccount: StrictInt | None = Field(default=None, ge=0)
    # No ``ge=0``: the spec ExchangeIndex permits ``-1`` to auto-route by market
    # ticker (mirrors ``cancel_v2``'s plain-int param), in which case
    # ``market_ticker`` below is required.
    exchange_index: StrictInt | None = None
    # Spec v3.22.0: required when exchange_index is -1 (auto-route by ticker).
    market_ticker: str | None = None

    model_config = {"extra": "forbid"}


class BatchCancelOrdersV2Request(BaseModel):
    """Body for DELETE /portfolio/events/orders/batched."""

    orders: list[BatchCancelOrdersV2RequestOrder]

    model_config = {"extra": "forbid"}


class BatchCancelOrdersV2ResponseEntry(BaseModel):
    """Single entry in BatchCancelOrdersV2Response — may carry an error per-order.

    Spec invariant (v3.18.0): when ``error`` is null, ``reduced_by`` is the
    count canceled. When ``error`` is set, ``reduced_by`` is still present
    and is ``0``. Both ``order_id`` and ``reduced_by`` are marked
    ``required`` in the spec, so they are non-optional on this model —
    Pydantic will raise ``ValidationError`` if upstream ever omits them.
    """

    order_id: str
    reduced_by: FixedPointCount
    client_order_id: str | None = None
    ts_ms: int | None = None
    error: dict[str, object] | None = None

    model_config = {"extra": "allow"}


class BatchCancelOrdersV2Response(BaseModel):
    """Response from DELETE /portfolio/events/orders/batched."""

    orders: list[BatchCancelOrdersV2ResponseEntry]

    model_config = {"extra": "allow"}
