"""Tests for the typed FIX message framework and session messages."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from kalshi.fix.codec import decode, encode
from kalshi.fix.enums import ApplVerID, EncryptMethod, MsgType
from kalshi.fix.messages import (
    Heartbeat,
    Logon,
    Logout,
    Reject,
    ResendRequest,
    SequenceReset,
    TestRequest,
)
from kalshi.fix.messages.base import (
    FixType,
    _format_utc_timestamp,
    _from_wire,
    _parse_utc_timestamp,
)
from kalshi.fix.tags import Tag


def _wire(msg_type: str, body: list[tuple[int, str]], seq: int = 1) -> bytes:
    header = [
        (int(Tag.MSG_TYPE), msg_type),
        (int(Tag.MSG_SEQ_NUM), str(seq)),
        (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
    ]
    return encode(header + body)


def test_logon_body_includes_defaults_and_auto_rawdata_length() -> None:
    logon = Logon(heartbeat_interval=30, raw_data="QhA8659M", reset_seq_num_flag=True)
    body = dict(logon.to_body_fields())
    assert body[int(Tag.ENCRYPT_METHOD)] == "0"  # EncryptMethod.NONE default
    assert body[int(Tag.HEART_BT_INT)] == "30"
    assert body[int(Tag.DEFAULT_APPL_VER_ID)] == "9"  # ApplVerID.FIX50SP2 default
    assert body[int(Tag.RESET_SEQ_NUM_FLAG)] == "Y"
    # RawData auto-emits its length field with the byte length of the value.
    assert body[int(Tag.RAW_DATA_LENGTH)] == str(len("QhA8659M"))
    assert body[int(Tag.RAW_DATA)] == "QhA8659M"


def test_logon_omits_none_optionals() -> None:
    logon = Logon(heartbeat_interval=30)
    tags = {t for t, _ in logon.to_body_fields()}
    assert int(Tag.USE_DOLLARS) not in tags
    assert int(Tag.RAW_DATA) not in tags


def test_logon_use_dollars_serializes_boolean() -> None:
    logon = Logon(heartbeat_interval=30, use_dollars=True)
    assert (int(Tag.USE_DOLLARS), "Y") in logon.to_body_fields()


def test_logon_enums_are_typed() -> None:
    logon = Logon(heartbeat_interval=30)
    assert logon.encrypt_method is EncryptMethod.NONE
    assert logon.default_appl_ver_id is ApplVerID.FIX50SP2


def test_logon_from_raw_roundtrip() -> None:
    logon = Logon(heartbeat_interval=45, use_dollars=True, reset_seq_num_flag=True)
    rm = decode(_wire("A", logon.to_body_fields()))
    parsed = Logon.from_raw(rm)
    assert parsed.heartbeat_interval == 45
    assert parsed.use_dollars is True
    assert parsed.reset_seq_num_flag is True


def test_msg_type_class_var() -> None:
    assert Logon.MSG_TYPE is MsgType.LOGON
    assert Heartbeat.MSG_TYPE is MsgType.HEARTBEAT
    assert SequenceReset.MSG_TYPE is MsgType.SEQUENCE_RESET


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        Logon(heartbeat_interval=30, bogus_field=1)  # type: ignore[call-arg]


def test_test_request_requires_id() -> None:
    with pytest.raises(ValidationError):
        TestRequest()  # type: ignore[call-arg]
    tr = TestRequest(test_req_id="ping")
    assert (int(Tag.TEST_REQ_ID), "ping") in tr.to_body_fields()


def test_resend_request_seqnums() -> None:
    rr = ResendRequest(begin_seq_no=5, end_seq_no=0)
    body = dict(rr.to_body_fields())
    assert body[int(Tag.BEGIN_SEQ_NO)] == "5"
    assert body[int(Tag.END_SEQ_NO)] == "0"


def test_sequence_reset_gap_fill() -> None:
    sr = SequenceReset(gap_fill_flag=True, new_seq_no=10)
    body = dict(sr.to_body_fields())
    assert body[int(Tag.GAP_FILL_FLAG)] == "Y"
    assert body[int(Tag.NEW_SEQ_NO)] == "10"


def test_reject_parses_unknown_reason_as_int() -> None:
    # Inbound reject codes are plain ints so an unknown code never raises.
    rm = decode(
        _wire(
            "3",
            [
                (int(Tag.REF_SEQ_NUM), "4"),
                (int(Tag.SESSION_REJECT_REASON), "10"),
                (int(Tag.TEXT), "SendingTime accuracy problem"),
            ],
            seq=5,
        )
    )
    rj = Reject.from_raw(rm)
    assert rj.ref_seq_num == 4
    assert rj.session_reject_reason == 10
    assert rj.text == "SendingTime accuracy problem"


def test_logout_text_optional() -> None:
    assert Logout().to_body_fields() == []
    assert Logout(text="bye").to_body_fields() == [(int(Tag.TEXT), "bye")]


def test_heartbeat_optional_test_req_id() -> None:
    assert Heartbeat().to_body_fields() == []
    assert Heartbeat(test_req_id="x").to_body_fields() == [(int(Tag.TEST_REQ_ID), "x")]


def test_utc_timestamp_format_and_parse() -> None:
    dt = datetime(2025, 9, 26, 21, 54, 7, 1000, tzinfo=UTC)
    assert _format_utc_timestamp(dt) == "20250926-21:54:07.001"
    assert _parse_utc_timestamp("20250926-21:54:07.001") == dt
    assert _parse_utc_timestamp("20250926-21:54:07") == datetime(
        2025, 9, 26, 21, 54, 7, tzinfo=UTC
    )


def test_utc_timestamp_truncates_sub_millisecond() -> None:
    # Millisecond precision via floor truncation (not rounding) — the SendingTime
    # in the logon pre-hash must be byte-identical to tag 52.
    assert (
        _format_utc_timestamp(datetime(2025, 9, 26, 21, 54, 7, 123456, tzinfo=UTC))
        == "20250926-21:54:07.123"
    )
    assert (
        _format_utc_timestamp(datetime(2025, 9, 26, 21, 54, 7, 999999, tzinfo=UTC))
        == "20250926-21:54:07.999"
    )
    assert _parse_utc_timestamp("20250926-21:54:07.123456").microsecond == 123456


def test_boolean_parsing_is_strict() -> None:
    assert _from_wire("Y", FixType.BOOLEAN) is True
    assert _from_wire("N", FixType.BOOLEAN) is False
    # Anything else must raise rather than silently become False.
    with pytest.raises(ValueError):
        _from_wire("X", FixType.BOOLEAN)
