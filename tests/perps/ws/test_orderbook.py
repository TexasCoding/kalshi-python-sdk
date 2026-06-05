"""Tests for PerpsOrderbookManager — bid/ask side handling (no yes/no leak)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from kalshi.perps.ws.models.control import PerpsBookSide
from kalshi.perps.ws.orderbook import PerpsOrderbookManager


@dataclass
class _SnapMsg:
    market_ticker: str
    bid: dict = field(default_factory=dict)
    ask: dict = field(default_factory=dict)


@dataclass
class _Snap:
    sid: int
    msg: _SnapMsg


@dataclass
class _DeltaMsg:
    market_ticker: str
    price: Decimal
    delta: Decimal
    side: object


@dataclass
class _Delta:
    sid: int
    msg: _DeltaMsg


def _snap(sid: int, ticker: str, bid: dict, ask: dict) -> _Snap:
    return _Snap(sid=sid, msg=_SnapMsg(market_ticker=ticker, bid=dict(bid), ask=dict(ask)))


def test_apply_snapshot_builds_bid_ask_book() -> None:
    mgr = PerpsOrderbookManager()
    book = mgr.apply_snapshot(
        _snap(
            1, "BTC-PERP",
            {Decimal("0.40"): Decimal("10"), Decimal("0.41"): Decimal("5")},
            {Decimal("0.60"): Decimal("8")},
        )
    )
    assert book.ticker == "BTC-PERP"
    # Levels emitted price-ascending.
    assert [lvl.price for lvl in book.bids] == [Decimal("0.40"), Decimal("0.41")]
    assert [lvl.quantity for lvl in book.bids] == [Decimal("10"), Decimal("5")]
    assert [lvl.price for lvl in book.asks] == [Decimal("0.60")]


def test_delta_applies_to_bid_side_enum_and_string() -> None:
    mgr = PerpsOrderbookManager()
    mgr.apply_snapshot(_snap(1, "X", {Decimal("0.40"): Decimal("10")}, {}))
    # Enum side
    mgr.apply_delta(_Delta(1, _DeltaMsg("X", Decimal("0.40"), Decimal("5"), PerpsBookSide.BID)))
    assert mgr.get("X").bids[0].quantity == Decimal("15")
    # Raw wire string side
    mgr.apply_delta(_Delta(1, _DeltaMsg("X", Decimal("0.40"), Decimal("-15"), "bid")))
    # Level removed when qty hits zero.
    assert mgr.get("X").bids == []


def test_delta_to_ask_side() -> None:
    mgr = PerpsOrderbookManager()
    mgr.apply_snapshot(_snap(1, "X", {}, {Decimal("0.60"): Decimal("3")}))
    mgr.apply_delta(_Delta(1, _DeltaMsg("X", Decimal("0.61"), Decimal("7"), "ask")))
    asks = {lvl.price: lvl.quantity for lvl in mgr.get("X").asks}
    assert asks == {Decimal("0.60"): Decimal("3"), Decimal("0.61"): Decimal("7")}
    # Bid side untouched (guards against yes/no hardcode regression).
    assert mgr.get("X").bids == []


def test_delta_before_snapshot_is_noop() -> None:
    mgr = PerpsOrderbookManager()
    assert mgr.apply_delta(_Delta(1, _DeltaMsg("X", Decimal("0.4"), Decimal("1"), "bid"))) is None


def test_remove_by_sid_tears_down_all_markets() -> None:
    mgr = PerpsOrderbookManager()
    mgr.apply_snapshot(_snap(9, "A", {Decimal("0.1"): Decimal("1")}, {}))
    mgr.apply_snapshot(_snap(9, "B", {Decimal("0.2"): Decimal("1")}, {}))
    removed = mgr.remove_by_sid(9)
    assert set(removed) == {"A", "B"}
    assert mgr.get("A") is None and mgr.get("B") is None


def test_get_caches_until_mutation() -> None:
    mgr = PerpsOrderbookManager()
    mgr.apply_snapshot(_snap(1, "X", {Decimal("0.4"): Decimal("10")}, {}))
    a = mgr.get("X")
    b = mgr.get("X")
    assert a is b  # identity-stable cache
    mgr.apply_delta(_Delta(1, _DeltaMsg("X", Decimal("0.4"), Decimal("1"), "bid")))
    c = mgr.get("X")
    assert c is not a  # invalidated on mutation
