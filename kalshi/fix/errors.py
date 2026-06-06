"""Exception hierarchy for the Kalshi FIX subsystem.

Mirrors the WebSocket error pattern in :mod:`kalshi.errors`: a single
``KalshiFixError`` base (extending the SDK-wide :class:`kalshi.errors.KalshiError`
so a caller can ``except KalshiError`` across REST / WS / FIX) with subclasses
that carry structured context fields rather than forcing callers to parse
message strings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kalshi.errors import KalshiError

if TYPE_CHECKING:
    from kalshi.fix.codec import RawMessage


class KalshiFixError(KalshiError):
    """Base exception for all Kalshi FIX errors.

    FIX is a TCP/TLS protocol with no HTTP status, so ``status_code`` is always
    ``None`` (the field exists on :class:`kalshi.errors.KalshiError` for the
    REST transport and is kept for cross-surface ``except KalshiError`` use).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=None)


class FixConnectionError(KalshiFixError):
    """TCP/TLS connection failed, was refused, or max reconnect attempts exceeded.

    The original transport exception (``OSError`` / ``ssl.SSLError`` /
    ``asyncio.TimeoutError``) is chained via ``__cause__``.
    """


class FixCodecError(KalshiFixError):
    """A FIX frame could not be encoded or decoded.

    Raised on malformed framing — missing ``BeginString`` / ``BodyLength`` /
    ``CheckSum``, a ``BodyLength`` that disagrees with the bytes on the wire, a
    ``CheckSum`` mismatch, or a field that is not ``tag=value``. ``raw`` carries
    the offending bytes (truncated) for debugging when available.
    """

    def __init__(self, message: str, *, raw: bytes | None = None) -> None:
        self.raw = raw
        super().__init__(message)


class FixLogonError(KalshiFixError):
    """Logon (35=A) was rejected by the acceptor.

    The acceptor answers a failed Logon with a Logout (35=5) carrying a
    human-readable ``Text`` (58); that text is surfaced in ``reason`` when
    present. Common causes: bad RawData signature, SendingTime outside the 30s
    skew window (``SessionRejectReason=10``), unknown CompID, or a missing
    ``ResetSeqNumFlag=Y`` on a non-retransmission session.
    """

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason
        super().__init__(message)


class FixSessionError(KalshiFixError):
    """A session-level protocol violation or unexpected lifecycle event.

    Covers an unexpected Logout, a liveness failure (no Heartbeat/TestRequest
    response within the interval), or an inbound message that breaks the session
    state machine.
    """


class FixSequenceError(KalshiFixError):
    """An unrecoverable sequence-number condition.

    Two cases, both fatal to the session:

    * The acceptor's ``MsgSeqNum`` is *lower* than expected (per spec the
      connection is terminated — a lower number means the peer's view of the
      session is corrupt).
    * A forward gap was detected on a session that does not support
      retransmission (``KalshiNR`` / ``KalshiDC``), so it cannot be recovered
      via ``ResendRequest``.
    """

    def __init__(
        self,
        message: str,
        *,
        expected: int | None = None,
        received: int | None = None,
    ) -> None:
        self.expected = expected
        self.received = received
        super().__init__(message)


class FixDecodeError(KalshiFixError):
    """A registered inbound application message failed schema validation.

    Distinguishes a *malformed* known message (a real message with an off-spec
    field — e.g. a bad ``DollarDecimal`` / ``FixedPointCount``) from an
    *unregistered* message type. :func:`~kalshi.fix.messages.decode_app_message`
    collapses both to ``None``;
    :func:`~kalshi.fix.messages.decode_app_message_strict` raises this for the
    former so the failure is observable (see ``FixSession``'s ``on_decode_error``
    hook). ``raw`` carries the offending message and ``msg_type`` its ``MsgType``
    (both always present); the underlying validation error chains via ``__cause__``.
    """

    def __init__(self, message: str, *, raw: RawMessage, msg_type: str) -> None:
        self.raw = raw
        self.msg_type = msg_type
        super().__init__(message)


class FixRejectError(KalshiFixError):
    """The acceptor rejected a message we sent.

    Raised for an inbound session-level Reject (35=3) or BusinessMessageReject
    (35=j). Carries the structured reject fields so callers can route on them
    without parsing ``Text``.
    """

    def __init__(
        self,
        message: str,
        *,
        ref_seq_num: int | None = None,
        ref_tag_id: int | None = None,
        ref_msg_type: str | None = None,
        reject_reason: int | None = None,
        text: str | None = None,
    ) -> None:
        self.ref_seq_num = ref_seq_num
        self.ref_tag_id = ref_tag_id
        self.ref_msg_type = ref_msg_type
        self.reject_reason = reject_reason
        self.text = text
        super().__init__(message)
