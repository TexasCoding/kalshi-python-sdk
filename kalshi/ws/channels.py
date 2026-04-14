"""Subscription management with client-side durable IDs and sid remapping."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from kalshi.ws.backpressure import MessageQueue, OverflowStrategy
from kalshi.ws.connection import ConnectionManager

logger = logging.getLogger("kalshi.ws")

# Keys forwarded from user params to the subscribe command.
_SUBSCRIBE_FORWARD_KEYS = (
    "market_ticker",
    "market_tickers",
    "market_id",
    "market_ids",
    "shard_factor",
    "shard_key",
    "send_initial_snapshot",
    "skip_ticker_ack",
)


class Subscription:
    """A single channel subscription with durable identity."""

    def __init__(
        self,
        client_id: int,
        channel: str,
        params: dict[str, Any],
        queue: MessageQueue[Any],
    ) -> None:
        self.client_id = client_id
        self.channel = channel
        self.params = params
        self.queue = queue
        self.server_sid: int | None = None

    def to_subscribe_params(self) -> dict[str, Any]:
        """Build the params dict for the subscribe command."""
        result: dict[str, Any] = {"channels": [self.channel]}
        for key in _SUBSCRIBE_FORWARD_KEYS:
            if key in self.params:
                result[key] = self.params[key]
        return result


class SubscriptionManager:
    """Manages WebSocket subscriptions with durable client-side IDs.

    Server-assigned sids change on reconnect. This manager maintains:
    - client_id -> Subscription mapping (durable)
    - server_sid -> client_id mapping (rebuilt on reconnect)
    """

    def __init__(self, connection: ConnectionManager) -> None:
        self._connection = connection
        self._subscriptions: dict[int, Subscription] = {}  # client_id -> Subscription
        self._sid_to_client: dict[int, int] = {}  # server_sid -> client_id
        self._next_client_id = 1
        self._next_msg_id = 1

    def _get_msg_id(self) -> int:
        mid = self._next_msg_id
        self._next_msg_id += 1
        return mid

    async def _wait_for_response(
        self, msg_id: int, timeout: float = 5.0
    ) -> dict[str, Any]:
        """Read frames until we get the response matching our command id.

        Non-matching frames (e.g. data messages queued before the ack) are
        logged and discarded.  The recv loop is paused during subscribe so
        these frames would not have been consumed anyway.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                from kalshi.errors import KalshiSubscriptionError

                raise KalshiSubscriptionError(
                    f"Timed out waiting for response to command {msg_id}"
                )
            raw = await asyncio.wait_for(
                self._connection.recv(), timeout=remaining
            )
            data: dict[str, Any] = json.loads(raw)
            if data.get("id") == msg_id:
                return data
            # Non-matching frame (data message that arrived before ack)
            logger.debug(
                "Discarding non-matching frame during subscribe: type=%s",
                data.get("type"),
            )

    async def subscribe(
        self,
        channel: str,
        params: dict[str, Any] | None = None,
        queue: MessageQueue[Any] | None = None,
        overflow: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        maxsize: int = 1000,
    ) -> Subscription:
        """Subscribe to a channel. Returns a Subscription with a durable client_id."""
        if queue is None:
            queue = MessageQueue(maxsize=maxsize, overflow=overflow)

        sub_params = params or {}
        client_id = self._next_client_id
        self._next_client_id += 1
        sub = Subscription(
            client_id=client_id, channel=channel, params=sub_params, queue=queue
        )

        # Send subscribe command
        msg_id = self._get_msg_id()
        cmd = {"id": msg_id, "cmd": "subscribe", "params": sub.to_subscribe_params()}
        await self._connection.send(cmd)

        # Read frames until we get our subscribe ack (by matching id)
        data = await self._wait_for_response(msg_id)
        if data.get("type") == "error":
            from kalshi.errors import KalshiSubscriptionError

            error_msg = data.get("msg", {})
            raise KalshiSubscriptionError(
                str(error_msg.get("msg", "Subscribe failed")),
                error_code=error_msg.get("code"),
            )

        server_sid = data.get("msg", {}).get("sid")
        if server_sid is not None:
            sub.server_sid = server_sid
            self._sid_to_client[server_sid] = client_id

        self._subscriptions[client_id] = sub
        logger.debug(
            "Subscribed to %s: client_id=%d, server_sid=%s",
            channel,
            client_id,
            server_sid,
        )
        return sub

    async def unsubscribe(self, client_id: int) -> None:
        """Unsubscribe by durable client_id."""
        sub = self._subscriptions.get(client_id)
        if not sub or sub.server_sid is None:
            return

        msg_id = self._get_msg_id()
        cmd = {"id": msg_id, "cmd": "unsubscribe", "params": {"sids": [sub.server_sid]}}
        await self._connection.send(cmd)

        await self._wait_for_response(msg_id)
        # Clean up mappings
        self._sid_to_client.pop(sub.server_sid, None)
        del self._subscriptions[client_id]
        logger.debug(
            "Unsubscribed client_id=%d (server_sid=%d)", client_id, sub.server_sid
        )

    async def update_subscription(
        self,
        client_id: int,
        action: str,  # "add_markets" or "delete_markets"
        market_tickers: list[str] | None = None,
        market_ids: list[str] | None = None,
        send_initial_snapshot: bool | None = None,
    ) -> None:
        """Add or remove markets from an existing subscription."""
        sub = self._subscriptions.get(client_id)
        if not sub or sub.server_sid is None:
            from kalshi.errors import KalshiSubscriptionError

            raise KalshiSubscriptionError("Subscription not found or not active")

        msg_id = self._get_msg_id()
        params: dict[str, Any] = {"sids": [sub.server_sid], "action": action}
        if market_tickers:
            params["market_tickers"] = market_tickers
        if market_ids:
            params["market_ids"] = market_ids
        if send_initial_snapshot is not None:
            params["send_initial_snapshot"] = send_initial_snapshot

        cmd = {"id": msg_id, "cmd": "update_subscription", "params": params}
        await self._connection.send(cmd)
        await self._wait_for_response(msg_id)
        logger.debug("Updated subscription client_id=%d action=%s", client_id, action)

    async def resubscribe_all(self) -> None:
        """Re-subscribe all active subscriptions after reconnect.

        Gets new server sids and updates the mapping.
        Iterators/callbacks continue working because they reference client_ids.
        """
        old_subs = dict(self._subscriptions)
        self._sid_to_client.clear()

        for client_id, sub in old_subs.items():
            sub.server_sid = None  # Clear old sid
            msg_id = self._get_msg_id()
            # Re-subscribe with send_initial_snapshot for orderbook channels
            params = sub.to_subscribe_params()
            if sub.channel == "orderbook_delta":
                params["send_initial_snapshot"] = True
            cmd = {"id": msg_id, "cmd": "subscribe", "params": params}
            await self._connection.send(cmd)

            data = await self._wait_for_response(msg_id)
            new_sid = data.get("msg", {}).get("sid")
            if new_sid is not None:
                sub.server_sid = new_sid
                self._sid_to_client[new_sid] = client_id
            logger.debug(
                "Resubscribed %s: client_id=%d, new_sid=%s",
                sub.channel,
                client_id,
                new_sid,
            )

    def get_subscription_by_sid(self, server_sid: int) -> Subscription | None:
        """Look up a subscription by current server sid."""
        client_id = self._sid_to_client.get(server_sid)
        if client_id is None:
            return None
        return self._subscriptions.get(client_id)

    def get_subscription(self, client_id: int) -> Subscription | None:
        """Look up a subscription by durable client id."""
        return self._subscriptions.get(client_id)

    @property
    def active_subscriptions(self) -> dict[int, Subscription]:
        """All active subscriptions keyed by client_id."""
        return dict(self._subscriptions)
