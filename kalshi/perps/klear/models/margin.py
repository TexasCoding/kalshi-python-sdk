"""Klear (SCM) margin models — settlement obligations, estimates, balances (#400).

Response and request models for the nine Self-Clearing-Member margin endpoints
on the Klear API (``klear-api/v1``): margin reports, the active settlement
obligation, obligation history, the settlement estimate, the settlement-buffer
balance + its history, the guaranty-fund balance, and settlement-balance
withdrawal (initiate + status-by-id).

**Money typing — read carefully.** Unlike the perps prediction/REST framing
(``FixedPointDollars`` / ``FixedPointCount`` strings), almost every monetary
field on the Klear margin schemas is an **integer ``int64`` in _centicents_**
(the spec states ``1 USD = 10,000 centicents``), serialized as a JSON number
with a ``_centicents`` field-name suffix. Those are **plain ``int``** — they are
NOT :data:`DollarDecimal` / :data:`FixedPointCount`. This mirrors the
integer-cents precedent in ``kalshi/models/portfolio.py`` (``Balance.balance``,
``Deposit.amount_cents``). The ONLY two fixed-point **dollar-string** fields in
this whole surface are :attr:`WithdrawSettlementBalanceRequest.amount` and
:attr:`GetSettlementBalanceWithdrawalResponse.amount` (e.g. ``"500.00"``); those
use :data:`DollarDecimal`.

**Timestamps.** Every REST timestamp is RFC3339 (``format: date-time``) and uses
:class:`pydantic.AwareDatetime`; the single ``format: date`` field
(:attr:`MarginReport.date`) uses :class:`datetime.date`.

Response models use ``model_config = {"extra": "allow"}`` (forward-compat with
additive spec drift, matching the prediction-API portfolio models). The one
request model — :class:`WithdrawSettlementBalanceRequest` — uses
``extra="forbid"`` so a typo'd body field fails at construction.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel

from kalshi.types import DollarDecimal, NullableList


def _require_positive_withdrawal(value: Decimal) -> Decimal:
    """Reject a non-positive settlement-withdrawal amount at construction.

    ``WithdrawSettlementBalanceRequest`` is the single real-money write in the
    Klear surface and the spec requires the amount to be positive. ``DollarDecimal``
    alone only rejects non-finite values (negatives/zero are legitimate on
    response-side balance/PnL fields), so this boundary guard mirrors the
    ``OrderPrice`` non-negative check used on the prediction-API order requests —
    a typo'd sign or zero fails here instead of shipping to the withdrawal endpoint.
    """
    if value <= 0:
        raise ValueError(
            f"withdrawal amount must be positive (got {value}); "
            "a non-positive amount must never reach the settlement-withdrawal endpoint."
        )
    return value


WithdrawalAmount = Annotated[DollarDecimal, AfterValidator(_require_positive_withdrawal)]
"""A request-side withdrawal amount: a positive fixed-point dollar value."""

# Spec ``MarginReport.report_type`` enum — surfaced as a Literal alias (mirrors
# the ``PaymentStatusLiteral`` style in kalshi/models/portfolio.py).
MarginReportTypeLiteral = Literal[
    "trade_audit",
    "position_snapshot",
    "market_price_snapshot",
    "funding_periods",
    "settlement_periods",
]
"""Spec ``MarginReport.report_type`` — the kind of margin report."""

# Spec ``GetSettlementBalanceWithdrawalResponse.status`` enum.
WithdrawalStatusLiteral = Literal["pending", "processing", "processed", "failed"]
"""Spec withdrawal ``status`` — lifecycle of an async settlement-balance withdrawal."""


class MarginReport(BaseModel):
    """Spec ``MarginReport`` — one downloadable margin report.

    ``url`` is a presigned download URL — treat it as sensitive and keep it out
    of logs.
    """

    report_type: MarginReportTypeLiteral
    url: str
    date: datetime.date
    created_ts: AwareDatetime
    is_end_of_day: bool

    model_config = {"extra": "allow"}

    def __repr__(self) -> str:
        # The presigned `url` grants download access — redact it from repr/logs.
        return (
            f"MarginReport(report_type={self.report_type!r}, date={self.date!r}, "
            f"created_ts={self.created_ts!r}, is_end_of_day={self.is_end_of_day!r}, "
            f"url=<redacted>)"
        )

    __str__ = __repr__


class GetMarginReportsResponse(BaseModel):
    """Spec ``GetMarginReportsResponse`` — flat array of reports (not paginated)."""

    reports: NullableList[MarginReport]

    model_config = {"extra": "allow"}


class ObligationReceiveInfo(BaseModel):
    """Spec ``ObligationReceiveInfo`` — a receivable line within an obligation."""

    id: str
    type: str
    amount_centicents: int
    external_reference: str
    created_ts: AwareDatetime

    model_config = {"extra": "allow"}


class SettlementDetail(BaseModel):
    """Spec ``SettlementDetail`` — per-market, per-subtrader settlement breakdown."""

    id: str
    market_ticker: str
    subtrader_id: str
    pnl_centicents: int
    total_fees_centicents: int
    total_amount_centicents: int

    model_config = {"extra": "allow"}


class MaintenanceMarginDetail(BaseModel):
    """Spec ``MaintenanceMarginDetail`` — maintenance-margin requirement + delta.

    ``subtrader_id`` may be an empty string when not populated.
    """

    id: str
    subtrader_id: str
    maintenance_margin_centicents: int
    maintenance_margin_delta_centicents: int

    model_config = {"extra": "allow"}


class ObligationEntry(BaseModel):
    """Spec ``ObligationEntry`` — a settlement obligation (flattened ``allOf``).

    The spec models ``ObligationEntry`` as ``allOf: [ObligationInfo, {inline}]``;
    the SDK **flattens** ``ObligationInfo`` and the inline object into this one
    model (the spec only ever returns the composed shape, never bare
    ``ObligationInfo``). ``amount_centicents`` is the net settlement amount:
    negative means the SCM pays Kalshi Klear, positive means Kalshi Klear pays
    the SCM. All ``_centicents`` fields are plain ``int``.
    """

    # From ObligationInfo.
    id: str
    user_id: str
    amount_centicents: int
    fees_centicents: int
    maintenance_margin_centicents: int
    pnl_centicents: int
    execution_time: AwareDatetime
    last_updated_ts: AwareDatetime
    # From the inline allOf object.
    receives: NullableList[ObligationReceiveInfo]
    settlement_details: NullableList[SettlementDetail]
    maintenance_margin_details: NullableList[MaintenanceMarginDetail]

    model_config = {"extra": "allow"}


class GetActiveMarginObligationResponse(BaseModel):
    """Spec ``GetActiveMarginObligationResponse`` — current-cycle obligation, if any.

    ``obligation`` is optional and nullable (the spec has no ``required`` block);
    null/absent both mean no obligation is pending.
    """

    obligation: ObligationEntry | None = None

    model_config = {"extra": "allow"}


class GetObligationHistoryResponse(BaseModel):
    """Spec ``GetObligationHistoryResponse`` — cursor-paginated obligation page.

    ``cursor`` is an RFC3339 date-time string; absent on the last page. The
    resource consumes this via the generic ``Page[ObligationEntry]`` envelope.
    """

    obligations: NullableList[ObligationEntry]
    cursor: str | None = None

    @property
    def has_next(self) -> bool:
        return bool(self.cursor)

    model_config = {"extra": "allow"}


class MarketSettlementEstimate(BaseModel):
    """Spec ``MarketSettlementEstimate`` — per-market settlement breakdown (centi units)."""

    quantity_centicount: int
    variation_margin_centicents: int
    notional_value_centicents: int

    model_config = {"extra": "allow"}


class SettlementEstimate(BaseModel):
    """Spec ``SettlementEstimate`` — estimated next-settlement amounts (centicents)."""

    variation_margin_centicents: int
    total_fees_centicents: int
    maintenance_margin_delta_centicents: int
    maintenance_margin_required_centicents: int
    total_amount_centicents: int
    # Spec v3.22.0: per-market breakdown map (market ticker -> estimate); optional.
    positions: dict[str, MarketSettlementEstimate] | None = None

    model_config = {"extra": "allow"}


class GetSettlementEstimateResponse(BaseModel):
    """Spec ``GetSettlementEstimateResponse`` — estimate + per-subtrader breakdowns.

    ``subtrader_breakdowns`` is the spec ``additionalProperties`` map
    (subtrader-id → :class:`SettlementEstimate`); optional.

    ``prev_settlement_prices`` (spec v3.22.0) maps market ticker → most
    recent settlement (mark) price in centicents; optional.
    """

    user_breakdown: SettlementEstimate
    subtrader_breakdowns: dict[str, SettlementEstimate] | None = None
    prev_settlement_prices: dict[str, int] | None = None
    settlement_balance_centicents: int

    model_config = {"extra": "allow"}


class GetSettlementBalanceResponse(BaseModel):
    """Spec ``GetSettlementBalanceResponse`` — settlement-buffer balance.

    ``locked_balance_centicents`` is optional (locked e.g. by pending withdrawals).
    """

    user_id: str
    balance_available_centicents: int
    locked_balance_centicents: int | None = None

    model_config = {"extra": "allow"}


class GetGuarantyFundBalanceResponse(BaseModel):
    """Spec ``GetGuarantyFundBalanceResponse`` — guaranty-fund contribution balance.

    ``amount_centicents`` is zero when no contribution has been made yet.
    """

    user_id: str
    amount_centicents: int
    updated_ts: AwareDatetime

    model_config = {"extra": "allow"}


class WithdrawSettlementBalanceRequest(BaseModel):
    """Spec ``WithdrawSettlementBalanceRequest`` — initiate a settlement withdrawal.

    The only request body in this surface. ``amount`` is a fixed-point **dollar
    string** (``"500.00"``), NOT centicents — wire name equals the Python name, so
    no ``serialization_alias`` is needed. It is validated **positive at construction**
    (this is the single real-money write; a negative/zero amount must never reach
    the endpoint). Uses ``extra="forbid"`` so a typo'd field fails at construction;
    serializes via ``model.model_dump(exclude_none=True, by_alias=True, mode="json")``
    to ``{"amount": "500.00"}``.
    """

    amount: WithdrawalAmount

    model_config = {"extra": "forbid"}


class WithdrawSettlementBalanceResponse(BaseModel):
    """Spec ``WithdrawSettlementBalanceResponse`` — id of the async withdrawal."""

    id: str

    model_config = {"extra": "allow"}


class GetSettlementBalanceWithdrawalResponse(BaseModel):
    """Spec ``GetSettlementBalanceWithdrawalResponse`` — withdrawal status by id.

    ``amount`` is a fixed-point **dollar string** (``"500.00"``), NOT centicents.
    """

    id: str
    amount: DollarDecimal
    status: WithdrawalStatusLiteral
    created_ts: AwareDatetime

    model_config = {"extra": "allow"}


class SettlementBalanceHistoryEntry(BaseModel):
    """Spec ``SettlementBalanceHistoryEntry`` — one settlement-balance change."""

    balance_delta_centicents: int
    locked_balance_delta_centicents: int
    reason: str
    business_transaction_id: str
    created_ts: AwareDatetime

    model_config = {"extra": "allow"}


class GetSettlementBalanceHistoryResponse(BaseModel):
    """Spec ``GetSettlementBalanceHistoryResponse`` — cursor-paginated history page.

    ``cursor`` is an opaque string; absent on the last page. The resource
    consumes this via the generic ``Page[SettlementBalanceHistoryEntry]`` envelope.
    """

    entries: NullableList[SettlementBalanceHistoryEntry]
    cursor: str | None = None

    @property
    def has_next(self) -> bool:
        return bool(self.cursor)

    model_config = {"extra": "allow"}
