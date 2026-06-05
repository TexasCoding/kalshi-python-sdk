"""Perps (margin) transfers & subaccounts models (#396).

Request/response bodies for the three ``/portfolio/*`` perps fund-movement
endpoints: intra-exchange-instance transfer, create margin subaccount, and
transfer between margin subaccounts.

**Units note:** unlike most of the SDK, none of these bodies use
``DollarDecimal``/``FixedPointCount``. Per spec the transfer amounts are plain
integers — ``IntraExchangeInstanceTransferRequest.amount`` is **centicents**
and ``ApplySubaccountTransferRequest.amount_cents`` is **cents**
(both ``integer``/``int64``). Introducing ``DollarDecimal`` here would be a
wire mismatch. ``StrictInt`` (rejects ``bool``) is used on the request bodies,
matching the event-contract ``ApplySubaccountTransferRequest``.

These FQNs are intentionally distinct from the event-contract
``kalshi.models.subaccounts.*`` models even though two schema names collide
(``CreateSubaccountResponse``, ``ApplySubaccountTransferRequest``) — they target
the perps spec/host and are not re-exports.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from kalshi.types import StrictInt

# Spec ``ExchangeInstance`` (string enum) — modeled as a Literal alias, mirroring
# the ``SettlementStatusLiteral`` pattern in kalshi.models.portfolio. The full
# StrEnum (kalshi.perps.models.common.ExchangeInstance) is the runtime enum; this
# alias is what the request-body fields below are annotated with.
ExchangeInstanceLiteral = Literal["event_contract", "margined"]
"""Spec ``ExchangeInstance`` — ``event_contract`` or ``margined``."""


class IntraExchangeInstanceTransferRequest(BaseModel):
    """Body for ``POST /portfolio/intra_exchange_instance_transfer``.

    Moves funds between the ``event_contract`` and ``margined`` exchange
    instances. ``amount`` is **centicents** (integer, ``int64``) — not dollars.
    Shard fields default to ``0`` (only ``0`` is currently supported); because
    the body is serialized with ``exclude_none=True`` (not ``exclude_defaults``),
    shard ``0`` values are emitted on the wire, which is fine.
    """

    source: ExchangeInstanceLiteral
    destination: ExchangeInstanceLiteral
    amount: StrictInt = Field(gt=0)
    source_exchange_shard: StrictInt = Field(default=0, ge=0)
    destination_exchange_shard: StrictInt = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}


class ApplySubaccountTransferRequest(BaseModel):
    """Body for ``POST /portfolio/margin/subaccounts/transfer``.

    Mirrors the event-contract
    :class:`kalshi.models.subaccounts.ApplySubaccountTransferRequest` exactly.
    ``amount_cents`` is integer **cents** (``int64``); pass ``500`` for $5.00,
    never a Decimal. ``from_subaccount``/``to_subaccount`` use ``0`` for the
    primary account and a positive integer for numbered subaccounts. Spec prose
    says ``1-32`` but defines no JSON-schema maximum, so only the lower bound is
    validated (``ge=0``) — server-assigned numbers always round-trip.
    """

    client_transfer_id: UUID
    from_subaccount: StrictInt = Field(ge=0)
    to_subaccount: StrictInt = Field(ge=0)
    amount_cents: StrictInt = Field(gt=0)

    model_config = {"extra": "forbid"}


class IntraExchangeInstanceTransferResponse(BaseModel):
    """Response from ``POST /portfolio/intra_exchange_instance_transfer``."""

    transfer_id: str

    model_config = {"extra": "allow"}


class CreateSubaccountResponse(BaseModel):
    """Response from ``POST /portfolio/margin/subaccounts`` — the new number.

    Distinct from the event-contract
    :class:`kalshi.models.subaccounts.CreateSubaccountResponse`.
    """

    subaccount_number: int

    model_config = {"extra": "allow"}
