"""RFQ / quoting FIX messages (GH #428) — prediction only.

Request-for-quote spans two roles on different sessions: an **RFQ creator**
(KalshiRT) solicits and accepts quotes, and a **market maker** (KalshiRFQ)
answers them. ``QuoteRequest`` (35=R) and ``Quote`` (35=S) are bidirectional;
the rest are one-directional.

Outbound (typed; build via the helpers, which enforce per-role required fields):
:class:`QuoteRequest` (R, creator create), :class:`Quote` (S, maker submit),
:class:`QuoteCancel` (Z), :class:`QuoteConfirm` (U7), :class:`AcceptQuote` (UA),
:class:`RFQCancel` (UE). Inbound (fields optional, codes raw — compare against
:mod:`kalshi.fix.enums`): :class:`QuoteRequestAck` (b), :class:`QuoteStatusReport`
(AI), :class:`QuoteRequestReject` (AG), :class:`QuoteConfirmStatus` (U8),
:class:`QuoteCancelStatus` (U9), :class:`RFQCancelStatus` (UB),
:class:`AcceptQuoteStatus` (UC). The bidirectional R/S also decode inbound.

Prices (``BidPx``/``OfferPx``) ride the FIX ``Price`` field; units follow the
session like order entry — integer cents on prediction, fixed-point dollars under
``UseDollars`` — so :data:`~kalshi.types.DollarDecimal` parses either.
"""

from __future__ import annotations

from typing import Annotated

from kalshi.fix.enums import MsgType, Side
from kalshi.fix.messages.base import (
    FixGroupMeta,
    FixMessage,
    FixType,
    fixfield,
    groupfield,
)
from kalshi.fix.messages.components import MultivariateSelectedLeg, Party
from kalshi.fix.tags import Tag
from kalshi.types import DollarDecimal, FixedPointCount

# ---------------------------------------------------------------------------
# Bidirectional (created outbound via helpers; also decoded inbound)
# ---------------------------------------------------------------------------


class QuoteRequest(FixMessage):
    """QuoteRequest (35=R) — create an RFQ (creator) / RFQ notification (maker).

    Fields are optional so the inbound notification parses robustly; use
    :meth:`create` to build a well-formed outbound RFQ. ``NoRelatedSym`` is always
    1 (single market); ``Symbol`` xor the MVE collection+legs identify the market,
    and ``OrderQty`` xor ``CashOrderQty`` size it.
    """

    MSG_TYPE = MsgType.QUOTE_REQUEST

    quote_req_id: str | None = fixfield(Tag.QUOTE_REQ_ID, FixType.STRING, default=None)
    no_related_sym: int | None = fixfield(Tag.NO_RELATED_SYM, FixType.NUMINGROUP, default=None)
    symbol: str | None = fixfield(Tag.SYMBOL, FixType.STRING, default=None)
    order_qty: FixedPointCount | None = fixfield(Tag.ORDER_QTY, FixType.QTY, default=None)
    cash_order_qty: DollarDecimal | None = fixfield(Tag.CASH_ORDER_QTY, FixType.AMT, default=None)
    parties: Annotated[list[Party], FixGroupMeta(Tag.NO_PARTY_IDS, Party)] = groupfield()
    rest_remainder: bool | None = fixfield(Tag.REST_REMAINDER, FixType.BOOLEAN, default=None)
    replace_existing: bool | None = fixfield(Tag.REPLACE_EXISTING, FixType.BOOLEAN, default=None)
    multivariate_collection_ticker: str | None = fixfield(
        Tag.MULTIVARIATE_COLLECTION_TICKER, FixType.STRING, default=None
    )
    multivariate_selected_legs: Annotated[
        list[MultivariateSelectedLeg],
        FixGroupMeta(Tag.NO_MULTIVARIATE_SELECTED_LEGS, MultivariateSelectedLeg),
    ] = groupfield()
    alloc_account: int | None = fixfield(Tag.ALLOC_ACCOUNT, FixType.INT, default=None)

    @classmethod
    def create(
        cls,
        quote_req_id: str,
        symbol: str,
        *,
        order_qty: FixedPointCount | None = None,
        cash_order_qty: DollarDecimal | None = None,
        alloc_account: int | None = None,
        rest_remainder: bool | None = None,
        replace_existing: bool | None = None,
    ) -> QuoteRequest:
        """Create a single-market RFQ for ``symbol``.

        Requires at least one of ``order_qty`` / ``cash_order_qty`` to size it.
        MVE/parlay RFQs (collection ticker + legs instead of a symbol) construct
        :class:`QuoteRequest` directly.
        """
        if order_qty is None and cash_order_qty is None:
            raise ValueError("QuoteRequest.create requires order_qty or cash_order_qty")
        return cls(
            quote_req_id=quote_req_id,
            no_related_sym=1,
            symbol=symbol,
            order_qty=order_qty,
            cash_order_qty=cash_order_qty,
            alloc_account=alloc_account,
            rest_remainder=rest_remainder,
            replace_existing=replace_existing,
        )


class Quote(FixMessage):
    """Quote (35=S) — submit a quote (maker) / quote notification (creator).

    Either ``bid_px`` or ``offer_px`` may be zero, but not both (zero = no quote
    for that side). Use :meth:`submit` for the maker path.
    """

    MSG_TYPE = MsgType.QUOTE

    quote_id: str | None = fixfield(Tag.QUOTE_ID, FixType.STRING, default=None)
    quote_req_id: str | None = fixfield(Tag.QUOTE_REQ_ID, FixType.STRING, default=None)
    symbol: str | None = fixfield(Tag.SYMBOL, FixType.STRING, default=None)
    bid_px: DollarDecimal | None = fixfield(Tag.BID_PX, FixType.PRICE, default=None)
    offer_px: DollarDecimal | None = fixfield(Tag.OFFER_PX, FixType.PRICE, default=None)
    order_qty: FixedPointCount | None = fixfield(Tag.ORDER_QTY, FixType.QTY, default=None)
    bid_size: FixedPointCount | None = fixfield(Tag.BID_SIZE, FixType.QTY, default=None)
    offer_size: FixedPointCount | None = fixfield(Tag.OFFER_SIZE, FixType.QTY, default=None)
    alloc_account: int | None = fixfield(Tag.ALLOC_ACCOUNT, FixType.INT, default=None)
    rest_remainder: bool | None = fixfield(Tag.REST_REMAINDER, FixType.BOOLEAN, default=None)

    @classmethod
    def submit(
        cls,
        quote_id: str,
        quote_req_id: str,
        symbol: str,
        *,
        bid_px: DollarDecimal | None = None,
        offer_px: DollarDecimal | None = None,
        alloc_account: int | None = None,
        rest_remainder: bool | None = None,
    ) -> Quote:
        """Build a maker quote for ``quote_req_id`` on ``symbol``.

        At least one of ``bid_px`` / ``offer_px`` is required (a quote with neither
        side is rejected by the exchange).
        """
        if bid_px is None and offer_px is None:
            raise ValueError("Quote.submit requires at least one of bid_px / offer_px")
        return cls(
            quote_id=quote_id,
            quote_req_id=quote_req_id,
            symbol=symbol,
            bid_px=bid_px,
            offer_px=offer_px,
            alloc_account=alloc_account,
            rest_remainder=rest_remainder,
        )


# ---------------------------------------------------------------------------
# Outbound requests
# ---------------------------------------------------------------------------


class QuoteCancel(FixMessage):
    """QuoteCancel (35=Z) — maker cancels an active quote."""

    MSG_TYPE = MsgType.QUOTE_CANCEL

    quote_id: str = fixfield(Tag.QUOTE_ID, FixType.STRING)


class QuoteConfirm(FixMessage):
    """QuoteConfirm (35=U7) — maker confirms execution after a quote is accepted."""

    MSG_TYPE = MsgType.QUOTE_CONFIRM

    quote_id: str = fixfield(Tag.QUOTE_ID, FixType.STRING)


class AcceptQuote(FixMessage):
    """AcceptQuote (35=UA) — creator accepts a maker's quote.

    NB: ``side`` (tag 54) is *inverted* for AcceptQuote per the Kalshi docs —
    ``Side.BUY_YES`` (1) accepts the maker's **NO** quote and ``Side.SELL_NO`` (2)
    accepts the maker's **YES** quote (the field reuses the shared FIX Side, so the
    enum member names read opposite to the accept semantics).
    """

    MSG_TYPE = MsgType.ACCEPT_QUOTE

    quote_id: str = fixfield(Tag.QUOTE_ID, FixType.STRING)
    side: Side = fixfield(Tag.SIDE, FixType.CHAR)
    order_qty: FixedPointCount | None = fixfield(Tag.ORDER_QTY, FixType.QTY, default=None)
    cl_ord_id: str | None = fixfield(Tag.CL_ORD_ID, FixType.STRING, default=None)
    parties: Annotated[list[Party], FixGroupMeta(Tag.NO_PARTY_IDS, Party)] = groupfield()
    prefer_better_quote: bool | None = fixfield(
        Tag.PREFER_BETTER_QUOTE, FixType.BOOLEAN, default=None
    )


class RFQCancel(FixMessage):
    """RFQCancel (35=UE) — creator cancels an active RFQ.

    Identify the RFQ by either ``quote_req_id`` (client id) or ``rfq_id`` (server
    id); use :meth:`for_req_id` / :meth:`for_rfq_id`.
    """

    MSG_TYPE = MsgType.RFQ_CANCEL

    quote_req_id: str | None = fixfield(Tag.QUOTE_REQ_ID, FixType.STRING, default=None)
    rfq_id: str | None = fixfield(Tag.RFQ_ID, FixType.STRING, default=None)
    parties: Annotated[list[Party], FixGroupMeta(Tag.NO_PARTY_IDS, Party)] = groupfield()

    @classmethod
    def for_req_id(cls, quote_req_id: str) -> RFQCancel:
        """Cancel by the client-assigned QuoteReqID."""
        return cls(quote_req_id=quote_req_id)

    @classmethod
    def for_rfq_id(cls, rfq_id: str) -> RFQCancel:
        """Cancel by the server-assigned RfqID."""
        return cls(rfq_id=rfq_id)


# ---------------------------------------------------------------------------
# Inbound messages (fields optional; codes raw for robustness)
# ---------------------------------------------------------------------------


class QuoteRequestAck(FixMessage):
    """QuoteRequestAck (35=b) — exchange ack of a creator's QuoteRequest.

    ``quote_request_type`` is a raw int (compare against
    :class:`~kalshi.fix.enums.QuoteRequestType`); ``rfq_id`` is the server id.
    """

    MSG_TYPE = MsgType.QUOTE_REQUEST_ACK

    quote_req_id: str | None = fixfield(Tag.QUOTE_REQ_ID, FixType.STRING, default=None)
    quote_request_type: int | None = fixfield(Tag.QUOTE_REQUEST_TYPE, FixType.INT, default=None)
    rfq_id: str | None = fixfield(Tag.RFQ_ID, FixType.STRING, default=None)
    symbol: str | None = fixfield(Tag.SYMBOL, FixType.STRING, default=None)
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)


class QuoteStatusReport(FixMessage):
    """QuoteStatusReport (35=AI) — quote lifecycle update to the maker.

    ``quote_status`` is a raw int (compare against
    :class:`~kalshi.fix.enums.QuoteStatus`); ``side`` (AcceptedSide) is a raw char,
    present only when ACCEPTED.
    """

    MSG_TYPE = MsgType.QUOTE_STATUS_REPORT

    quote_id: str | None = fixfield(Tag.QUOTE_ID, FixType.STRING, default=None)
    quote_req_id: str | None = fixfield(Tag.QUOTE_REQ_ID, FixType.STRING, default=None)
    alloc_account: int | None = fixfield(Tag.ALLOC_ACCOUNT, FixType.INT, default=None)
    quote_status: int | None = fixfield(Tag.QUOTE_STATUS, FixType.INT, default=None)
    order_qty: FixedPointCount | None = fixfield(Tag.ORDER_QTY, FixType.QTY, default=None)
    bid_px: DollarDecimal | None = fixfield(Tag.BID_PX, FixType.PRICE, default=None)
    offer_px: DollarDecimal | None = fixfield(Tag.OFFER_PX, FixType.PRICE, default=None)
    bid_size: FixedPointCount | None = fixfield(Tag.BID_SIZE, FixType.QTY, default=None)
    offer_size: FixedPointCount | None = fixfield(Tag.OFFER_SIZE, FixType.QTY, default=None)
    side: str | None = fixfield(Tag.SIDE, FixType.CHAR, default=None)
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)


class QuoteRequestReject(FixMessage):
    """QuoteRequestReject (35=AG) — exchange rejected/cancelled an RFQ request.

    ``quote_request_reject_reason`` is a raw int (compare against
    :class:`~kalshi.fix.enums.QuoteRequestRejectReason`).
    """

    MSG_TYPE = MsgType.QUOTE_REQUEST_REJECT

    quote_req_id: str | None = fixfield(Tag.QUOTE_REQ_ID, FixType.STRING, default=None)
    quote_request_reject_reason: int | None = fixfield(
        Tag.QUOTE_REQUEST_REJECT_REASON, FixType.INT, default=None
    )
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)


class QuoteConfirmStatus(FixMessage):
    """QuoteConfirmStatus (35=U8) — exchange response to a QuoteConfirm.

    ``quote_confirm_status`` is a raw int (compare against
    :class:`~kalshi.fix.enums.QuoteConfirmResult`).
    """

    MSG_TYPE = MsgType.QUOTE_CONFIRM_STATUS

    quote_id: str | None = fixfield(Tag.QUOTE_ID, FixType.STRING, default=None)
    quote_confirm_status: int | None = fixfield(Tag.QUOTE_CONFIRM_STATUS, FixType.INT, default=None)
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)


class QuoteCancelStatus(FixMessage):
    """QuoteCancelStatus (35=U9) — exchange response to a QuoteCancel.

    ``quote_cancel_status`` is a raw int (compare against
    :class:`~kalshi.fix.enums.QuoteCancelResult`).
    """

    MSG_TYPE = MsgType.QUOTE_CANCEL_STATUS

    quote_id: str | None = fixfield(Tag.QUOTE_ID, FixType.STRING, default=None)
    quote_cancel_status: int | None = fixfield(Tag.QUOTE_CANCEL_STATUS, FixType.INT, default=None)
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)


class RFQCancelStatus(FixMessage):
    """RFQCancelStatus (35=UB) — exchange response to an RFQCancel.

    ``rfq_cancel_status`` is a raw int (compare against
    :class:`~kalshi.fix.enums.RFQCancelResult`).
    """

    MSG_TYPE = MsgType.RFQ_CANCEL_STATUS

    quote_req_id: str | None = fixfield(Tag.QUOTE_REQ_ID, FixType.STRING, default=None)
    rfq_cancel_status: int | None = fixfield(Tag.RFQ_CANCEL_STATUS, FixType.INT, default=None)
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)


class AcceptQuoteStatus(FixMessage):
    """AcceptQuoteStatus (35=UC) — exchange response to an AcceptQuote.

    ``accept_quote_status`` is a raw int (compare against
    :class:`~kalshi.fix.enums.AcceptQuoteResult`); ``accepted_quote_id`` may differ
    from the requested quote when ``PreferBetterQuote`` was set.
    """

    MSG_TYPE = MsgType.ACCEPT_QUOTE_STATUS

    quote_id: str | None = fixfield(Tag.QUOTE_ID, FixType.STRING, default=None)
    accept_quote_status: int | None = fixfield(Tag.ACCEPT_QUOTE_STATUS, FixType.INT, default=None)
    accepted_quote_id: str | None = fixfield(Tag.ACCEPTED_QUOTE_ID, FixType.STRING, default=None)
    cl_ord_id: str | None = fixfield(Tag.CL_ORD_ID, FixType.STRING, default=None)
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)
