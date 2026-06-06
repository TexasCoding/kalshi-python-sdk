"""Tests for the order-entry FIX message flow (GH #424)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

from kalshi.fix.auth import FixSigner
from kalshi.fix.codec import RawMessage, decode, encode
from kalshi.fix.config import FixConfig, FixSessionType
from kalshi.fix.enums import (
    ExecInst,
    ExecType,
    OrdStatus,
    OrdType,
    SelfTradePreventionType,
    Side,
    TimeInForce,
)
from kalshi.fix.messages import (
    BusinessMessageReject,
    CollateralAmountChange,
    ExecutionReport,
    MiscFee,
    NewOrderSingle,
    OrderCancelReject,
    OrderCancelReplaceRequest,
    OrderCancelRequest,
    OrderMassCancelReport,
    OrderMassCancelRequest,
    Party,
    decode_app_message,
)
from kalshi.fix.messages.base import FixMessage
from kalshi.fix.session import FixSession
from kalshi.fix.tags import Tag

from .conftest import MockAcceptor


def _roundtrip(msg: FixMessage) -> FixMessage:
    full = [
        (int(Tag.MSG_TYPE), msg.MSG_TYPE.value),
        (int(Tag.MSG_SEQ_NUM), "1"),
        (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
        *msg.to_body_fields(),
    ]
    return type(msg).from_raw(decode(encode(full)))


def test_new_order_single_roundtrip_with_parties() -> None:
    order = NewOrderSingle(
        cl_ord_id="abc",
        order_qty=Decimal("10"),
        price=Decimal("0.7500"),
        side=Side.BUY_YES,
        symbol="KXTEST-25",
        time_in_force=TimeInForce.GTC,
        exec_inst=ExecInst.POST_ONLY,
        self_trade_prevention_type=SelfTradePreventionType.MAKER,
        parties=[Party(party_id="0", party_role=24)],
    )
    back = _roundtrip(order)
    assert back == order
    assert back.side is Side.BUY_YES
    assert back.ord_type is OrdType.LIMIT  # default
    assert back.parties[0].party_id == "0"


def test_new_order_enum_and_price_wire_values() -> None:
    order = NewOrderSingle(
        cl_ord_id="x",
        order_qty=Decimal("3"),
        price=Decimal("0.7500"),
        side=Side.SELL_NO,
        symbol="Y",
        time_in_force=TimeInForce.IOC,
        exec_inst=ExecInst.POST_ONLY,
        self_trade_prevention_type=SelfTradePreventionType.TAKER_AT_CROSS,
    )
    body = dict(order.to_body_fields())
    assert body[int(Tag.SIDE)] == "2"  # SELL_NO
    assert body[int(Tag.ORD_TYPE)] == "2"  # LIMIT
    assert body[int(Tag.TIME_IN_FORCE)] == "3"  # IOC
    assert body[int(Tag.EXEC_INST)] == "6"  # POST_ONLY
    assert body[int(Tag.SELF_TRADE_PREVENTION_TYPE)] == "1"  # TAKER_AT_CROSS
    assert body[int(Tag.PRICE)] == "0.7500"  # fixed-point dollars preserved


def test_price_cents_vs_dollars_encoding() -> None:
    # The Decimal value is emitted verbatim; units follow the session UseDollars.
    cents = NewOrderSingle(
        cl_ord_id="c", order_qty=Decimal("1"), price=Decimal("75"), side=Side.BUY_YES, symbol="Y"
    )
    assert dict(cents.to_body_fields())[int(Tag.PRICE)] == "75"
    dollars = NewOrderSingle(
        cl_ord_id="d", order_qty=Decimal("1"), price=Decimal("19.5"), side=Side.BUY_YES, symbol="Y"
    )
    assert dict(dollars.to_body_fields())[int(Tag.PRICE)] == "19.5"


def test_cancel_request_roundtrip() -> None:
    msg = OrderCancelRequest(
        cl_ord_id="c1", orig_cl_ord_id="o1", side=Side.BUY_YES, symbol="KXTEST", alloc_account=3
    )
    assert _roundtrip(msg) == msg


def test_cancel_replace_roundtrip() -> None:
    msg = OrderCancelReplaceRequest(
        cl_ord_id="r1",
        orig_cl_ord_id="o1",
        order_qty=Decimal("5"),
        price=Decimal("0.6000"),
        side=Side.SELL_NO,
        symbol="KXTEST",
        order_group_id="grp-1",
    )
    back = _roundtrip(msg)
    assert back == msg
    assert back.price == Decimal("0.6000")


def test_mass_cancel_request_roundtrip() -> None:
    msg = OrderMassCancelRequest(cl_ord_id="m1")
    body = dict(msg.to_body_fields())
    assert body[int(Tag.MASS_CANCEL_REQUEST_TYPE)] == "6"  # CANCEL_FOR_SESSION
    assert _roundtrip(msg) == msg


def test_execution_report_trade_roundtrip() -> None:
    report = ExecutionReport(
        order_id="OID-1",
        cl_ord_id="abc",
        exec_id="4;7",
        exec_type=ExecType.TRADE.value,
        ord_status=OrdStatus.PARTIALLY_FILLED.value,
        side=Side.BUY_YES.value,
        symbol="KXTEST",
        leaves_qty=Decimal("5"),
        cum_qty=Decimal("5"),
        avg_px=Decimal("0.6600"),
        order_qty=Decimal("10"),
        last_px=Decimal("0.7000"),
        last_qty=Decimal("5"),
        long_qty=Decimal("5"),
        short_qty=Decimal("0"),
        trd_match_id="T-1",
        aggressor_indicator=True,
        misc_fees=[
            MiscFee(
                misc_fee_amt=Decimal("0.02"),
                misc_fee_curr="USD",
                misc_fee_type="4",
                misc_fee_basis=0,
            )
        ],
        collateral_amount_changes=[
            CollateralAmountChange(
                collateral_amount_change=Decimal("1.50"), collateral_amount_type="BALANCE"
            )
        ],
        parties=[Party(party_id="0", party_role=24)],
    )
    back = _roundtrip(report)
    assert back == report
    # Raw char codes compare against the enums (StrEnum equality with str).
    assert back.exec_type == ExecType.TRADE
    assert back.ord_status == OrdStatus.PARTIALLY_FILLED
    assert back.misc_fees[0].misc_fee_amt == Decimal("0.02")
    assert back.collateral_amount_changes[0].collateral_amount_type == "BALANCE"
    assert back.aggressor_indicator is True


def test_inbound_report_tolerates_minimal_fields() -> None:
    # A sparse report (e.g. PENDING_NEW) still parses; absent fields are None.
    report = ExecutionReport(
        cl_ord_id="abc",
        exec_id="-1;-1",
        exec_type=ExecType.PENDING_NEW.value,
        ord_status=OrdStatus.PENDING_NEW.value,
    )
    back = _roundtrip(report)
    assert back == report
    assert back.avg_px is None
    assert back.misc_fees == []


def test_order_cancel_reject_roundtrip() -> None:
    msg = OrderCancelReject(
        order_id="OID-1",
        cl_ord_id="c1",
        orig_cl_ord_id="o1",
        ord_status=OrdStatus.NEW.value,
        cxl_rej_reason=1,
        text="UNKNOWN_ORDER",
    )
    assert _roundtrip(msg) == msg


def test_mass_cancel_report_roundtrip() -> None:
    msg = OrderMassCancelReport(cl_ord_id="m1", order_id="op-1", mass_cancel_response="6")
    assert _roundtrip(msg) == msg


def test_business_message_reject_roundtrip() -> None:
    msg = BusinessMessageReject(
        ref_seq_num=5, ref_msg_type="D", business_reject_reason=3, text="UNSUPPORTED_MESSAGE_TYPE"
    )
    assert _roundtrip(msg) == msg


def test_decode_app_message_dispatch() -> None:
    report = ExecutionReport(
        cl_ord_id="abc", exec_type=ExecType.NEW.value, ord_status=OrdStatus.NEW.value
    )
    raw = decode(
        encode(
            [
                (int(Tag.MSG_TYPE), "8"),
                (int(Tag.MSG_SEQ_NUM), "2"),
                (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
                *report.to_body_fields(),
            ]
        )
    )
    decoded = decode_app_message(raw)
    assert isinstance(decoded, ExecutionReport)
    assert decoded.cl_ord_id == "abc"
    # Admin / unregistered message types return None.
    heartbeat = RawMessage([(int(Tag.MSG_TYPE), "0"), (int(Tag.MSG_SEQ_NUM), "3")])
    assert decode_app_message(heartbeat) is None
    # A message with no MsgType at all also returns None (no dispatch key).
    assert decode_app_message(RawMessage([])) is None


def test_decode_app_message_all_inbound_types() -> None:
    for msg in (
        OrderCancelReject(cl_ord_id="c", cxl_rej_reason=1, text="UNKNOWN_ORDER"),
        OrderMassCancelReport(cl_ord_id="m", mass_cancel_response="6"),
        BusinessMessageReject(business_reject_reason=3, text="x"),
    ):
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


def test_decode_app_message_returns_none_on_malformed() -> None:
    # A malformed inbound payload is swallowed (logged) rather than raised into
    # the consumer's on_message — bad bool (ValueError) and bad Decimal
    # (ArithmeticError) both yield None.
    bad_bool = RawMessage([(int(Tag.MSG_TYPE), "8"), (int(Tag.AGGRESSOR_INDICATOR), "X")])
    assert decode_app_message(bad_bool) is None
    bad_decimal = RawMessage([(int(Tag.MSG_TYPE), "8"), (int(Tag.AVG_PX), "notanumber")])
    assert decode_app_message(bad_decimal) is None


def test_cancel_replace_without_price_is_qty_only() -> None:
    # Kalshi allows a quantity-only amend (Price is required only when changing it).
    msg = OrderCancelReplaceRequest(
        cl_ord_id="r", orig_cl_ord_id="o", order_qty=Decimal("5"), side=Side.BUY_YES, symbol="Y"
    )
    assert int(Tag.PRICE) not in {t for t, _ in msg.to_body_fields()}
    back = _roundtrip(msg)
    assert back == msg
    assert back.price is None


def test_new_order_parties_default_empty() -> None:
    order = NewOrderSingle(
        cl_ord_id="x",
        order_qty=Decimal("1"),
        price=Decimal("0.5"),
        side=Side.BUY_YES,
        symbol="Y",
    )
    assert order.parties == []
    assert int(Tag.NO_PARTY_IDS) not in {t for t, _ in order.to_body_fields()}


async def test_send_order_and_receive_execution_report(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR, on_message=on_message
    )
    await session.start()
    try:
        seq = await session.send(
            NewOrderSingle(
                cl_ord_id="abc",
                order_qty=Decimal("10"),
                price=Decimal("0.7500"),
                side=Side.BUY_YES,
                symbol="KXTEST-25",
            )
        )
        assert seq == 2  # logon consumed 1
        await until(lambda: acceptor.first("D") is not None)
        sent = acceptor.first("D")
        assert sent is not None
        assert sent.get(Tag.CL_ORD_ID) == "abc"
        assert sent.get(Tag.SIDE) == "1"
        assert sent.get(Tag.PRICE) == "0.7500"

        # Server streams back an ExecutionReport; the consumer decodes it typed.
        report = ExecutionReport(
            order_id="OID-1",
            cl_ord_id="abc",
            exec_id="1;1",
            exec_type=ExecType.NEW.value,
            ord_status=OrdStatus.NEW.value,
            side=Side.BUY_YES.value,
            symbol="KXTEST-25",
            leaves_qty=Decimal("10"),
            cum_qty=Decimal("0"),
            avg_px=Decimal("0"),
            order_qty=Decimal("10"),
        )
        await acceptor.push("8", report.to_body_fields(), seq=2)
        await until(lambda: len(received) == 1)
        decoded = decode_app_message(received[0])
        assert isinstance(decoded, ExecutionReport)
        assert decoded.order_id == "OID-1"
        assert decoded.ord_status == OrdStatus.NEW
        assert decoded.leaves_qty == Decimal("10")
    finally:
        await session.close()
