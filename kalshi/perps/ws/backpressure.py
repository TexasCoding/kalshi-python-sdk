"""Backpressure primitives for the perps WebSocket — re-exported verbatim.

The perps WS has no perps-specific overflow behavior, so it reuses
:class:`kalshi.ws.backpressure.MessageQueue` and
:class:`~kalshi.ws.backpressure.OverflowStrategy` unchanged. This module is a
thin re-export so the perps WS package presents the same module layout as
``kalshi/ws/`` (mirror parity) without duplicating the bounded-queue logic.
"""

from __future__ import annotations

from kalshi.ws.backpressure import MessageQueue, OverflowStrategy

__all__ = ["MessageQueue", "OverflowStrategy"]
