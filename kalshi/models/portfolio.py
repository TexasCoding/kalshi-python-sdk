"""Portfolio-related models."""

from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal, NullableList


class Balance(BaseModel):
    """Account balance. Values are integer cents."""

    balance: int
    portfolio_value: int
    updated_ts: int

    model_config = {"extra": "allow"}


class TotalRestingOrderValue(BaseModel):
    """Total value of resting orders in cents.

    Spec: "intended for use by FCM members (rare)". Non-FCM accounts see
    403 on this endpoint (demo audit 2026-04-18).
    """

    total_resting_order_value: int

    model_config = {"extra": "allow"}


class MarketPosition(BaseModel):
    """A position in a single market."""

    ticker: str
    total_traded: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("total_traded_dollars", "total_traded"),
    )
    position: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("position_fp", "position"),
    )
    market_exposure: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("market_exposure_dollars", "market_exposure"),
    )
    realized_pnl: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("realized_pnl_dollars", "realized_pnl"),
    )
    resting_orders_count: int | None = None
    fees_paid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("fees_paid_dollars", "fees_paid"),
    )
    last_updated_ts: datetime | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class EventPosition(BaseModel):
    """A position aggregated at the event level."""

    event_ticker: str
    total_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("total_cost_dollars", "total_cost"),
    )
    total_cost_shares: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("total_cost_shares_fp", "total_cost_shares"),
    )
    event_exposure: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("event_exposure_dollars", "event_exposure"),
    )
    realized_pnl: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("realized_pnl_dollars", "realized_pnl"),
    )
    fees_paid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("fees_paid_dollars", "fees_paid"),
    )

    model_config = {"extra": "allow", "populate_by_name": True}


class PositionsResponse(BaseModel):
    """Response from the positions endpoint containing both market and event positions."""

    market_positions: NullableList[MarketPosition] = []
    event_positions: NullableList[EventPosition] = []
    cursor: str | None = None

    @property
    def has_next(self) -> bool:
        return bool(self.cursor)

    model_config = {"extra": "allow"}


class Settlement(BaseModel):
    """A settled market position."""

    ticker: str
    event_ticker: str | None = None
    market_result: str | None = None
    yes_count: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_count_fp", "yes_count"),
    )
    yes_total_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_total_cost_dollars", "yes_total_cost"),
    )
    no_count: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_count_fp", "no_count"),
    )
    no_total_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_total_cost_dollars", "no_total_cost"),
    )
    revenue: int | None = None
    settled_time: datetime | None = None
    fee_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("fee_cost_dollars", "fee_cost"),
    )

    model_config = {"extra": "allow", "populate_by_name": True}
