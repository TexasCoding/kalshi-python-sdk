"""Portfolio-related models."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, AwareDatetime, BaseModel, Field, StrictInt

from kalshi.types import DollarDecimal, FixedPointCount, NullableList, UnixSecondsTimestamp

SettlementStatusLiteral = Literal["all", "unsettled", "settled"]
"""Position settlement status filter for GET /fcm/positions. Spec: settlement_status query enum."""


class IndexedBalance(BaseModel):
    """Balance for a single exchange shard. Added by spec v3.18.0 alongside
    the ``balance_breakdown`` field on :class:`Balance`.

    Currently only ``exchange_index=0`` is supported per spec.

    **Type note:** ``balance`` here is ``DollarDecimal`` (fixed-point
    dollar string per spec), unlike :attr:`Balance.balance` which is
    integer cents. Same field name, different semantics — be deliberate
    when reading from ``balance.balance_breakdown[i].balance`` versus
    ``balance.balance``. The :attr:`Balance.balance_dollars` field
    rendered in dollars matches the breakdown's units.
    """

    exchange_index: int
    balance: DollarDecimal

    model_config = {"extra": "allow"}


class Balance(BaseModel):
    """Account balance.

    ``balance`` is integer cents (legacy field). ``balance_dollars`` is the
    same value as a fixed-point dollar string, added by spec v3.18.0 and
    now required on every response. ``balance_breakdown`` (optional) splits
    the total across exchange shards when present.
    """

    balance: int
    balance_dollars: DollarDecimal
    portfolio_value: int
    updated_ts: UnixSecondsTimestamp
    balance_breakdown: list[IndexedBalance] | None = None

    model_config = {"extra": "allow"}


class TotalRestingOrderValue(BaseModel):
    """Total value of resting orders in cents.

    Spec: "intended for use by FCM members (rare)". Non-FCM accounts see
    403 on this endpoint (demo audit 2026-04-18).

    ``resting_order_value_breakdown`` (required as of OpenAPI 3.28.0) splits
    the total across exchange shards. Each :class:`IndexedBalance.balance`
    is a :class:`~kalshi.types.DollarDecimal`, not integer cents.
    """

    total_resting_order_value: int
    resting_order_value_breakdown: list[IndexedBalance]

    model_config = {"extra": "allow"}


class MarketPosition(BaseModel):
    """A position in a single market.

    ``total_traded`` and ``position`` are typed ``DollarDecimal | None`` /
    ``FixedPointCount | None`` without ``default=None`` because the OpenAPI
    spec (``MarketPosition.required``) marks ``total_traded_dollars`` and
    ``position_fp`` as **required** response keys. The ``| None`` admits the
    server's observed ``null`` on flat positions while a missing key still
    raises ValidationError — silent omission is treated as a schema regression,
    not a default.
    """

    ticker: str
    exchange_index: int
    total_traded: DollarDecimal | None = Field(
        validation_alias=AliasChoices("total_traded_dollars", "total_traded"),
    )
    position: FixedPointCount | None = Field(
        validation_alias=AliasChoices("position_fp", "position"),
    )
    market_exposure: DollarDecimal | None = Field(
        validation_alias=AliasChoices("market_exposure_dollars", "market_exposure"),
    )
    realized_pnl: DollarDecimal | None = Field(
        validation_alias=AliasChoices("realized_pnl_dollars", "realized_pnl"),
    )
    # Spec 3.23.0 dropped this field from the MarketPosition schema (previously
    # required). Optional/defensive so a server that stops emitting it does not
    # hard-fail MarketPosition parsing.
    resting_orders_count: int | None = None
    fees_paid: DollarDecimal | None = Field(
        validation_alias=AliasChoices("fees_paid_dollars", "fees_paid"),
    )
    last_updated_ts: AwareDatetime

    model_config = {"extra": "allow", "populate_by_name": True}


class EventPosition(BaseModel):
    """A position aggregated at the event level."""

    event_ticker: str
    total_cost: DollarDecimal | None = Field(
        validation_alias=AliasChoices("total_cost_dollars", "total_cost"),
    )
    total_cost_shares: FixedPointCount | None = Field(
        validation_alias=AliasChoices("total_cost_shares_fp", "total_cost_shares"),
    )
    event_exposure: DollarDecimal | None = Field(
        validation_alias=AliasChoices("event_exposure_dollars", "event_exposure"),
    )
    realized_pnl: DollarDecimal | None = Field(
        validation_alias=AliasChoices("realized_pnl_dollars", "realized_pnl"),
    )
    fees_paid: DollarDecimal | None = Field(
        validation_alias=AliasChoices("fees_paid_dollars", "fees_paid"),
    )

    model_config = {"extra": "allow", "populate_by_name": True}


class PositionsResponse(BaseModel):
    """Response from the positions endpoint containing both market and event positions."""

    market_positions: NullableList[MarketPosition]
    event_positions: NullableList[EventPosition]
    cursor: str | None = None

    @property
    def has_next(self) -> bool:
        return bool(self.cursor)

    model_config = {"extra": "allow"}


PaymentStatusLiteral = Literal["pending", "applied", "failed", "returned"]
"""Status of a Deposit/Withdrawal. Spec defines two structurally-identical
inline enums (Deposit.status, Withdrawal.status); the SDK shares one alias
since the values are identical.
"""

PaymentTypeLiteral = Literal["ach", "wire", "crypto", "debit", "apm"]
"""Payment method used for a deposit/withdrawal."""


class Deposit(BaseModel):
    """A single deposit history entry. Amounts are integer cents."""

    id: str
    status: PaymentStatusLiteral
    type: PaymentTypeLiteral
    amount_cents: int
    fee_cents: int
    created_ts: UnixSecondsTimestamp
    finalized_ts: UnixSecondsTimestamp | None = None

    model_config = {"extra": "allow"}


class Withdrawal(BaseModel):
    """A single withdrawal history entry. Amounts are integer cents."""

    id: str
    status: PaymentStatusLiteral
    type: PaymentTypeLiteral
    amount_cents: int
    fee_cents: int
    created_ts: UnixSecondsTimestamp
    finalized_ts: UnixSecondsTimestamp | None = None

    model_config = {"extra": "allow"}


class Settlement(BaseModel):
    """A settled market position."""

    ticker: str
    exchange_index: int
    event_ticker: str
    market_result: str
    yes_count: FixedPointCount | None = Field(
        validation_alias=AliasChoices("yes_count_fp", "yes_count"),
    )
    yes_total_cost: DollarDecimal | None = Field(
        validation_alias=AliasChoices("yes_total_cost_dollars", "yes_total_cost"),
    )
    no_count: FixedPointCount | None = Field(
        validation_alias=AliasChoices("no_count_fp", "no_count"),
    )
    no_total_cost: DollarDecimal | None = Field(
        validation_alias=AliasChoices("no_total_cost_dollars", "no_total_cost"),
    )
    revenue: int
    settled_time: AwareDatetime
    fee_cost: DollarDecimal | None = Field(
        validation_alias=AliasChoices("fee_cost_dollars", "fee_cost"),
    )

    # v3.18.0 backfill (#160). `value` is integer cents per spec
    # ("Payout of a single yes contract in cents") — plain int, NOT DollarDecimal.
    value: int | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


ExchangeInstanceLiteral = Literal["event_contract", "margined"]
"""Exchange instance for intra-exchange fund movement (event vs margined)."""

IntraExchangeInstanceTransferStatusLiteral = Literal["pending", "complete"]
"""Status of an intra-exchange instance transfer."""


class IntraExchangeInstanceTransfer(BaseModel):
    """A single intra-exchange instance transfer history entry.

    Spec ``IntraExchangeInstanceTransfer``. ``amount`` is a fixed-point
    dollar string (``FixedPointDollars``), not centicents — unlike the
    POST request body's integer ``amount`` on
    :class:`~kalshi.perps.models.transfers.IntraExchangeInstanceTransferRequest`.
    """

    transfer_id: str
    source: ExchangeInstanceLiteral
    destination: ExchangeInstanceLiteral
    source_exchange_shard: int
    destination_exchange_shard: int
    amount: DollarDecimal
    status: IntraExchangeInstanceTransferStatusLiteral
    created_ts: int

    model_config = {"extra": "allow"}


class TargetBalanceAllocation(BaseModel):
    """One shard's target share of sweepable balance."""

    exchange_index: StrictInt = Field(ge=0)
    percent: StrictInt = Field(ge=0, le=100)

    model_config = {"extra": "allow"}


class TargetBalanceAllocationInput(BaseModel):
    """Write-side counterpart of :class:`TargetBalanceAllocation`."""

    exchange_index: StrictInt = Field(ge=0)
    percent: StrictInt = Field(ge=0, le=100)

    model_config = {"extra": "forbid"}


class GetTargetBalanceAllocationResponse(BaseModel):
    """Response from GET /portfolio/target_balance_allocation."""

    allocations: list[TargetBalanceAllocation]

    model_config = {"extra": "allow"}


class SetTargetBalanceAllocationRequest(BaseModel):
    """Body for POST /portfolio/target_balance_allocation."""

    allocations: list[TargetBalanceAllocationInput] = Field(max_length=101)

    model_config = {"extra": "forbid"}

