"""Perps margin-account models — balance, risk, notional risk limit, fee tiers.

Response models for the four read-only direct-margin account endpoints (#394):
``GetMarginBalance``, ``GetMarginRisk``, ``GetMarginNotionalRiskLimit`` and
``GetMarginFeeTiers``. All are pure response models — every one carries
``model_config = {"extra": "allow"}`` so additive spec fields don't break
parsing, and none have request bodies (the endpoints are GETs with at most a
single query flag).

Money fields use :data:`~kalshi.types.DollarDecimal` (the perps spec's
``FixedPointDollars`` string), and the signed position quantity uses
:data:`~kalshi.types.FixedPointCount`. Wire field names already match the short
Python names (no ``_dollars`` suffix on this surface), so no ``validation_alias``
is used here. The fee-rate maps and leverage ratios are spec ``number/double``
and use :data:`~kalshi.types.MultiplierDecimal` (exact ``Decimal``,
string-serialized) — consistent with the perps exchange + WS ticker surfaces
and so callers can do exact fee/leverage math without binary-float drift.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from kalshi.types import (
    DollarDecimal,
    FixedPointCount,
    MultiplierDecimal,
    NullableList,
)


class MarginSubaccountBalance(BaseModel):
    """Spec ``MarginSubaccountBalance`` — one subaccount's balance breakdown."""

    model_config = ConfigDict(extra="allow")

    subaccount: int
    position_value: DollarDecimal
    account_equity: DollarDecimal
    maintenance_margin: DollarDecimal
    initial_margin: DollarDecimal
    resting_orders_margin: DollarDecimal
    available_balance: DollarDecimal


class GetMarginBalanceResponse(BaseModel):
    """Spec ``GetMarginBalanceResponse`` — per-subaccount balances + settled funds."""

    model_config = ConfigDict(extra="allow")

    subaccount_balances: NullableList[MarginSubaccountBalance]
    settled_funds: DollarDecimal


class MarginRiskPosition(BaseModel):
    """Spec ``MarginRiskPosition`` — leverage/liquidation risk for one position."""

    model_config = ConfigDict(extra="allow")

    subaccount: int
    market_ticker: str
    position: FixedPointCount
    mark_price: DollarDecimal
    position_notional: DollarDecimal
    maintenance_margin_required: DollarDecimal | None = None
    position_leverage: MultiplierDecimal | None = None
    estimated_liquidation_price: DollarDecimal | None = None
    # Spec v3.23.0 (required): True when the position is hedged within a
    # portfolio, so its margin is computed at the portfolio level.
    is_portfolio: bool


class GetMarginRiskResponse(BaseModel):
    """Spec ``GetMarginRiskResponse`` — account leverage + per-position risk array."""

    model_config = ConfigDict(extra="allow")

    account_leverage: MultiplierDecimal | None = None
    total_position_notional: DollarDecimal
    total_maintenance_margin: DollarDecimal
    positions: NullableList[MarginRiskPosition]


class NotionalRiskLimitResponse(BaseModel):
    """Spec ``NotionalRiskLimitResponse`` — default limit + per-ticker overrides."""

    model_config = ConfigDict(extra="allow")

    default_notional_value_risk_limit: DollarDecimal
    notional_value_risk_limits_by_market_ticker: dict[str, DollarDecimal]


class GetMarginFeeTiersResponse(BaseModel):
    """Spec ``GetMarginFeeTiersResponse`` — maker/taker fee-rate maps by ticker.

    Values are decimal fractions of notional (e.g. ``0.0005`` = 5 bps), spec
    ``number/double``. They use :data:`~kalshi.types.MultiplierDecimal` (exact
    ``Decimal``) so ``notional * fee_rate`` stays exact for the caller.
    """

    model_config = ConfigDict(extra="allow")

    maker_fee_rates: dict[str, MultiplierDecimal]
    taker_fee_rates: dict[str, MultiplierDecimal]


FeeScheduleLiteral = Literal["self_clearing_members", "kalshi_prime", "fcm"]
"""Fee schedule containing a :class:`MarginFeeTierRate`."""


class MarginFeeTierRate(BaseModel):
    """One row of the authenticated account's margin fee-tier schedule."""

    model_config = ConfigDict(extra="allow")

    fee_schedule: FeeScheduleLiteral
    tier: int = Field(ge=0)
    maker_fee_rate: MultiplierDecimal
    taker_fee_rate: MultiplierDecimal


class GetMarginFeeTierRatesResponse(BaseModel):
    """Response from GET /margin/fee_tier_rates."""

    model_config = ConfigDict(extra="allow")

    fee_tier_rates: list[MarginFeeTierRate]
