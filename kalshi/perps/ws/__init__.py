"""Kalshi Perps (margin) WebSocket client.

The transport foundation (#397): connection, subscription/command framing,
dispatch, sequence-gap and orderbook reuse, and the :class:`PerpsWebSocket`
facade. Per-channel payload models and typed ``subscribe_*`` helpers land in the
``perps: WS channels`` issue (#398).
"""

from kalshi.perps.ws.backpressure import MessageQueue, OverflowStrategy
from kalshi.perps.ws.client import PerpsWebSocket
from kalshi.perps.ws.connection import ConnectionState, PerpsConnectionManager

__all__ = [
    "ConnectionState",
    "MessageQueue",
    "OverflowStrategy",
    "PerpsConnectionManager",
    "PerpsWebSocket",
]
