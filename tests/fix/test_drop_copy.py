"""Tests for the drop-copy FIX flow (GH #425)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest

from kalshi.fix.auth import FixSigner
from kalshi.fix.codec import RawMessage, decode, encode
from kalshi.fix.config import FixConfig, FixEnvironment, FixSessionType
from kalshi.fix.enums import EventResendRejectReason, ExecType, OrdStatus, Side
from kalshi.fix.messages import (
    EventResendComplete,
    EventResendReject,
    EventResendRequest,
    ExecutionReport,
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


def test_event_resend_request_roundtrip() -> None:
    msg = EventResendRequest(begin_exec_id="12345;67890", end_exec_id="12350;67895")
    body = dict(msg.to_body_fields())
    assert body[int(Tag.BEGIN_EXEC_ID)] == "12345;67890"
    assert body[int(Tag.END_EXEC_ID)] == "12350;67895"
    assert _roundtrip(msg) == msg


def test_event_resend_request_begin_only() -> None:
    msg = EventResendRequest(begin_exec_id="12345;67890")
    assert int(Tag.END_EXEC_ID) not in {t for t, _ in msg.to_body_fields()}
    assert _roundtrip(msg) == msg


def test_event_resend_complete_roundtrip() -> None:
    msg = EventResendComplete(ref_seq_num=7, resend_event_count=12)
    assert _roundtrip(msg) == msg


def test_event_resend_reject_roundtrip() -> None:
    msg = EventResendReject(ref_seq_num=7, event_resend_reject_reason=3)
    back = _roundtrip(msg)
    assert back == msg
    assert back.event_resend_reject_reason == EventResendRejectReason.BEGIN_EXECID_TOO_SMALL


def test_decode_app_message_drop_copy_types() -> None:
    for msg in (
        EventResendComplete(ref_seq_num=7, resend_event_count=3),
        EventResendReject(ref_seq_num=7, event_resend_reject_reason=1),
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


def test_listener_session_requires_skip_pending() -> None:
    # Both factories feed the same __post_init__ validator.
    with pytest.raises(ValueError, match="skip_pending_exec_reports"):
        FixConfig.prediction(listener_session=True)
    with pytest.raises(ValueError, match="skip_pending_exec_reports"):
        FixConfig.margin(listener_session=True)


async def test_drop_copy_query_returns_execution_reports(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.DROP_COPY, on_message=on_message
    )
    await session.start()
    try:
        await session.send(EventResendRequest(begin_exec_id="1;1", end_exec_id="9;9"))
        await until(lambda: acceptor.first("U1") is not None)
        assert acceptor.first("U1").get(Tag.BEGIN_EXEC_ID) == "1;1"  # type: ignore[union-attr]

        # The gateway replays matching ExecutionReports then an EventResendComplete.
        report = ExecutionReport(
            order_id="OID-1",
            cl_ord_id="abc",
            exec_id="4;7",
            exec_type=ExecType.TRADE.value,
            ord_status=OrdStatus.FILLED.value,
            side=Side.BUY_YES.value,
            symbol="KXTEST",
            leaves_qty=Decimal("0"),
            cum_qty=Decimal("10"),
            avg_px=Decimal("0.66"),
            order_qty=Decimal("10"),
        )
        await acceptor.push("8", report.to_body_fields(), seq=2)
        await acceptor.push(
            "U2", EventResendComplete(ref_seq_num=2, resend_event_count=1).to_body_fields(), seq=3
        )
        await until(lambda: len(received) == 2)
        decoded = [decode_app_message(r) for r in received]
        assert isinstance(decoded[0], ExecutionReport)
        assert decoded[0].exec_id == "4;7"
        assert isinstance(decoded[1], EventResendComplete)
        assert decoded[1].resend_event_count == 1
    finally:
        await session.close()


async def test_listener_logon_emits_flags(
    fix_signer: FixSigner,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    config = FixConfig.prediction(
        environment=FixEnvironment.DEMO,
        host="127.0.0.1",
        port=acceptor.port,
        use_tls=False,
        heartbeat_interval=4,
        connect_timeout=2.0,
        listener_session=True,
        skip_pending_exec_reports=True,
    )
    session = FixSession(fix_signer, config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        # start() returns only after the Logon round-trips (the acceptor records
        # before it responds), so the Logon is already landed — poll anyway to
        # match the file's idiom and stay robust to acceptor changes.
        await until(lambda: acceptor.first("A") is not None)
        logon = acceptor.first("A")
        assert logon is not None
        assert logon.get(Tag.LISTENER_SESSION) == "Y"
        assert logon.get(Tag.SKIP_PENDING_EXEC_REPORTS) == "Y"
    finally:
        await session.close()
