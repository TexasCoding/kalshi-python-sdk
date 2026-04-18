"""Order-related models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from kalshi.types import DollarDecimal, FixedPointCount


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
    type: str | None = None
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
    count: DollarDecimal | None = Field(
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
