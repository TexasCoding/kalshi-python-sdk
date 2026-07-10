"""Subaccount models — multi-account workflows under one authenticated user."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from kalshi.types import DollarDecimal, OrderPrice, StrictInt


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


class ApplySubaccountPositionTransferRequest(BaseModel):
    """Body for POST /portfolio/subaccounts/positions/transfer (spec v3.24.0).

    Moves an open **position** (contracts) between subaccounts — distinct from
    the cash-only :class:`ApplySubaccountTransferRequest`. ``price`` is the
    per-contract price in **fixed-point dollars** (``0``-``1.0``) used to set the
    cost basis on the destination subaccount; ``count`` is the number of contracts
    and must be positive. ``from_subaccount`` / ``to_subaccount`` use ``0`` for the
    primary account; the SDK enforces only the lower bound (``ge=0``), leaving the
    upper bound to the server (mirrors :class:`ApplySubaccountTransferRequest`).

    Spec v3.24.0 renamed ``price_cents`` (integer cents) → ``price``
    (``FixedPointDollars``); pass a ``Decimal`` in dollars, e.g. ``Decimal("0.50")``
    for a 50¢ cost basis. Uses :data:`~kalshi.types.OrderPrice` so a negative or
    sub-$0.0001-tick value fails at construction rather than as a server 400.
    """

    client_transfer_id: UUID
    from_subaccount: StrictInt = Field(ge=0)
    to_subaccount: StrictInt = Field(ge=0)
    market_ticker: str
    side: Literal["yes", "no"]
    count: StrictInt = Field(gt=0)
    price: OrderPrice

    model_config = {"extra": "forbid"}


class ApplySubaccountPositionTransferResponse(BaseModel):
    """Response from POST /portfolio/subaccounts/positions/transfer (spec v3.23.0).

    ``position_transfer_id`` is the server-generated identifier for the applied
    position transfer.
    """

    position_transfer_id: str

    model_config = {"extra": "allow"}


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

    Spec v3.23.0 split transfers into two kinds via ``transfer_type``: ``cash``
    (money moved; ``amount_cents`` set) and ``position`` (contracts moved). The
    ``market_ticker`` / ``side`` / ``count`` / ``price`` fields are populated only
    for ``position`` transfers, so they are optional here. Spec v3.24.0 renamed the
    per-contract ``price_cents`` (integer cents) → ``price``
    (``FixedPointDollars``), surfacing as a ``Decimal`` in dollars.
    """

    transfer_id: str
    from_subaccount: int
    to_subaccount: int
    amount_cents: int
    created_ts: int
    # Spec v3.23.0 required additions.
    exchange_index: int
    transfer_type: Literal["cash", "position"]
    # Position-transfer-only fields (absent on cash transfers).
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
