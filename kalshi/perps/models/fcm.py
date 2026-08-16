"""Perps FCM (futures commission merchant) models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from kalshi.types import DollarDecimal, OrderPrice


class CreateMarginFCMSubtraderRequest(BaseModel):
    """Body for POST /margin/fcm/subtraders.

    ``subtrader_suffix`` is the client-chosen suffix; the server composes the
    full id as ``{user_id}_{subtrader_suffix}``. Spec pattern: 1-16 lowercase
    alphanumeric characters.
    """

    subtrader_suffix: str = Field(min_length=1, max_length=16, pattern=r"^[a-z0-9]{1,16}$")

    model_config = {"extra": "forbid"}


class CreateMarginFCMSubtraderResponse(BaseModel):
    """Response from POST /margin/fcm/subtraders."""

    subtrader_id: str

    model_config = {"extra": "allow"}


class FCMSubtraderRiskControls(BaseModel):
    """One initial-margin cap for an FCM subtrader.

    A missing ``market_ticker`` means the cap applies across all markets.
    """

    subtrader_id: str
    im_cap: DollarDecimal
    market_ticker: str | None = None

    model_config = {"extra": "allow"}


class GetFCMSubtraderRiskControlsResponse(BaseModel):
    """Response from GET /margin/fcm/subtraders/risk_controls."""

    risk_controls: list[FCMSubtraderRiskControls]

    model_config = {"extra": "allow"}


class UpdateFCMSubtraderRiskControlsRequest(BaseModel):
    """Body for PUT /margin/fcm/subtraders/risk_controls.

    ``im_cap`` is a non-negative fixed-point dollar amount (max 4 decimals).
    """

    subtrader_id: str
    im_cap: OrderPrice
    market_ticker: str | None = None

    model_config = {"extra": "forbid"}
