"""Subaccount models — multi-account workflows under one authenticated user."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from kalshi.types import DollarDecimal, StrictInt


class CreateSubaccountResponse(BaseModel):
    """Response from POST /portfolio/subaccounts — the new subaccount number."""

    subaccount_number: int

    model_config = {"extra": "allow"}


class ApplySubaccountTransferRequest(BaseModel):
    """Body for POST /portfolio/subaccounts/transfer.

    ``amount_cents`` is integer cents per spec (e.g. ``500`` for $5.00, never
    a Decimal). ``from_subaccount`` / ``to_subaccount`` use ``0`` for the
    primary account and a positive integer for numbered subaccounts. The
    server is the source of truth for the upper bound: spec describes
    ``1-63`` in prose but defines no JSON-schema maximum, and demo has
    been observed allocating values above 32. The SDK validates only the
    lower bound (``ge=0``) so server-assigned numbers always round-trip.
    """

    client_transfer_id: UUID
    from_subaccount: StrictInt = Field(ge=0)
    to_subaccount: StrictInt = Field(ge=0)
    amount_cents: StrictInt = Field(gt=0)

    model_config = {"extra": "forbid"}


class SubaccountBalance(BaseModel):
    """Balance for a single subaccount.

    Note: ``updated_ts`` is a Unix seconds integer per spec
    (``format: int64``), not an ISO datetime. RFQ/Quote timestamps are
    ``format: date-time`` and surface as ``datetime``; subaccount
    timestamps follow the spec's int wire format. Callers wanting a
    ``datetime`` can ``datetime.fromtimestamp(obj.updated_ts, tz=timezone.utc)``.
    """

    subaccount_number: int
    # Spec v3.22.0: exchange shard the balance is held on (required).
    exchange_index: int
    balance: DollarDecimal
    updated_ts: int

    model_config = {"extra": "allow"}


class GetSubaccountBalancesResponse(BaseModel):
    """Response from GET /portfolio/subaccounts/balances."""

    subaccount_balances: list[SubaccountBalance]

    model_config = {"extra": "allow"}


class SubaccountTransfer(BaseModel):
    """A past transfer between subaccounts.

    ``created_ts`` is a Unix seconds integer per spec (``format: int64``),
    matching ``SubaccountBalance.updated_ts``. This is intentionally
    different from RFQ/Quote timestamps, which are ISO datetime strings.
    """

    transfer_id: str
    from_subaccount: int
    to_subaccount: int
    amount_cents: int
    created_ts: int

    model_config = {"extra": "allow"}


class UpdateSubaccountNettingRequest(BaseModel):
    """Body for PUT /portfolio/subaccounts/netting."""

    subaccount_number: StrictInt = Field(ge=0)
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
