"""Pydantic models for the Kalshi Klear (SCM) API."""

from __future__ import annotations

from kalshi.perps.klear.models.common import Error
from kalshi.perps.klear.models.margin import (
    GetActiveMarginObligationResponse,
    GetGuarantyFundBalanceResponse,
    GetMarginReportsResponse,
    GetObligationHistoryResponse,
    GetSettlementBalanceHistoryResponse,
    GetSettlementBalanceResponse,
    GetSettlementBalanceWithdrawalResponse,
    GetSettlementEstimateResponse,
    MaintenanceMarginDetail,
    MarginReport,
    MarginReportTypeLiteral,
    ObligationEntry,
    ObligationReceiveInfo,
    SettlementBalanceHistoryEntry,
    SettlementDetail,
    SettlementEstimate,
    WithdrawalStatusLiteral,
    WithdrawSettlementBalanceRequest,
    WithdrawSettlementBalanceResponse,
)

__all__ = [
    "Error",
    "GetActiveMarginObligationResponse",
    "GetGuarantyFundBalanceResponse",
    "GetMarginReportsResponse",
    "GetObligationHistoryResponse",
    "GetSettlementBalanceHistoryResponse",
    "GetSettlementBalanceResponse",
    "GetSettlementBalanceWithdrawalResponse",
    "GetSettlementEstimateResponse",
    "MaintenanceMarginDetail",
    "MarginReport",
    "MarginReportTypeLiteral",
    "ObligationEntry",
    "ObligationReceiveInfo",
    "SettlementBalanceHistoryEntry",
    "SettlementDetail",
    "SettlementEstimate",
    "WithdrawSettlementBalanceRequest",
    "WithdrawSettlementBalanceResponse",
    "WithdrawalStatusLiteral",
]
