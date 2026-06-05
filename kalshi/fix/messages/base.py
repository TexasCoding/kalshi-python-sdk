"""Typed FIX message framework: Pydantic models that round-trip to wire fields.

Each message subclasses :class:`FixMessage` and declares its body fields with
:func:`fixfield`, attaching the FIX tag number and wire type to the Pydantic
field via ``json_schema_extra``. The base then drives:

* :meth:`FixMessage.to_body_fields` — ordered ``(tag, value)`` pairs for the
  message body (everything after the standard header), with length-prefixed
  data fields (``RawData``/``Signature``) auto-emitting their length field.
* :meth:`FixMessage.from_raw` — build a typed model from a decoded
  :class:`~kalshi.fix.codec.RawMessage`, reading only the tags it declares
  (unknown/header tags are ignored, so inbound messages with extra fields
  parse cleanly).

The standard header (``SenderCompID``/``TargetCompID``/``MsgSeqNum``/
``SendingTime``) and ``MsgType`` are owned by the session/connection layer, not
the message body — see :mod:`kalshi.fix.session`.

Scope note: scalar fields only. Repeating groups (``NoPartyIDs``, ``NoMiscFees``,
…) land with the order-entry / settlement message phases; see GH #402.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field

from kalshi.fix.codec import RawMessage
from kalshi.fix.enums import MsgType
from kalshi.fix.tags import DATA_LENGTH_FIELDS

# Reverse of DATA_LENGTH_FIELDS: data_tag -> length_tag. Used by to_body_fields
# to auto-emit the length field immediately before a data field.
_DATA_TO_LENGTH: dict[int, int] = {data: length for length, data in DATA_LENGTH_FIELDS.items()}


class FixType(StrEnum):
    """Wire type of a FIX field, governing string<->Python conversion."""

    STRING = "STRING"
    CHAR = "CHAR"
    MULTIPLEVALUESTRING = "MULTIPLEVALUESTRING"
    INT = "INT"
    SEQNUM = "SEQNUM"
    LENGTH = "LENGTH"
    NUMINGROUP = "NUMINGROUP"
    BOOLEAN = "BOOLEAN"
    PRICE = "PRICE"
    QTY = "QTY"
    AMT = "AMT"
    DECIMAL = "DECIMAL"
    CURRENCY = "CURRENCY"
    UTCTIMESTAMP = "UTCTIMESTAMP"
    LOCALMKTDATE = "LOCALMKTDATE"
    DATA = "DATA"


_INT_TYPES = frozenset({FixType.INT, FixType.SEQNUM, FixType.LENGTH, FixType.NUMINGROUP})
_DECIMAL_TYPES = frozenset({FixType.PRICE, FixType.QTY, FixType.AMT, FixType.DECIMAL})


def fixfield(tag: int, fix_type: FixType, *, default: Any = ..., **kwargs: Any) -> Any:
    """Declare a FIX-mapped Pydantic field.

    ``tag`` is the FIX tag number, ``fix_type`` its wire type. Omit ``default``
    for a required field (Pydantic treats ``...`` as required). The metadata
    rides on ``json_schema_extra`` so the base can introspect tag + type in
    declaration order.
    """
    extra: dict[str, Any] = {"fix_tag": int(tag), "fix_type": fix_type.value}
    return Field(default=default, json_schema_extra=extra, **kwargs)


def _to_wire(value: Any, fix_type: FixType) -> str:
    """Convert a Python field value to its FIX wire string."""
    if fix_type is FixType.BOOLEAN:
        return "Y" if value else "N"
    if fix_type in _DECIMAL_TYPES:
        # value is a Decimal; ``f"{d:f}"`` avoids scientific notation and float drift.
        return f"{value:f}"
    if fix_type is FixType.UTCTIMESTAMP:
        return _format_utc_timestamp(value)
    if fix_type is FixType.LOCALMKTDATE:
        return value if isinstance(value, str) else value.strftime("%Y%m%d")
    # STRING / CHAR / MULTIPLEVALUESTRING / INT-likes / enums. ``str()`` of a
    # StrEnum is its value; of an IntEnum (Py3.11+) its integer — both correct.
    return str(value)


def _from_wire(raw: str, fix_type: FixType) -> Any:
    """Convert a FIX wire string to a Python value Pydantic can validate.

    Enum-typed fields are returned as the underlying ``int``/``str`` and coerced
    to the enum by Pydantic at construction.
    """
    if fix_type is FixType.BOOLEAN:
        if raw == "Y":
            return True
        if raw == "N":
            return False
        raise ValueError(f"invalid FIX boolean {raw!r} (expected 'Y' or 'N')")
    if fix_type in _INT_TYPES:
        return int(raw)
    if fix_type in _DECIMAL_TYPES:
        return Decimal(raw)
    if fix_type is FixType.UTCTIMESTAMP:
        return _parse_utc_timestamp(raw)
    return raw


def _format_utc_timestamp(dt: datetime) -> str:
    """FIX UTCTimestamp with millisecond precision: ``YYYYMMDD-HH:MM:SS.sss``."""
    return dt.strftime("%Y%m%d-%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def _parse_utc_timestamp(value: str) -> datetime:
    """Parse a FIX UTCTimestamp (with or without fractional seconds) as UTC-aware."""
    fmt = "%Y%m%d-%H:%M:%S.%f" if "." in value else "%Y%m%d-%H:%M:%S"
    return datetime.strptime(value, fmt).replace(tzinfo=UTC)


class FixMessage(BaseModel):
    """Base for all typed FIX messages.

    Subclasses set the ``MSG_TYPE`` class var and declare body fields with
    :func:`fixfield`. ``extra="forbid"`` makes a typo in an outbound message
    fail at construction; inbound messages are built via :meth:`from_raw`, which
    only passes declared tags, so server-added fields never reach the
    constructor.
    """

    MSG_TYPE: ClassVar[MsgType]

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def _fix_fields(cls) -> list[tuple[str, int, FixType]]:
        """``(attr_name, tag, fix_type)`` for each FIX-mapped field, in declaration order."""
        out: list[tuple[str, int, FixType]] = []
        for name, field in cls.model_fields.items():
            extra = field.json_schema_extra
            if isinstance(extra, dict) and "fix_tag" in extra:
                tag = int(extra["fix_tag"])  # type: ignore[arg-type]
                fix_type = FixType(str(extra["fix_type"]))
                out.append((name, tag, fix_type))
        return out

    def to_body_fields(self) -> list[tuple[int, str]]:
        """Ordered ``(tag, value)`` body fields (excludes the standard header).

        ``None`` values are omitted. A data field auto-emits its length field
        immediately before it.
        """
        out: list[tuple[int, str]] = []
        for name, tag, fix_type in self._fix_fields():
            value = getattr(self, name)
            if value is None:
                continue
            wire = _to_wire(value, fix_type)
            length_tag = _DATA_TO_LENGTH.get(tag)
            if length_tag is not None:
                out.append((length_tag, str(len(wire.encode("latin-1")))))
            out.append((tag, wire))
        return out

    @classmethod
    def from_raw(cls, raw: RawMessage) -> Self:
        """Build a typed message from a decoded :class:`RawMessage`.

        Reads only the tags this model declares; all other fields (header,
        trailer, server extensions) are ignored.
        """
        kwargs: dict[str, Any] = {}
        for name, tag, fix_type in cls._fix_fields():
            value = raw.get(tag)
            if value is None:
                continue
            kwargs[name] = _from_wire(value, fix_type)
        return cls(**kwargs)
