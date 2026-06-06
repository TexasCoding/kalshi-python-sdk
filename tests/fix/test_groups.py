"""Tests for FIX repeating-group support (GH #423)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from kalshi.fix.codec import SOH, RawMessage, decode, encode
from kalshi.fix.enums import MsgType
from kalshi.fix.messages.base import (
    FixGroupMeta,
    FixMessage,
    FixType,
    fixfield,
    groupfield,
)
from kalshi.fix.messages.components import (
    CollateralAmountChange,
    MarketSettlementParty,
    MiscFee,
    MultivariateSelectedLeg,
    Party,
)
from kalshi.fix.tags import Tag


class _OrderWithParties(FixMessage):
    """Scalar, then a flat NoPartyIDs group, then a trailing scalar."""

    MSG_TYPE = MsgType.NEW_ORDER_SINGLE

    cl_ord_id: str = fixfield(Tag.CL_ORD_ID, FixType.STRING)
    parties: Annotated[list[Party], FixGroupMeta(Tag.NO_PARTY_IDS, Party)] = groupfield()
    symbol: str = fixfield(Tag.SYMBOL, FixType.STRING)


class _WithLegs(FixMessage):
    MSG_TYPE = MsgType.QUOTE_REQUEST

    quote_req_id: str = fixfield(Tag.QUOTE_REQ_ID, FixType.STRING)
    legs: Annotated[
        list[MultivariateSelectedLeg],
        FixGroupMeta(Tag.NO_MULTIVARIATE_SELECTED_LEGS, MultivariateSelectedLeg),
    ] = groupfield()


class _Settlement(FixMessage):
    """A nested group: NoMarketSettlementPartyIDs -> collateral + misc fees."""

    MSG_TYPE = MsgType.MARKET_SETTLEMENT_REPORT

    report_id: str = fixfield(Tag.MARKET_SETTLEMENT_REPORT_ID, FixType.STRING)
    parties: Annotated[
        list[MarketSettlementParty],
        FixGroupMeta(Tag.NO_MARKET_SETTLEMENT_PARTY_IDS, MarketSettlementParty),
    ] = groupfield()


def _roundtrip(msg: FixMessage) -> FixMessage:
    full = [
        (int(Tag.MSG_TYPE), msg.MSG_TYPE.value),
        (int(Tag.MSG_SEQ_NUM), "1"),
        (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
        *msg.to_body_fields(),
    ]
    return type(msg).from_raw(decode(encode(full)))


def test_flat_group_roundtrip_multiple_entries() -> None:
    msg = _OrderWithParties(
        cl_ord_id="abc",
        symbol="KXTEST",
        parties=[Party(party_id="0", party_role=24), Party(party_id="7", party_role=24)],
    )
    back = _roundtrip(msg)
    assert back == msg
    assert [p.party_id for p in back.parties] == ["0", "7"]
    # The trailing scalar after the group must survive (group boundary correct).
    assert back.symbol == "KXTEST"


def test_group_wire_layout() -> None:
    msg = _OrderWithParties(
        cl_ord_id="abc", symbol="KXTEST", parties=[Party(party_id="0", party_role=24)]
    )
    body = dict(msg.to_body_fields())
    assert body[int(Tag.NO_PARTY_IDS)] == "1"  # NumInGroup count
    # Count precedes the entry's delimiter, which precedes the trailing scalar.
    tags = [t for t, _ in msg.to_body_fields()]
    assert tags.index(int(Tag.NO_PARTY_IDS)) < tags.index(int(Tag.PARTY_ID))
    assert tags.index(int(Tag.PARTY_ID)) < tags.index(int(Tag.SYMBOL))


def test_empty_group_is_omitted() -> None:
    msg = _OrderWithParties(cl_ord_id="x", symbol="Y")
    tags = {t for t, _ in msg.to_body_fields()}
    assert int(Tag.NO_PARTY_IDS) not in tags
    assert _roundtrip(msg) == msg


def test_single_entry_group() -> None:
    msg = _WithLegs(
        quote_req_id="q1",
        legs=[MultivariateSelectedLeg(event_ticker="E", market_ticker="M", side="yes")],
    )
    back = _roundtrip(msg)
    assert back == msg
    assert back.legs[0].side == "yes"


def test_decimal_group_field_coerces_without_float_drift() -> None:
    # A str amount coerces to Decimal (DollarDecimal) and round-trips exactly.
    fee = MiscFee(misc_fee_amt="0.02", misc_fee_curr="USD", misc_fee_type="4", misc_fee_basis=0)  # type: ignore[arg-type]
    assert fee.misc_fee_amt == Decimal("0.02")
    assert (int(Tag.MISC_FEE_AMT), "0.02") in fee.to_body_fields()


def test_nested_group_roundtrip() -> None:
    msg = _Settlement(
        report_id="R1",
        parties=[
            MarketSettlementParty(
                party_id="0",
                party_role=24,
                long_qty=Decimal("10.00"),
                collateral_amount_changes=[
                    CollateralAmountChange(
                        collateral_amount_change=Decimal("1.50"),
                        collateral_amount_type="BALANCE",
                    )
                ],
                misc_fees=[
                    MiscFee(
                        misc_fee_amt=Decimal("0.02"),
                        misc_fee_curr="USD",
                        misc_fee_type="4",
                        misc_fee_basis=0,
                    )
                ],
            ),
            MarketSettlementParty(
                party_id="1",
                party_role=24,
                collateral_amount_changes=[
                    CollateralAmountChange(
                        collateral_amount_change=Decimal("2.00"),
                        collateral_amount_type="PAYOUT",
                    )
                ],
            ),
        ],
    )
    back = _roundtrip(msg)
    assert back == msg
    # First party: one collateral change + one misc fee.
    assert back.parties[0].collateral_amount_changes[0].collateral_amount_type == "BALANCE"
    assert back.parties[0].misc_fees[0].misc_fee_amt == Decimal("0.02")
    assert back.parties[0].long_qty == Decimal("10.00")
    # Second party: collateral only, empty nested misc-fees group.
    assert back.parties[1].misc_fees == []
    assert back.parties[1].collateral_amount_changes[0].collateral_amount_type == "PAYOUT"


def test_short_numingroup_parses_available_entries() -> None:
    # NumInGroup promises 3 entries but only 1 is delivered — parse the one present
    # (the short-count debug path in _parse_group) and keep the trailing scalar.
    raw = RawMessage(
        [
            (int(Tag.MSG_TYPE), "D"),
            (int(Tag.CL_ORD_ID), "x"),
            (int(Tag.NO_PARTY_IDS), "3"),
            (int(Tag.PARTY_ID), "0"),
            (int(Tag.PARTY_ROLE), "24"),
            (int(Tag.SYMBOL), "Y"),
        ]
    )
    msg = _OrderWithParties.from_raw(raw)
    assert len(msg.parties) == 1
    assert msg.symbol == "Y"


def test_non_integer_numingroup_drops_group() -> None:
    # A non-integer NumInGroup drops the group (debug path) but keeps scalars.
    raw = RawMessage(
        [
            (int(Tag.MSG_TYPE), "D"),
            (int(Tag.CL_ORD_ID), "x"),
            (int(Tag.NO_PARTY_IDS), "abc"),
            (int(Tag.SYMBOL), "Y"),
        ]
    )
    msg = _OrderWithParties.from_raw(raw)
    assert msg.parties == []
    assert msg.symbol == "Y"


def test_nested_group_wire_structure() -> None:
    msg = _Settlement(
        report_id="R1",
        parties=[
            MarketSettlementParty(
                party_id="0",
                collateral_amount_changes=[
                    CollateralAmountChange(
                        collateral_amount_change=Decimal("1.50"),
                        collateral_amount_type="BALANCE",
                    )
                ],
            )
        ],
    )
    wire = encode(
        [
            (int(Tag.MSG_TYPE), "UMS"),
            (int(Tag.MSG_SEQ_NUM), "1"),
            (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
            *msg.to_body_fields(),
        ]
    )
    rendered = wire.replace(SOH, b"|").decode()
    # Outer count, outer delimiter, inner count, inner delimiter — in order.
    assert "20108=1|20109=0|" in rendered
    assert "1703=1|1704=1.50|1705=BALANCE|" in rendered
