"""Subaccount models — multi-account workflows under one authenticated user."""

from __future__ import annotations

from pydantic import BaseModel, Field

from kalshi.types import DollarDecimal


class CreateSubaccountResponse(BaseModel):
    """Response from POST /portfolio/subaccounts — the new subaccount number."""

    subaccount_number: int

    model_config = {"extra": "allow"}


class ApplySubaccountTransferRequest(BaseModel):
    """Body for POST /portfolio/subaccounts/transfer.

    ``amount_cents`` is integer cents per spec (matches the ``buy_max_cost``
    convention on ``CreateOrderRequest``). Pass ``500`` for $5.00, never
    a Decimal. ``from_subaccount`` and ``to_subaccount`` use ``0`` for
    the primary account and ``1-32`` for numbered subaccounts.
    """

    client_transfer_id: str
    from_subaccount: int = Field(ge=0)
    to_subaccount: int = Field(ge=0)
    amount_cents: int = Field(ge=0)

    model_config = {"extra": "forbid"}


class SubaccountBalance(BaseModel):
    """Balance for a single subaccount."""

    subaccount_number: int
    balance: DollarDecimal
    updated_ts: int

    model_config = {"extra": "allow"}


class GetSubaccountBalancesResponse(BaseModel):
    """Response from GET /portfolio/subaccounts/balances."""

    subaccount_balances: list[SubaccountBalance]

    model_config = {"extra": "allow"}


class SubaccountTransfer(BaseModel):
    """A past transfer between subaccounts."""

    transfer_id: str
    from_subaccount: int
    to_subaccount: int
    amount_cents: int
    created_ts: int

    model_config = {"extra": "allow"}


class UpdateSubaccountNettingRequest(BaseModel):
    """Body for PUT /portfolio/subaccounts/netting."""

    subaccount_number: int = Field(ge=0)
    enabled: bool

    model_config = {"extra": "forbid"}


class SubaccountNettingConfig(BaseModel):
    """Netting state for a single subaccount."""

    subaccount_number: int
    enabled: bool

    model_config = {"extra": "allow"}


class GetSubaccountNettingResponse(BaseModel):
    """Response from GET /portfolio/subaccounts/netting."""

    netting_configs: list[SubaccountNettingConfig]

    model_config = {"extra": "allow"}
