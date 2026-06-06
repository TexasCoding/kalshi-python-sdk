"""Tests for the RFQ / quoting FIX flow (GH #428)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest

from kalshi.fix.auth import FixSigner
from kalshi.fix.codec import RawMessage, decode, encode
from kalshi.fix.config import FixConfig, FixSessionType
from kalshi.fix.enums import (
    AcceptQuoteResult,
    MsgType,
    QuoteCancelResult,
    QuoteConfirmResult,
    QuoteRequestType,
    QuoteStatus,
    RFQCancelResult,
    Side,
)
from kalshi.fix.messages import (
    APP_MESSAGE_MODELS,
    AcceptQuote,
    AcceptQuoteStatus,
    MultivariateSelectedLeg,
    Quote,
    QuoteCancel,
    QuoteCancelStatus,
    QuoteConfirm,
    QuoteConfirmStatus,
    QuoteRequest,
    QuoteRequestAck,
    QuoteRequestReject,
    QuoteStatusReport,
    RFQCancel,
    RFQCancelStatus,
    decode_app_message,
)
from kalshi.fix.messages.base import FixMessage
from kalshi.fix.session import FixSession
from kalshi.fix.tags import Tag

from .conftest import MockAcceptor

REQ = "client-req-123"
RFQ = "server-rfq-456"
QID = "quote-789"
SYM = "HIGHNY-23DEC31"


def _roundtrip(msg: FixMessage) -> FixMessage:
    full = [
        (int(Tag.MSG_TYPE), msg.MSG_TYPE.value),
        (int(Tag.MSG_SEQ_NUM), "1"),
        (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
        *msg.to_body_fields(),
    ]
    return type(msg).from_raw(decode(encode(full)))


def _wire(msg: FixMessage) -> str:
    return "|".join(f"{t}={v}" for t, v in msg.to_body_fields())


# ---------------------------------------------------------------------------
# Golden wire fixtures (pinned to docs.kalshi.com/fix/rfq-messages examples)
# ---------------------------------------------------------------------------


def test_golden_quote_request_create() -> None:
    msg = QuoteRequest.create(REQ, symbol=SYM, order_qty=Decimal("100"))
    assert _wire(msg) == f"131={REQ}|146=1|55={SYM}|38=100"


def test_golden_quote_request_mve_legs() -> None:
    msg = QuoteRequest(
        quote_req_id="client-req-456",
        no_related_sym=1,
        order_qty=Decimal("100"),
        multivariate_collection_ticker="PARLAY-COLLECTION",
        multivariate_selected_legs=[
            MultivariateSelectedLeg(event_ticker="EVENT1", market_ticker="MKT1", side="yes"),
            MultivariateSelectedLeg(event_ticker="EVENT2", market_ticker="MKT2", side="no"),
        ],
    )
    assert _wire(msg) == (
        "131=client-req-456|146=1|38=100|20180=PARLAY-COLLECTION|"
        "20181=2|20182=EVENT1|20183=MKT1|20184=yes|20182=EVENT2|20183=MKT2|20184=no"
    )


def test_golden_quote_request_ack() -> None:
    msg = QuoteRequestAck(quote_req_id=REQ, quote_request_type=1, rfq_id=RFQ)
    assert _wire(msg) == f"131={REQ}|303=1|21023={RFQ}"


def test_golden_quote_submit_maker() -> None:
    # MM -> Exchange: cents on the wire (prediction default).
    msg = Quote.submit(QID, RFQ, SYM, bid_px=Decimal("75"), offer_px=Decimal("25"))
    assert _wire(msg) == f"117={QID}|131={RFQ}|55={SYM}|132=75|133=25"


def test_golden_quote_notification_creator() -> None:
    # Exchange -> Creator: dollars on the wire (UseDollars).
    msg = Quote(
        quote_id=QID,
        quote_req_id=RFQ,
        symbol=SYM,
        bid_px=Decimal("0.7500"),
        offer_px=Decimal("0.2500"),
        order_qty=Decimal("100"),
    )
    assert _wire(msg) == f"117={QID}|131={RFQ}|55={SYM}|132=0.7500|133=0.2500|38=100"


def test_golden_accept_quote() -> None:
    msg = AcceptQuote(
        quote_id=QID, side=Side.BUY_YES, order_qty=Decimal("100"), cl_ord_id="client-accept-123"
    )
    assert _wire(msg) == f"117={QID}|54=1|38=100|11=client-accept-123"


def test_golden_accept_quote_status() -> None:
    msg = AcceptQuoteStatus(
        quote_id=QID, accept_quote_status=0, accepted_quote_id=QID, cl_ord_id="client-accept-123"
    )
    assert _wire(msg) == f"117={QID}|21025=0|21024={QID}|11=client-accept-123"


def test_golden_rfq_cancel_and_status() -> None:
    assert _wire(RFQCancel.for_req_id(REQ)) == f"131={REQ}"
    assert _wire(RFQCancel.for_rfq_id(RFQ)) == f"21023={RFQ}"
    assert _wire(RFQCancelStatus(quote_req_id=REQ, rfq_cancel_status=0)) == f"131={REQ}|21013=0"


def test_golden_quote_status_report_pending() -> None:
    msg = QuoteStatusReport(
        quote_id=QID,
        quote_req_id=RFQ,
        quote_status=int(QuoteStatus.PENDING),
        order_qty=Decimal("100"),
        bid_px=Decimal("75"),
        offer_px=Decimal("25"),
    )
    assert _wire(msg) == f"117={QID}|131={RFQ}|297=10|38=100|132=75|133=25"


def test_golden_quote_cancel_flow() -> None:
    assert _wire(QuoteCancel(quote_id=QID)) == f"117={QID}"
    assert _wire(QuoteCancelStatus(quote_id=QID, quote_cancel_status=0)) == f"117={QID}|298=0"


def test_golden_quote_confirm_flow() -> None:
    assert _wire(QuoteConfirm(quote_id=QID)) == f"117={QID}"
    assert _wire(QuoteConfirmStatus(quote_id=QID, quote_confirm_status=0)) == f"117={QID}|21010=0"


def test_golden_quote_request_reject() -> None:
    msg = QuoteRequestReject(quote_req_id=REQ, quote_request_reject_reason=1, text="unknown symbol")
    assert _wire(msg) == f"131={REQ}|658=1|58=unknown symbol"


# ---------------------------------------------------------------------------
# Round-trips for the full message set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg",
    [
        QuoteRequest.create(REQ, symbol=SYM, order_qty=Decimal("100")),
        Quote.submit(QID, RFQ, SYM, bid_px=Decimal("75"), offer_px=Decimal("25")),
        QuoteCancel(quote_id=QID),
        QuoteConfirm(quote_id=QID),
        AcceptQuote(quote_id=QID, side=Side.SELL_NO),
        RFQCancel.for_req_id(REQ),
        QuoteRequestAck(quote_req_id=REQ, quote_request_type=1, rfq_id=RFQ),
        QuoteStatusReport(quote_id=QID, quote_req_id=RFQ, quote_status=0, side="1"),
        QuoteRequestReject(quote_req_id=REQ, quote_request_reject_reason=99, text="x"),
        QuoteConfirmStatus(quote_id=QID, quote_confirm_status=1, text="no"),
        QuoteCancelStatus(quote_id=QID, quote_cancel_status=0),
        RFQCancelStatus(quote_req_id=REQ, rfq_cancel_status=1, text="no"),
        AcceptQuoteStatus(quote_id=QID, accept_quote_status=0, accepted_quote_id=QID),
    ],
)
def test_rfq_message_roundtrip(msg: FixMessage) -> None:
    assert _roundtrip(msg) == msg


def test_quote_request_with_parties_roundtrip() -> None:
    from kalshi.fix.messages import Party

    msg = QuoteRequest.create(REQ, symbol=SYM, order_qty=Decimal("100"))
    msg = msg.model_copy(update={"parties": [Party(party_id="SUB-1", party_role=24)]})
    rt = _roundtrip(msg)
    assert isinstance(rt, QuoteRequest)
    assert rt.parties[0].party_id == "SUB-1"
    assert rt == msg


def test_status_field_enum_comparisons() -> None:
    # The raw-int status fields compare against their suffixed *Result enums.
    assert QuoteCancelStatus(quote_id=QID, quote_cancel_status=1).quote_cancel_status == (
        QuoteCancelResult.REJECTED
    )
    assert QuoteConfirmStatus(quote_id=QID, quote_confirm_status=0).quote_confirm_status == (
        QuoteConfirmResult.ACCEPTED
    )
    assert RFQCancelStatus(quote_req_id=REQ, rfq_cancel_status=0).rfq_cancel_status == (
        RFQCancelResult.CANCELLED
    )
    assert AcceptQuoteStatus(quote_id=QID, accept_quote_status=1).accept_quote_status == (
        AcceptQuoteResult.REJECTED
    )


def test_quote_submit_requires_a_price() -> None:
    with pytest.raises(ValueError, match="bid_px / offer_px"):
        Quote.submit(QID, RFQ, SYM)


def test_quote_request_create_requires_a_size() -> None:
    with pytest.raises(ValueError, match="order_qty or cash_order_qty"):
        QuoteRequest.create(REQ, SYM)


def test_rfq_cancel_requires_an_identifier() -> None:
    # Direct construction with neither identifier is rejected (outbound-only guard).
    with pytest.raises(ValueError, match="quote_req_id or rfq_id"):
        RFQCancel()


def test_rfq_cancel_stays_outbound_only() -> None:
    # RFQCancel carries a construction-time validator; it must NOT be registered
    # for inbound dispatch (that would reject inbound messages lacking both ids).
    # This tripwire fails if someone wires it into APP_MESSAGE_MODELS.
    assert MsgType.RFQ_CANCEL.value not in APP_MESSAGE_MODELS


def test_quote_request_type_enum_comparison() -> None:
    msg = QuoteRequestAck(quote_req_id=REQ, quote_request_type=1, rfq_id=RFQ)
    assert msg.quote_request_type == QuoteRequestType.MANUAL


@pytest.mark.parametrize(
    ("status", "wire"),
    [
        (QuoteStatus.ACCEPTED, "0"),
        (QuoteStatus.REJECTED, "5"),
        (QuoteStatus.PENDING, "10"),
        (QuoteStatus.CANCELLED, "17"),
    ],
)
def test_quote_status_report_status_values(status: QuoteStatus, wire: str) -> None:
    # Pin every QuoteStatus wire value (catches enum-value drift on 297).
    msg = QuoteStatusReport(quote_id=QID, quote_req_id=RFQ, quote_status=int(status))
    assert _wire(msg) == f"117={QID}|131={RFQ}|297={wire}"
    rt = _roundtrip(msg)
    assert isinstance(rt, QuoteStatusReport)
    assert rt.quote_status == status


def test_accept_quote_side_inverted_wire_values() -> None:
    # AcceptQuote.side is inverted per spec: BUY_YES(1) accepts the maker's NO
    # quote, SELL_NO(2) accepts the YES quote. Pin the wire values either way.
    assert dict(AcceptQuote(quote_id=QID, side=Side.BUY_YES).to_body_fields())[int(Tag.SIDE)] == "1"
    assert dict(AcceptQuote(quote_id=QID, side=Side.SELL_NO).to_body_fields())[int(Tag.SIDE)] == "2"


def test_fix_public_api_exports_are_importable() -> None:
    # Every name in kalshi.fix.__all__ must actually be bound (guards the
    # __all__-without-import class of bug, which mypy cannot catch).
    import kalshi.fix as fix_pkg

    missing = [name for name in fix_pkg.__all__ if not hasattr(fix_pkg, name)]
    assert missing == []


@pytest.mark.parametrize(
    "msg",
    [
        QuoteRequestAck(quote_req_id=REQ, quote_request_type=1),
        QuoteStatusReport(quote_id=QID, quote_req_id=RFQ, quote_status=10),
        QuoteRequestReject(quote_req_id=REQ, quote_request_reject_reason=1, text="x"),
        QuoteConfirmStatus(quote_id=QID, quote_confirm_status=0),
        QuoteCancelStatus(quote_id=QID, quote_cancel_status=0),
        RFQCancelStatus(quote_req_id=REQ, rfq_cancel_status=0),
        AcceptQuoteStatus(quote_id=QID, accept_quote_status=0),
        QuoteRequest.create(REQ, symbol=SYM, order_qty=Decimal("1")),
        Quote.submit(QID, RFQ, SYM, bid_px=Decimal("50")),
    ],
)
def test_decode_app_message_rfq_types(msg: FixMessage) -> None:
    raw = decode(
        encode(
            [
                (int(Tag.MSG_TYPE), msg.MSG_TYPE.value),
                (int(Tag.MSG_SEQ_NUM), "2"),
                (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
                *msg.to_body_fields(),
            ]
        )
    )
    decoded = decode_app_message(raw)
    assert type(decoded) is type(msg)
    assert decoded == msg


# ---------------------------------------------------------------------------
# Market-maker quote lifecycle against the mock acceptor
# ---------------------------------------------------------------------------


async def test_market_maker_quote_lifecycle(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    session = FixSession(fix_signer, fix_config, FixSessionType.RFQ, on_message=on_message)
    await session.start()
    try:
        # Exchange notifies the maker of a new RFQ.
        notif = QuoteRequest.create(RFQ, symbol=SYM, order_qty=Decimal("100"))
        await acceptor.push("R", notif.to_body_fields(), seq=2)
        await until(lambda: len(received) == 1)
        decoded = decode_app_message(received[0])
        assert isinstance(decoded, QuoteRequest)
        assert decoded.symbol == SYM

        # Maker submits a quote.
        quote = Quote.submit(QID, RFQ, SYM, bid_px=Decimal("75"), offer_px=Decimal("25"))
        await session.send(quote)
        await until(lambda: acceptor.first("S") is not None)
        raw_s = acceptor.first("S")
        assert raw_s is not None
        assert raw_s.get(Tag.QUOTE_ID) == QID

        # Exchange reports PENDING then ACCEPTED.
        pending = QuoteStatusReport(quote_id=QID, quote_req_id=RFQ, quote_status=10)
        accepted = QuoteStatusReport(quote_id=QID, quote_req_id=RFQ, quote_status=0, side="1")
        await acceptor.push("AI", pending.to_body_fields(), seq=3)
        await acceptor.push("AI", accepted.to_body_fields(), seq=4)
        await until(lambda: len(received) == 3)
        statuses = [decode_app_message(r) for r in received[1:]]
        assert all(isinstance(s, QuoteStatusReport) for s in statuses)
        accepted_report = statuses[1]
        assert isinstance(accepted_report, QuoteStatusReport)
        assert accepted_report.quote_status == QuoteStatus.ACCEPTED
        assert accepted_report.side == "1"  # AcceptedSide present only when ACCEPTED

        # Maker confirms; exchange acks.
        await session.send(QuoteConfirm(quote_id=QID))
        await until(lambda: acceptor.first("U7") is not None)
        await acceptor.push(
            "U8", QuoteConfirmStatus(quote_id=QID, quote_confirm_status=0).to_body_fields(), seq=5
        )
        await until(lambda: len(received) == 4)
        confirm = decode_app_message(received[3])
        assert isinstance(confirm, QuoteConfirmStatus)
        assert confirm.quote_confirm_status == 0
    finally:
        await session.close()


async def test_rfq_creator_lifecycle(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    """Creator flow on KalshiRT: R -> b -> S -> UA -> UC, then UE -> UB."""
    received: list[RawMessage] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.ORDER_ENTRY_RT, on_message=on_message
    )
    await session.start()
    try:
        # Create the RFQ; exchange acks with the server RFQ id.
        await session.send(QuoteRequest.create(REQ, symbol=SYM, order_qty=Decimal("100")))
        await until(lambda: acceptor.first("R") is not None)
        r = acceptor.first("R")
        assert r is not None
        assert r.get(Tag.QUOTE_REQ_ID) == REQ
        ack = QuoteRequestAck(quote_req_id=REQ, quote_request_type=1, rfq_id=RFQ)
        await acceptor.push("b", ack.to_body_fields(), seq=2)

        # A maker's quote is forwarded to the creator (dollars on the wire).
        notif = Quote(
            quote_id=QID, quote_req_id=RFQ, symbol=SYM,
            bid_px=Decimal("0.7500"), offer_px=Decimal("0.2500"), order_qty=Decimal("100"),
        )
        await acceptor.push("S", notif.to_body_fields(), seq=3)
        await until(lambda: len(received) == 2)
        quote = decode_app_message(received[1])
        assert isinstance(quote, Quote)
        assert quote.quote_id == QID

        # Accept it; exchange confirms.
        await session.send(AcceptQuote(quote_id=QID, side=Side.SELL_NO, order_qty=Decimal("100")))
        await until(lambda: acceptor.first("UA") is not None)
        await acceptor.push(
            "UC",
            AcceptQuoteStatus(quote_id=QID, accept_quote_status=0, accepted_quote_id=QID)
            .to_body_fields(),
            seq=4,
        )
        await until(lambda: len(received) == 3)
        accept_status = decode_app_message(received[2])
        assert isinstance(accept_status, AcceptQuoteStatus)
        assert accept_status.accept_quote_status == AcceptQuoteResult.ACCEPTED

        # Cancel the RFQ; exchange acks the cancel.
        await session.send(RFQCancel.for_req_id(REQ))
        await until(lambda: acceptor.first("UE") is not None)
        await acceptor.push(
            "UB", RFQCancelStatus(quote_req_id=REQ, rfq_cancel_status=0).to_body_fields(), seq=5
        )
        await until(lambda: len(received) == 4)
        cancel_status = decode_app_message(received[3])
        assert isinstance(cancel_status, RFQCancelStatus)
        assert cancel_status.rfq_cancel_status == RFQCancelResult.CANCELLED
    finally:
        await session.close()
