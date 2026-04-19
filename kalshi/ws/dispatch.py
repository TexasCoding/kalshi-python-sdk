"""Message dispatcher: parse raw frames, route to queues/callbacks."""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from kalshi.ws.channels import SubscriptionManager
from kalshi.ws.models.base import ErrorMessage
from kalshi.ws.models.communications import CommunicationsMessage
from kalshi.ws.models.fill import FillMessage
from kalshi.ws.models.market_lifecycle import MarketLifecycleMessage
from kalshi.ws.models.market_positions import MarketPositionsMessage
from kalshi.ws.models.multivariate import MultivariateLifecycleMessage, MultivariateMessage
from kalshi.ws.models.order_group import OrderGroupMessage
from kalshi.ws.models.orderbook_delta import OrderbookDeltaMessage, OrderbookSnapshotMessage
from kalshi.ws.models.ticker import TickerMessage
from kalshi.ws.models.trade import TradeMessage
from kalshi.ws.models.user_orders import UserOrdersMessage

logger = logging.getLogger("kalshi.ws")

# Map message type string -> Pydantic model class
MESSAGE_MODELS: dict[str, type[BaseModel]] = {
    "orderbook_snapshot": OrderbookSnapshotMessage,
    "orderbook_delta": OrderbookDeltaMessage,
    "ticker": TickerMessage,
    "trade": TradeMessage,
    "fill": FillMessage,
    "market_position": MarketPositionsMessage,
    "user_order": UserOrdersMessage,
    "order_group_updates": OrderGroupMessage,
    "market_lifecycle_v2": MarketLifecycleMessage,
    "multivariate_lookup": MultivariateMessage,
    "multivariate_market_lifecycle": MultivariateLifecycleMessage,
    "communications": CommunicationsMessage,
}

# Control message types (not routed to subscription queues)
CONTROL_TYPES = {"subscribed", "unsubscribed", "ok", "error"}


class MessageDispatcher:
    """Routes parsed WebSocket messages to the correct subscription queue."""

    def __init__(
        self,
        sub_mgr: SubscriptionManager,
        on_error: Callable[[ErrorMessage], Awaitable[None]] | None = None,
    ) -> None:
        self._sub_mgr = sub_mgr
        self._on_error = on_error
        self._callbacks: dict[str, Callable[[Any], Awaitable[None]]] = {}

    def register_callback(
        self, channel: str, callback: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Register a callback for a specific channel type."""
        self._callbacks[channel] = callback

    def unregister_callback(self, channel: str) -> None:
        """Remove a callback for a channel type."""
        self._callbacks.pop(channel, None)

    async def dispatch(self, raw: str) -> None:
        """Parse a raw JSON frame and route it."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Received non-JSON frame: %s", raw[:100])
            return

        msg_type: str = data.get("type", "")

        # Skip control messages (handled by subscribe/unsubscribe flow)
        if msg_type in CONTROL_TYPES:
            if msg_type == "error" and self._on_error is not None:
                error = ErrorMessage.model_validate(data)
                await self._on_error(error)
            return

        # Parse into typed model
        model_cls = MESSAGE_MODELS.get(msg_type)
        if model_cls is None:
            logger.warning("Unknown message type: %s", msg_type)
            return

        try:
            parsed = model_cls.model_validate(data)
        except Exception:
            logger.warning("Failed to parse %s message", msg_type, exc_info=True)
            return

        # Route to subscription queue
        sid = data.get("sid")
        if sid is None:
            logger.debug("Message without sid: type=%s", msg_type)
            return

        sub = self._sub_mgr.get_subscription_by_sid(sid)
        if sub is None:
            logger.debug("Message for unknown sid %d (may be stale)", sid)
            return

        # Check for callback first
        if sub.channel in self._callbacks:
            await self._callbacks[sub.channel](parsed)
        else:
            # Route to queue
            await sub.queue.put(parsed)
