"""Tests for PerpsSequenceTracker — perps channel set, reuse of the state machine."""

from __future__ import annotations

from kalshi.perps.ws.sequence import (
    PERPS_SEQUENCED_CHANNELS,
    PerpsSequenceTracker,
    SequenceGap,
)


def test_sequenced_channels_set() -> None:
    assert {
        "orderbook_delta",
        "orderbook_snapshot",
        "order_group_updates",
    } == PERPS_SEQUENCED_CHANNELS


def test_should_track_only_perps_sequenced_channels() -> None:
    t = PerpsSequenceTracker()
    assert t.should_track("orderbook_delta")
    assert t.should_track("orderbook_snapshot")
    assert t.should_track("order_group_updates")
    # Non-sequenced perps channels pass through untracked.
    for ch in ("ticker", "trade", "fill", "user_order", "user_orders"):
        assert not t.should_track(ch)


def test_forward_gap_fires_for_order_group_updates() -> None:
    gaps: list[SequenceGap] = []
    t = PerpsSequenceTracker()
    # First seq seeds the watermark.
    ok, gap = t.track_sync(1, 1, "order_group_updates")
    assert ok and gap is None
    # Jump from 1 -> 3 is a forward gap.
    ok, gap = t.track_sync(1, 3, "order_group_updates")
    assert not ok
    assert gap is not None and gap.kind == "gap"
    assert gap.expected == 2 and gap.received == 3
    gaps.append(gap)
    assert gaps


def test_orderbook_delta_gap() -> None:
    t = PerpsSequenceTracker()
    t.track_sync(7, 5, "orderbook_delta")
    ok, gap = t.track_sync(7, 9, "orderbook_delta")
    assert not ok
    assert gap is not None and gap.kind == "gap"


def test_non_sequenced_channel_never_gaps() -> None:
    t = PerpsSequenceTracker()
    # Even a wild seq jump on ticker is a pass-through (untracked).
    ok, gap = t.track_sync(1, 1, "ticker")
    assert ok and gap is None
    ok, gap = t.track_sync(1, 99, "ticker")
    assert ok and gap is None
