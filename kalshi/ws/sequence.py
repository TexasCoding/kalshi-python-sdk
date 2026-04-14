"""Sequence number tracking for channels that support it."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger("kalshi.ws")

# Channels that have seq fields
SEQUENCED_CHANNELS = {"orderbook_delta", "orderbook_snapshot", "order_group_updates"}


@dataclass
class SequenceGap:
    """Represents a detected sequence gap."""

    sid: int
    expected: int
    received: int


class SequenceTracker:
    """Tracks sequence numbers per subscription for gap detection.

    Only tracks channels in SEQUENCED_CHANNELS. All other channels
    are passed through without tracking.
    """

    def __init__(
        self,
        on_gap: Callable[[SequenceGap], Awaitable[None]] | None = None,
    ) -> None:
        self._last_seq: dict[int, int] = {}  # sid -> last seen seq
        self._on_gap = on_gap

    def should_track(self, channel: str) -> bool:
        """Whether this channel type has sequence numbers."""
        return channel in SEQUENCED_CHANNELS

    async def track(self, sid: int, seq: int | None, channel: str) -> bool:
        """Track a message's sequence number. Returns True if OK, False if gap detected.

        For non-sequenced channels, always returns True.
        For seq=None on a sequenced channel, returns True (first message or snapshot).
        """
        if not self.should_track(channel) or seq is None:
            return True

        last = self._last_seq.get(sid)

        if last is None:
            # First message for this sid
            self._last_seq[sid] = seq
            return True

        expected = last + 1
        if seq == expected:
            self._last_seq[sid] = seq
            return True

        if seq <= last:
            # Duplicate or old message, skip
            logger.debug("Duplicate seq %d for sid %d (last=%d)", seq, sid, last)
            return True

        # Gap detected
        gap = SequenceGap(sid=sid, expected=expected, received=seq)
        logger.warning("Sequence gap: sid=%d expected=%d got=%d", sid, expected, seq)
        self._last_seq[sid] = seq  # Accept the new seq to continue tracking

        if self._on_gap is not None:
            await self._on_gap(gap)

        return False

    def reset(self, sid: int) -> None:
        """Reset tracking for a subscription (after resync/resubscribe)."""
        self._last_seq.pop(sid, None)

    def reset_all(self) -> None:
        """Reset all tracking (after full reconnect)."""
        self._last_seq.clear()
