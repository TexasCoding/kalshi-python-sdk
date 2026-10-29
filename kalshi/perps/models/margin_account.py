"""Perps margin-account models — balance, risk, notional risk limit, fee tiers.

Response models for the read-only direct-margin account endpoints (#394) plus
``GetMarginCorporateActions`` (#550). All are pure response models — every one
carries ``model_config = {"extra": "allow"}`` so additive spec fields don't
break parsing, and none have request bodies (the endpoints are GETs with at
most query flags).

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

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from kalshi.perps.models.common import SubaccountTypeLiteral
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
    # Spec 3.35.0 marks subaccount_type required. Kept optional so a balance
    # row that omits it still parses. See PERPS_EXCLUSIONS.
    subaccount_type: SubaccountTypeLiteral | None = None
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
    # Spec 3.35.0 marks subaccount_type required. Kept optional so a risk
    # row that omits it still parses. See PERPS_EXCLUSIONS.
    subaccount_type: SubaccountTypeLiteral | None = None
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
    """Spec ``NotionalRiskLimitResponse`` — default limit, usage, and overrides.

    ``total_current_usage`` and ``current_usage_by_market_ticker`` are
    spec-required. ``member_notional_value_risk_limit`` and
    ``effective_account_notional_value_risk_limit`` are present only when set.
    """

    model_config = ConfigDict(extra="allow")

    default_notional_value_risk_limit: DollarDecimal
    notional_value_risk_limits_by_market_ticker: dict[str, DollarDecimal]
    total_current_usage: DollarDecimal
    current_usage_by_market_ticker: dict[str, DollarDecimal]
    member_notional_value_risk_limit: DollarDecimal | None = None
    effective_account_notional_value_risk_limit: DollarDecimal | None = None


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


MarginCorporateActionTypeLiteral = Literal[
    "cash_dividend",
    "special_dividend",
    "spin_off",
    "stock_split",
    "final_settlement",
    "ticker_change",
]
"""Spec ``MarginCorporateAction.type`` — which terms object is present."""


MarginCorporateActionStatusLiteral = Literal[
    "scheduled",
    "cancelled",
    "applied",
    "lapsed",
]
"""Spec ``MarginCorporateAction.status`` — public notice status."""


class MarginCorporateActionCashTerms(BaseModel):
    """Terms for ``cash_dividend``, ``special_dividend``, or ``spin_off``.

    Spec ``MarginCorporateActionCashTerms``. Omitted for other types and
    cancelled notices. All properties are optional.
    """

    model_config = ConfigDict(extra="allow")

    cash_per_share: DollarDecimal | None = None
    cash_per_contract: DollarDecimal | None = None
    ex_date: date | None = None


class MarginCorporateActionSplitTerms(BaseModel):
    """Terms for ``stock_split``.

    Spec ``MarginCorporateActionSplitTerms``. Omitted for other types and
    cancelled notices. All properties are optional.
    """

    model_config = ConfigDict(extra="allow")

    ratio_old: str | None = None
    ratio_new: str | None = None
    ex_date: date | None = None


class MarginCorporateActionFinalSettlementTerms(BaseModel):
    """Terms for ``final_settlement``.

    Spec ``MarginCorporateActionFinalSettlementTerms``. Omitted for other
    types and cancelled notices. ``reason`` is spec-required when the object
    is present.
    """

    model_config = ConfigDict(extra="allow")

    reason: str
    settlement_price_per_share: DollarDecimal | None = None
    settlement_price_per_contract: DollarDecimal | None = None


class MarginCorporateActionTickerChangeTerms(BaseModel):
    """Terms for ``ticker_change``.

    Spec ``MarginCorporateActionTickerChangeTerms``. Omitted for other types
    and cancelled notices. ``old_ticker`` and ``new_ticker`` are required
    when the object is present.
    """

    model_config = ConfigDict(extra="allow")

    old_ticker: str
    new_ticker: str


class MarginCorporateAction(BaseModel):
    """Spec ``MarginCorporateAction`` — a margin corporate action notice.

    Scheduled, applied, and lapsed notices have exactly one terms object
    matching ``type``. Cancelled notices omit all four terms objects and
    ``execution_time``.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    market_id: str
    market_ticker: str
    type: MarginCorporateActionTypeLiteral
    status: MarginCorporateActionStatusLiteral
    updated_ts: AwareDatetime
    execution_time: AwareDatetime | None = None
    cash: MarginCorporateActionCashTerms | None = None
    split: MarginCorporateActionSplitTerms | None = None
    final_settlement: MarginCorporateActionFinalSettlementTerms | None = None
    ticker_change: MarginCorporateActionTickerChangeTerms | None = None


class GetMarginCorporateActionsResponse(BaseModel):
    """Spec ``GetMarginCorporateActionsResponse`` — notices envelope.

    ``corporate_actions`` is spec-required and uses
    :data:`~kalshi.types.NullableList`: a missing key raises
    ``ValidationError``, while a ``null`` array coerces to ``[]``.
    """

    model_config = ConfigDict(extra="allow")

    corporate_actions: NullableList[MarginCorporateAction]
