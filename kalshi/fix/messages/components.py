"""Repeating-group entry models shared across FIX message flows (GH #423).

Each class is one entry of a FIX repeating group. Messages embed them via
``Annotated[list[Entry], FixGroupMeta(NumInGroupTag, Entry)] = groupfield()``.
Prices/amounts use :data:`~kalshi.types.DollarDecimal` and quantities
:data:`~kalshi.types.FixedPointCount` so values coerce to ``Decimal`` without
float drift (the SDK money-precision invariant). The order-entry, market-data,
and settlement phases reuse these.
"""

from __future__ import annotations

from typing import Annotated

from kalshi.fix.messages.base import FixGroup, FixGroupMeta, FixType, fixfield, groupfield
from kalshi.fix.tags import Tag
from kalshi.types import DollarDecimal, FixedPointCount


class Party(FixGroup):
    """One ``NoPartyIDs`` (453) entry — delimiter ``PartyID`` (448)."""

    party_id: str = fixfield(Tag.PARTY_ID, FixType.STRING)
    party_role: int | None = fixfield(Tag.PARTY_ROLE, FixType.INT, default=None)


class MiscFee(FixGroup):
    """One ``NoMiscFees`` (136) entry — delimiter ``MiscFeeAmt`` (137)."""

    misc_fee_amt: DollarDecimal = fixfield(Tag.MISC_FEE_AMT, FixType.AMT)
    misc_fee_curr: str = fixfield(Tag.MISC_FEE_CURR, FixType.CURRENCY)
    misc_fee_type: str = fixfield(Tag.MISC_FEE_TYPE, FixType.CHAR)
    misc_fee_basis: int | None = fixfield(Tag.MISC_FEE_BASIS, FixType.INT, default=None)


class CollateralAmountChange(FixGroup):
    """One ``NoCollateralAmountChanges`` (1703) entry — delimiter (1704)."""

    collateral_amount_change: DollarDecimal = fixfield(Tag.COLLATERAL_AMOUNT_CHANGE, FixType.AMT)
    collateral_amount_type: str = fixfield(Tag.COLLATERAL_AMOUNT_TYPE, FixType.STRING)


class MultivariateSelectedLeg(FixGroup):
    """One ``NoMultivariateSelectedLegs`` (20181) entry — delimiter (20182)."""

    event_ticker: str = fixfield(Tag.MULTIVARIATE_SELECTED_EVENT_TICKER, FixType.STRING)
    market_ticker: str = fixfield(Tag.MULTIVARIATE_SELECTED_MARKET_TICKER, FixType.STRING)
    side: str = fixfield(Tag.MULTIVARIATE_SELECTED_SIDE, FixType.STRING)


class MarketSettlementParty(FixGroup):
    """One ``NoMarketSettlementPartyIDs`` (20108) entry — delimiter (20109).

    Nests ``NoCollateralAmountChanges`` (1703) and ``NoMiscFees`` (136).
    """

    party_id: str = fixfield(Tag.MARKET_SETTLEMENT_PARTY_ID, FixType.STRING)
    party_role: int | None = fixfield(Tag.MARKET_SETTLEMENT_PARTY_ROLE, FixType.INT, default=None)
    long_qty: FixedPointCount | None = fixfield(Tag.LONG_QTY, FixType.QTY, default=None)
    short_qty: FixedPointCount | None = fixfield(Tag.SHORT_QTY, FixType.QTY, default=None)
    collateral_amount_changes: Annotated[
        list[CollateralAmountChange],
        FixGroupMeta(Tag.NO_COLLATERAL_AMOUNT_CHANGES, CollateralAmountChange),
    ] = groupfield()
    misc_fees: Annotated[
        list[MiscFee], FixGroupMeta(Tag.NO_MISC_FEES, MiscFee)
    ] = groupfield()
