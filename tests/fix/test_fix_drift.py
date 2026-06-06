"""FIX dictionary <-> model drift test (GH #437).

The REST SDK hard-fails on drift between its models and ``specs/openapi.yaml``
(``TestRequestParamDrift`` / ``TestRequestBodyDrift``). This is the FIX analogue:
it diffs every declared field of every FIX message/group model against the
authoritative Kalshi FIX dictionary (``specs/kalshi-fix-dictionary.xml``), so a
future dictionary revision (renamed tag, changed type) can't silently pass.

Drift checked per (model, field): the field's tag exists in the dictionary's
global field table with an equivalent FIX type, every group's ``NumInGroup`` tag
is typed ``NUMINGROUP``, and every message's ``MsgType`` is a real dictionary
message. ``EXCLUSIONS`` carries the documented Kalshi-dialect deviations with a
reason; ``test_exclusions_not_stale`` keeps them honest.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

import kalshi.fix.messages  # noqa: F401  (import side effect: load all message/group classes)
from kalshi.fix.messages.base import (
    FixGroup,
    FixMessage,
    FixType,
    _GroupSpec,
    _ScalarSpec,
)

_DICT_PATH = Path(__file__).resolve().parents[2] / "specs" / "kalshi-fix-dictionary.xml"


def _load_dictionary() -> tuple[dict[int, tuple[str, str, frozenset[str]]], set[str]]:
    root = ET.parse(_DICT_PATH).getroot()
    fields: dict[int, tuple[str, str, frozenset[str]]] = {}
    for f in root.find("fields"):  # type: ignore[union-attr]
        enums = frozenset(e.get("enum") or "" for e in f.findall("value"))
        fields[int(f.get("number") or "0")] = (f.get("name") or "", f.get("type") or "", enums)
    msgtypes = {m.get("msgtype") or "" for m in root.find("messages")}  # type: ignore[union-attr]
    return fields, msgtypes


DICT_FIELDS, DICT_MSGTYPES = _load_dictionary()

# --- Documented Kalshi-dialect deviations (the only allowed drift) -----------

# Tags the SDK uses that the bundled v1.03 dictionary lacks: it predates market
# data, so those models were derived from docs.kalshi.com/fix/market-data instead.
# (Replace these with a refreshed dictionary when one ships — see GH #437.)
MD_DOC_DERIVED_TAGS: dict[int, str] = {
    263: "SubscriptionRequestType",
    268: "NoMDEntries",
    269: "MDEntryType",
    270: "MDEntryPx",
    271: "MDEntrySize",
    279: "MDUpdateAction",
    281: "MDReqRejReason",
    326: "SecurityTradingStatus",
}
# MsgTypes likewise absent from the stale dictionary (market data + security status).
MD_DOC_DERIVED_MSGTYPES: set[str] = {"V", "W", "X", "Y", "e", "f"}


def _all_models() -> list[type]:
    seen: set[type] = set()

    def rec(cls: type) -> None:
        for sub in cls.__subclasses__():
            if sub not in seen:
                seen.add(sub)
                rec(sub)

    rec(FixMessage)
    rec(FixGroup)
    return sorted(seen, key=lambda c: c.__name__)


MODELS = _all_models()


def _type_equivalent(fix_type: FixType, dict_type: str, dict_enums: frozenset[str]) -> bool:
    """Whether a model's FIX type matches the dictionary's, allowing one mapping.

    The dictionary types the RFQ Y/N flags as ``CHAR`` with exactly ``{Y, N}``
    values; the SDK models them as ``BOOLEAN`` (which serializes to the same Y/N
    bytes), so a BOOLEAN field is accepted against such a CHAR field.
    """
    if fix_type.value == dict_type:
        return True
    yn = frozenset({"Y", "N"})
    return fix_type is FixType.BOOLEAN and dict_type == "CHAR" and dict_enums == yn


def _scalar_params() -> list[Any]:
    return [
        pytest.param(m.__name__, spec.tag, spec.fix_type, id=f"{m.__name__}.{spec.name}")
        for m in MODELS
        for spec in m._layout()  # type: ignore[attr-defined]
        if isinstance(spec, _ScalarSpec)
    ]


def _group_params() -> list[Any]:
    return [
        pytest.param(m.__name__, spec.count_tag, id=f"{m.__name__}.{spec.name}")
        for m in MODELS
        for spec in m._layout()  # type: ignore[attr-defined]
        if isinstance(spec, _GroupSpec)
    ]


def _message_params() -> list[Any]:
    return [
        pytest.param(m.__name__, m.MSG_TYPE.value, id=m.__name__)
        for m in MODELS
        if issubclass(m, FixMessage)
    ]


@pytest.mark.parametrize(("model", "tag", "fix_type"), _scalar_params())
def test_scalar_field_matches_dictionary(model: str, tag: int, fix_type: FixType) -> None:
    if tag in MD_DOC_DERIVED_TAGS:
        assert tag not in DICT_FIELDS, (
            f"tag {tag} is now defined in the dictionary; drop it from MD_DOC_DERIVED_TAGS"
        )
        return
    assert tag in DICT_FIELDS, f"{model}: tag {tag} ({fix_type.value}) is not in the FIX dictionary"
    name, dtype, denums = DICT_FIELDS[tag]
    assert _type_equivalent(fix_type, dtype, denums), (
        f"{model}: tag {tag} ({name}) is {fix_type.value} in the model, {dtype} in the dictionary"
    )


@pytest.mark.parametrize(("model", "count_tag"), _group_params())
def test_group_count_tag_is_numingroup(model: str, count_tag: int) -> None:
    if count_tag in MD_DOC_DERIVED_TAGS:
        assert count_tag not in DICT_FIELDS
        return
    assert count_tag in DICT_FIELDS, f"{model}: NumInGroup tag {count_tag} is not in the dictionary"
    assert DICT_FIELDS[count_tag][1] == "NUMINGROUP", (
        f"{model}: tag {count_tag} is {DICT_FIELDS[count_tag][1]} in the dictionary, not NUMINGROUP"
    )


@pytest.mark.parametrize(("model", "msgtype"), _message_params())
def test_message_msgtype_in_dictionary(model: str, msgtype: str) -> None:
    if msgtype in MD_DOC_DERIVED_MSGTYPES:
        assert msgtype not in DICT_MSGTYPES
        return
    assert msgtype in DICT_MSGTYPES, f"{model}: MsgType {msgtype!r} is not a dictionary message"


def test_exclusions_not_stale() -> None:
    # Every excluded tag must still be (a) used by a model and (b) genuinely absent
    # from the dictionary — otherwise the exclusion has rotted and should be removed.
    used_tags: set[int] = set()
    for m in MODELS:
        for spec in m._layout():  # type: ignore[attr-defined]
            used_tags.add(spec.tag if isinstance(spec, _ScalarSpec) else spec.count_tag)
    for tag in MD_DOC_DERIVED_TAGS:
        assert tag in used_tags, f"excluded tag {tag} is no longer used by any model"
        assert tag not in DICT_FIELDS, f"excluded tag {tag} is now in the dictionary"

    used_msgtypes = {m.MSG_TYPE.value for m in MODELS if issubclass(m, FixMessage)}
    for mt in MD_DOC_DERIVED_MSGTYPES:
        assert mt in used_msgtypes, f"excluded MsgType {mt!r} is no longer used by any model"
        assert mt not in DICT_MSGTYPES, f"excluded MsgType {mt!r} is now in the dictionary"
