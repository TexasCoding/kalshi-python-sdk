"""Order-related models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from kalshi.types import DollarDecimal


class Order(BaseModel):
    """A Kalshi order."""

    order_id: str
    ticker: str | None = None
    user_id: str | None = None
    status: str | None = None
    side: str | None = None
    is_yes: bool | None = None
    type: str | None = None
    yes_price: DollarDecimal | None = None
    no_price: DollarDecimal | None = None
    count: int | None = None
    initial_count: int | None = None
    remaining_count: int | None = None
    fill_count: int | None = None
    taker_fill_cost: DollarDecimal | None = None
    maker_fill_cost: DollarDecimal | None = None
    taker_fees: DollarDecimal | None = None
    maker_fees: DollarDecimal | None = None
    created_time: datetime | None = None
    expiration_time: datetime | None = None
    client_order_id: str | None = None
    subaccount: int | None = None

    model_config = {"extra": "allow"}


class Fill(BaseModel):
    """A filled trade."""

    trade_id: str
    order_id: str | None = None
    ticker: str | None = None
    side: str | None = None
    is_taker: bool | None = None
    yes_price: DollarDecimal | None = None
    no_price: DollarDecimal | None = None
    count: int | None = None
    action: str | None = None
    created_time: datetime | None = None

    model_config = {"extra": "allow"}


class CreateOrderRequest(BaseModel):
    """Parameters for creating an order."""

    ticker: str
    side: str
    type: str = "limit"
    action: str = "buy"
    count: int = 1
    yes_price: DollarDecimal | None = None
    no_price: DollarDecimal | None = None
    client_order_id: str | None = None
    expiration_ts: int | None = None
    buy_max_cost: DollarDecimal | None = None
