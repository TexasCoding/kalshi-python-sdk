"""Sequence tracking for perps WS channels that carry ``seq``.

Reuses :class:`kalshi.ws.sequence.SequenceTracker` (and re-exports
:class:`~kalshi.ws.sequence.SequenceGap`) unchanged — only the *channel set*
differs. The prediction-API tracker keys off ``SEQUENCED_CHANNELS``; perps
carries ``seq`` on ``orderbook_delta`` / ``orderbook_snapshot`` (margin order
book) and ``order_group_updates``. (``unsubscribed`` also carries ``seq`` per
spec, but it is a control frame handled by the dispatcher, not a sequenced data
channel.)

We subclass and override :meth:`should_track` against
:data:`PERPS_SEQUENCED_CHANNELS` rather than copying the watermark state machine
(gap / reset / duplicate handling, rollback, peek) which is identical.
"""

from __future__ import annotations

from kalshi.ws.sequence import SequenceGap, SequenceTracker

__all__ = ["PERPS_SEQUENCED_CHANNELS", "PerpsSequenceTracker", "SequenceGap"]

# Perps channels (and message types) that carry a per-sid ``seq``. Mirrors the
# prediction-API ``SEQUENCED_CHANNELS`` set; identical members today but kept
# perps-local so the two surfaces can diverge without cross-impact.
PERPS_SEQUENCED_CHANNELS = {
    "orderbook_delta",
    "orderbook_snapshot",
    "order_group_updates",
}


class PerpsSequenceTracker(SequenceTracker):
    """:class:`SequenceTracker` keyed to :data:`PERPS_SEQUENCED_CHANNELS`.

    Inherits the full watermark/gap/reset/duplicate state machine; only the
    set of channels eligible for tracking changes.
    """

    def should_track(self, channel: str) -> bool:
        """Whether this perps channel/message-type has sequence numbers."""
        return channel in PERPS_SEQUENCED_CHANNELS
