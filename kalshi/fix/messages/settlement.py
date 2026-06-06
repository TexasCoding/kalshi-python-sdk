"""Market-settlement / post-trade FIX messages (GH #429) — prediction only.

A :class:`MarketSettlementReport` (35=UMS) is a read-only settlement notification
streamed on the ``KalshiPT`` session (and on ``KalshiRT`` when
``ReceiveSettlementReports`` is opted in). Per-party collateral changes and fees
are nested inside the ``NoMarketSettlementPartyIDs`` group (the shared
:class:`~kalshi.fix.messages.components.MarketSettlementParty` entry, which itself
nests ``NoCollateralAmountChanges`` and ``NoMiscFees``).

Fields are optional and code fields raw (compare against :mod:`kalshi.fix.enums`)
per the inbound convention. Large settlement batches paginate across several
fragments — correlate them by ``Symbol`` (the report id differs per page) and
reassemble with :class:`~kalshi.fix.settlement.SettlementReassembler`.
"""

from __future__ import annotations

from typing import Annotated

from kalshi.fix.enums import MsgType
from kalshi.fix.messages.base import (
    FixGroupMeta,
    FixMessage,
    FixType,
    fixfield,
    groupfield,
)
from kalshi.fix.messages.components import MarketSettlementParty
from kalshi.fix.tags import Tag
from kalshi.types import DollarDecimal


class MarketSettlementReport(FixMessage):
    """MarketSettlementReport (35=UMS) — a market's settlement detail.

    ``market_result`` is a raw str (compare against
    :class:`~kalshi.fix.enums.MarketResult`). ``settlement_price`` rides the FIX
    ``Price`` field as a no-float ``Decimal`` (``DollarDecimal`` is just the
    coercion type); the value is in *cents*, 2 dp — ``Decimal("100.00")`` is 100c
    (full YES payout) and ``Decimal("30.60")`` a scalar market — not dollars.
    ``clearing_business_date`` is the raw ``YYYYMMDD`` string. ``last_fragment``
    is ``False`` on non-final pages of a paginated batch, ``True`` (or absent) on
    the last.
    """

    MSG_TYPE = MsgType.MARKET_SETTLEMENT_REPORT

    market_settlement_report_id: str | None = fixfield(
        Tag.MARKET_SETTLEMENT_REPORT_ID, FixType.STRING, default=None
    )
    symbol: str | None = fixfield(Tag.SYMBOL, FixType.STRING, default=None)
    clearing_business_date: str | None = fixfield(
        Tag.CLEARING_BUSINESS_DATE, FixType.LOCALMKTDATE, default=None
    )
    tot_num_market_settlement_reports: int | None = fixfield(
        Tag.TOT_NUM_MARKET_SETTLEMENT_REPORTS, FixType.INT, default=None
    )
    market_result: str | None = fixfield(Tag.MARKET_RESULT, FixType.STRING, default=None)
    settlement_price: DollarDecimal | None = fixfield(
        Tag.SETTLEMENT_PRICE, FixType.PRICE, default=None
    )
    last_fragment: bool | None = fixfield(Tag.LAST_FRAGMENT, FixType.BOOLEAN, default=None)
    parties: Annotated[
        list[MarketSettlementParty],
        FixGroupMeta(Tag.NO_MARKET_SETTLEMENT_PARTY_IDS, MarketSettlementParty),
    ] = groupfield()
