"""Message dispatcher: parse raw frames, route to queues/callbacks."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from kalshi.ws.channels import SubscriptionManager
from kalshi.ws.models.base import ErrorMessage, ErrorPayload
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
from kalshi.ws.orderbook import OrderbookManager
from kalshi.ws.sequence import SequenceTracker

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
        seq_tracker: SequenceTracker | None = None,
        orderbook_mgr: OrderbookManager | None = None,
    ) -> None:
        self._sub_mgr = sub_mgr
        self._on_error = on_error
        self._seq_tracker = seq_tracker
        self._orderbook_mgr = orderbook_mgr
        self._callbacks: dict[str, Callable[[Any], Awaitable[None]]] = {}

    def register_callback(
        self, channel: str, callback: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Register a callback for a specific channel type.

        Messages on this channel are fanned out to BOTH the callback and any
        active subscription queue for the same channel. If an active
        subscription queue exists, a warning is logged so users know the
        callback was registered after the fact.
        """
        if any(
            sub.channel == channel
            for sub in self._sub_mgr.active_subscriptions.values()
        ):
            logger.warning(
                "register_callback(%r): an active subscription exists on this "
                "channel; messages will be delivered to BOTH the callback and "
                "the existing iterator queue.",
                channel,
            )
        self._callbacks[channel] = callback

    def unregister_callback(self, channel: str) -> None:
        """Remove a callback for a channel type."""
        self._callbacks.pop(channel, None)

    async def _handle_server_unsubscribe(self, data: dict[str, Any]) -> None:
        """Reap state for a server-initiated unsubscribe envelope (#81).

        Client-initiated unsubscribes consume the ack inside
        SubscriptionManager._wait_for_response, so any unsubscribed frame
        that reaches the dispatcher is server-initiated (admin action,
        session expiry) or a late ack after teardown. In either case the
        sid mappings, seq tracker state, and any held iterator must be
        cleaned up so they don't leak across reconnects.
        """
        # The envelope can carry sid at the top level or nested under msg.
        sid = data.get("sid")
        if sid is None:
            msg_body = data.get("msg")
            if isinstance(msg_body, dict):
                sid = msg_body.get("sid")
        if sid is None:
            logger.debug("server unsubscribed envelope without sid: %s", data)
            return

        client_id = self._sub_mgr._sid_to_client.pop(sid, None)
        if self._seq_tracker is not None:
            self._seq_tracker.reset(sid)
        # #206: server-initiated unsubscribe must also tear down local
        # orderbook state seeded by this sid; otherwise stale books are
        # served by ``OrderbookManager.get`` indefinitely after the
        # server reaps the sub.
        if self._orderbook_mgr is not None:
            self._orderbook_mgr.remove_by_sid(sid)

        if client_id is None:
            logger.debug(
                "server unsubscribed for unknown sid %d (already reaped)", sid
            )
            return

        sub = self._sub_mgr._subscriptions.pop(client_id, None)
        if sub is not None:
            # Wake any held iterator so async-for exits cleanly.
            await sub.queue.put_sentinel()
            logger.info(
                "Server-initiated unsubscribe: channel=%s sid=%d client_id=%d",
                sub.channel, sid, client_id,
            )

    async def _surface_channel_error(
        self, msg_type: str, data: dict[str, Any]
    ) -> None:
        """Route a channel-level error envelope to on_error (#82).

        AsyncAPI allows errors to ride on a typed message (e.g. a payload
        with an `error` field, or an unrecognized type that still carries
        error semantics) rather than the top-level type="error" envelope.
        Previously these fell through to a debug log and were silently
        dropped; surface them via on_error if registered, or log at
        WARNING with the envelope contents so the user has a signal.
        """
        if self._on_error is not None:
            # Best-effort: synthesize an ErrorMessage. If the payload
            # doesn't match the strict schema, fall back to model_construct
            # so the handler still fires with the raw payload visible.
            try:
                synthesized = {
                    "id": data.get("id", 0),
                    "type": "error",
                    "msg": data.get("error")
                    if isinstance(data.get("error"), dict)
                    else data.get("msg"),
                }
                error = ErrorMessage.model_validate(synthesized)
            except Exception:
                logger.error(
                    "Channel-level error envelope (type=%s) failed strict "
                    "ErrorMessage validation; firing on_error with raw payload: %s",
                    msg_type, data,
                )
                error = ErrorMessage.model_construct(
                    id=data.get("id", 0),
                    type="error",
                    msg=ErrorPayload.model_construct(code="unknown", msg=str(data)),
                )
            await self._on_error(error)
        else:
            logger.warning(
                "Channel-level error envelope (type=%s) with no on_error "
                "handler registered: %s",
                msg_type, data,
            )

    async def dispatch(
        self,
        data: dict[str, Any],
        *,
        pre_validated: BaseModel | None = None,
    ) -> None:
        """Route a pre-parsed frame to its subscriber.

        ``data`` is the already-decoded JSON envelope. The recv loop owns
        ``json.loads`` (so the dispatcher doesn't parse twice).

        ``pre_validated`` lets the recv loop hand off a typed model it
        already validated (orderbook snapshots/deltas applied to the
        local book), so the dispatcher routes the same instance to the
        queue without re-running Pydantic.
        """
        msg_type: str = data.get("type", "")

        # Skip control messages (handled by subscribe/unsubscribe flow)
        if msg_type in CONTROL_TYPES:
            if msg_type == "error" and self._on_error is not None:
                error = ErrorMessage.model_validate(data)
                await self._on_error(error)
            elif msg_type == "unsubscribed":
                await self._handle_server_unsubscribe(data)
            return

        # Channel-level error semantics on a non-"error" envelope (#82):
        # `data.get("error") is not None` (NOT `"error" in data`) so a
        # legitimate `"error": null` field on a typed envelope isn't
        # falsely routed as an error.
        if data.get("error") is not None:
            await self._surface_channel_error(msg_type, data)
            return

        # Parse into typed model
        model_cls = MESSAGE_MODELS.get(msg_type)
        if model_cls is None:
            logger.warning("Unknown message type: %s", msg_type)
            return

        if pre_validated is not None and isinstance(pre_validated, model_cls):
            parsed = pre_validated
        else:
            try:
                parsed = model_cls.model_validate(data)
            except Exception as exc:
                # Drop exc_info: Pydantic's ValidationError __str__ echoes the
                # full input including trade payload (price, count, user fields)
                # straight into log sinks. Surface type + exception class only.
                logger.warning(
                    "Failed to parse %s message: %s",
                    msg_type, type(exc).__name__,
                )
                # #241: re-raise so `_process_frame` can roll back the seq
                # watermark for sequenced channels (order_group_updates,
                # orderbook_*). Without this, a malformed sequenced frame
                # silently advances the watermark and the next legitimate
                # frame's gap is missed. The recv-loop's existing
                # malformed-frame handler catches and continues the loop.
                raise

        # Route to subscription queue
        sid = data.get("sid")
        if sid is None:
            logger.debug("Message without sid: type=%s", msg_type)
            return

        sub = self._sub_mgr.get_subscription_by_sid(sid)
        if sub is None:
            logger.debug("Message for unknown sid %d (may be stale)", sid)
            return

        # Fan out: deliver to the callback (if any) AND the subscription queue.
        # Previously the queue was skipped when a callback was registered,
        # which silently stranded any iterator on the same channel (#80).
        if sub.channel in self._callbacks:
            await self._callbacks[sub.channel](parsed)
        await sub.queue.put(parsed)
