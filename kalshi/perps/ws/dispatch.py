"""Perps message dispatcher: parse raw margin frames, route to queues/callbacks.

Mirrors :class:`kalshi.ws.dispatch.MessageDispatcher`. ``CONTROL_TYPES`` is
``{"subscribed", "unsubscribed", "ok", "error"}`` (same control surface as the
prediction API). ``MESSAGE_MODELS`` maps each data ``type`` (``ticker``,
``trade``, ``fill``, ``user_order``, ``orderbook_*``, ``order_group_updates``)
to its Pydantic payload model. The dispatcher also handles control-frame
routing (orphan-subscribed cleanup, server-initiated unsubscribe teardown) and
the "unknown message type" path.

``type: "ok"`` collision: the perps ``list_subscriptions`` reply and the
``update_subscription`` ack BOTH use ``type: "ok"``. They are disambiguated by
the *shape of* ``msg`` — an **array** for list-subscriptions, an **object**
(or absent) for the update ack — NOT by ``type``. Both are command acks consumed
by :class:`~kalshi.perps.ws.channels.PerpsSubscriptionManager` (matched on
``id``), so they don't normally reach the dispatcher; the disambiguation helper
:meth:`classify_ok` is provided so the framing layer can branch on ``msg`` shape
wherever an ``ok`` frame must be classified.

Timestamp note: control envelopes carry no timestamps. Channel payloads (#398)
carry epoch-ms ``int`` ``*_ms`` fields; this dispatcher routes the typed model
without touching them, so the int-typed convention is preserved.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel

from kalshi.perps.ws.channels import PerpsSubscriptionManager
from kalshi.perps.ws.models.control import (
    PerpsErrorResponse,
    UnsubscribeCommand,
    UnsubscribeParams,
)
from kalshi.perps.ws.models.fill import MarginFillMessage
from kalshi.perps.ws.models.order_group import OrderGroupUpdatesMessage
from kalshi.perps.ws.models.orderbook import (
    MarginOrderbookDeltaMessage,
    MarginOrderbookSnapshotMessage,
)
from kalshi.perps.ws.models.ticker import MarginTickerMessage
from kalshi.perps.ws.models.trade import MarginTradeMessage
from kalshi.perps.ws.models.user_orders import MarginUserOrderMessage
from kalshi.perps.ws.orderbook import PerpsOrderbookManager
from kalshi.perps.ws.sequence import PerpsSequenceTracker

logger = logging.getLogger("kalshi.perps.ws")

# Map envelope ``type`` string -> Pydantic model class (#398). Keyed by the
# wire ``type``, which differs from the subscribe channel name for the order
# book (channel ``orderbook_delta`` -> types ``orderbook_snapshot`` +
# ``orderbook_delta``) and user orders (channel ``user_orders`` -> type
# ``user_order``).
MESSAGE_MODELS: dict[str, type[BaseModel]] = {
    "orderbook_snapshot": MarginOrderbookSnapshotMessage,
    "orderbook_delta": MarginOrderbookDeltaMessage,
    "ticker": MarginTickerMessage,
    "trade": MarginTradeMessage,
    "fill": MarginFillMessage,
    "user_order": MarginUserOrderMessage,
    "order_group_updates": OrderGroupUpdatesMessage,
}

# Control message types (not routed to subscription queues).
CONTROL_TYPES = {"subscribed", "unsubscribed", "ok", "error"}


def classify_ok(data: dict[str, Any]) -> Literal["list_subscriptions", "update_ack"]:
    """Disambiguate a ``type: "ok"`` frame by the shape of its ``msg``.

    The perps ``list_subscriptions`` response and the ``update_subscription``
    ack share ``type: "ok"``. The framing layer branches on ``msg`` being an
    **array** (``list_subscriptions``) vs an object / absent (``update_ack``),
    NOT on ``type`` — encoded here rather than excluded from drift checks.
    """
    return "list_subscriptions" if isinstance(data.get("msg"), list) else "update_ack"


class PerpsMessageDispatcher:
    """Routes parsed perps WebSocket messages to the correct subscription queue."""

    def __init__(
        self,
        sub_mgr: PerpsSubscriptionManager,
        on_error: Callable[[PerpsErrorResponse], Awaitable[None]] | None = None,
        seq_tracker: PerpsSequenceTracker | None = None,
        orderbook_mgr: PerpsOrderbookManager | None = None,
    ) -> None:
        self._sub_mgr = sub_mgr
        self._on_error = on_error
        self._seq_tracker = seq_tracker
        self._orderbook_mgr = orderbook_mgr
        self._callbacks: dict[str, Callable[[Any], Awaitable[None]]] = {}
        # Sids the client never owned but proactively unsubscribed (orphan
        # subscribe acks). When the server's ``unsubscribed`` ack for one of
        # these arrives, ``_handle_server_unsubscribe`` short-circuits instead
        # of running full teardown — otherwise a sid the server has already
        # reused for a freshly-completed subscribe would have its seq watermark
        # and orderbook state clobbered by the late orphan ack.
        self._pending_orphan_unsub: set[int] = set()

    def register_callback(
        self, channel: str, callback: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Register a callback for a specific channel type.

        Messages on this channel are fanned out to BOTH the callback and any
        active subscription queue for the same channel.
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
        """Reap state for a server-initiated unsubscribe envelope.

        Client-initiated unsubscribes consume the ack inside
        ``PerpsSubscriptionManager._wait_for_response``, so any unsubscribed
        frame that reaches the dispatcher is server-initiated or a late ack
        after teardown. Either way the sid mappings, seq tracker state, and
        any held iterator must be cleaned up so they don't leak across
        reconnects.
        """
        sid = data.get("sid")
        if sid is None:
            msg_body = data.get("msg")
            if isinstance(msg_body, dict):
                sid = msg_body.get("sid")
        if sid is None:
            logger.debug("server unsubscribed envelope without sid: %s", data)
            return

        # Correlate orphan-unsubscribe acks: short-circuit unconditionally so a
        # reused sid's new owner isn't torn down by a late orphan ack.
        if sid in self._pending_orphan_unsub:
            self._pending_orphan_unsub.discard(sid)
            logger.debug(
                "server unsubscribed: orphan-correlation ack for sid %d", sid
            )
            return

        client_id = self._sub_mgr._sid_to_client.pop(sid, None)
        if self._seq_tracker is not None:
            self._seq_tracker.reset(sid)
        if self._orderbook_mgr is not None:
            self._orderbook_mgr.remove_by_sid(sid)

        sub = (
            self._sub_mgr._subscriptions.pop(client_id, None)
            if client_id is not None
            else None
        )
        if sub is not None:
            await sub.queue.put_sentinel()
            logger.info(
                "Server-initiated unsubscribe: channel=%s sid=%d client_id=%d",
                sub.channel, sid, client_id,
            )
        elif client_id is None:
            logger.debug(
                "server unsubscribed for unknown sid %d (already reaped)", sid
            )

    async def _handle_orphan_subscribed(self, data: dict[str, Any]) -> None:
        """Release a server-side sid whose subscribe ack has no client mapping.

        Normal subscribes consume the ``subscribed`` ack inside
        ``PerpsSubscriptionManager._wait_for_response`` and install the
        ``sid -> client_id`` mapping before the dispatcher sees it. If the
        awaiting task is cancelled between send and ack, the ack lands here
        with a sid that has no mapping; without intervention the server holds
        an active sid the client can never address again. Best-effort: send an
        ``unsubscribe`` for the orphan sid.
        """
        sid = data.get("sid")
        if sid is None:
            msg_body = data.get("msg")
            if isinstance(msg_body, dict):
                sid = msg_body.get("sid")
        if not isinstance(sid, int):
            logger.debug(
                "Orphan-subscribed handler: no int sid in envelope: %s", data
            )
            return
        if sid in self._sub_mgr._sid_to_client:
            return
        # Mark the sid as orphan-unsubscribed BEFORE sending so the eventual
        # ``unsubscribed`` ack short-circuits in ``_handle_server_unsubscribe``.
        self._pending_orphan_unsub.add(sid)
        logger.warning(
            "Orphan subscribed ack for sid=%d (no client mapping); "
            "sending unsubscribe to release server-side state.",
            sid,
        )
        try:
            msg_id = self._sub_mgr._get_msg_id()
            # Build through the extra="forbid" model (like every other command
            # path) so a key typo fails here instead of silently on the wire.
            cmd = UnsubscribeCommand(id=msg_id, params=UnsubscribeParams(sids=[sid]))
            await self._sub_mgr._connection.send(
                cmd.model_dump(exclude_none=True, by_alias=True, mode="json")
            )
        except Exception:
            logger.warning(
                "Failed to send orphan-unsubscribe for sid=%d", sid, exc_info=True
            )

    async def dispatch(
        self,
        data: dict[str, Any],
        *,
        pre_validated: BaseModel | None = None,
    ) -> None:
        """Route a pre-parsed frame to its subscriber.

        ``data`` is the already-decoded JSON envelope. ``pre_validated`` lets
        the recv loop hand off a typed model it already validated (orderbook
        snapshots/deltas applied to the local book), so the dispatcher routes
        the same instance without re-running Pydantic.
        """
        msg_type: str = data.get("type", "")

        # Skip control messages (handled by subscribe/unsubscribe flow). ``ok``
        # frames (update_ack / list_subscriptions) are command acks consumed by
        # the subscription manager on ``id``; if one falls through here it has
        # no further routing, so it is silently absorbed by this branch.
        if msg_type in CONTROL_TYPES:
            if msg_type == "error" and self._on_error is not None:
                error = PerpsErrorResponse.model_validate(data)
                await self._on_error(error)
            elif msg_type == "unsubscribed":
                await self._handle_server_unsubscribe(data)
            elif msg_type == "subscribed":
                await self._handle_orphan_subscribed(data)
            return

        # Parse into the typed payload model registered for this wire ``type``.
        model_cls = MESSAGE_MODELS.get(msg_type)
        if model_cls is None:
            logger.warning("Unknown message type: %s", msg_type)
            return

        if pre_validated is not None and isinstance(pre_validated, model_cls):
            parsed: BaseModel = pre_validated
        else:
            try:
                parsed = model_cls.model_validate(data)
            except Exception as exc:
                logger.warning(
                    "Failed to parse %s message: %s", msg_type, type(exc).__name__
                )
                # Re-raise so the recv loop can roll back the seq watermark for
                # sequenced channels (orderbook_*, order_group_updates).
                raise

        sid = data.get("sid")
        if sid is None:
            logger.debug("Message without sid: type=%s", msg_type)
            return

        sub = self._sub_mgr.get_subscription_by_sid(sid)
        if sub is None:
            logger.debug("Message for unknown sid %d (may be stale)", sid)
            return

        # Fan out: deliver to the callback (if any) AND the subscription queue.
        if sub.channel in self._callbacks:
            await self._callbacks[sub.channel](parsed)
        await sub.queue.put(parsed)
