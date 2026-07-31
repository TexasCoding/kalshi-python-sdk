"""Subaccount models — multi-account workflows under one authenticated user."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from kalshi.types import DollarDecimal, StrictInt


class CreateSubaccountRequest(BaseModel):
    """Body for POST /portfolio/subaccounts (spec v3.23.0).

    Every field is optional — an empty body spins up the next subaccount on
    exchange shard ``0``. ``exchange_index`` targets a specific shard (spec
    ``ExchangeIndex``, integer; "defaults to 0 if unspecified", and only ``0``
    is currently supported). The SDK validates only the lower bound (``ge=0``),
    leaving the upper bound to the server.
    """

    exchange_index: StrictInt | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


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
    # Spec v3.23.0: exchange shard to apply the transfer on (spec ExchangeIndex,
    # integer). Optional — "defaults to 0 if unspecified" per spec, and only 0
    # is currently supported, so callers rarely set it.
    exchange_index: StrictInt | None = Field(default=None, ge=0)

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
    """A past **cash** transfer between subaccounts.

    ``created_ts`` is a Unix seconds integer per spec (``format: int64``),
    matching ``SubaccountBalance.updated_ts``. This is intentionally
    different from RFQ/Quote timestamps, which are ISO datetime strings.

    Spec sync (in-place edit under OpenAPI 3.25.0, 2026-07-20/21) narrowed
    ``GET /portfolio/subaccounts/transfers`` to cash rows only. Upstream
    dropped ``transfer_type`` and the position-only fields
    (``market_ticker`` / ``side`` / ``count`` / ``price``) from this schema.
    Spec 3.27.0 later removed ``POST /portfolio/subaccounts/positions/transfer``
    entirely. Fields removed from the wire schema are retained as optional
    (defensive optional-ization) so payloads from lagging servers still parse;
    new responses omit them.
    """

    transfer_id: str
    from_subaccount: int
    to_subaccount: int
    amount_cents: int
    created_ts: int
    exchange_index: int
    # Soft-kept after upstream removal from SubaccountTransfer (cash-only list).
    transfer_type: Literal["cash", "position"] | None = None
    market_ticker: str | None = None
    side: Literal["yes", "no"] | None = None
    count: int | None = None
    price: DollarDecimal | None = None

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
    # Spec v3.24.0: exchange index of the subaccount (required).
    exchange_index: int

    model_config = {"extra": "allow"}


class GetSubaccountNettingResponse(BaseModel):
    """Response from GET /portfolio/subaccounts/netting."""

    netting_configs: list[SubaccountNettingConfig]

    model_config = {"extra": "allow"}
