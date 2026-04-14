"""Order-related models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, Field

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

    Price fields are serialized with ``_dollars`` suffix for the API.
    ``buy_max_cost`` is sent as-is (the API expects integer cents for this field;
    callers should pass cents, not dollars).
    """

    ticker: str
    side: str
    type: str = "limit"
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
    buy_max_cost: DollarDecimal | None = None

    model_config = {"extra": "forbid"}
