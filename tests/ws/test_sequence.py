"""Tests for SequenceTracker."""
from __future__ import annotations

import pytest

from kalshi.ws.sequence import SEQUENCED_CHANNELS, SequenceGap, SequenceTracker


@pytest.mark.asyncio
class TestSequenceTracker:
    async def test_sequential_messages_ok(self) -> None:
        tracker = SequenceTracker()
        assert await tracker.track(1, 1, "orderbook_delta") is True
        assert await tracker.track(1, 2, "orderbook_delta") is True
        assert await tracker.track(1, 3, "orderbook_delta") is True

    async def test_gap_detected(self) -> None:
        gaps: list[SequenceGap] = []

        async def on_gap(gap: SequenceGap) -> None:
            gaps.append(gap)

        tracker = SequenceTracker(on_gap=on_gap)
        await tracker.track(1, 1, "orderbook_delta")
        result = await tracker.track(1, 4, "orderbook_delta")  # gap: expected 2
        assert result is False
        assert len(gaps) == 1
        assert gaps[0].expected == 2
        assert gaps[0].received == 4

    async def test_duplicate_seq_dropped(self) -> None:
        """#196: exact-duplicate seq is dropped (return False), not dispatched."""
        tracker = SequenceTracker()
        await tracker.track(1, 1, "orderbook_delta")
        await tracker.track(1, 2, "orderbook_delta")
        result = await tracker.track(1, 2, "orderbook_delta")  # duplicate
        assert result is False
        # Watermark unchanged.
        assert tracker.peek(1) == 2

    async def test_non_sequenced_channel_always_ok(self) -> None:
        tracker = SequenceTracker()
        assert await tracker.track(1, None, "ticker") is True
        assert await tracker.track(1, None, "fill") is True

    async def test_first_message_ok(self) -> None:
        tracker = SequenceTracker()
        assert await tracker.track(1, 1, "orderbook_snapshot") is True

    async def test_reset_sid(self) -> None:
        tracker = SequenceTracker()
        await tracker.track(1, 5, "orderbook_delta")
        tracker.reset(1)
        # After reset, next message is treated as first
        assert await tracker.track(1, 1, "orderbook_delta") is True

    async def test_reset_all(self) -> None:
        tracker = SequenceTracker()
        await tracker.track(1, 5, "orderbook_delta")
        await tracker.track(2, 3, "order_group_updates")
        tracker.reset_all()
        assert await tracker.track(1, 1, "orderbook_delta") is True
        assert await tracker.track(2, 1, "order_group_updates") is True

    async def test_independent_tracking_per_sid(self) -> None:
        tracker = SequenceTracker()
        await tracker.track(1, 1, "orderbook_delta")
        await tracker.track(2, 1, "orderbook_delta")
        assert await tracker.track(1, 2, "orderbook_delta") is True
        assert await tracker.track(2, 2, "orderbook_delta") is True

    async def test_should_track(self) -> None:
        tracker = SequenceTracker()
        assert tracker.should_track("orderbook_delta") is True
        assert tracker.should_track("orderbook_snapshot") is True
        assert tracker.should_track("order_group_updates") is True
        assert tracker.should_track("ticker") is False
        assert tracker.should_track("fill") is False

    async def test_sequenced_channels_constant(self) -> None:
        expected = {"orderbook_delta", "orderbook_snapshot", "order_group_updates"}
        assert expected == SEQUENCED_CHANNELS

    async def test_gap_updates_last_seq(self) -> None:
        """After a gap, tracking continues from the new seq."""
        gaps: list[SequenceGap] = []

        async def on_gap(gap: SequenceGap) -> None:
            gaps.append(gap)

        tracker = SequenceTracker(on_gap=on_gap)
        await tracker.track(1, 1, "orderbook_delta")
        await tracker.track(1, 5, "orderbook_delta")  # gap
        assert len(gaps) == 1
        # Next expected is 6
        assert await tracker.track(1, 6, "orderbook_delta") is True
        assert len(gaps) == 1  # no new gap

    async def test_none_seq_on_sequenced_channel(self) -> None:
        """seq=None on a sequenced channel is treated as OK (snapshot/first)."""
        tracker = SequenceTracker()
        assert await tracker.track(1, None, "orderbook_delta") is True


def test_issue_330_track_sync_happy_path_no_gap() -> None:
    """#330: sync fast path returns (True, None) for in-order frames without
    allocating any coroutine. Verified by calling it as plain sync."""
    tracker = SequenceTracker()
    assert tracker.track_sync(1, 1, "orderbook_delta") == (True, None)
    assert tracker.track_sync(1, 2, "orderbook_delta") == (True, None)
    assert tracker.track_sync(1, 3, "orderbook_delta") == (True, None)


def test_issue_330_track_sync_forward_gap_returns_gap() -> None:
    """#330: forward gap returns (False, SequenceGap(kind='gap')) without
    invoking on_gap — the caller awaits it. on_gap MUST NOT fire from
    track_sync even when one is registered on the tracker."""
    called: list[SequenceGap] = []

    async def on_gap(g: SequenceGap) -> None:
        called.append(g)

    tracker = SequenceTracker(on_gap=on_gap)
    tracker.track_sync(1, 1, "orderbook_delta")
    ok, gap = tracker.track_sync(1, 5, "orderbook_delta")
    assert ok is False
    assert gap is not None
    assert gap.kind == "gap"
    assert gap.expected == 2
    assert gap.received == 5
    # Hot path responsibility: track_sync NEVER awaits on_gap.
    assert called == []


def test_issue_330_track_sync_reset_returns_gap() -> None:
    """#330: backwards seq returns (False, SequenceGap(kind='reset')) and
    rewinds the watermark, without awaiting the callback."""
    tracker = SequenceTracker()
    tracker.track_sync(1, 10, "orderbook_delta")
    ok, gap = tracker.track_sync(1, 1, "orderbook_delta")
    assert ok is False
    assert gap is not None and gap.kind == "reset"
    assert tracker.peek(1) == 1


def test_issue_330_track_sync_duplicate_no_gap() -> None:
    """#330: exact duplicate returns (False, None) — drop without gap."""
    tracker = SequenceTracker()
    tracker.track_sync(1, 1, "orderbook_delta")
    tracker.track_sync(1, 2, "orderbook_delta")
    ok, gap = tracker.track_sync(1, 2, "orderbook_delta")
    assert ok is False
    assert gap is None


def test_issue_330_track_sync_non_sequenced_passthrough() -> None:
    """#330: non-sequenced channels and seq=None return (True, None)."""
    tracker = SequenceTracker()
    assert tracker.track_sync(1, None, "ticker") == (True, None)
    assert tracker.track_sync(1, 5, "fill") == (True, None)


@pytest.mark.asyncio
async def test_issue_330_async_wrapper_still_awaits_on_gap() -> None:
    """#330: the async track() wrapper must remain a working back-compat
    surface — gap callbacks still fire when callers use the old API."""
    gaps: list[SequenceGap] = []

    async def on_gap(g: SequenceGap) -> None:
        gaps.append(g)

    tracker = SequenceTracker(on_gap=on_gap)
    await tracker.track(1, 1, "orderbook_delta")
    result = await tracker.track(1, 5, "orderbook_delta")
    assert result is False
    assert len(gaps) == 1 and gaps[0].kind == "gap"
