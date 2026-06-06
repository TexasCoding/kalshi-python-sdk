"""Hand-rolled FIX tag=value codec (SOH framing, BodyLength, CheckSum).

No third-party FIX library: this is a pure-Python encoder/decoder plus an
incremental stream parser. Three responsibilities:

* :func:`encode` — assemble an ordered ``(tag, value)`` field list into wire
  bytes, computing ``BodyLength`` (tag 9) and the 3-digit ``CheckSum`` (tag 10)
  and prepending ``BeginString`` (tag 8).
* :func:`decode` — parse one *complete* message's bytes into a
  :class:`RawMessage`, validating the checksum and body length. Length-prefixed
  data fields (``RawData``/``Signature``) are read by byte count so an embedded
  SOH in the value cannot corrupt framing.
* :class:`FixParser` — buffer raw TCP reads and hand back complete messages.
  Framing is *deterministic*: ``BodyLength`` tells us exactly how many body
  bytes follow, so we never scan for SOH to find message boundaries.

Values are carried as ``str`` (decoded latin-1, a reversible 1:1 byte mapping —
Kalshi FIX values are ASCII, and latin-1 round-trips any byte without error so
framing stays byte-accurate even on unexpected input).
"""

from __future__ import annotations

import logging

from kalshi.fix.errors import FixCodecError
from kalshi.fix.tags import DATA_LENGTH_FIELDS, Tag

logger = logging.getLogger("kalshi.fix")

SOH = b"\x01"
"""The FIX field delimiter (Start Of Header, ASCII 0x01)."""

BEGIN_STRING_FIXT11 = "FIXT.1.1"
"""Kalshi runs the FIXT.1.1 transport (application layer is FIX50SP2)."""

# A correct message ends with the fixed-width trailer ``10=NNN\x01`` (CheckSum is
# always modulo 256, zero-padded to three digits) — exactly 7 bytes.
_CHECKSUM_FIELD_LEN = 7

# Guard against an unbounded buffer when a malformed/garbage BodyLength is read
# off the wire. Kalshi FIX application messages are well under this; the value is
# a denial-of-service backstop, not a real protocol limit.
MAX_BODY_LENGTH = 1_000_000

# Max digits a plausible BodyLength field may have (digit width of
# MAX_BODY_LENGTH plus slack). Bounds the pre-frame buffer so an un-terminated
# BodyLength field cannot force unbounded buffering before the MAX_BODY_LENGTH
# check is reached.
_MAX_BODYLEN_DIGITS = len(str(MAX_BODY_LENGTH)) + 2

# Values redacted in :meth:`RawMessage.__repr__` so the logon signature and any
# credential never reach logs / tracebacks / exception sinks.
_REDACTED_TAGS = frozenset({Tag.RAW_DATA, Tag.SIGNATURE, Tag.PASSWORD})

# Length-prefixed DATA fields whose value may legally contain the SOH delimiter
# (they are framed by their preceding length field, not by SOH-scanning).
_DATA_TAGS = frozenset(DATA_LENGTH_FIELDS.values())


def encode(fields: list[tuple[int, str]], *, begin_string: str = BEGIN_STRING_FIXT11) -> bytes:
    """Encode an ordered field list into a complete FIX wire message.

    ``fields`` must be the ordered ``(tag, value)`` pairs starting with
    ``(35, MsgType)`` followed by the remaining header fields, the body, and any
    trailer fields *other than* CheckSum. ``BeginString`` (8), ``BodyLength``
    (9), and ``CheckSum`` (10) are computed here and must not appear in
    ``fields``.

    Per FIXT.1.1, ``BodyLength`` counts every byte from the start of the
    MsgType field (the byte after the SOH that terminates BodyLength) up to and
    including the SOH that immediately precedes the CheckSum field.
    """
    if not fields:
        raise FixCodecError("cannot encode an empty field list")
    for tag, value in fields:
        if tag in (Tag.BEGIN_STRING, Tag.BODY_LENGTH, Tag.CHECK_SUM):
            raise FixCodecError(
                f"tag {int(tag)} (BeginString/BodyLength/CheckSum) is computed by "
                "encode() and must not be supplied in the field list"
            )
        # Reject SOH in non-DATA fields: a caller-controlled value containing the
        # delimiter would otherwise smuggle extra tags into a checksum-valid
        # message. DATA fields (RawData/Signature) are length-prefixed and may
        # legally contain SOH.
        if tag not in _DATA_TAGS and "\x01" in value:
            raise FixCodecError(f"SOH (0x01) is not allowed in non-data field {int(tag)}")
    if fields[0][0] != Tag.MSG_TYPE:
        raise FixCodecError(
            f"first encoded field must be MsgType (35), got tag {int(fields[0][0])}"
        )

    body = b"".join(
        f"{int(tag)}=".encode("ascii") + value.encode("latin-1") + SOH for tag, value in fields
    )
    header = (
        b"8=" + begin_string.encode("ascii") + SOH + b"9=" + str(len(body)).encode("ascii") + SOH
    )
    without_checksum = header + body
    checksum = sum(without_checksum) % 256
    return without_checksum + b"10=" + f"{checksum:03d}".encode("ascii") + SOH


def _parse_fields(data: bytes) -> list[tuple[int, str]]:
    """Parse ``tag=value\\x01`` pairs from ``data`` (no trailing CheckSum field).

    Honors :data:`kalshi.fix.tags.DATA_LENGTH_FIELDS`: when a length field is
    seen, the immediately following data field's value is read by exact byte
    count rather than by scanning for the next SOH.
    """
    pairs: list[tuple[int, str]] = []
    i = 0
    n = len(data)
    expected_data_tag: int | None = None
    expected_data_len = 0
    while i < n:
        eq = data.find(b"=", i)
        if eq == -1:
            raise FixCodecError("field without '=' separator", raw=data[i : i + 64])
        try:
            tag = int(data[i:eq])
        except ValueError:
            raise FixCodecError(f"non-integer tag {data[i:eq]!r}", raw=data[i : i + 64]) from None
        vstart = eq + 1
        if expected_data_tag is not None:
            # A length field MUST be immediately followed by its data field; a
            # mismatch would let arbitrary tag=value pairs be smuggled inside the
            # declared byte length while keeping BodyLength/CheckSum valid.
            if tag != expected_data_tag:
                raise FixCodecError(
                    f"data field tag {expected_data_tag} must immediately follow its length "
                    f"field, got tag {tag}",
                    raw=data[i : i + 64],
                )
            vend = vstart + expected_data_len
            if vend > n or data[vend : vend + 1] != SOH:
                raise FixCodecError(
                    f"data field {tag} length {expected_data_len} overruns message",
                    raw=data[i : i + 64],
                )
            value = data[vstart:vend]
            soh = vend
            expected_data_tag = None
        else:
            soh = data.find(SOH, vstart)
            if soh == -1:
                raise FixCodecError(f"field {tag} not SOH-terminated", raw=data[i : i + 64])
            value = data[vstart:soh]
        pairs.append((tag, value.decode("latin-1")))
        if tag in DATA_LENGTH_FIELDS:
            try:
                expected_data_len = int(value)
            except ValueError:
                raise FixCodecError(
                    f"length field {tag} has non-integer value {value!r}",
                    raw=data[i : i + 64],
                ) from None
            expected_data_tag = DATA_LENGTH_FIELDS[tag]
        i = soh + 1
    return pairs


def decode(data: bytes) -> RawMessage:
    """Decode one complete FIX message's bytes into a :class:`RawMessage`.

    ``data`` must be exactly one frame: ``8=...`` through the SOH that
    terminates the CheckSum field. Validates that the message begins with
    ``BeginString``, that ``BodyLength`` matches the bytes on the wire, and that
    the ``CheckSum`` is correct.
    """
    if len(data) < _CHECKSUM_FIELD_LEN or not data.startswith(b"8="):
        raise FixCodecError("message does not begin with BeginString (tag 8)", raw=data[:64])
    if not data.endswith(SOH):
        raise FixCodecError("message not SOH-terminated", raw=data[-64:])

    checksum_start = len(data) - _CHECKSUM_FIELD_LEN
    if data[checksum_start : checksum_start + 3] != b"10=":
        raise FixCodecError("message does not end with CheckSum (tag 10)", raw=data[-64:])
    try:
        declared_checksum = int(data[checksum_start + 3 : checksum_start + 6])
    except ValueError:
        raise FixCodecError("CheckSum value is not a 3-digit integer", raw=data[-64:]) from None
    computed = sum(data[:checksum_start]) % 256
    if computed != declared_checksum:
        raise FixCodecError(
            f"CheckSum mismatch: declared {declared_checksum:03d}, computed {computed:03d}",
            raw=data[:64],
        )

    # Validate BodyLength against the actual framed body (tags 8 and 9 are always
    # the first two fields, so the body starts after the second SOH).
    soh1 = data.find(SOH)
    soh2 = data.find(SOH, soh1 + 1)
    if soh1 == -1 or soh2 == -1 or data[soh1 + 1 : soh1 + 3] != b"9=":
        raise FixCodecError("BodyLength (tag 9) must immediately follow BeginString", raw=data[:64])
    try:
        declared_body_len = int(data[soh1 + 3 : soh2])
    except ValueError:
        raise FixCodecError("BodyLength value is not an integer", raw=data[:64]) from None
    actual_body_len = checksum_start - (soh2 + 1)
    if declared_body_len != actual_body_len:
        raise FixCodecError(
            f"BodyLength mismatch: declared {declared_body_len}, actual {actual_body_len}",
            raw=data[:64],
        )

    pairs = _parse_fields(data[:checksum_start])
    pairs.append((int(Tag.CHECK_SUM), f"{declared_checksum:03d}"))
    return RawMessage(pairs)


class RawMessage:
    """An ordered, decoded FIX message as ``(tag, value)`` string pairs.

    The low-level wire representation used by the codec and the session state
    machine. Typed Pydantic models (:mod:`kalshi.fix.messages`) are built from /
    rendered to this. Tag lookups are linear scans — FIX messages are small.
    """

    __slots__ = ("pairs",)

    def __init__(self, pairs: list[tuple[int, str]]) -> None:
        self.pairs = pairs

    def get(self, tag: int) -> str | None:
        """First value for ``tag``, or ``None``."""
        for t, v in self.pairs:
            if t == tag:
                return v
        return None

    def get_all(self, tag: int) -> list[str]:
        """All values for ``tag`` in order (repeating-group fields)."""
        return [v for t, v in self.pairs if t == tag]

    def get_int(self, tag: int) -> int | None:
        """First value for ``tag`` parsed as ``int``, or ``None`` if absent.

        Raises :class:`FixCodecError` if present but not an integer.
        """
        v = self.get(tag)
        if v is None:
            return None
        try:
            return int(v)
        except ValueError:
            raise FixCodecError(f"tag {tag} value {v!r} is not an integer") from None

    @property
    def msg_type(self) -> str | None:
        """The MsgType (tag 35) value."""
        return self.get(Tag.MSG_TYPE)

    @property
    def seq_num(self) -> int | None:
        """The MsgSeqNum (tag 34) value."""
        return self.get_int(Tag.MSG_SEQ_NUM)

    def __repr__(self) -> str:
        rendered = " ".join(
            f"{t}={'<redacted>' if t in _REDACTED_TAGS else v}" for t, v in self.pairs
        )
        return f"RawMessage({rendered})"


class FixParser:
    """Incremental FIX frame extractor over a byte stream.

    Feed raw socket reads with :meth:`append`; pull complete messages with
    :meth:`get_message` (one at a time) or :meth:`messages` (all currently
    available). Partial frames stay buffered until the rest arrives. Framing is
    by ``BodyLength`` byte count, so a value containing SOH never splits a frame.
    """

    __slots__ = ("_buf", "_expected_header")

    def __init__(self, begin_string: str = BEGIN_STRING_FIXT11) -> None:
        self._buf = bytearray()
        # The exact bytes a real frame must start with, e.g. b"8=FIXT.1.1\x01".
        # Used both to resync past a false "8=" inside junk and to know where
        # the BodyLength field begins.
        self._expected_header = b"8=" + begin_string.encode("ascii") + SOH

    def append(self, data: bytes) -> None:
        """Add bytes read from the socket to the parse buffer."""
        self._buf.extend(data)

    def get_message(self) -> RawMessage | None:
        """Extract and return the next complete message, or ``None`` if incomplete.

        Resynchronizes across junk: a ``8=`` that is not a genuine BeginString
        (its value is not the expected ``BeginString``) is skipped rather than
        treated as a frame, so a stray ``8=`` in inter-frame noise cannot abort
        the session or consume a valid frame that follows. Every code path that
        raises first advances the buffer past the offending marker, so a caught
        :class:`FixCodecError` cannot make the read loop spin on the same bytes.
        """
        buf = self._buf
        expected = self._expected_header
        hlen = len(expected)
        while True:
            start = buf.find(b"8=")
            if start == -1:
                # No BeginString marker yet. Keep a trailing byte in case "8="
                # is split across two reads.
                if len(buf) > 1:
                    del buf[:-1]
                return None
            if start > 0:
                del buf[: start]

            n = len(buf)
            if n < hlen:
                # Incomplete: wait only if what we have is a prefix of the real
                # header; otherwise this "8=" is a false marker — skip it.
                if expected.startswith(bytes(buf)):
                    return None
                del buf[:2]
                continue
            if not buf.startswith(expected):
                # A "8=" whose BeginString value isn't ours — junk; resync.
                del buf[:2]
                continue

            # Genuine BeginString. BodyLength ("9=<digits>\x01") follows it.
            if n < hlen + 2:
                return None  # wait for the "9=" marker
            if bytes(buf[hlen : hlen + 2]) != b"9=":
                del buf[:2]  # advance before raising (no busy-loop)
                raise FixCodecError(
                    "BodyLength (tag 9) must immediately follow BeginString",
                    raw=bytes(buf[:64]),
                )
            soh2 = buf.find(SOH, hlen + 2)
            if soh2 == -1:
                if n - (hlen + 2) > _MAX_BODYLEN_DIGITS:
                    del buf[:2]
                    raise FixCodecError(
                        "BodyLength field too long / not SOH-terminated", raw=bytes(buf[:64])
                    )
                return None  # wait for the SOH terminating BodyLength
            try:
                body_len = int(buf[hlen + 2 : soh2])
            except ValueError:
                del buf[:2]
                raise FixCodecError(
                    "BodyLength value is not an integer", raw=bytes(buf[:64])
                ) from None
            if body_len < 0 or body_len > MAX_BODY_LENGTH:
                del buf[:2]
                raise FixCodecError(f"implausible BodyLength {body_len}", raw=bytes(buf[:64]))

            end = soh2 + 1 + body_len + _CHECKSUM_FIELD_LEN
            if n < end:
                return None  # frame not fully arrived yet

            msg_bytes = bytes(buf[:end])
            try:
                msg = decode(msg_bytes)
            except FixCodecError:
                # Corrupt frame (CheckSum / BodyLength inconsistency). A corrupted
                # BodyLength could have made `end` over-reach into the next frame,
                # so do NOT consume the whole span — skip past this BeginString
                # marker and resync, preserving any valid frame that follows.
                logger.warning("discarding corrupt FIX frame; resyncing")
                del buf[:2]
                continue
            del buf[:end]
            return msg

    def messages(self) -> list[RawMessage]:
        """Drain and return all currently-complete messages."""
        out: list[RawMessage] = []
        while True:
            msg = self.get_message()
            if msg is None:
                return out
            out.append(msg)
