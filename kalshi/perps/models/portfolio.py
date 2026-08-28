"""Perps (margin) portfolio models — positions, fills, trades (#393).

Response models for the three margin portfolio/market read endpoints:
``GET /margin/positions``, ``GET /margin/fills``, ``GET /margin/trades``.

All models use ``model_config = {"extra": "allow"}`` to tolerate additive
spec fields, matching the prediction-API portfolio models.

**Wire-name note:** unlike the v2 ``MarketPosition`` (which uses ``position_fp`` /
``*_dollars`` wire keys), the perps spec names these keys plainly
(``position``, ``entry_price``, ``unrealized_pnl``, …) and types them via
``$ref: FixedPointCount`` / ``$ref: FixedPointDollars``. So the count/dollar
fields are **plain fields with no ``AliasChoices``**. The only aliased field is
``roe`` → :attr:`MarginPosition.return_on_equity`.

**Timestamp note:** every timestamp here is RFC3339 (``format: date-time``) and
uses :class:`pydantic.AwareDatetime` — there are no ``_ms`` epoch-millisecond
fields in this issue (that convention applies only to perps WebSocket payloads).
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, AwareDatetime, BaseModel, Field

from kalshi.types import (
    DollarDecimal,
    FixedPointCount,
    MultiplierDecimal,
    NullableList,
)

# Spec ``BookSide`` is ``enum: [bid, ask]`` — surfaced as a Literal alias
# (mirroring ``SettlementStatusLiteral`` in kalshi/models/portfolio.py).
BookSideLiteral = Literal["bid", "ask"]
"""Spec ``BookSide`` — the side of an order or trade (``bid``/``ask``)."""

# Spec ``OrderSource`` is ``enum: [user, system]``; ``system`` = liquidation order.
OrderSourceLiteral = Literal["user", "system"]
"""Spec ``OrderSource`` — ``user`` (user-placed) or ``system`` (liquidation)."""


class MarginPosition(BaseModel):
    """Spec ``MarginPosition`` — an open margin position in a single market.

    All ``required`` keys are non-nullable except ``roe`` (spec
    ``nullable: true``; null when ``margin_used`` is zero). The dollar/count
    fields are plain — the perps spec names them without ``_dollars``/``_fp``
    suffixes — so no ``AliasChoices`` are used. Only ``roe`` is renamed, to the
    friendlier :attr:`return_on_equity`.
    """

    subaccount: int
    market_ticker: str
    position: FixedPointCount
    entry_price: DollarDecimal
    unrealized_pnl: DollarDecimal
    # Spec 3.23.0 relaxed margin_used from required to optional (still a property).
    # Optional/defensive so a response omitting it does not hard-fail parsing.
    margin_used: DollarDecimal | None = None
    fees: DollarDecimal
    return_on_equity: MultiplierDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("roe", "return_on_equity"),
    )
    # Spec v3.23.0 (required): True when the position is hedged within a
    # portfolio, so its margin is computed at the portfolio level.
    is_portfolio: bool

    model_config = {"extra": "allow", "populate_by_name": True}


class GetMarginPositionsResponse(BaseModel):
    """Spec ``GetMarginPositionsResponse`` — single-page positions array.

    No ``cursor`` field; this endpoint is not paginated.
    """

    positions: NullableList[MarginPosition]

    model_config = {"extra": "allow"}


class MarginFill(BaseModel):
    """Spec ``MarginFill`` — a single margin fill for the authenticated user."""

    fill_id: str
    order_id: str
    is_taker: bool
    side: BookSideLiteral
    count: FixedPointCount
    created_time: AwareDatetime
    ticker: str
    price: DollarDecimal
    entry_price: DollarDecimal
    fees: DollarDecimal
    realized_pnl: DollarDecimal
    order_source: OrderSourceLiteral | None = None

    model_config = {"extra": "allow"}


class GetMarginFillsResponse(BaseModel):
    """Spec ``GetMarginFillsResponse`` — cursor-paginated fills page."""

    fills: NullableList[MarginFill]
    cursor: str | None = None

    @property
    def has_next(self) -> bool:
        return bool(self.cursor)

    model_config = {"extra": "allow"}


class MarginTrade(BaseModel):
    """Spec ``MarginTrade`` — a public margin trade for a ticker."""

    trade_id: str
    ticker: str
    count: FixedPointCount
    price: DollarDecimal
    created_time: AwareDatetime
    taker_side: BookSideLiteral

    model_config = {"extra": "allow"}


class GetMarginTradesResponse(BaseModel):
    """Spec ``GetMarginTradesResponse`` — cursor-paginated trades page."""

    trades: NullableList[MarginTrade]
    cursor: str | None = None

    @property
    def has_next(self) -> bool:
        return bool(self.cursor)

    model_config = {"extra": "allow"}


ExitTriggerKindLiteral = Literal["bracket", "trailing"]
"""Trigger family: stop-loss/take-profit pair, or a trailing stop."""

ExitTriggerStatusLiteral = Literal[
    "pending_on_entry",
    "active",
    "filled",
    "failed",
    "canceled",
    "unknown",
]
"""Lifecycle of a live exit trigger."""

ExitTriggerReasonLiteral = Literal[
    "user_canceled",
    "position_closed",
    "entry_not_filled",
    "order_rejected",
    "position_flipped",
]
"""Why a trigger reached a terminal status."""

ExitTriggerLegLiteral = Literal["stop_loss", "take_profit"]
"""Which bracket leg fired."""


class ExitTrigger(BaseModel):
    """A live stop-loss / take-profit / trailing-stop on a margin position."""

    id: str
    ticker: str
    kind: ExitTriggerKindLiteral
    status: ExitTriggerStatusLiteral
    count: FixedPointCount
    filled_count: FixedPointCount
    created_time: AwareDatetime
    updated_time: AwareDatetime
    status_reason: ExitTriggerReasonLiteral | None = None
    triggered_leg: ExitTriggerLegLiteral | None = None
    triggered_order_id: str | None = None
    anchor_order_id: str | None = None
    client_trigger_id: str | None = None
    stop_loss_price: DollarDecimal | None = None
    take_profit_price: DollarDecimal | None = None
    trail_amount: DollarDecimal | None = None
    trail_bps: int | None = None
    watermark_price: DollarDecimal | None = None
    effective_stop_price: DollarDecimal | None = None

    model_config = {"extra": "allow"}


class GetExitTriggersResponse(BaseModel):
    """Response from GET .../positions/{ticker}/exit_trigger."""

    exit_triggers: list[ExitTrigger]

    model_config = {"extra": "allow"}


class SetCrossExitTriggerRequest(BaseModel):
    """Body for PUT /margin/cross/positions/{ticker}/exit_trigger."""

    count: FixedPointCount | None = None
    anchor_order_id: str | None = None
    client_trigger_id: str | None = None
    kind: ExitTriggerKindLiteral | None = None
    stop_loss_price: DollarDecimal | None = None
    take_profit_price: DollarDecimal | None = None
    trail_amount: DollarDecimal | None = None
    trail_bps: int | None = Field(default=None, ge=1, le=9999)

    model_config = {"extra": "forbid"}


class SetIsolatedExitTriggerRequest(BaseModel):
    """Body for PUT /margin/isolated/positions/{ticker}/exit_trigger."""

    kind: ExitTriggerKindLiteral | None = None
    stop_loss_price: DollarDecimal | None = None
    take_profit_price: DollarDecimal | None = None
    trail_amount: DollarDecimal | None = None
    trail_bps: int | None = Field(default=None, ge=1, le=9999)

    model_config = {"extra": "forbid"}


class UpdateExitTriggerRequest(BaseModel):
    """Body for PUT /margin/cross/positions/{ticker}/exit_trigger/{trigger_id}."""

    stop_loss_price: DollarDecimal | None = None
    take_profit_price: DollarDecimal | None = None

    model_config = {"extra": "forbid"}
