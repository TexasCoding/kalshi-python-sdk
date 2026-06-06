"""Typed FIX message framework: Pydantic models that round-trip to wire fields.

Each message subclasses :class:`FixMessage` and declares its fields with
:func:`fixfield` (scalars) and :func:`groupfield` (repeating groups). Scalar
metadata (tag + wire type) rides on ``json_schema_extra``; group metadata (the
``NumInGroup`` tag + entry model) rides on an :class:`Annotated`
:class:`FixGroupMeta`. The shared base (:class:`_FixFieldModel`) drives:

* :meth:`to_body_fields` — ordered ``(tag, value)`` pairs in declaration order,
  with length-prefixed data fields auto-emitting their length field and repeating
  groups expanding to ``NumInGroup`` + each entry's fields (nesting supported).
* :meth:`from_raw` — build a typed model from a decoded
  :class:`~kalshi.fix.codec.RawMessage`. Scalars are read by tag; groups are
  parsed *positionally* (each entry delimited by its first field's tag), which
  recurses for nested groups.

The standard header (``SenderCompID``/``TargetCompID``/``MsgSeqNum``/
``SendingTime``) and ``MsgType`` are owned by the session/connection layer, not
the message body — see :mod:`kalshi.fix.session`.

Positional group decoding assumes group-member tags are distinct from top-level
scalar tags (true for the Kalshi FIX dictionary v1.03), so a scalar is found by
first-occurrence without confusion with a same-tagged field inside a group.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field

from kalshi.fix._timefmt import format_utc_timestamp, parse_utc_timestamp
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


@dataclass(frozen=True)
class FixGroupMeta:
    """``Annotated`` metadata marking a repeating-group field.

    Declare a group as ``Annotated[list[EntryModel], FixGroupMeta(count_tag,
    EntryModel)]`` where ``count_tag`` is the ``NumInGroup`` tag and
    ``EntryModel`` is the :class:`FixGroup` subclass describing one entry.
    """

    num_in_group_tag: int
    entry_model: type[_FixFieldModel]


@dataclass(frozen=True)
class _ScalarSpec:
    name: str
    tag: int
    fix_type: FixType


@dataclass(frozen=True)
class _GroupSpec:
    name: str
    count_tag: int
    entry_model: type[_FixFieldModel]


_FieldSpec = _ScalarSpec | _GroupSpec


def fixfield(tag: int, fix_type: FixType, *, default: Any = ..., **kwargs: Any) -> Any:
    """Declare a scalar FIX field.

    ``tag`` is the FIX tag number, ``fix_type`` its wire type. Omit ``default``
    for a required field (Pydantic treats ``...`` as required).
    """
    extra: dict[str, Any] = {"fix_tag": int(tag), "fix_type": fix_type.value}
    return Field(default=default, json_schema_extra=extra, **kwargs)


def groupfield() -> Any:
    """Declare a repeating-group field (defaults to an empty list).

    The ``NumInGroup`` tag and entry model ride on the field's
    :class:`Annotated` :class:`FixGroupMeta`; this only supplies the default.
    """
    return Field(default_factory=list)


def _to_wire(value: Any, fix_type: FixType) -> str:
    """Convert a Python field value to its FIX wire string."""
    if fix_type is FixType.BOOLEAN:
        return "Y" if value else "N"
    if fix_type in _DECIMAL_TYPES:
        # value is a Decimal; ``f"{d:f}"`` avoids scientific notation and float drift.
        return f"{value:f}"
    if fix_type is FixType.UTCTIMESTAMP:
        return format_utc_timestamp(value)
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
        return parse_utc_timestamp(raw)
    return raw


def _first_value(pairs: list[tuple[int, str]], tag: int) -> str | None:
    """First value for ``tag`` in ``pairs``, or ``None``."""
    for t, v in pairs:
        if t == tag:
            return v
    return None


def _index_of(pairs: list[tuple[int, str]], tag: int) -> int | None:
    """Index of the first pair with ``tag``, or ``None``."""
    for i, (t, _) in enumerate(pairs):
        if t == tag:
            return i
    return None


def _parse_group(
    pairs: list[tuple[int, str]],
    start: int,
    count: int,
    entry_model: type[_FixFieldModel],
) -> tuple[list[_FixFieldModel], int]:
    """Parse up to ``count`` group entries from ``pairs`` beginning at ``start``.

    Each entry begins at the entry model's delimiter (first) tag and runs until
    the next delimiter or a tag the entry does not own — which naturally captures
    nested groups (their tags are part of the entry's member set). Returns the
    parsed entries and the index just past the group.
    """
    delim = entry_model._first_tag()
    member_tags = entry_model._member_tags()
    entries: list[_FixFieldModel] = []
    i = start
    n = len(pairs)
    while len(entries) < count and i < n and pairs[i][0] == delim:
        entry_pairs = [pairs[i]]
        i += 1
        while i < n and pairs[i][0] != delim and pairs[i][0] in member_tags:
            entry_pairs.append(pairs[i])
            i += 1
        entries.append(entry_model._from_pairs(entry_pairs))
    return entries, i


# Per-class caches of the introspected layout / member-tag set. Both are
# deterministic per class and read on every encode/decode, so caching avoids
# re-walking ``model_fields``. Classes live for the process lifetime, so plain
# dicts keyed by class are fine.
_LAYOUT_CACHE: dict[type[_FixFieldModel], list[_FieldSpec]] = {}
_MEMBER_TAGS_CACHE: dict[type[_FixFieldModel], frozenset[int]] = {}


class _FixFieldModel(BaseModel):
    """Shared machinery for FIX messages and repeating-group entries.

    ``extra="forbid"`` makes a typo in an outbound model fail at construction;
    inbound models are built via :meth:`from_raw` / :meth:`_from_pairs`, which
    pass only declared tags, so server-added fields never reach the constructor.
    """

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def _layout(cls) -> list[_FieldSpec]:
        """Ordered scalar/group field specs in declaration order (cached)."""
        cached = _LAYOUT_CACHE.get(cls)
        if cached is not None:
            return cached
        specs: list[_FieldSpec] = []
        for name, field in cls.model_fields.items():
            group_meta = next(
                (m for m in field.metadata if isinstance(m, FixGroupMeta)), None
            )
            if group_meta is not None:
                specs.append(_GroupSpec(name, group_meta.num_in_group_tag, group_meta.entry_model))
                continue
            extra = field.json_schema_extra
            if isinstance(extra, dict) and "fix_tag" in extra:
                tag = int(extra["fix_tag"])  # type: ignore[arg-type]
                specs.append(_ScalarSpec(name, tag, FixType(str(extra["fix_type"]))))
        _LAYOUT_CACHE[cls] = specs
        return specs

    @classmethod
    def _member_tags(cls) -> frozenset[int]:
        """Every tag this model can contain, transitively through nested groups."""
        cached = _MEMBER_TAGS_CACHE.get(cls)
        if cached is not None:
            return cached
        tags: set[int] = set()
        for spec in cls._layout():
            if isinstance(spec, _GroupSpec):
                tags.add(spec.count_tag)
                tags |= spec.entry_model._member_tags()
            else:
                tags.add(spec.tag)
                length_tag = _DATA_TO_LENGTH.get(spec.tag)
                if length_tag is not None:
                    tags.add(length_tag)
        frozen = frozenset(tags)
        _MEMBER_TAGS_CACHE[cls] = frozen
        return frozen

    @classmethod
    def _first_tag(cls) -> int:
        """The delimiter tag — the first declared field's tag (group entry start)."""
        for spec in cls._layout():
            return spec.tag if isinstance(spec, _ScalarSpec) else spec.count_tag
        raise ValueError(f"{cls.__name__} declares no FIX fields")

    def to_body_fields(self) -> list[tuple[int, str]]:
        """Ordered ``(tag, value)`` fields in declaration order.

        ``None`` scalars and empty groups are omitted; a data field auto-emits
        its length field; a group emits ``NumInGroup`` then each entry's fields.
        """
        out: list[tuple[int, str]] = []
        for spec in self._layout():
            value = getattr(self, spec.name)
            if isinstance(spec, _GroupSpec):
                if not value:
                    continue
                out.append((spec.count_tag, str(len(value))))
                for entry in value:
                    out.extend(entry.to_body_fields())
            else:
                if value is None:
                    continue
                wire = _to_wire(value, spec.fix_type)
                length_tag = _DATA_TO_LENGTH.get(spec.tag)
                if length_tag is not None:
                    out.append((length_tag, str(len(wire.encode("latin-1")))))
                out.append((spec.tag, wire))
        return out

    @classmethod
    def from_raw(cls, raw: RawMessage) -> Self:
        """Build a typed model from a decoded :class:`RawMessage`."""
        return cls._from_pairs(raw.pairs)

    @classmethod
    def _from_pairs(cls, pairs: list[tuple[int, str]]) -> Self:
        """Build a typed model from an ordered ``(tag, value)`` slice.

        Scalars are read by tag; groups are parsed positionally from the
        ``NumInGroup`` field onward (recursing for nested groups).
        """
        kwargs: dict[str, Any] = {}
        for spec in cls._layout():
            if isinstance(spec, _GroupSpec):
                idx = _index_of(pairs, spec.count_tag)
                if idx is None:
                    continue
                try:
                    count = int(pairs[idx][1])
                except ValueError:
                    continue
                entries, _ = _parse_group(pairs, idx + 1, count, spec.entry_model)
                kwargs[spec.name] = entries
            else:
                value = _first_value(pairs, spec.tag)
                if value is not None:
                    kwargs[spec.name] = _from_wire(value, spec.fix_type)
        return cls(**kwargs)


class FixMessage(_FixFieldModel):
    """Base for all typed FIX messages. Subclasses set the ``MSG_TYPE`` class var."""

    MSG_TYPE: ClassVar[MsgType]


class FixGroup(_FixFieldModel):
    """Base for one entry of a repeating group (no ``MsgType`` of its own)."""
