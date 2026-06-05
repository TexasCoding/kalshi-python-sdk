"""Tests for the hand-rolled FIX codec."""

from __future__ import annotations

import pytest

from kalshi.fix.codec import (
    BEGIN_STRING_FIXT11,
    SOH,
    FixParser,
    RawMessage,
    decode,
    encode,
)
from kalshi.fix.errors import FixCodecError
from kalshi.fix.tags import Tag


def _logon_fields() -> list[tuple[int, str]]:
    return [
        (int(Tag.MSG_TYPE), "A"),
        (int(Tag.SENDER_COMP_ID), "uuid"),
        (int(Tag.TARGET_COMP_ID), "KalshiNR"),
        (int(Tag.MSG_SEQ_NUM), "1"),
        (int(Tag.SENDING_TIME), "20250926-21:54:07.001"),
        (int(Tag.ENCRYPT_METHOD), "0"),
        (int(Tag.HEART_BT_INT), "30"),
    ]


def test_encode_prepends_beginstring_bodylength_checksum() -> None:
    wire = encode(_logon_fields())
    assert wire.startswith(b"8=" + BEGIN_STRING_FIXT11.encode() + SOH + b"9=")
    assert wire.endswith(SOH)
    # CheckSum is the final field, 3 zero-padded digits.
    assert wire[-7:-4] == b"10="


def test_encode_bodylength_and_checksum_are_correct() -> None:
    wire = encode(_logon_fields())
    cs_start = len(wire) - 7
    # CheckSum = sum of all preceding bytes mod 256.
    assert int(wire[cs_start + 3 : cs_start + 6]) == sum(wire[:cs_start]) % 256
    # BodyLength = bytes from MsgType through the SOH before CheckSum.
    soh1 = wire.index(SOH)
    soh2 = wire.index(SOH, soh1 + 1)
    declared = int(wire[soh1 + 3 : soh2])
    assert declared == cs_start - (soh2 + 1)


def test_encode_rejects_framing_tags() -> None:
    for tag in (Tag.BEGIN_STRING, Tag.BODY_LENGTH, Tag.CHECK_SUM):
        with pytest.raises(FixCodecError):
            encode([(int(Tag.MSG_TYPE), "A"), (int(tag), "x")])


def test_encode_requires_msgtype_first() -> None:
    with pytest.raises(FixCodecError):
        encode([(int(Tag.SENDER_COMP_ID), "uuid"), (int(Tag.MSG_TYPE), "A")])


def test_roundtrip_decode() -> None:
    wire = encode(_logon_fields())
    rm = decode(wire)
    assert rm.msg_type == "A"
    assert rm.seq_num == 1
    assert rm.get(Tag.TARGET_COMP_ID) == "KalshiNR"
    assert rm.get_int(Tag.HEART_BT_INT) == 30


def test_data_field_with_embedded_equals_and_soh_safe() -> None:
    # RawData carries a length prefix; its value may contain '=' (and even SOH).
    raw_value = "ab=cd"
    fields = [
        (int(Tag.MSG_TYPE), "A"),
        (int(Tag.MSG_SEQ_NUM), "1"),
        (int(Tag.RAW_DATA_LENGTH), str(len(raw_value))),
        (int(Tag.RAW_DATA), raw_value),
    ]
    rm = decode(encode(fields))
    assert rm.get(Tag.RAW_DATA) == raw_value


def test_checksum_mismatch_raises() -> None:
    wire = bytearray(encode(_logon_fields()))
    # Corrupt a byte in the body.
    wire[10] = wire[10] ^ 0x01
    with pytest.raises(FixCodecError, match="CheckSum"):
        decode(bytes(wire))


def test_bodylength_mismatch_raises() -> None:
    wire = encode(_logon_fields())
    soh1 = wire.index(SOH)
    soh2 = wire.index(SOH, soh1 + 1)
    # Rewrite BodyLength to a wrong value of the same digit width.
    declared = int(wire[soh1 + 3 : soh2])
    bad = wire[: soh1 + 3] + str(declared + 1).encode().rjust(soh2 - (soh1 + 3), b"0") + wire[soh2:]
    with pytest.raises(FixCodecError):
        decode(bad)


def test_decode_requires_beginstring() -> None:
    with pytest.raises(FixCodecError, match="BeginString"):
        decode(b"35=A\x0110=000\x01")


def test_parser_handles_split_and_multiple_frames() -> None:
    a = encode(_logon_fields())
    b = encode(
        [
            (int(Tag.MSG_TYPE), "0"),
            (int(Tag.MSG_SEQ_NUM), "2"),
            (int(Tag.SENDING_TIME), "20250926-21:54:08.001"),
        ]
    )
    stream = a + b
    parser = FixParser()
    seen: list[tuple[str | None, int | None]] = []
    for byte in stream:  # feed one byte at a time
        parser.append(bytes([byte]))
        msg = parser.get_message()
        if msg is not None:
            seen.append((msg.msg_type, msg.seq_num))
    assert seen == [("A", 1), ("0", 2)]


def test_parser_discards_junk_before_beginstring() -> None:
    parser = FixParser()
    parser.append(b"garbage\x01noise" + encode(_logon_fields()))
    msgs = parser.messages()
    assert [m.msg_type for m in msgs] == ["A"]


def test_parser_rejects_implausible_bodylength() -> None:
    parser = FixParser()
    parser.append(b"8=FIXT.1.1\x019=99999999\x01")
    with pytest.raises(FixCodecError, match="implausible"):
        parser.get_message()


def test_rawmessage_repr_redacts_sensitive_fields() -> None:
    rm = RawMessage([(int(Tag.MSG_TYPE), "A"), (int(Tag.RAW_DATA), "secretsig")])
    text = repr(rm)
    assert "secretsig" not in text
    assert "<redacted>" in text


def test_get_int_raises_on_non_integer() -> None:
    rm = RawMessage([(int(Tag.HEART_BT_INT), "abc")])
    with pytest.raises(FixCodecError):
        rm.get_int(Tag.HEART_BT_INT)


def test_parser_resyncs_past_false_8equals_then_9() -> None:
    # Junk that contains "8=" followed by a SOH and "9=" but whose BeginString
    # value is not FIXT.1.1 must be skipped, not framed.
    parser = FixParser()
    parser.append(b"8=XXX\x019=5\x01junk\x01" + encode(_logon_fields()))
    assert [m.msg_type for m in parser.messages()] == ["A"]


def test_parser_resyncs_past_stray_8equals_without_9() -> None:
    parser = FixParser()
    parser.append(b"8=junk\x01ZZ\x01" + encode(_logon_fields()))
    assert [m.msg_type for m in parser.messages()] == ["A"]


def test_parser_bounds_unterminated_bodylength() -> None:
    # Valid BeginString then a BodyLength digit run with no SOH must be rejected
    # (bounded), not buffered forever.
    parser = FixParser()
    parser.append(b"8=FIXT.1.1\x019=" + b"1" * 100)
    with pytest.raises(FixCodecError):
        parser.get_message()


def test_parser_bounds_garbage_after_8equals() -> None:
    # A "8=" followed by a long non-FIXT.1.1 run must not grow the buffer.
    parser = FixParser()
    parser.append(b"8=" + b"X" * 100_000)
    assert parser.get_message() is None
    assert len(parser._buf) <= 1  # resynced down to a possible split "8="


def test_parser_frames_data_field_with_embedded_soh() -> None:
    raw_value = "ab\x01cd"  # an actual SOH inside the value
    fields = [
        (int(Tag.MSG_TYPE), "A"),
        (int(Tag.MSG_SEQ_NUM), "1"),
        (int(Tag.SENDING_TIME), "20250926-21:54:07.001"),
        (int(Tag.RAW_DATA_LENGTH), str(len(raw_value.encode("latin-1")))),
        (int(Tag.RAW_DATA), raw_value),
    ]
    parser = FixParser()
    parser.append(encode(fields))
    msgs = parser.messages()
    assert len(msgs) == 1
    assert msgs[0].get(Tag.RAW_DATA) == raw_value


def test_encode_rejects_empty_field_list() -> None:
    with pytest.raises(FixCodecError):
        encode([])


def test_rawmessage_get_all_returns_repeating_values() -> None:
    rm = RawMessage(
        [(int(Tag.NO_PARTY_IDS), "2"), (int(Tag.PARTY_ID), "a"), (int(Tag.PARTY_ID), "b")]
    )
    assert rm.get_all(Tag.PARTY_ID) == ["a", "b"]


def test_encode_rejects_soh_in_non_data_field() -> None:
    # A SOH in a normal field would smuggle extra tags into a checksum-valid frame.
    with pytest.raises(FixCodecError, match="SOH"):
        encode([(int(Tag.MSG_TYPE), "A"), (int(Tag.TEXT), "a\x01b")])


def test_encode_allows_soh_in_data_field() -> None:
    # DATA fields are length-prefixed, so an embedded SOH is legal.
    wire = encode(
        [
            (int(Tag.MSG_TYPE), "A"),
            (int(Tag.MSG_SEQ_NUM), "1"),
            (int(Tag.RAW_DATA_LENGTH), "3"),
            (int(Tag.RAW_DATA), "a\x01b"),
        ]
    )
    assert decode(wire).get(Tag.RAW_DATA) == "a\x01b"


def test_decode_rejects_non_adjacent_data_field() -> None:
    # A length field not immediately followed by its data field is malformed.
    wire = encode(
        [
            (int(Tag.MSG_TYPE), "A"),
            (int(Tag.MSG_SEQ_NUM), "1"),
            (int(Tag.RAW_DATA_LENGTH), "5"),
            (int(Tag.PRICE), "0.5"),  # not RawData (96)
        ]
    )
    with pytest.raises(FixCodecError, match="must immediately follow"):
        decode(wire)


def test_parser_resyncs_after_corrupt_frame() -> None:
    # A frame with a bad CheckSum must be skipped, and a following valid frame
    # must still be delivered (not lost to over-consumption).
    corrupt = bytearray(
        encode(
            [
                (int(Tag.MSG_TYPE), "0"),
                (int(Tag.MSG_SEQ_NUM), "9"),
                (int(Tag.SENDING_TIME), "20250926-21:54:08.001"),
            ]
        )
    )
    # Corrupt the declared CheckSum (the "NNN" digits in the trailing "10=NNN\x01").
    idx = len(corrupt) - 5
    corrupt[idx] = ord("0") if corrupt[idx] != ord("0") else ord("1")
    parser = FixParser()
    parser.append(bytes(corrupt) + encode(_logon_fields()))
    types = [m.msg_type for m in parser.messages()]
    assert types == ["A"]  # corrupt heartbeat skipped, valid logon returned
