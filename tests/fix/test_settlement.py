"""Tests for the market-settlement / post-trade FIX flow (GH #429)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest

from kalshi.fix.auth import FixSigner
from kalshi.fix.codec import RawMessage, decode, encode
from kalshi.fix.config import FixConfig, FixEnvironment, FixSessionType
from kalshi.fix.enums import CollateralAmountType, MarketResult
from kalshi.fix.messages import (
    CollateralAmountChange,
    MarketSettlementParty,
    MarketSettlementReport,
    MiscFee,
    decode_app_message,
)
from kalshi.fix.messages.base import FixMessage
from kalshi.fix.session import FixSession
from kalshi.fix.settlement import SettlementReassembler
from kalshi.fix.tags import Tag

from .conftest import MockAcceptor

SYM = "HIGHNY-23DEC31"


def _roundtrip(msg: FixMessage) -> FixMessage:
    full = [
        (int(Tag.MSG_TYPE), msg.MSG_TYPE.value),
        (int(Tag.MSG_SEQ_NUM), "1"),
        (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
        *msg.to_body_fields(),
    ]
    return type(msg).from_raw(decode(encode(full)))


def _wire(msg: FixMessage) -> str:
    return "|".join(f"{t}={v}" for t, v in msg.to_body_fields())


def _party(party_id: str, role: int = 24) -> MarketSettlementParty:
    return MarketSettlementParty(party_id=party_id, party_role=role)


# ---------------------------------------------------------------------------
# MarketSettlementReport (35=UMS) golden wire + round-trip
# ---------------------------------------------------------------------------


def test_settlement_report_golden_wire() -> None:
    msg = MarketSettlementReport(
        market_settlement_report_id="settle-123",
        symbol=SYM,
        clearing_business_date="20231231",
        market_result="yes",
        settlement_price=Decimal("100.00"),
        last_fragment=True,
    )
    assert _wire(msg) == (
        f"20105=settle-123|55={SYM}|715=20231231|20107=yes|730=100.00|893=Y"
    )


def test_settlement_report_nested_roundtrip() -> None:
    party = MarketSettlementParty(
        party_id="user-456",
        party_role=24,
        long_qty=Decimal("100"),
        short_qty=Decimal("0"),
        collateral_amount_changes=[
            CollateralAmountChange(
                collateral_amount_change=Decimal("100.00"), collateral_amount_type="PAYOUT"
            )
        ],
        misc_fees=[
            MiscFee(
                misc_fee_amt=Decimal("0.006"),
                misc_fee_curr="USD",
                misc_fee_type="4",
                misc_fee_basis=0,
            )
        ],
    )
    msg = MarketSettlementReport(
        market_settlement_report_id="settle-456",
        symbol=SYM,
        clearing_business_date="20231231",
        market_result="yes",
        settlement_price=Decimal("100.00"),
        last_fragment=True,
        parties=[party],
    )
    assert _roundtrip(msg) == msg


@pytest.mark.parametrize(
    ("result", "wire"),
    [(MarketResult.YES, "yes"), (MarketResult.NO, "no"), (MarketResult.SCALAR, "scalar")],
)
def test_settlement_report_market_result_values(result: MarketResult, wire: str) -> None:
    msg = MarketSettlementReport(
        symbol=SYM, market_result=wire, settlement_price=Decimal("30.60"), last_fragment=True
    )
    assert dict(msg.to_body_fields())[int(Tag.MARKET_RESULT)] == wire
    rt = _roundtrip(msg)
    assert isinstance(rt, MarketSettlementReport)
    assert rt.market_result == result


def test_settlement_report_two_parties_with_nested_groups_roundtrip() -> None:
    # Each party carries its own collateral + misc-fee groups; the positional
    # decoder must keep them separated (no cross-party leakage). Exercises negative
    # collateral (BALANCE) and a sub-cent fee.
    def _mk(pid: str, coll: str, coll_type: str, fee: str) -> MarketSettlementParty:
        return MarketSettlementParty(
            party_id=pid,
            party_role=24,
            long_qty=Decimal("100"),
            short_qty=Decimal("0"),
            collateral_amount_changes=[
                CollateralAmountChange(
                    collateral_amount_change=Decimal(coll), collateral_amount_type=coll_type
                )
            ],
            misc_fees=[
                MiscFee(
                    misc_fee_amt=Decimal(fee), misc_fee_curr="USD", misc_fee_type="4",
                    misc_fee_basis=0,
                )
            ],
        )

    msg = MarketSettlementReport(
        market_settlement_report_id="settle-789",
        symbol=SYM,
        clearing_business_date="20231231",
        market_result="yes",
        settlement_price=Decimal("100.00"),
        last_fragment=True,
        parties=[_mk("u1", "100.00", "PAYOUT", "0.00"), _mk("u2", "-50.00", "BALANCE", "0.006")],
    )
    rt = _roundtrip(msg)
    assert rt == msg
    assert isinstance(rt, MarketSettlementReport)
    assert [p.party_id for p in rt.parties] == ["u1", "u2"]
    assert rt.parties[1].collateral_amount_changes[0].collateral_amount_change == Decimal("-50.00")
    assert rt.parties[1].misc_fees[0].misc_fee_amt == Decimal("0.006")


def test_settlement_report_decodes_doc_example_with_trailing_last_fragment() -> None:
    # Doc example wire: LastFragment(893) comes AFTER the nested party group.
    # Positional group decode must still attribute the nested fields to the party
    # and read the trailing top-level 893 by tag.
    raw = decode(
        encode(
            [
                (int(Tag.MSG_TYPE), "UMS"),
                (int(Tag.MSG_SEQ_NUM), "2"),
                (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
                (int(Tag.MARKET_SETTLEMENT_REPORT_ID), "settle-123"),
                (int(Tag.SYMBOL), SYM),
                (int(Tag.CLEARING_BUSINESS_DATE), "20231231"),
                (int(Tag.MARKET_RESULT), "yes"),
                (int(Tag.SETTLEMENT_PRICE), "100.00"),
                (int(Tag.NO_MARKET_SETTLEMENT_PARTY_IDS), "1"),
                (int(Tag.MARKET_SETTLEMENT_PARTY_ID), "user-456"),
                (int(Tag.MARKET_SETTLEMENT_PARTY_ROLE), "24"),
                (int(Tag.LONG_QTY), "100"),
                (int(Tag.SHORT_QTY), "0"),
                (int(Tag.NO_COLLATERAL_AMOUNT_CHANGES), "1"),
                (int(Tag.COLLATERAL_AMOUNT_CHANGE), "100.00"),
                (int(Tag.COLLATERAL_AMOUNT_TYPE), "PAYOUT"),
                (int(Tag.NO_MISC_FEES), "1"),
                (int(Tag.MISC_FEE_AMT), "0.00"),
                (int(Tag.MISC_FEE_CURR), "USD"),
                (int(Tag.MISC_FEE_TYPE), "4"),
                (int(Tag.MISC_FEE_BASIS), "0"),
                (int(Tag.LAST_FRAGMENT), "Y"),
            ]
        )
    )
    msg = decode_app_message(raw)
    assert isinstance(msg, MarketSettlementReport)
    assert msg.symbol == SYM
    assert msg.market_result == MarketResult.YES
    assert msg.settlement_price == Decimal("100.00")
    assert msg.last_fragment is True
    assert len(msg.parties) == 1
    party = msg.parties[0]
    assert party.party_id == "user-456"
    assert party.long_qty == Decimal("100")
    assert party.collateral_amount_changes[0].collateral_amount_type == CollateralAmountType.PAYOUT
    assert party.collateral_amount_changes[0].collateral_amount_change == Decimal("100.00")
    assert party.misc_fees[0].misc_fee_amt == Decimal("0.00")
    assert party.misc_fees[0].misc_fee_type == "4"


def test_decode_app_message_settlement() -> None:
    msg = MarketSettlementReport(symbol=SYM, market_result="no", last_fragment=True)
    raw = decode(
        encode(
            [
                (int(Tag.MSG_TYPE), msg.MSG_TYPE.value),
                (int(Tag.MSG_SEQ_NUM), "2"),
                (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
                *msg.to_body_fields(),
            ]
        )
    )
    decoded = decode_app_message(raw)
    assert isinstance(decoded, MarketSettlementReport)
    assert decoded == msg


# ---------------------------------------------------------------------------
# Multi-fragment reassembly
# ---------------------------------------------------------------------------


def _frag(symbol: str | None, party_ids: list[str], last: bool | None) -> MarketSettlementReport:
    return MarketSettlementReport(
        symbol=symbol,
        market_result="yes",
        parties=[_party(p) for p in party_ids],
        last_fragment=last,
    )


@pytest.mark.parametrize("terminal", [True, None])
def test_reassembler_multi_fragment(terminal: bool | None) -> None:
    # The terminal page may carry LastFragment=Y or omit it (absent == Y); both
    # must merge the buffered fragments.
    r = SettlementReassembler()
    assert r.add(_frag(SYM, ["a"], False)) is None
    assert r.add(_frag(SYM, ["b"], False)) is None
    assert r.pending_symbols() == {SYM}
    done = r.add(_frag(SYM, ["c"], terminal))
    assert done is not None
    assert [p.party_id for p in done.parties] == ["a", "b", "c"]
    assert r.pending_symbols() == set()


@pytest.mark.parametrize("last", [True, None])
def test_reassembler_standalone(last: bool | None) -> None:
    # A standalone report (terminal True, or LastFragment absent) returns as-is.
    r = SettlementReassembler()
    done = r.add(_frag(SYM, ["x"], last))
    assert done is not None
    assert [p.party_id for p in done.parties] == ["x"]
    assert r.pending_symbols() == set()


def test_reassembler_routes_by_symbol() -> None:
    r = SettlementReassembler()
    r.add(_frag("A", ["a1"], False))
    r.add(_frag("B", ["b1"], False))
    done_a = r.add(_frag("A", ["a2"], True))
    assert done_a is not None
    assert [p.party_id for p in done_a.parties] == ["a1", "a2"]
    assert r.pending_symbols() == {"B"}
    done_b = r.add(_frag("B", ["b2"], True))
    assert done_b is not None
    assert [p.party_id for p in done_b.parties] == ["b1", "b2"]


def test_reassembler_non_final_without_symbol_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    r = SettlementReassembler()
    with caplog.at_level(logging.WARNING, logger="kalshi.fix"):
        assert r.add(_frag(None, ["a"], False)) is None
    assert r.pending_symbols() == set()
    assert any("without Symbol" in rec.message for rec in caplog.records)


def test_reassembler_sequential_same_symbol_batches() -> None:
    # Two contiguous batches for the same symbol, each terminated by Y, reassemble
    # independently — the buffer clears on each terminal, so they do not coalesce.
    r = SettlementReassembler()
    assert r.add(_frag(SYM, ["a1"], False)) is None
    done1 = r.add(_frag(SYM, ["a2"], True))
    assert done1 is not None
    assert [p.party_id for p in done1.parties] == ["a1", "a2"]
    assert r.pending_symbols() == set()

    assert r.add(_frag(SYM, ["b1"], False)) is None
    done2 = r.add(_frag(SYM, ["b2"], True))
    assert done2 is not None
    assert [p.party_id for p in done2.parties] == ["b1", "b2"]


def test_reassembler_clear_warns_on_pending(caplog: pytest.LogCaptureFixture) -> None:
    r = SettlementReassembler()
    r.add(_frag(SYM, ["a"], False))
    with caplog.at_level(logging.WARNING, logger="kalshi.fix"):
        r.clear()
    assert r.pending_symbols() == set()
    assert any("dropping buffered settlement" in rec.message for rec in caplog.records)


def test_reassembler_clear_silent_when_empty(caplog: pytest.LogCaptureFixture) -> None:
    r = SettlementReassembler()
    with caplog.at_level(logging.WARNING, logger="kalshi.fix"):
        r.clear()
    assert caplog.records == []


# ---------------------------------------------------------------------------
# Post-trade session stream + ReceiveSettlementReports logon flag
# ---------------------------------------------------------------------------


async def test_post_trade_settlement_stream(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.POST_TRADE, on_message=on_message
    )
    await session.start()
    reasm = SettlementReassembler()
    try:
        f1 = MarketSettlementReport(
            market_settlement_report_id="s1", symbol=SYM, market_result="yes",
            settlement_price=Decimal("100.00"), last_fragment=False, parties=[_party("u1")],
        )
        f2 = MarketSettlementReport(
            market_settlement_report_id="s2", symbol=SYM, market_result="yes",
            last_fragment=True, parties=[_party("u2")],
        )
        await acceptor.push("UMS", f1.to_body_fields(), seq=2)
        await acceptor.push("UMS", f2.to_body_fields(), seq=3)
        await until(lambda: len(received) == 2)
        results: list[MarketSettlementReport | None] = []
        for raw in received:
            decoded = decode_app_message(raw)
            assert isinstance(decoded, MarketSettlementReport)  # dispatch routed UMS correctly
            results.append(reasm.add(decoded))
        assert results[0] is None  # first fragment buffered
        assert results[1] is not None
        assert [p.party_id for p in results[1].parties] == ["u1", "u2"]
    finally:
        await session.close()


@pytest.mark.parametrize(("setting", "expected"), [(True, "Y"), (False, "N"), (None, None)])
async def test_receive_settlement_reports_logon_flag(
    fix_signer: FixSigner,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
    setting: bool | None,
    expected: str | None,
) -> None:
    config = FixConfig.prediction(
        environment=FixEnvironment.DEMO,
        host="127.0.0.1",
        port=acceptor.port,
        use_tls=False,
        heartbeat_interval=4,
        connect_timeout=2.0,
        receive_settlement_reports=setting,
    )
    session = FixSession(fix_signer, config, FixSessionType.POST_TRADE)
    await session.start()
    try:
        await until(lambda: acceptor.first("A") is not None)
        logon = acceptor.first("A")
        assert logon is not None
        assert logon.get(Tag.RECEIVE_SETTLEMENT_REPORTS) == expected
    finally:
        await session.close()
