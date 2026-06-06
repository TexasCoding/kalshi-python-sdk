"""Async FIX session state machine: logon, liveness, sequencing, recovery.

:class:`FixSession` owns one FIX session (one TCP connection, one ``TargetCompID``)
and implements the session layer on top of :class:`kalshi.fix.connection.FixConnection`:

* **Logon** (35=A) with an RSA-PSS ``RawData`` signature; ``ResetSeqNumFlag=Y`` on
  non-retransmission sessions (NR/DC/RFQ/MD), continuity on RT/PT reconnect.
* **Liveness** — periodic Heartbeat (35=0), TestRequest (35=1) on inbound silence,
  and reconnect when the peer goes quiet.
* **Sequencing** — track expected inbound ``MsgSeqNum``; on a forward gap buffer the
  out-of-order messages and send a ResendRequest (retransmission sessions) or fail
  (non-retransmission). Honor inbound SequenceReset/gap-fill and drop duplicates.
* **Recovery** — AWS full-jitter reconnect backoff (matching the WS/REST transports).

Application messages are delivered to an ``on_message`` callback as decoded
:class:`~kalshi.fix.codec.RawMessage`; the order-entry / market-data phases build
typed streams on top. Admin messages are handled internally.

Foundation scope note: responses to an inbound ResendRequest are administrative
gap-fills (no outbound message store yet); a persistent store for true
retransmission is a later phase. See GH #402.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import ssl
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import Enum
from types import TracebackType

from pydantic import ValidationError

from kalshi.fix._timefmt import format_utc_timestamp
from kalshi.fix.auth import FixSigner
from kalshi.fix.codec import RawMessage, encode
from kalshi.fix.config import FixConfig, FixSessionType
from kalshi.fix.connection import FixConnection
from kalshi.fix.enums import MsgType
from kalshi.fix.errors import (
    FixConnectionError,
    FixDecodeError,
    FixLogonError,
    FixSequenceError,
    FixSessionError,
)
from kalshi.fix.messages.base import FixMessage
from kalshi.fix.messages.dispatch import decode_app_message_strict
from kalshi.fix.messages.session import (
    Heartbeat,
    Logon,
    Logout,
    Reject,
    ResendRequest,
    SequenceReset,
    TestRequest,
)
from kalshi.fix.tags import Tag

logger = logging.getLogger("kalshi.fix")

MessageHandler = Callable[[RawMessage], Awaitable[None]]
StateChangeHandler = Callable[["FixSessionState", "FixSessionState"], Awaitable[None]]
DecodeErrorHandler = Callable[[RawMessage, FixDecodeError], Awaitable[None]]


def _heartbeat_due(now: float, last_send: float, interval: float) -> bool:
    """True when an idle Heartbeat is due (no outbound message for >= interval)."""
    return now - last_send >= interval


def _liveness(now: float, last_recv: float, interval: float) -> str:
    """Classify peer liveness from inbound silence.

    Returns ``"ok"``, ``"test_request"`` (silent >= one interval — probe with a
    TestRequest), or ``"dead"`` (silent >= two intervals — force a reconnect).
    """
    silence = now - last_recv
    if silence >= interval * 2:
        return "dead"
    if silence >= interval:
        return "test_request"
    return "ok"


class FixSessionState(Enum):
    """FIX session lifecycle states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    LOGGING_ON = "logging_on"
    ACTIVE = "active"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"


class FixSession:
    """A single async FIX session.

    Usage::

        signer = FixSigner.from_env()
        config = FixConfig.prediction(environment=FixEnvironment.DEMO)
        session = FixSession(signer, config, FixSessionType.ORDER_ENTRY_NR,
                             on_message=handle)
        async with session:
            ...  # send order-entry messages, receive execution reports

    ``on_message`` receives every inbound application message as a raw
    :class:`~kalshi.fix.codec.RawMessage` (decode it with
    :func:`~kalshi.fix.messages.decode_app_message`). Setting ``on_decode_error``
    additionally routes a *registered-but-malformed* message (a real message lost
    to one off-spec field) — but it makes the session run a full Pydantic
    validation on **every** inbound application message to detect failures, so on a
    high-rate session that is real per-message overhead (and the consumer's own
    decode in ``on_message`` is then a second pass). Leave it unset unless you
    need malformed messages surfaced; there is no cost when it is ``None``.
    """

    def __init__(
        self,
        signer: FixSigner,
        config: FixConfig,
        session_type: FixSessionType,
        *,
        on_message: MessageHandler | None = None,
        on_state_change: StateChangeHandler | None = None,
        on_decode_error: DecodeErrorHandler | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        config._check_session(session_type)
        self._signer = signer
        self._config = config
        self._session_type = session_type
        self._target = config.target_comp_id(session_type)
        self._supports_retransmission = config.supports_retransmission(session_type)
        self._on_message = on_message
        self._on_state_change = on_state_change
        # Routes registered-but-malformed inbound messages; see the class docstring
        # for the per-message decode cost this opts into. GH #432.
        self._on_decode_error = on_decode_error
        self._ssl_context = ssl_context

        self._hb = config.heartbeat_interval
        self._connection: FixConnection | None = None
        self._state = FixSessionState.DISCONNECTED
        self._running = False

        # Sequence numbers: next to send / next expected inbound.
        self._out_seq = 1
        self._in_seq = 1
        self._logged_on_once = False
        # Out-of-order inbound buffer (seq -> message) and resend bookkeeping.
        self._pending: dict[int, RawMessage] = {}
        self._resend_requested = False

        # Liveness bookkeeping (monotonic seconds).
        self._last_send = 0.0
        self._last_recv = 0.0
        self._test_request_outstanding = False
        self._test_req_counter = 0

        self._send_lock = asyncio.Lock()
        self._recv_task: asyncio.Task[None] | None = None
        self._hb_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> FixSessionState:
        """Current session state."""
        return self._state

    @property
    def session_type(self) -> FixSessionType:
        """The session type (TargetCompID) this session connects as."""
        return self._session_type

    @property
    def outbound_seq_num(self) -> int:
        """The MsgSeqNum that will be used for the next outbound message."""
        return self._out_seq

    @property
    def inbound_seq_num(self) -> int:
        """The MsgSeqNum expected on the next inbound message."""
        return self._in_seq

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> FixSession:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def start(self) -> None:
        """Connect, log on, and start the background recv + heartbeat tasks."""
        if self._running:
            raise RuntimeError("FixSession is already started")
        self._running = True
        try:
            await self._open_and_logon()
        except BaseException:
            self._running = False
            await self._close_connection()
            await self._set_state(FixSessionState.CLOSED)
            raise
        self._recv_task = asyncio.create_task(self._recv_loop())
        self._hb_task = asyncio.create_task(self._heartbeat_loop())

    async def close(self) -> None:
        """Stop background tasks, send a best-effort (bounded) Logout, close the socket.

        The heartbeat loop is cancelled first so it cannot race the Logout send,
        and the Logout is wrapped in a timeout so a dead/half-open connection
        (where ``writer.drain()`` never returns) cannot hang ``close()``.
        """
        self._running = False
        await self._cancel(self._hb_task)
        self._hb_task = None
        if self._state is FixSessionState.ACTIVE:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._send(Logout()), timeout=2.0)
        await self._cancel(self._recv_task)
        self._recv_task = None
        await self._close_connection()
        await self._set_state(FixSessionState.CLOSED)

    @staticmethod
    async def _cancel(task: asyncio.Task[None] | None) -> None:
        """Cancel a background task and await its teardown. Never raises."""
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send(self, message: FixMessage) -> int:
        """Send an application message; returns the assigned MsgSeqNum.

        Admin messages are managed by the session itself — use the typed
        order-entry / market-data helpers (later phases) rather than sending
        session-layer messages directly.
        """
        return await self._send(message)

    async def _send(self, message: FixMessage) -> int:
        async with self._send_lock:
            if self._connection is None or not self._connection.is_open:
                raise FixSessionError("cannot send: FIX connection is not open")
            seq = self._out_seq
            # Reserve the sequence number BEFORE handing bytes to the transport.
            # If the write fails after the bytes reached the peer, the number is
            # consumed (a recoverable gap) rather than silently reused for a
            # different message on the next reconnect.
            self._out_seq += 1
            sending_time = self._now_sending_time()
            # Logon's RawData signature is bound to this exact seq + sending_time.
            # Sign onto a COPY rather than mutating the caller's object (which a
            # caller might reuse across reconnects or inspect after send()).
            if isinstance(message, Logon):
                message = message.model_copy(
                    update={
                        "raw_data": self._signer.sign_logon(
                            sending_time=sending_time,
                            msg_seq_num=seq,
                            target_comp_id=self._target,
                        )
                    }
                )
            header: list[tuple[int, str]] = [
                (int(Tag.MSG_TYPE), type(message).MSG_TYPE.value),
                (int(Tag.SENDER_COMP_ID), self._signer.sender_comp_id),
                (int(Tag.TARGET_COMP_ID), self._target),
                (int(Tag.MSG_SEQ_NUM), str(seq)),
                (int(Tag.SENDING_TIME), sending_time),
            ]
            wire = encode(header + message.to_body_fields())
            await self._connection.send_bytes(wire)
            self._last_send = time.monotonic()
            return seq

    async def _send_gap_fill(self, begin_seq_no: int) -> None:
        """Reply to an inbound ResendRequest with an administrative gap-fill.

        We do not yet persist outbound application messages, so the only correct
        response is a SequenceReset/gap-fill covering ``[begin, NewSeqNo)``:
        MsgSeqNum=begin, PossDupFlag=Y. ``NewSeqNo`` is clamped to be strictly
        greater than ``begin`` (FIX requires NewSeqNo > MsgSeqNum) even when the
        peer asks to resend from a sequence at or beyond our next outbound — a
        real message store for true retransmission is a later phase.
        """
        async with self._send_lock:
            if self._connection is None or not self._connection.is_open:
                return
            # Deliberately NOT via _send(): a gap-fill must carry begin_seq_no as
            # its MsgSeqNum (not the next outbound slot) and must not consume an
            # outbound sequence number — _send() always assigns + increments _out_seq.
            sending_time = self._now_sending_time()
            new_seq_no = max(self._out_seq, begin_seq_no + 1)
            sr = SequenceReset(gap_fill_flag=True, new_seq_no=new_seq_no)
            header: list[tuple[int, str]] = [
                (int(Tag.MSG_TYPE), MsgType.SEQUENCE_RESET.value),
                (int(Tag.SENDER_COMP_ID), self._signer.sender_comp_id),
                (int(Tag.TARGET_COMP_ID), self._target),
                (int(Tag.MSG_SEQ_NUM), str(begin_seq_no)),
                (int(Tag.POSS_DUP_FLAG), "Y"),
                (int(Tag.SENDING_TIME), sending_time),
                (int(Tag.ORIG_SENDING_TIME), sending_time),
            ]
            wire = encode(header + sr.to_body_fields())
            await self._connection.send_bytes(wire)
            self._last_send = time.monotonic()

    def _now_sending_time(self) -> str:
        return format_utc_timestamp(datetime.now(UTC))

    # ------------------------------------------------------------------
    # Connect + logon
    # ------------------------------------------------------------------

    async def _open_and_logon(self) -> None:
        await self._set_state(FixSessionState.CONNECTING)
        host = self._config.host_for(self._session_type)
        port = self._config.port_for(self._session_type)
        self._connection = FixConnection(
            host,
            port,
            use_tls=self._config.use_tls,
            connect_timeout=self._config.connect_timeout,
            ssl_context=self._ssl_context,
        )
        await self._connection.open()

        # Reset policy: non-retransmission sessions always reset; retransmission
        # sessions reset only on their first-ever logon (we have no on-disk store
        # to resume across process restarts) and resume on reconnect.
        reset = (not self._supports_retransmission) or (not self._logged_on_once)
        if reset:
            self._out_seq = 1
            self._in_seq = 1
            self._pending.clear()
            self._resend_requested = False

        await self._set_state(FixSessionState.LOGGING_ON)
        logon = Logon(
            heartbeat_interval=self._hb,
            reset_seq_num_flag=True if reset else None,
            use_dollars=True if self._config.effective_use_dollars else None,
            cancel_orders_on_disconnect=True if self._config.cancel_orders_on_disconnect else None,
            listener_session=True if self._config.listener_session else None,
            skip_pending_exec_reports=True if self._config.skip_pending_exec_reports else None,
            # Pass through directly: None omits the tag (gateway default), True/False
            # explicitly opt in (RT) / out (PT).
            receive_settlement_reports=self._config.receive_settlement_reports,
        )
        await self._send(logon)

        try:
            raw = await asyncio.wait_for(
                self._connection.read_message(), timeout=self._config.connect_timeout
            )
        except TimeoutError as e:
            raise FixLogonError("timed out waiting for Logon response") from e
        self._last_recv = time.monotonic()

        mt = raw.msg_type
        if mt == MsgType.LOGOUT:
            raise FixLogonError("FIX logon rejected", reason=Logout.from_raw(raw).text)
        if mt != MsgType.LOGON:
            raise FixSessionError(f"expected Logon response, got MsgType={mt!r}")

        resp_seq = raw.seq_num if raw.seq_num is not None else self._in_seq
        need_resend = False
        if resp_seq == self._in_seq:
            self._in_seq = resp_seq + 1
        elif resp_seq > self._in_seq:
            if self._supports_retransmission:
                # Gap immediately after logon (retransmission session resuming):
                # buffer the logon and request the missing range.
                self._pending[resp_seq] = raw
                need_resend = True
            else:
                # NR/DC/RFQ/MD cannot recover a gap; per spec a too-high seq
                # terminates the session. Fail the logon.
                raise FixLogonError(
                    f"Logon response seq {resp_seq} ahead of expected {self._in_seq} on "
                    f"non-retransmission session {self._session_type.value}"
                )
        else:
            # Lower-than-expected Logon sequence: never rewind the inbound
            # watermark. A backwards seq signals a corrupt/duplicated server
            # session and is fatal per spec (do not silently re-process old
            # messages on reconnect).
            raise FixLogonError(
                f"Logon response seq {resp_seq} below expected {self._in_seq}; refusing to rewind"
            )

        self._logged_on_once = True
        self._test_request_outstanding = False
        await self._set_state(FixSessionState.ACTIVE)

        if need_resend:
            await self._request_resend()

    # ------------------------------------------------------------------
    # Receive loop + inbound handling
    # ------------------------------------------------------------------

    async def _recv_loop(self) -> None:
        assert self._connection is not None
        while self._running:
            try:
                raw = await self._connection.read_message()
            except asyncio.CancelledError:
                break
            except FixConnectionError:
                if not self._running:
                    break
                if not await self._reconnect():
                    self._running = False
                    break
                continue
            except Exception:
                # Malformed framing (FixCodecError) or unexpected error: skip the
                # frame and keep the session alive.
                logger.warning("skipping malformed FIX frame", exc_info=True)
                continue

            self._last_recv = time.monotonic()
            self._test_request_outstanding = False
            try:
                await self._handle_inbound(raw)
            except FixSequenceError:
                logger.error("unrecoverable FIX sequence error; closing session", exc_info=True)
                self._running = False
                await self._close_connection()
                await self._set_state(FixSessionState.CLOSED)
                break
            except (FixConnectionError, FixSessionError):
                # An admin reply (Heartbeat / ResendRequest gap-fill) failed
                # because the socket dropped between the read and the reply.
                # Recover via the same reconnect path used for read failures
                # rather than letting the recv loop die with the session wedged.
                if not self._running:
                    break
                logger.warning(
                    "FIX send failed while handling inbound message; reconnecting",
                    exc_info=True,
                )
                if not await self._reconnect():
                    self._running = False
                    break
            except Exception:
                # Backstop: no unexpected error may silently kill the recv loop
                # and leave the session wedged in ACTIVE. Log and keep reading;
                # genuine sequence/connection failures are handled above.
                logger.exception("unexpected error handling inbound FIX message; continuing")

    async def _handle_inbound(self, raw: RawMessage) -> None:
        mt = raw.msg_type

        if mt == MsgType.SEQUENCE_RESET:
            await self._handle_sequence_reset(raw)
            return

        seq = raw.seq_num
        if seq is None:
            logger.warning("inbound FIX message %r without MsgSeqNum; ignoring", mt)
            return

        if seq == self._in_seq:
            await self._safe_process(raw, mt, seq)
            self._in_seq += 1
            await self._drain_pending()
        elif seq < self._in_seq:
            if raw.get(Tag.POSS_DUP_FLAG) == "Y":
                # Legitimate retransmission of an already-processed message.
                logger.debug("ignoring PossDup inbound seq %d (expected %d)", seq, self._in_seq)
            else:
                # Per spec a lower-than-expected MsgSeqNum without PossDupFlag is
                # a fatal session error — terminate rather than silently skip.
                raise FixSequenceError(
                    f"inbound MsgSeqNum {seq} below expected {self._in_seq} without PossDupFlag",
                    expected=self._in_seq,
                    received=seq,
                )
        else:
            # Forward gap.
            self._pending[seq] = raw
            if self._supports_retransmission:
                await self._request_resend()
            else:
                raise FixSequenceError(
                    f"forward sequence gap on non-retransmission session "
                    f"{self._session_type.value}",
                    expected=self._in_seq,
                    received=seq,
                )

    async def _handle_sequence_reset(self, raw: RawMessage) -> None:
        """Apply an inbound SequenceReset, honoring sequencing rules.

        GapFill mode participates in sequencing via its own MsgSeqNum: a gap-fill
        arriving ahead of the expected inbound seq is itself a gap (recover on
        RT/PT, fatal otherwise). Both gap-fill and reset mode only ever move the
        watermark FORWARD — a stale/duplicate reset never rewinds (which would
        re-process already-delivered messages).
        """
        try:
            sr = SequenceReset.from_raw(raw)
        except (ValidationError, ValueError):
            logger.warning("malformed inbound SequenceReset; ignoring", exc_info=True)
            return

        seq = raw.seq_num
        if bool(sr.gap_fill_flag) and seq is not None and seq > self._in_seq:
            # Out-of-order gap-fill: it is itself ahead of the expected seq.
            # Buffer it so _drain_pending applies its NewSeqNo jump once the
            # preceding gap is recovered (RT/PT); otherwise it is unrecoverable.
            if self._supports_retransmission:
                self._pending[seq] = raw
                await self._request_resend()
                return
            raise FixSequenceError(
                f"SequenceReset gap-fill at seq {seq} ahead of expected {self._in_seq} on "
                f"non-retransmission session {self._session_type.value}",
                expected=self._in_seq,
                received=seq,
            )

        self._apply_sequence_reset_forward(sr)
        await self._drain_pending()

    def _apply_sequence_reset_forward(self, sr: SequenceReset) -> None:
        """Advance the expected inbound counter to ``NewSeqNo`` (forward only).

        Never rewinds (a stale/duplicate reset must not re-process delivered
        messages); drops any buffered messages now behind the watermark.
        """
        if sr.new_seq_no > self._in_seq:
            self._in_seq = sr.new_seq_no
        for s in [s for s in self._pending if s < self._in_seq]:
            del self._pending[s]
        if not self._pending:
            self._resend_requested = False

    async def _drain_pending(self) -> None:
        """Process buffered out-of-order messages now made contiguous."""
        while self._in_seq in self._pending:
            raw = self._pending.pop(self._in_seq)
            if raw.msg_type == MsgType.SEQUENCE_RESET:
                # A buffered gap-fill SequenceReset applies its own NewSeqNo jump
                # (it does not consume a single slot), so route it through the
                # reset logic rather than _safe_process.
                try:
                    sr = SequenceReset.from_raw(raw)
                except (ValidationError, ValueError):
                    logger.warning("malformed buffered SequenceReset; skipping", exc_info=True)
                    self._in_seq += 1
                    continue
                self._apply_sequence_reset_forward(sr)
            else:
                await self._safe_process(raw, raw.msg_type, self._in_seq)
                self._in_seq += 1
        if not self._pending:
            self._resend_requested = False

    async def _safe_process(self, raw: RawMessage, mt: str | None, seq: int) -> None:
        """Process one in-order message; a malformed admin payload becomes a Reject.

        A schema/parse failure on an admin message must not crash the recv loop —
        treat it as consumed (the caller still advances ``_in_seq``) and answer
        with a session-level Reject (35=3) rather than wedging the session.
        """
        try:
            await self._process(raw, mt)
        except (ValidationError, ValueError):
            logger.warning("malformed inbound %s at seq %d; sending Reject", mt, seq, exc_info=True)
            with contextlib.suppress(FixConnectionError, FixSessionError):
                await self._send(Reject(ref_seq_num=seq))

    async def _process(self, raw: RawMessage, mt: str | None) -> None:
        """Dispatch one in-order message (admin handled here, app to callback)."""
        if mt == MsgType.HEARTBEAT:
            return
        if mt == MsgType.TEST_REQUEST:
            await self._send(Heartbeat(test_req_id=TestRequest.from_raw(raw).test_req_id))
            return
        if mt == MsgType.RESEND_REQUEST:
            if self._supports_retransmission:
                await self._send_gap_fill(ResendRequest.from_raw(raw).begin_seq_no)
            else:
                # NR/DC/RFQ/MD do not support retransmission; an inbound
                # ResendRequest is anomalous — log and ignore rather than emit an
                # invalid recovery message.
                logger.warning(
                    "ignoring inbound ResendRequest on non-retransmission session %s",
                    self._session_type.value,
                )
            return
        if mt == MsgType.LOGOUT:
            logger.info("received Logout from peer: %s", Logout.from_raw(raw).text)
            self._running = False
            await self._close_connection()
            await self._set_state(FixSessionState.CLOSED)
            return
        if mt == MsgType.LOGON:
            # A mid-session Logon is a protocol anomaly once ACTIVE; log and
            # ignore (Kalshi's gateway drives session lifecycle via Logout).
            logger.warning("unexpected mid-session Logon from peer; ignoring")
            return
        if mt == MsgType.REJECT:
            rj = Reject.from_raw(raw)
            logger.warning(
                "FIX session Reject: refSeqNum=%s reason=%s text=%r",
                rj.ref_seq_num,
                rj.session_reject_reason,
                rj.text,
            )
            return
        # Application message. Isolate consumer callback failures so a buggy
        # handler cannot tear down the session (the message's seq is already
        # accounted for by the caller).
        if self._on_decode_error is not None:
            # Detect a registered-but-malformed message and route it, so a fill
            # lost to one off-spec field is observable rather than silently None.
            try:
                decode_app_message_strict(raw)
            except FixDecodeError as exc:
                try:
                    await self._on_decode_error(raw, exc)
                except Exception:
                    logger.exception("FIX on_decode_error callback raised; continuing session")
        if self._on_message is not None:
            try:
                await self._on_message(raw)
            except Exception:
                logger.exception("FIX on_message callback raised; continuing session")

    async def _request_resend(self) -> None:
        if self._resend_requested:
            return
        self._resend_requested = True
        # end=0 means "through the latest message".
        await self._send(ResendRequest(begin_seq_no=self._in_seq, end_seq_no=0))

    # ------------------------------------------------------------------
    # Heartbeat / liveness
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        interval = self._hb
        while self._running:
            await asyncio.sleep(interval / 2)
            if not self._running:
                break
            if self._state is not FixSessionState.ACTIVE:
                continue
            now = time.monotonic()
            try:
                if _heartbeat_due(now, self._last_send, interval):
                    await self._send(Heartbeat())
                liveness = _liveness(now, self._last_recv, interval)
                if liveness == "dead":
                    logger.warning(
                        "FIX peer silent for %.1fs (interval %ds); forcing reconnect",
                        now - self._last_recv,
                        interval,
                    )
                    # Drop the socket; the recv loop observes EOF and reconnects.
                    await self._close_connection()
                elif liveness == "test_request" and not self._test_request_outstanding:
                    self._test_request_outstanding = True
                    self._test_req_counter += 1
                    await self._send(TestRequest(test_req_id=f"TR{self._test_req_counter}"))
            except (FixConnectionError, FixSessionError):
                # Transition in flight (closing / reconnecting); let the recv loop drive.
                continue

    # ------------------------------------------------------------------
    # Reconnect
    # ------------------------------------------------------------------

    async def _reconnect(self) -> bool:
        """Reconnect with AWS full-jitter backoff. Returns True on success."""
        await self._close_connection()
        await self._set_state(FixSessionState.RECONNECTING)
        last_exc: BaseException | None = None
        for attempt in range(self._config.max_retries):
            delay = random.uniform(
                0,
                min(
                    self._config.retry_max_delay,
                    self._config.retry_base_delay * (2**attempt),
                ),
            )
            logger.warning(
                "FIX reconnect in %.1fs (attempt %d/%d)",
                delay,
                attempt + 1,
                self._config.max_retries,
            )
            await asyncio.sleep(delay)
            if not self._running:
                return False
            try:
                await self._open_and_logon()
                return True
            except Exception as exc:
                last_exc = exc
                logger.debug("FIX reconnect attempt %d failed", attempt + 1, exc_info=True)
                continue
        await self._set_state(FixSessionState.CLOSED)
        logger.error(
            "FIX reconnect exhausted %d attempts", self._config.max_retries, exc_info=last_exc
        )
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _close_connection(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def _set_state(self, new_state: FixSessionState) -> None:
        old = self._state
        if old is new_state:
            return
        self._state = new_state
        logger.debug("FIX session state: %s -> %s", old.value, new_state.value)
        if self._on_state_change is not None:
            await self._on_state_change(old, new_state)
