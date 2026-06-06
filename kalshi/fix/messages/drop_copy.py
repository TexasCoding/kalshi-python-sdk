"""Drop-copy FIX messages (GH #425).

Kalshi drop copy is a request/response history query, not a streaming feed:
send an :class:`EventResendRequest` (35=U1) for an ExecID range on a ``KalshiDC``
session; the gateway replays the matching :class:`~kalshi.fix.messages.order_entry.ExecutionReport`
messages (35=8, rejects and pending ``-1;-1`` excluded, 3-hour lookback) and
terminates the batch with :class:`EventResendComplete` (35=U2) or
:class:`EventResendReject` (35=U3). For a real-time stream use a listener session
on KalshiRT instead (see ``FixConfig.listener_session``).

ExecIDs use the Kalshi compound ``"int;int"`` format (e.g. ``"12345;67890"``);
resent reports carry new FIX sequence numbers, so reconcile by ExecID.
"""

from __future__ import annotations

from kalshi.fix.enums import MsgType
from kalshi.fix.messages.base import FixMessage, FixType, fixfield
from kalshi.fix.tags import Tag


class EventResendRequest(FixMessage):
    """EventResendRequest (35=U1) — request execution reports in an ExecID range."""

    MSG_TYPE = MsgType.EVENT_RESEND_REQUEST

    begin_exec_id: str = fixfield(Tag.BEGIN_EXEC_ID, FixType.STRING)
    end_exec_id: str | None = fixfield(Tag.END_EXEC_ID, FixType.STRING, default=None)


class EventResendComplete(FixMessage):
    """EventResendComplete (35=U2) — all requested events have been resent."""

    MSG_TYPE = MsgType.EVENT_RESEND_COMPLETE

    ref_seq_num: int | None = fixfield(Tag.REF_SEQ_NUM, FixType.SEQNUM, default=None)
    resend_event_count: int | None = fixfield(Tag.RESEND_EVENT_COUNT, FixType.INT, default=None)


class EventResendReject(FixMessage):
    """EventResendReject (35=U3) — the resend request could not be fulfilled.

    ``event_resend_reject_reason`` is a raw int (compare against
    :class:`~kalshi.fix.enums.EventResendRejectReason`).
    """

    MSG_TYPE = MsgType.EVENT_RESEND_REJECT

    ref_seq_num: int | None = fixfield(Tag.REF_SEQ_NUM, FixType.SEQNUM, default=None)
    event_resend_reject_reason: int | None = fixfield(
        Tag.EVENT_RESEND_REJECT_REASON, FixType.INT, default=None
    )
