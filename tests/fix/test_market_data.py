"""Tests for the market-data FIX flow + order-book reconstruction (GH #426)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest

from kalshi.fix.auth import FixSigner
from kalshi.fix.codec import RawMessage, decode, encode
from kalshi.fix.config import FixConfig, FixSessionType
from kalshi.fix.enums import (
    MDEntryType,
    MDReqRejReason,
    MDUpdateAction,
    SecurityTradingStatus,
    SubscriptionRequestType,
)
from kalshi.fix.messages import (
    MarketDataIncrementalRefresh,
    MarketDataRequest,
    MarketDataRequestReject,
    MarketDataSnapshotFullRefresh,
    MDIncrementalEntry,
    MDSnapshotEntry,
    SecurityStatus,
    SecurityStatusRequest,
    decode_app_message,
)
from kalshi.fix.messages.base import FixMessage
from kalshi.fix.orderbook import FixOrderBook
from kalshi.fix.session import FixSession, FixSessionState
from kalshi.fix.tags import Tag

from .conftest import MockAcceptor

TICKER = "KXNBAGAME-26MAY25NYKCLE-NYK"
TICKER2 = "KXTEST-OTHER"


def _roundtrip(msg: FixMessage) -> FixMessage:
    full = [
        (int(Tag.MSG_TYPE), msg.MSG_TYPE.value),
        (int(Tag.MSG_SEQ_NUM), "1"),
        (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
        *msg.to_body_fields(),
    ]
    return type(msg).from_raw(decode(encode(full)))


def _wire(msg: FixMessage) -> str:
    """The message body as a ``tag=value|...`` string (delimiter rendered ``|``).

    Pins exact field order and repeating-group layout — which round-trip equality
    cannot, since a symmetric encode/decode bug would pass a round-trip.
    """
    return "|".join(f"{t}={v}" for t, v in msg.to_body_fields())


# ---------------------------------------------------------------------------
# Golden wire fixtures (pinned to the docs.kalshi.com/fix/market-data examples)
# ---------------------------------------------------------------------------


def test_golden_wire_market_data_request() -> None:
    # docs market-data.md: snapshot request body, and cancel-all body.
    assert _wire(MarketDataRequest.snapshot([TICKER])) == f"263=0|146=1|55={TICKER}"
    assert _wire(MarketDataRequest.unsubscribe_all()) == "263=2"


def test_golden_wire_snapshot_full_refresh() -> None:
    msg = MarketDataSnapshotFullRefresh(
        symbol=TICKER,
        entries=[
            MDSnapshotEntry(
                md_entry_type="0", md_entry_px=Decimal("0.3500"), md_entry_size=Decimal("10.00")
            ),
            MDSnapshotEntry(
                md_entry_type="1", md_entry_px=Decimal("0.6500"), md_entry_size=Decimal("5.00")
            ),
        ],
    )
    assert _wire(msg) == f"55={TICKER}|268=2|269=0|270=0.3500|271=10.00|269=1|270=0.6500|271=5.00"


def test_golden_wire_incremental_refresh() -> None:
    msg = MarketDataIncrementalRefresh(
        entries=[
            MDIncrementalEntry(
                md_update_action="1",
                symbol=TICKER,
                md_entry_type="0",
                md_entry_px=Decimal("0.3500"),
                md_entry_size=Decimal("15.00"),
            )
        ]
    )
    assert _wire(msg) == f"268=1|279=1|55={TICKER}|269=0|270=0.3500|271=15.00"


def test_golden_wire_request_reject() -> None:
    msg = MarketDataRequestReject(md_req_rej_reason="4", text="bad")
    assert _wire(msg) == "281=4|58=bad"


def test_golden_wire_security_status_request() -> None:
    assert _wire(SecurityStatusRequest.subscribe(TICKER)) == f"263=1|55={TICKER}"


def test_golden_wire_security_status() -> None:
    assert _wire(SecurityStatus(symbol=TICKER, security_trading_status=2)) == f"55={TICKER}|326=2"


# ---------------------------------------------------------------------------
# Outbound: MarketDataRequest (35=V) + SecurityStatusRequest (35=e)
# ---------------------------------------------------------------------------


def test_market_data_request_snapshot() -> None:
    msg = MarketDataRequest.snapshot([TICKER])
    body = msg.to_body_fields()
    assert body[0] == (int(Tag.SUBSCRIPTION_REQUEST_TYPE), SubscriptionRequestType.SNAPSHOT.value)
    assert (int(Tag.NO_RELATED_SYM), "1") in body
    assert (int(Tag.SYMBOL), TICKER) in body
    assert _roundtrip(msg) == msg


def test_market_data_request_subscribe_multi() -> None:
    msg = MarketDataRequest.subscribe([TICKER, TICKER2])
    body = dict(msg.to_body_fields())
    assert body[int(Tag.SUBSCRIPTION_REQUEST_TYPE)] == SubscriptionRequestType.SNAPSHOT_PLUS_UPDATES
    assert body[int(Tag.NO_RELATED_SYM)] == "2"
    rt = _roundtrip(msg)
    assert isinstance(rt, MarketDataRequest)
    assert [e.symbol for e in rt.related_symbols] == [TICKER, TICKER2]


def test_market_data_request_unsubscribe() -> None:
    msg = MarketDataRequest.unsubscribe([TICKER])
    body = dict(msg.to_body_fields())
    assert body[int(Tag.SUBSCRIPTION_REQUEST_TYPE)] == SubscriptionRequestType.DISABLE.value
    assert body[int(Tag.NO_RELATED_SYM)] == "1"


def test_market_data_request_unsubscribe_all_omits_symbols() -> None:
    msg = MarketDataRequest.unsubscribe_all()
    tags = {t for t, _ in msg.to_body_fields()}
    assert int(Tag.SUBSCRIPTION_REQUEST_TYPE) in tags
    # Cancel-all carries no NoRelatedSym / Symbol per the spec.
    assert int(Tag.NO_RELATED_SYM) not in tags
    assert int(Tag.SYMBOL) not in tags


@pytest.mark.parametrize("ctor", ["snapshot", "subscribe", "unsubscribe"])
def test_market_data_request_requires_symbol(ctor: str) -> None:
    with pytest.raises(ValueError, match="symbol"):
        getattr(MarketDataRequest, ctor)([])


def test_security_status_request_subscribe() -> None:
    msg = SecurityStatusRequest.subscribe(TICKER)
    body = dict(msg.to_body_fields())
    assert body[int(Tag.SUBSCRIPTION_REQUEST_TYPE)] == SubscriptionRequestType.SNAPSHOT_PLUS_UPDATES
    assert body[int(Tag.SYMBOL)] == TICKER
    assert _roundtrip(msg) == msg


def test_security_status_request_unsubscribe() -> None:
    msg = SecurityStatusRequest.unsubscribe(TICKER)
    body = dict(msg.to_body_fields())
    assert body[int(Tag.SUBSCRIPTION_REQUEST_TYPE)] == SubscriptionRequestType.DISABLE.value
    assert body[int(Tag.SYMBOL)] == TICKER


# ---------------------------------------------------------------------------
# Inbound: W / X / Y / f round-trips + dispatch
# ---------------------------------------------------------------------------


def test_snapshot_full_refresh_roundtrip() -> None:
    msg = MarketDataSnapshotFullRefresh(
        symbol=TICKER,
        entries=[
            MDSnapshotEntry(
                md_entry_type=MDEntryType.BID.value,
                md_entry_px=Decimal("0.3500"),
                md_entry_size=Decimal("10.00"),
            ),
            MDSnapshotEntry(
                md_entry_type=MDEntryType.OFFER.value,
                md_entry_px=Decimal("0.6500"),
                md_entry_size=Decimal("5.00"),
            ),
        ],
    )
    body = dict(msg.to_body_fields())
    assert body[int(Tag.SYMBOL)] == TICKER
    assert body[int(Tag.NO_MD_ENTRIES)] == "2"
    assert _roundtrip(msg) == msg


def test_incremental_refresh_roundtrip() -> None:
    msg = MarketDataIncrementalRefresh(
        entries=[
            MDIncrementalEntry(
                md_update_action=MDUpdateAction.CHANGE.value,
                symbol=TICKER,
                md_entry_type=MDEntryType.BID.value,
                md_entry_px=Decimal("0.3500"),
                md_entry_size=Decimal("15.00"),
            ),
            MDIncrementalEntry(
                md_update_action=MDUpdateAction.DELETE.value,
                symbol=TICKER,
                md_entry_type=MDEntryType.OFFER.value,
                md_entry_px=Decimal("0.6500"),
                md_entry_size=Decimal("0.00"),
            ),
        ],
    )
    rt = _roundtrip(msg)
    assert rt == msg
    assert isinstance(rt, MarketDataIncrementalRefresh)
    assert [e.symbol for e in rt.entries] == [TICKER, TICKER]


def test_market_data_request_reject_roundtrip() -> None:
    msg = MarketDataRequestReject(
        md_req_rej_reason=MDReqRejReason.UNSUPPORTED_SUBSCRIPTION_REQUEST_TYPE.value,
        text="bad request type",
    )
    back = _roundtrip(msg)
    assert back == msg
    assert isinstance(back, MarketDataRequestReject)
    assert back.md_req_rej_reason == MDReqRejReason.UNSUPPORTED_SUBSCRIPTION_REQUEST_TYPE


def test_security_status_roundtrip() -> None:
    msg = SecurityStatus(symbol=TICKER, security_trading_status=SecurityTradingStatus.TRADING_HALT)
    back = _roundtrip(msg)
    assert back == msg
    assert isinstance(back, SecurityStatus)
    assert back.security_trading_status == SecurityTradingStatus.TRADING_HALT


def test_decode_app_message_md_types() -> None:
    for msg in (
        MarketDataSnapshotFullRefresh(symbol=TICKER),
        MarketDataIncrementalRefresh(),
        MarketDataRequestReject(md_req_rej_reason="2"),
        SecurityStatus(symbol=TICKER, security_trading_status=3),
    ):
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
        assert type(decoded) is type(msg)
        assert decoded == msg


# ---------------------------------------------------------------------------
# Order-book reconstruction
# ---------------------------------------------------------------------------


def _snapshot_for(symbol: str, *entries: tuple[str, str, str]) -> MarketDataSnapshotFullRefresh:
    return MarketDataSnapshotFullRefresh(
        symbol=symbol,
        entries=[
            MDSnapshotEntry(md_entry_type=t, md_entry_px=Decimal(px), md_entry_size=Decimal(sz))
            for t, px, sz in entries
        ],
    )


def _snapshot(*entries: tuple[str, str, str]) -> MarketDataSnapshotFullRefresh:
    return _snapshot_for(TICKER, *entries)


def _incr(symbol: str, action: str, side: str, px: str, sz: str) -> MarketDataIncrementalRefresh:
    return MarketDataIncrementalRefresh(
        entries=[
            MDIncrementalEntry(
                md_update_action=action,
                symbol=symbol,
                md_entry_type=side,
                md_entry_px=Decimal(px),
                md_entry_size=Decimal(sz),
            )
        ]
    )


def test_orderbook_snapshot_orders_levels() -> None:
    book = FixOrderBook()
    book.apply_snapshot(
        _snapshot(
            (MDEntryType.BID.value, "0.30", "10"),
            (MDEntryType.BID.value, "0.35", "20"),
            (MDEntryType.OFFER.value, "0.70", "5"),
            (MDEntryType.OFFER.value, "0.65", "8"),
        )
    )
    view = book.get(TICKER)
    assert view is not None
    # Bids best-first (descending), offers best-first (ascending).
    assert [(lvl.price, lvl.size) for lvl in view.bids] == [
        (Decimal("0.35"), Decimal("20")),
        (Decimal("0.30"), Decimal("10")),
    ]
    assert [(lvl.price, lvl.size) for lvl in view.offers] == [
        (Decimal("0.65"), Decimal("8")),
        (Decimal("0.70"), Decimal("5")),
    ]


def test_orderbook_incremental_change_and_delete() -> None:
    book = FixOrderBook()
    book.apply_snapshot(
        _snapshot(
            (MDEntryType.BID.value, "0.35", "20"),
            (MDEntryType.OFFER.value, "0.65", "8"),
        )
    )
    applied = book.apply_incremental(
        MarketDataIncrementalRefresh(
            entries=[
                # Change the bid size.
                MDIncrementalEntry(
                    md_update_action=MDUpdateAction.CHANGE.value,
                    symbol=TICKER,
                    md_entry_type=MDEntryType.BID.value,
                    md_entry_px=Decimal("0.35"),
                    md_entry_size=Decimal("25"),
                ),
                # Add a new bid level.
                MDIncrementalEntry(
                    md_update_action=MDUpdateAction.CHANGE.value,
                    symbol=TICKER,
                    md_entry_type=MDEntryType.BID.value,
                    md_entry_px=Decimal("0.34"),
                    md_entry_size=Decimal("12"),
                ),
                # Delete the offer level.
                MDIncrementalEntry(
                    md_update_action=MDUpdateAction.DELETE.value,
                    symbol=TICKER,
                    md_entry_type=MDEntryType.OFFER.value,
                    md_entry_px=Decimal("0.65"),
                    md_entry_size=Decimal("0"),
                ),
            ]
        )
    )
    assert applied == 3
    view = book.get(TICKER)
    assert view is not None
    assert [(lvl.price, lvl.size) for lvl in view.bids] == [
        (Decimal("0.35"), Decimal("25")),
        (Decimal("0.34"), Decimal("12")),
    ]
    assert view.offers == ()


def test_orderbook_change_to_zero_removes_level() -> None:
    book = FixOrderBook()
    book.apply_snapshot(_snapshot((MDEntryType.BID.value, "0.35", "20")))
    book.apply_incremental(
        MarketDataIncrementalRefresh(
            entries=[
                MDIncrementalEntry(
                    md_update_action=MDUpdateAction.CHANGE.value,
                    symbol=TICKER,
                    md_entry_type=MDEntryType.BID.value,
                    md_entry_px=Decimal("0.35"),
                    md_entry_size=Decimal("0"),
                )
            ]
        )
    )
    view = book.get(TICKER)
    assert view is not None
    assert view.bids == ()


def test_orderbook_incremental_before_snapshot_dropped() -> None:
    book = FixOrderBook()
    applied = book.apply_incremental(
        MarketDataIncrementalRefresh(
            entries=[
                MDIncrementalEntry(
                    md_update_action=MDUpdateAction.CHANGE.value,
                    symbol=TICKER,
                    md_entry_type=MDEntryType.BID.value,
                    md_entry_px=Decimal("0.35"),
                    md_entry_size=Decimal("20"),
                )
            ]
        )
    )
    assert applied == 0
    assert book.get(TICKER) is None


def test_orderbook_snapshot_replaces_stale_book() -> None:
    book = FixOrderBook()
    book.apply_snapshot(_snapshot((MDEntryType.BID.value, "0.35", "20")))
    book.apply_incremental(
        MarketDataIncrementalRefresh(
            entries=[
                MDIncrementalEntry(
                    md_update_action=MDUpdateAction.CHANGE.value,
                    symbol=TICKER,
                    md_entry_type=MDEntryType.BID.value,
                    md_entry_px=Decimal("0.34"),
                    md_entry_size=Decimal("99"),
                )
            ]
        )
    )
    # Gap recovery: clear + fresh snapshot fully replaces prior state.
    book.clear()
    assert book.get(TICKER) is None
    book.apply_snapshot(_snapshot((MDEntryType.BID.value, "0.40", "7")))
    view = book.get(TICKER)
    assert view is not None
    assert [(lvl.price, lvl.size) for lvl in view.bids] == [(Decimal("0.40"), Decimal("7"))]


def test_orderbook_incremental_routes_by_symbol() -> None:
    book = FixOrderBook()
    book.apply_snapshot(_snapshot((MDEntryType.BID.value, "0.35", "20")))  # TICKER only
    applied = book.apply_incremental(
        MarketDataIncrementalRefresh(
            entries=[
                MDIncrementalEntry(
                    md_update_action=MDUpdateAction.CHANGE.value,
                    symbol=TICKER,
                    md_entry_type=MDEntryType.BID.value,
                    md_entry_px=Decimal("0.36"),
                    md_entry_size=Decimal("3"),
                ),
                # Entry for an un-seeded symbol is dropped.
                MDIncrementalEntry(
                    md_update_action=MDUpdateAction.CHANGE.value,
                    symbol=TICKER2,
                    md_entry_type=MDEntryType.BID.value,
                    md_entry_px=Decimal("0.10"),
                    md_entry_size=Decimal("1"),
                ),
            ]
        )
    )
    assert applied == 1
    assert book.symbols() == {TICKER}


def test_orderbook_apply_ignores_non_md_message() -> None:
    book = FixOrderBook()
    book.apply(SecurityStatus(symbol=TICKER, security_trading_status=2))
    book.apply(MarketDataRequestReject(md_req_rej_reason="2"))
    assert book.symbols() == set()


def test_orderbook_snapshot_drops_zero_size_levels() -> None:
    # A 0-size level in a snapshot is "no level" (parity with an incremental Delete).
    book = FixOrderBook()
    book.apply_snapshot(
        _snapshot((MDEntryType.BID.value, "0.35", "0"), (MDEntryType.BID.value, "0.30", "10"))
    )
    view = book.get(TICKER)
    assert view is not None
    assert [(lvl.price, lvl.size) for lvl in view.bids] == [(Decimal("0.30"), Decimal("10"))]


def test_orderbook_empty_snapshot_clears_book() -> None:
    # The server sends an empty snapshot for a market it has no book for.
    book = FixOrderBook()
    book.apply_snapshot(_snapshot((MDEntryType.BID.value, "0.35", "20")))
    book.apply_snapshot(MarketDataSnapshotFullRefresh(symbol=TICKER))
    view = book.get(TICKER)
    assert view is not None
    assert view.bids == ()
    assert view.offers == ()
    assert TICKER in book.symbols()  # still seeded, just empty


def test_orderbook_incremental_unknown_action_dropped() -> None:
    # An out-of-spec MDUpdateAction must not be silently applied as a Change.
    book = FixOrderBook()
    book.apply_snapshot(_snapshot((MDEntryType.BID.value, "0.35", "20")))
    applied = book.apply_incremental(_incr(TICKER, "9", MDEntryType.BID.value, "0.35", "5"))
    assert applied == 0
    view = book.get(TICKER)
    assert view is not None
    assert [(lvl.price, lvl.size) for lvl in view.bids] == [(Decimal("0.35"), Decimal("20"))]


def test_orderbook_resubscribe_without_clear_leaves_stale_book() -> None:
    # Snapshot replacement is per-market: re-subscribing to a subset after a gap
    # WITHOUT clear() leaves stale books for markets not re-seeded — clear() is the
    # documented remedy.
    book = FixOrderBook()
    book.apply_snapshot(_snapshot_for(TICKER, (MDEntryType.BID.value, "0.35", "20")))
    book.apply_snapshot(_snapshot_for(TICKER2, (MDEntryType.BID.value, "0.40", "5")))
    # Re-snapshot only TICKER (as if re-subscribing to a smaller set post-gap).
    book.apply_snapshot(_snapshot_for(TICKER, (MDEntryType.BID.value, "0.36", "9")))
    assert book.get(TICKER2) is not None  # stale book survives — hazard the contract warns of

    book.clear()
    book.apply_snapshot(_snapshot_for(TICKER, (MDEntryType.BID.value, "0.36", "9")))
    assert book.get(TICKER2) is None
    assert book.get(TICKER) is not None


def test_orderbook_apply_dispatches_snapshot_and_incremental() -> None:
    book = FixOrderBook()
    book.apply(_snapshot((MDEntryType.BID.value, "0.35", "20")))
    book.apply(
        MarketDataIncrementalRefresh(
            entries=[
                MDIncrementalEntry(
                    md_update_action=MDUpdateAction.CHANGE.value,
                    symbol=TICKER,
                    md_entry_type=MDEntryType.BID.value,
                    md_entry_px=Decimal("0.35"),
                    md_entry_size=Decimal("21"),
                )
            ]
        )
    )
    view = book.get(TICKER)
    assert view is not None
    assert view.bids[0].size == Decimal("21")


# ---------------------------------------------------------------------------
# Session integration against the mock acceptor
# ---------------------------------------------------------------------------


async def test_market_data_subscription_flow(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.MARKET_DATA, on_message=on_message
    )
    await session.start()
    book = FixOrderBook()
    try:
        await session.send(MarketDataRequest.subscribe([TICKER]))
        await until(lambda: acceptor.first("V") is not None)
        req = acceptor.first("V")
        assert req is not None
        assert req.get(Tag.SUBSCRIPTION_REQUEST_TYPE) == (
            SubscriptionRequestType.SNAPSHOT_PLUS_UPDATES
        )
        assert req.get(Tag.SYMBOL) == TICKER

        snapshot = MarketDataSnapshotFullRefresh(
            symbol=TICKER,
            entries=[
                MDSnapshotEntry(
                    md_entry_type=MDEntryType.BID.value,
                    md_entry_px=Decimal("0.35"),
                    md_entry_size=Decimal("10"),
                ),
                MDSnapshotEntry(
                    md_entry_type=MDEntryType.OFFER.value,
                    md_entry_px=Decimal("0.65"),
                    md_entry_size=Decimal("5"),
                ),
            ],
        )
        incremental = MarketDataIncrementalRefresh(
            entries=[
                MDIncrementalEntry(
                    md_update_action=MDUpdateAction.CHANGE.value,
                    symbol=TICKER,
                    md_entry_type=MDEntryType.BID.value,
                    md_entry_px=Decimal("0.36"),
                    md_entry_size=Decimal("4"),
                )
            ]
        )
        await acceptor.push("W", snapshot.to_body_fields(), seq=2)
        await acceptor.push("X", incremental.to_body_fields(), seq=3)
        await until(lambda: len(received) == 2)

        for raw in received:
            book.apply(decode_app_message(raw))
        view = book.get(TICKER)
        assert view is not None
        assert [(lvl.price, lvl.size) for lvl in view.bids] == [
            (Decimal("0.36"), Decimal("4")),
            (Decimal("0.35"), Decimal("10")),
        ]
        assert [(lvl.price, lvl.size) for lvl in view.offers] == [(Decimal("0.65"), Decimal("5"))]
    finally:
        await session.close()


async def test_market_data_gap_recovery_resubscribe(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    """A dropped KalshiMD connection reconnects; clear() + re-subscribe rebuilds.

    KalshiMD has no retransmission, so a gap tears the session down and the
    client reconnects (fresh logon, ResetSeqNumFlag=Y). The caller clears the
    stale book and re-subscribes; the fresh snapshot rebuilds it.
    """
    received: list[RawMessage] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.MARKET_DATA, on_message=on_message
    )
    await session.start()
    book = FixOrderBook()
    try:
        await session.send(MarketDataRequest.subscribe([TICKER]))
        await until(lambda: acceptor.first("V") is not None)
        snap1 = _snapshot((MDEntryType.BID.value, "0.35", "20"))
        await acceptor.push("W", snap1.to_body_fields(), seq=2)
        await until(lambda: len(received) == 1)
        book.apply(decode_app_message(received[0]))
        assert book.get(TICKER) is not None

        # Gap: drop the connection. The MD session reconnects and re-logs-on.
        acceptor.drop_connection()
        await until(
            lambda: acceptor.connection_count >= 2 and session.state is FixSessionState.ACTIVE
        )

        # Caller's reconnect handling: clear stale state, then re-subscribe.
        book.clear()
        assert book.get(TICKER) is None
        await session.send(MarketDataRequest.subscribe([TICKER]))
        # Fresh snapshot on the new connection (seq reset to 1 by ResetSeqNumFlag=Y,
        # so the first server app message after the logon response is seq 2).
        snap2 = _snapshot((MDEntryType.BID.value, "0.40", "7"))
        await acceptor.push("W", snap2.to_body_fields(), seq=2)
        await until(lambda: len(received) == 2)
        book.apply(decode_app_message(received[1]))
        view = book.get(TICKER)
        assert view is not None
        assert [(lvl.price, lvl.size) for lvl in view.bids] == [(Decimal("0.40"), Decimal("7"))]
    finally:
        await session.close()
