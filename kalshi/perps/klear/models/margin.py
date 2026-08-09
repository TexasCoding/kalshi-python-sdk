"""Klear (SCM) margin models — settlement obligations, estimates, balances (#400).

Response and request models for the Self-Clearing-Member margin endpoints on
the Klear API (``klear-api/v1``): margin reports, active obligations,
obligation history + paged detail rows, settlement estimates by asset class,
settlement-buffer balance + history, guaranty-fund balance, settlement-balance
withdrawal (initiate + status-by-id), and FCM subtrader groups.

**Money typing — read carefully.** Unlike the perps prediction/REST framing
(``FixedPointDollars`` / ``FixedPointCount`` strings), almost every monetary
field on the Klear margin schemas is an **integer ``int64`` in _centicents_**
(the spec states ``1 USD = 10,000 centicents``), serialized as a JSON number
with a ``_centicents`` field-name suffix. Those are **plain ``int``** — they are
NOT :data:`DollarDecimal` / :data:`FixedPointCount`. This mirrors the
integer-cents precedent in ``kalshi/models/portfolio.py`` (``Balance.balance``,
``Deposit.amount_cents``). Fixed-point **count** strings appear on
:attr:`SettlementDetail.position_quantity_fp` and
:attr:`FundingPaymentDetail.position_quantity_fp`. The ONLY fixed-point
**dollar-string** fields are :attr:`WithdrawSettlementBalanceRequest.amount` and
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

from pydantic import AfterValidator, AwareDatetime, BaseModel, Field

from kalshi.types import DollarDecimal, FixedPointCount, NullableList


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

# Spec ``AssetClass`` enum (single value today). Named alias mirrors the other
# *Literal aliases; shared by ObligationEntry.asset_class and the settlement
# estimates keyed by asset class (spec sync 3.24.0).
AssetClassLiteral = Literal["Crypto"]
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
    position_quantity_fp: FixedPointCount
    pnl_centicents: int
    total_fees_centicents: int
    total_amount_centicents: int

    model_config = {"extra": "allow"}


class MaintenanceMarginDetail(BaseModel):
    """Spec ``MaintenanceMarginDetail`` — maintenance-margin requirement + delta.

    ``subtrader_id`` may be an empty string when not populated.
    ``margin_group_id`` is set when the subtrader is part of a subtrader group.
    """

    id: str
    subtrader_id: str
    maintenance_margin_centicents: int
    maintenance_margin_delta_centicents: int
    margin_group_id: str | None = None

    model_config = {"extra": "allow"}


class FundingPaymentDetail(BaseModel):
    """Spec ``FundingPaymentDetail`` — per-market funding payment within an obligation.

    ``position_quantity_fp`` is a fixed-point contract count string (e.g. ``"1.25"``).
    Centicents fields are plain ``int``.
    """

    id: str
    market_ticker: str
    subtrader_id: str
    funding_time: AwareDatetime
    position_quantity_fp: FixedPointCount
    notional_value_centicents: int
    funding_amount_centicents: int

    model_config = {"extra": "allow"}


class ObligationEntry(BaseModel):
    """Spec ``ObligationEntry`` — a settlement obligation (flattened ``allOf``).

    The spec models ``ObligationEntry`` as ``allOf: [ObligationInfo, {inline}]``;
    the SDK **flattens** ``ObligationInfo`` and the inline object into this one
    model (the spec only ever returns the composed shape, never bare
    ``ObligationInfo``). ``amount_centicents`` is the net settlement amount:
    negative means the SCM pays Kalshi Klear, positive means Kalshi Klear pays
    the SCM. All ``_centicents`` fields are plain ``int``.

    Inline detail arrays are capped at 1000 rows; when truncated the matching
    ``*_truncated`` flag is set and the full set is available via the paged
    ``/margin/obligations/{obligation_id}/...`` endpoints.
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
    # Spec (perps SCM) added a required ``asset_class`` on ``ObligationInfo``.
    asset_class: AssetClassLiteral
    # From the inline allOf object.
    receives: NullableList[ObligationReceiveInfo]
    settlement_details: NullableList[SettlementDetail]
    maintenance_margin_details: NullableList[MaintenanceMarginDetail]
    funding_payments: NullableList[FundingPaymentDetail]
    settlement_details_truncated: bool | None = None
    maintenance_margin_details_truncated: bool | None = None
    funding_payments_truncated: bool | None = None

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


class GetObligationSettlementDetailsResponse(BaseModel):
    """Spec ``GetObligationSettlementDetailsResponse`` — paged settlement details."""

    settlement_details: NullableList[SettlementDetail]
    cursor: str | None = None

    @property
    def has_next(self) -> bool:
        return bool(self.cursor)

    model_config = {"extra": "allow"}


class GetObligationMaintenanceMarginDetailsResponse(BaseModel):
    """Spec ``GetObligationMaintenanceMarginDetailsResponse`` — paged MM details."""

    maintenance_margin_details: NullableList[MaintenanceMarginDetail]
    cursor: str | None = None

    @property
    def has_next(self) -> bool:
        return bool(self.cursor)

    model_config = {"extra": "allow"}


class GetObligationFundingPaymentsResponse(BaseModel):
    """Spec ``GetObligationFundingPaymentsResponse`` — paged funding payments."""

    funding_payments: NullableList[FundingPaymentDetail]
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


# ── Spec sync 3.24.0 additions (perps SCM) ──────────────────────────────────


class GetActiveMarginObligationsResponse(BaseModel):
    """Spec ``GetActiveMarginObligationsResponse`` — all currently-active obligations.

    Backs ``GET /margin/active_obligations`` (the singular
    ``/margin/active_obligation`` endpoint was removed upstream).
    """

    obligations: NullableList[ObligationEntry]

    model_config = {"extra": "allow"}


class AssetClassSettlementEstimate(BaseModel):
    """Spec ``AssetClassSettlementEstimate`` — settlement estimate for one asset class.

    User + per-subtrader breakdowns + previous settlement prices, plus
    ``next_runtime`` (the next settlement-cycle time). Only ``next_runtime`` is
    spec-required; the breakdowns are optional.

    ``omitted_subtrader_count`` is the number of subtraders omitted from
    ``subtrader_breakdowns`` (their amounts remain in ``user_breakdown``).

    ``group_breakdowns`` / ``omitted_group_count`` cover netted subtrader groups.
    """

    next_runtime: AwareDatetime
    user_breakdown: SettlementEstimate | None = None
    subtrader_breakdowns: dict[str, SettlementEstimate] | None = None
    prev_settlement_prices: dict[str, int] | None = None
    omitted_subtrader_count: int | None = None
    group_breakdowns: dict[str, SettlementEstimate] | None = None
    omitted_group_count: int | None = None

    model_config = {"extra": "allow"}


class GetSettlementEstimateByAssetClassResponse(BaseModel):
    """Spec ``GetSettlementEstimateByAssetClassResponse`` — estimates keyed by asset class.

    ``estimates`` is the spec ``additionalProperties`` map (asset class →
    :class:`AssetClassSettlementEstimate`). Backs
    ``GET /margin/settlement_estimate_by_asset_class``.
    """

    estimates: dict[str, AssetClassSettlementEstimate]
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


# ── Spec sync: margin subtrader groups (perps SCM) ──────────────────────────


class MarginSubtraderGroup(BaseModel):
    """Spec ``MarginSubtraderGroup`` — a netted portfolio of subtraders."""

    group_id: str
    member_subtrader_ids: NullableList[str]

    model_config = {"extra": "allow"}


class GetMarginSubtraderGroupsResponse(BaseModel):
    """Response from GET /fcm/margin/subtrader_groups."""

    groups: NullableList[MarginSubtraderGroup]

    model_config = {"extra": "allow"}


class CreateMarginSubtraderGroupRequest(BaseModel):
    """Body for POST /fcm/margin/subtrader_groups.

    ``subtrader_ids`` must be non-empty; members must not already belong to
    another group. Grouped subtraders are margined as one netted portfolio.
    """

    subtrader_ids: list[str] = Field(min_length=1)

    model_config = {"extra": "forbid"}


class CreateMarginSubtraderGroupResponse(BaseModel):
    """Response from POST /fcm/margin/subtrader_groups."""

    group_id: str

    model_config = {"extra": "allow"}


class UpdateMarginSubtraderGroupRequest(BaseModel):
    """Body for PUT /fcm/margin/subtrader_groups/{group_id}.

    Full replacement membership list (not a patch).
    """

    subtrader_ids: list[str] = Field(min_length=1)

    model_config = {"extra": "forbid"}
