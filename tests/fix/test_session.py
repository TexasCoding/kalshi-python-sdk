"""State-machine tests for FixSession against the in-memory mock acceptor."""

from __future__ import annotations

import base64
import itertools
from collections.abc import Awaitable, Callable

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi.fix.auth import FixSigner
from kalshi.fix.codec import RawMessage
from kalshi.fix.config import FixConfig, FixSessionType
from kalshi.fix.errors import FixLogonError
from kalshi.fix.session import FixSession, FixSessionState, _heartbeat_due, _liveness
from kalshi.fix.tags import Tag

from .conftest import MockAcceptor

# asyncio_mode = "auto" (pyproject) runs async tests without an explicit marker,
# so the sync helper tests below stay unmarked (no spurious asyncio warning).


def _verify_logon_signature(logon: RawMessage, public_key: rsa.RSAPublicKey) -> None:
    """Reconstruct the logon pre-hash from the wire fields and verify RawData."""
    pre_hash = b"\x01".join(
        s.encode()
        for s in [
            logon.get(Tag.SENDING_TIME) or "",
            "A",
            str(logon.seq_num),
            logon.get(Tag.SENDER_COMP_ID) or "",
            logon.get(Tag.TARGET_COMP_ID) or "",
        ]
    )
    public_key.verify(
        base64.b64decode(logon.get(Tag.RAW_DATA) or ""),
        pre_hash,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


async def test_logon_handshake_sends_signed_reset_logon(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    rsa_private_key: rsa.RSAPrivateKey,
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        assert session.state is FixSessionState.ACTIVE
        # Logon consumed outbound seq 1; next outbound is 2. Logon response was
        # seq 1, so next expected inbound is 2.
        assert session.outbound_seq_num == 2
        assert session.inbound_seq_num == 2

        logon = acceptor.first("A")
        assert logon is not None
        assert logon.get(Tag.SENDER_COMP_ID) == "test-api-key-uuid"
        assert logon.get(Tag.TARGET_COMP_ID) == "KalshiNR"
        assert logon.get(Tag.RESET_SEQ_NUM_FLAG) == "Y"
        assert logon.get(Tag.ENCRYPT_METHOD) == "0"
        assert logon.get(Tag.DEFAULT_APPL_VER_ID) == "9"
        assert logon.get_int(Tag.HEART_BT_INT) == 4
        # The RawData signature verifies against the account public key.
        _verify_logon_signature(logon, rsa_private_key.public_key())
    finally:
        await session.close()


async def test_logon_rejection_raises(
    fix_signer: FixSigner, fix_config: FixConfig, acceptor: MockAcceptor
) -> None:
    acceptor.reject_logon = True
    acceptor.reject_text = "bad signature"
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    with pytest.raises(FixLogonError) as exc:
        await session.start()
    assert exc.value.reason == "bad signature"
    assert session.state is FixSessionState.CLOSED


async def test_test_request_answered_with_heartbeat(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        await acceptor.push("1", [(int(Tag.TEST_REQ_ID), "ping")], seq=2)
        await until(lambda: acceptor.first("0") is not None)
        hb = acceptor.first("0")
        assert hb is not None
        assert hb.get(Tag.TEST_REQ_ID) == "ping"
        assert session.inbound_seq_num == 3
    finally:
        await session.close()


async def test_application_message_delivered_to_callback(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []

    async def on_message(msg: RawMessage) -> None:
        received.append(msg)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR, on_message=on_message
    )
    await session.start()
    try:
        await acceptor.push("8", [(int(Tag.CL_ORD_ID), "abc")], seq=2)
        await until(lambda: len(received) == 1)
        assert received[0].msg_type == "8"
        assert received[0].get(Tag.CL_ORD_ID) == "abc"
        assert session.inbound_seq_num == 3
    finally:
        await session.close()


async def test_inbound_gap_fatal_on_non_retransmission_session(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        # Expected seq is 2; a jump to 5 is an unrecoverable gap on NR.
        await acceptor.push("8", seq=5)
        await until(lambda: session.state is FixSessionState.CLOSED)
    finally:
        await session.close()


async def test_inbound_gap_requests_resend_on_rt(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []

    async def on_message(msg: RawMessage) -> None:
        received.append(msg)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.ORDER_ENTRY_RT, on_message=on_message
    )
    await session.start()
    try:
        # Gap: expected 2, server sends an app message at 5.
        await acceptor.push("8", [(int(Tag.CL_ORD_ID), "late")], seq=5)
        # Client should request a resend rather than fail.
        await until(lambda: acceptor.first("2") is not None)
        resend = acceptor.first("2")
        assert resend is not None
        assert resend.get_int(Tag.BEGIN_SEQ_NO) == 2

        # Server resends the missing 2,3,4 (as PossDup heartbeats); 5 then drains.
        await acceptor.push("0", seq=2, poss_dup=True)
        await acceptor.push("0", seq=3, poss_dup=True)
        await acceptor.push("0", seq=4, poss_dup=True)
        await until(lambda: session.inbound_seq_num == 6)
        # The buffered app message at seq 5 reached the callback after the gap filled.
        assert any(m.get(Tag.CL_ORD_ID) == "late" for m in received)
    finally:
        await session.close()


async def test_sequence_reset_gapfill_advances_expected(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        # GapFill SequenceReset advances the expected inbound counter to NewSeqNo.
        await acceptor.push(
            "4", [(int(Tag.GAP_FILL_FLAG), "Y"), (int(Tag.NEW_SEQ_NO), "5")], seq=2
        )
        await until(lambda: session.inbound_seq_num == 5)
    finally:
        await session.close()


async def test_duplicate_inbound_ignored(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []

    async def on_message(msg: RawMessage) -> None:
        received.append(msg)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR, on_message=on_message
    )
    await session.start()
    try:
        await acceptor.push("8", [(int(Tag.CL_ORD_ID), "first")], seq=2)
        await until(lambda: session.inbound_seq_num == 3)
        # Re-deliver seq 2 as a PossDup — must be ignored, not re-dispatched.
        await acceptor.push("8", [(int(Tag.CL_ORD_ID), "first")], seq=2, poss_dup=True)
        await acceptor.push("8", [(int(Tag.CL_ORD_ID), "second")], seq=3)
        await until(lambda: session.inbound_seq_num == 4)
        assert [m.get(Tag.CL_ORD_ID) for m in received] == ["first", "second"]
    finally:
        await session.close()


async def test_graceful_close_sends_logout(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    await session.close()
    await until(lambda: acceptor.first("5") is not None)
    assert session.state is FixSessionState.CLOSED


async def test_reconnect_after_disconnect(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        assert acceptor.connection_count == 1
        # Server drops the connection; the client should reconnect and re-logon.
        acceptor.drop_connection()
        await until(lambda: acceptor.connection_count == 2, timeout=3.0)
        await until(lambda: session.state is FixSessionState.ACTIVE, timeout=3.0)
    finally:
        await session.close()


async def test_context_manager(
    fix_signer: FixSigner, fix_config: FixConfig, acceptor: MockAcceptor
) -> None:
    async with FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR) as session:
        assert session.state is FixSessionState.ACTIVE
    assert session.state is FixSessionState.CLOSED


async def test_on_state_change_callback_fires(
    fix_signer: FixSigner, fix_config: FixConfig, acceptor: MockAcceptor
) -> None:
    transitions: list[tuple[FixSessionState, FixSessionState]] = []

    async def on_change(old: FixSessionState, new: FixSessionState) -> None:
        transitions.append((old, new))

    session = FixSession(
        fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR, on_state_change=on_change
    )
    await session.start()
    await session.close()

    news = [new for _, new in transitions]
    # Logon drives CONNECTING -> LOGGING_ON -> ACTIVE; close ends at CLOSED.
    assert FixSessionState.CONNECTING in news
    assert FixSessionState.LOGGING_ON in news
    assert FixSessionState.ACTIVE in news
    assert news[-1] is FixSessionState.CLOSED
    # Each transition's "old" chains from the previous "new".
    for prev, cur in itertools.pairwise(transitions):
        assert cur[0] is prev[1]


async def test_inbound_resend_request_replies_with_gap_fill(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_RT)
    await session.start()
    try:
        out_before = session.outbound_seq_num
        # Server asks us to resend from seq 1; we have no message store, so the
        # correct reply is a SequenceReset/gap-fill (admin, PossDup, no seq bump).
        await acceptor.push(
            "2", [(int(Tag.BEGIN_SEQ_NO), "1"), (int(Tag.END_SEQ_NO), "0")], seq=2
        )
        await until(lambda: acceptor.first("4") is not None)
        gap_fill = acceptor.first("4")
        assert gap_fill is not None
        assert gap_fill.seq_num == 1  # MsgSeqNum == BeginSeqNo, not out_seq
        assert gap_fill.get(Tag.GAP_FILL_FLAG) == "Y"
        assert gap_fill.get(Tag.POSS_DUP_FLAG) == "Y"
        assert gap_fill.get(Tag.ORIG_SENDING_TIME) is not None
        assert gap_fill.get_int(Tag.NEW_SEQ_NO) == out_before
        assert session.outbound_seq_num == out_before  # gap-fill must not consume a seq
    finally:
        await session.close()


async def test_too_low_seq_without_possdup_terminates(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        # Expected inbound is 2; a non-PossDup message at seq 1 is a fatal error.
        await acceptor.push("8", seq=1)
        await until(lambda: session.state is FixSessionState.CLOSED)
    finally:
        await session.close()


async def test_logon_gap_requests_resend_on_rt(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    acceptor.logon_resp_seq = 3  # Logon reply arrives ahead of expected (gap)
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_RT)
    await session.start()
    try:
        assert session.state is FixSessionState.ACTIVE
        await until(lambda: acceptor.first("2") is not None)
        resend = acceptor.first("2")
        assert resend is not None
        assert resend.get_int(Tag.BEGIN_SEQ_NO) == 1
    finally:
        await session.close()


async def test_logon_gap_fails_on_non_retransmission_session(
    fix_signer: FixSigner, fix_config: FixConfig, acceptor: MockAcceptor
) -> None:
    acceptor.logon_resp_seq = 3
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    with pytest.raises(FixLogonError):
        await session.start()
    assert session.state is FixSessionState.CLOSED


async def test_margin_logon_emits_use_dollars(
    fix_signer: FixSigner, acceptor: MockAcceptor
) -> None:
    config = FixConfig.margin(host="127.0.0.1", port=acceptor.port, use_tls=False)
    session = FixSession(fix_signer, config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        logon = acceptor.first("A")
        assert logon is not None
        assert logon.get(Tag.USE_DOLLARS) == "Y"  # margin is always fixed-point dollars
    finally:
        await session.close()


async def test_prediction_logon_omits_use_dollars_by_default(
    fix_signer: FixSigner, fix_config: FixConfig, acceptor: MockAcceptor
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        logon = acceptor.first("A")
        assert logon is not None
        assert logon.get(Tag.USE_DOLLARS) is None
        assert logon.get(Tag.CANCEL_ORDERS_ON_DISCONNECT) is None
    finally:
        await session.close()


async def test_cancel_orders_on_disconnect_emitted(
    fix_signer: FixSigner, acceptor: MockAcceptor
) -> None:
    config = FixConfig.prediction(
        host="127.0.0.1", port=acceptor.port, use_tls=False, cancel_orders_on_disconnect=True
    )
    session = FixSession(fix_signer, config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        logon = acceptor.first("A")
        assert logon is not None
        assert logon.get(Tag.CANCEL_ORDERS_ON_DISCONNECT) == "Y"
    finally:
        await session.close()


async def test_peer_initiated_logout_tears_down(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        await acceptor.push("5", [(int(Tag.TEXT), "bye")], seq=2)
        await until(lambda: session.state is FixSessionState.CLOSED)
        assert acceptor.connection_count == 1  # no reconnect on peer logout
    finally:
        await session.close()


async def test_rt_reconnect_resumes_without_reset(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_RT)
    await session.start()
    try:
        acceptor.drop_connection()
        await until(lambda: acceptor.connection_count == 2, timeout=3.0)
        await until(lambda: session.state is FixSessionState.ACTIVE, timeout=3.0)
        logons = [m for m in acceptor.received if m.msg_type == "A"]
        assert len(logons) >= 2
        # First logon resets; the RT reconnect resumes continuity (no reset flag).
        assert logons[0].get(Tag.RESET_SEQ_NUM_FLAG) == "Y"
        assert logons[-1].get(Tag.RESET_SEQ_NUM_FLAG) is None
    finally:
        await session.close()


async def test_sequence_reset_never_rewinds(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        await acceptor.push("8", seq=2)
        await acceptor.push("8", seq=3)
        await until(lambda: session.inbound_seq_num == 4)
        # A reset-mode SequenceReset below the watermark must NOT rewind.
        await acceptor.push("4", [(int(Tag.NEW_SEQ_NO), "2")], seq=4)
        await acceptor.push("8", seq=4)  # force the recv loop to make a pass
        await until(lambda: session.inbound_seq_num == 5)
        # A gap-fill SequenceReset below the watermark must also not rewind.
        await acceptor.push(
            "4", [(int(Tag.GAP_FILL_FLAG), "Y"), (int(Tag.NEW_SEQ_NO), "2")], seq=5
        )
        await acceptor.push("8", seq=5)
        await until(lambda: session.inbound_seq_num == 6)
    finally:
        await session.close()


async def test_out_of_order_gapfill_sequence_reset_is_buffered_on_rt(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_RT)
    await session.start()
    try:
        # A gap-fill SequenceReset arrives AHEAD of expected (seq 5, expected 2):
        # it must be buffered and applied only once the preceding gap is filled.
        await acceptor.push(
            "4", [(int(Tag.GAP_FILL_FLAG), "Y"), (int(Tag.NEW_SEQ_NO), "7")], seq=5
        )
        await until(lambda: acceptor.first("2") is not None)  # resend requested
        # Fill 2,3,4; then the buffered reset at 5 applies NewSeqNo -> in_seq == 7.
        await acceptor.push("0", seq=2, poss_dup=True)
        await acceptor.push("0", seq=3, poss_dup=True)
        await acceptor.push("0", seq=4, poss_dup=True)
        await until(lambda: session.inbound_seq_num == 7)
    finally:
        await session.close()


async def test_on_message_exception_does_not_kill_session(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    calls = 0

    async def boom(_msg: RawMessage) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("consumer bug")

    session = FixSession(
        fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR, on_message=boom
    )
    await session.start()
    try:
        await acceptor.push("8", seq=2)
        await acceptor.push("8", seq=3)
        await until(lambda: session.inbound_seq_num == 4)
        assert calls == 2  # both delivered despite raising
        assert session.state is FixSessionState.ACTIVE  # session survived
    finally:
        await session.close()


async def test_malformed_admin_message_does_not_wedge(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        # A TestRequest missing its required TestReqID (112) fails schema
        # validation in from_raw — the session must Reject it, not die.
        await acceptor.push("1", seq=2)
        await until(lambda: acceptor.first("3") is not None)  # Reject (35=3) sent
        assert session.state is FixSessionState.ACTIVE
        assert session.inbound_seq_num == 3  # malformed message consumed, not stuck
    finally:
        await session.close()


async def test_inbound_resend_request_ignored_on_nr(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    session = FixSession(fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR)
    await session.start()
    try:
        await acceptor.push(
            "2", [(int(Tag.BEGIN_SEQ_NO), "1"), (int(Tag.END_SEQ_NO), "0")], seq=2
        )
        await until(lambda: session.inbound_seq_num == 3)
        assert acceptor.first("4") is None  # no gap-fill emitted on NR
        assert session.state is FixSessionState.ACTIVE
    finally:
        await session.close()


def test_heartbeat_due_threshold() -> None:
    assert _heartbeat_due(now=10.0, last_send=5.0, interval=5.0) is True
    assert _heartbeat_due(now=9.9, last_send=5.0, interval=5.0) is False


def test_liveness_thresholds() -> None:
    assert _liveness(now=10.0, last_recv=9.0, interval=5.0) == "ok"  # silence 1
    assert _liveness(now=10.0, last_recv=5.0, interval=5.0) == "test_request"  # silence 5
    assert _liveness(now=10.0, last_recv=4.9, interval=5.0) == "test_request"  # silence 5.1
    assert _liveness(now=10.0, last_recv=0.0, interval=5.0) == "dead"  # silence 10 >= 2*interval
