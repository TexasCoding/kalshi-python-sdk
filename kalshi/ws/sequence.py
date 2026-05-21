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
    """Represents a detected sequence gap.

    ``kind`` is ``"gap"`` for the normal forward-gap case (``received >
    expected``) and ``"reset"`` for the seq-went-backwards case
    (``received <= last``, treated as a server-side reset that preserved
    the sid). Both cases require the same recovery action (clear local
    state, resubscribe), so they share the ``on_gap`` callback.
    """

    sid: int
    expected: int
    received: int
    kind: str = "gap"


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
        """Track a message's sequence number.

        Returns ``True`` if the caller should dispatch the message,
        ``False`` if it should be dropped.

        Three-way distinction for sequenced channels (#196):

        1. ``seq == expected`` — happy path. Advance watermark, dispatch.
        2. ``seq > expected`` — forward gap. Fire ``on_gap`` with
           ``kind="gap"``, advance watermark to ``seq``, drop the
           message (caller's resync handler will resubscribe).
        3. ``seq == last`` — exact duplicate. **Drop** without
           dispatch. Previously dispatched-without-tracking, which
           let a re-delivered delta be applied twice to the orderbook.
        4. ``seq < last`` — server-side reset that reused the sid (or
           seq=1 after a high watermark). Fire ``on_gap`` with
           ``kind="reset"``, rewind watermark to ``seq``, drop the
           message so the resync handler can resubscribe from a clean
           snapshot. Without this, every subsequent post-reset message
           would be treated as another duplicate until the old
           watermark was re-crossed, silently corrupting state.

        Non-sequenced channels and ``seq=None`` always return ``True``.
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

        if seq == last:
            # Exact duplicate. Drop instead of dispatching, so a redelivered
            # delta cannot be applied twice to the orderbook.
            logger.debug("Duplicate seq %d for sid %d (last=%d); dropping", seq, sid, last)
            return False

        if seq < last:
            # Server-side reset that preserved the sid (or seq=1 after a
            # high watermark). Treat as a gap with kind="reset" so the
            # gap handler clears local state and resubscribes from a
            # fresh snapshot. Rewind the watermark so subsequent
            # post-reset messages aren't silently dropped as "still old".
            gap = SequenceGap(sid=sid, expected=expected, received=seq, kind="reset")
            logger.warning(
                "Sequence reset on sid=%d: last=%d got=%d", sid, last, seq,
            )
            self._last_seq[sid] = seq
            if self._on_gap is not None:
                await self._on_gap(gap)
            return False

        # Forward gap (seq > expected).
        gap = SequenceGap(sid=sid, expected=expected, received=seq, kind="gap")
        logger.warning("Sequence gap: sid=%d expected=%d got=%d", sid, expected, seq)
        self._last_seq[sid] = seq  # Accept the new seq to continue tracking

        if self._on_gap is not None:
            await self._on_gap(gap)

        return False

    def peek(self, sid: int) -> int | None:
        """Return the current last-seen seq for ``sid``, or None if untracked.

        Capture this before calling :meth:`track` so the watermark can be
        restored via :meth:`rollback` if downstream dispatch fails — an
        already-advanced watermark would silently treat the dropped message
        as already-seen on the next gap check.
        """
        return self._last_seq.get(sid)

    def rollback(self, sid: int, prev: int | None) -> None:
        """Restore the last-seen seq for ``sid`` to ``prev``.

        If ``prev`` is None, the entry is removed entirely (the message was
        the first one seen for this sid and never landed). This is the
        compensation for a failed downstream dispatch — pair every successful
        :meth:`track` whose dispatch may raise with a captured :meth:`peek`
        and call this on failure.
        """
        if prev is None:
            self._last_seq.pop(sid, None)
        else:
            self._last_seq[sid] = prev

    def reset(self, sid: int) -> None:
        """Reset tracking for a subscription (after resync/resubscribe)."""
        self._last_seq.pop(sid, None)

    def reset_all(self) -> None:
        """Reset all tracking (after full reconnect)."""
        self._last_seq.clear()
