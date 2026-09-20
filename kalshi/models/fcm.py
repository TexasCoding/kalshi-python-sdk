"""FCM (Futures Commission Merchant) models — subtraders, category blocks, daily caps."""

from __future__ import annotations

from pydantic import BaseModel, Field

from kalshi.types import DollarDecimal


class CreateFCMSubtraderRequest(BaseModel):
    """Body for POST /fcm/subtraders.

    ``subtrader_suffix`` is 1-16 case-sensitive ASCII alphanumeric characters.
    The full id is composed server-side as ``{account_id}_{suffix}``.
    """

    subtrader_suffix: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9]{1,16}$")

    model_config = {"extra": "forbid"}


class CreateFCMSubtraderResponse(BaseModel):
    """Response from POST /fcm/subtraders."""

    subtrader_id: str

    model_config = {"extra": "allow"}


class FCMSubtrader(BaseModel):
    """One FCM-owned subtrader from GET /fcm/subtraders."""

    subtrader_id: str
    exchange_indices: list[int]
    trading_blocked: bool
    fcm_trading_blocked: bool
    propagation_pending: bool

    model_config = {"extra": "allow"}


class ListFCMSubtradersResponse(BaseModel):
    """Response from GET /fcm/subtraders."""

    subtraders: list[FCMSubtrader]

    model_config = {"extra": "allow"}


class GetFCMSubtraderBlockedCategoriesResponse(BaseModel):
    """Response from GET /fcm/subtraders/blocked_categories."""

    categories: list[str]

    model_config = {"extra": "allow"}


class UpdateFCMSubtraderBlockedCategoriesRequest(BaseModel):
    """Body for PUT /fcm/subtraders/blocked_categories."""

    subtrader_id: str
    category: str = Field(min_length=1, max_length=100)
    blocked: bool

    model_config = {"extra": "forbid"}


class UpdateFCMSubtraderBlockedCategoriesResponse(BaseModel):
    """Response from PUT /fcm/subtraders/blocked_categories."""

    categories: list[str]

    model_config = {"extra": "allow"}


class GetFCMEventContractDailyCapResponse(BaseModel):
    """Response from GET /fcm/subtraders/event_contract_daily_cap."""

    subtrader_id: str
    limit: DollarDecimal
    executed_utilization: DollarDecimal
    resting_order_utilization: DollarDecimal
    pending_order_utilization: DollarDecimal
    cap_date: str

    model_config = {"extra": "allow"}


class UpdateFCMEventContractDailyCapRequest(BaseModel):
    """Body for PUT /fcm/subtraders/event_contract_daily_cap."""

    subtrader_id: str
    limit: DollarDecimal

    model_config = {"extra": "forbid"}
