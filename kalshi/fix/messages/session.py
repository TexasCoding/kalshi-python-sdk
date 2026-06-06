"""Typed session-layer (admin) FIX messages.

These are the messages the :class:`kalshi.fix.session.FixSession` state machine
constructs and consumes directly: Logon, Logout, Heartbeat, TestRequest,
ResendRequest, SequenceReset, and Reject. Application messages (order entry,
market data, …) land in later phases.

Reason/reject *codes* on inbound messages (e.g. ``session_reject_reason``) are
typed as plain ``int`` rather than enums so an unknown code from the server
parses cleanly instead of raising; compare against :mod:`kalshi.fix.enums`
(e.g. ``SessionRejectReason.SENDINGTIME_ACCURACY_PROBLEM``) at the call site.
"""

from __future__ import annotations

from kalshi.fix.enums import ApplVerID, EncryptMethod, MsgType
from kalshi.fix.messages.base import FixMessage, FixType, fixfield


class Logon(FixMessage):
    """Logon (35=A).

    The ``raw_data`` field carries the base64 RSA-PSS logon signature; the codec
    auto-emits its ``RawDataLength`` (95) field. ``heartbeat_interval`` must be
    > 3 (Kalshi default 30). ``reset_seq_num_flag`` must be ``True`` on
    non-retransmission sessions (KalshiNR / KalshiDC).
    """

    MSG_TYPE = MsgType.LOGON

    encrypt_method: EncryptMethod = fixfield(98, FixType.INT, default=EncryptMethod.NONE)
    heartbeat_interval: int = fixfield(108, FixType.INT)
    raw_data: str | None = fixfield(96, FixType.DATA, default=None)
    reset_seq_num_flag: bool | None = fixfield(141, FixType.BOOLEAN, default=None)
    next_expected_msg_seq_num: int | None = fixfield(789, FixType.SEQNUM, default=None)
    max_message_size: int | None = fixfield(383, FixType.LENGTH, default=None)
    test_message_indicator: bool | None = fixfield(464, FixType.BOOLEAN, default=None)
    username: str | None = fixfield(553, FixType.STRING, default=None)
    password: str | None = fixfield(554, FixType.STRING, default=None)
    default_appl_ver_id: ApplVerID = fixfield(1137, FixType.STRING, default=ApplVerID.FIX50SP2)
    # Kalshi custom logon options.
    cancel_orders_on_disconnect: bool | None = fixfield(8013, FixType.BOOLEAN, default=None)
    skip_pending_exec_reports: bool | None = fixfield(21011, FixType.BOOLEAN, default=None)
    use_dollars: bool | None = fixfield(21005, FixType.BOOLEAN, default=None)
    cancel_order_on_pause: bool | None = fixfield(21006, FixType.BOOLEAN, default=None)
    enable_ioc_cancel_report: bool | None = fixfield(21007, FixType.BOOLEAN, default=None)
    listener_session: bool | None = fixfield(20126, FixType.BOOLEAN, default=None)
    receive_settlement_reports: bool | None = fixfield(20127, FixType.BOOLEAN, default=None)
    message_retention_period: int | None = fixfield(20200, FixType.INT, default=None)
    preserve_original_order_qty: bool | None = fixfield(21008, FixType.BOOLEAN, default=None)
    use_expired_ord_status: bool | None = fixfield(21012, FixType.BOOLEAN, default=None)
    always_emit_new_before_trade: bool | None = fixfield(21026, FixType.BOOLEAN, default=None)


class Logout(FixMessage):
    """Logout (35=5). ``text`` carries a human-readable reason when present."""

    MSG_TYPE = MsgType.LOGOUT

    text: str | None = fixfield(58, FixType.STRING, default=None)


class Heartbeat(FixMessage):
    """Heartbeat (35=0). ``test_req_id`` echoes a TestRequest when responding to one."""

    MSG_TYPE = MsgType.HEARTBEAT

    test_req_id: str | None = fixfield(112, FixType.STRING, default=None)


class TestRequest(FixMessage):
    """TestRequest (35=1). The peer must echo ``test_req_id`` in its Heartbeat."""

    # Stop pytest from collecting this FIX message as a test class when it is
    # imported into a test module (its name matches the default ``Test*`` glob).
    __test__ = False

    MSG_TYPE = MsgType.TEST_REQUEST

    test_req_id: str = fixfield(112, FixType.STRING)


class ResendRequest(FixMessage):
    """ResendRequest (35=2). Inclusive range; ``end_seq_no=0`` means "through latest"."""

    MSG_TYPE = MsgType.RESEND_REQUEST

    begin_seq_no: int = fixfield(7, FixType.SEQNUM)
    end_seq_no: int = fixfield(16, FixType.SEQNUM)


class SequenceReset(FixMessage):
    """SequenceReset (35=4). ``gap_fill_flag`` distinguishes gap-fill from reset mode."""

    MSG_TYPE = MsgType.SEQUENCE_RESET

    gap_fill_flag: bool | None = fixfield(123, FixType.BOOLEAN, default=None)
    new_seq_no: int = fixfield(36, FixType.SEQNUM)


class Reject(FixMessage):
    """Reject (35=3) — session-level rejection of a message we sent."""

    MSG_TYPE = MsgType.REJECT

    ref_seq_num: int = fixfield(45, FixType.SEQNUM)
    ref_tag_id: int | None = fixfield(371, FixType.INT, default=None)
    ref_msg_type: str | None = fixfield(372, FixType.STRING, default=None)
    session_reject_reason: int | None = fixfield(373, FixType.INT, default=None)
    text: str | None = fixfield(58, FixType.STRING, default=None)
