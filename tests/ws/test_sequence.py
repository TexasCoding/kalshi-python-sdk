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

    async def test_duplicate_seq_accepted(self) -> None:
        tracker = SequenceTracker()
        await tracker.track(1, 1, "orderbook_delta")
        await tracker.track(1, 2, "orderbook_delta")
        result = await tracker.track(1, 2, "orderbook_delta")  # duplicate
        assert result is True  # duplicates are OK

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
