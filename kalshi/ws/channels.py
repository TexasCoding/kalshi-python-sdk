"""Subscription management with client-side durable IDs and sid remapping."""

from __future__ import annotations

import asyncio
import collections
import json
import logging
from typing import Any

from websockets.exceptions import ConnectionClosed

from kalshi.errors import KalshiConnectionError, KalshiSubscriptionError
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

    def __init__(
        self,
        connection: ConnectionManager,
        *,
        stash_maxlen: int = 1000,
    ) -> None:
        self._connection = connection
        self._subscriptions: dict[int, Subscription] = {}  # client_id -> Subscription
        self._sid_to_client: dict[int, int] = {}  # server_sid -> client_id
        self._next_client_id = 1
        self._next_msg_id = 1
        # Stash for #176: data frames arriving during `_wait_for_response`
        # while `_stashing` is True (i.e., during `resubscribe_all`) are
        # captured here keyed by their server sid, then replayed through
        # the dispatcher once resubscribe completes and all new sids are
        # wired. Without this, the recv loop misses frames sent between
        # `_sid_to_client.clear()` and the ack landing in
        # `_wait_for_response`. Each per-sid deque is bounded by
        # `stash_maxlen` (1000 default — generous enough for normal
        # market-burst reconnects, low enough to bound memory if
        # resubscribe stalls).
        self._stash: dict[int, collections.deque[str]] = {}
        self._stashing: bool = False
        self._stash_maxlen: int = stash_maxlen
        # Sids that have already triggered an overflow WARNING in the current
        # resubscribe cycle. Cleared by `take_stash()` so the next resubscribe
        # gets fresh warnings. Without this gating, the `len(bucket) ==
        # maxlen` check below would be True on every append after the deque
        # fills, producing one WARNING per frame on every high-volume
        # channel during a prolonged stall.
        self._stash_warned: set[int] = set()

    def _get_msg_id(self) -> int:
        mid = self._next_msg_id
        self._next_msg_id += 1
        return mid

    async def _wait_for_response(
        self, msg_id: int, timeout: float = 5.0
    ) -> dict[str, Any]:
        """Read frames until we get the response matching our command id.

        Non-matching frames during a normal subscribe/unsubscribe are
        logged and discarded; the recv loop is paused so these frames
        would not have been consumed anyway.

        During ``resubscribe_all`` (``self._stashing is True``) the
        non-matching frames are STASHED by sid for replay after the
        resubscribe completes (#176). Without this, frames arriving
        between ``_sid_to_client.clear()`` and the new sid mapping are
        silently dropped — a real signal-loss bug under high-volume
        reconnect bursts.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise KalshiSubscriptionError(
                    f"Timed out waiting for response to command {msg_id}"
                )
            try:
                raw = await asyncio.wait_for(
                    self._connection.recv(), timeout=remaining
                )
            except ConnectionClosed as e:
                # F-P-05: surface as KalshiConnectionError instead of raw
                # websockets exception. The recv loop's reconnect path will
                # restore the subscription via resubscribe_all.
                raise KalshiConnectionError(
                    f"Connection closed while awaiting response to command {msg_id}"
                ) from e
            data: dict[str, Any] = json.loads(raw)
            if data.get("id") == msg_id:
                return data
            # Non-matching frame. During resubscribe, stash it by sid for
            # post-resubscribe replay; otherwise discard.
            if self._stashing:
                self._maybe_stash(raw, data)
            else:
                logger.debug(
                    "Discarding non-matching frame during subscribe: type=%s",
                    data.get("type"),
                )

    def _maybe_stash(self, raw: str, data: dict[str, Any]) -> None:
        """Save a raw data frame to the per-sid stash, if it carries a sid.

        Frames without a sid (control envelopes that fall through to the
        wait loop) are still discarded — they have nowhere to replay to.
        Per-sid deques are bounded by ``self._stash_maxlen``; on overflow,
        the deque silently evicts oldest (deque's own ``maxlen`` semantics)
        and a single WARNING per (sid, replay-cycle) is logged so callers
        notice congestion.
        """
        sid = data.get("sid")
        if sid is None:
            logger.debug(
                "Stash mode: dropping non-matching frame with no sid: type=%s",
                data.get("type"),
            )
            return
        bucket = self._stash.get(sid)
        if bucket is None:
            bucket = collections.deque(maxlen=self._stash_maxlen)
            self._stash[sid] = bucket
        elif len(bucket) == self._stash_maxlen and sid not in self._stash_warned:
            # About to evict oldest. Log once per (sid, resubscribe cycle):
            # without the warned-set gate this fires on every subsequent
            # append while the deque stays full, which under a prolonged
            # stall becomes per-frame log spam on every high-volume sid.
            self._stash_warned.add(sid)
            logger.warning(
                "Stash for sid %d is full (%d frames); oldest frame will be "
                "evicted. Resubscribe may be stalled or the channel is too "
                "high-volume for the configured stash_maxlen.",
                sid, self._stash_maxlen,
            )
        bucket.append(raw)

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
        # F-P-08: push sentinel before deleting so any held iterator exits
        # cleanly via StopAsyncIteration instead of hanging on queue.get().
        await sub.queue.put_sentinel()
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

        F-P-01: Each resubscribe is independent. If one fails, the failed
        subscription is removed and its iterator gets a sentinel, but other
        subscriptions continue working. The whole reconnect is not aborted.

        #176: ``_stashing`` is enabled for the duration of this method so
        non-matching data frames received by ``_wait_for_response`` are
        captured by sid for post-resubscribe replay. The caller
        (``KalshiWebSocket._handle_reconnect``) is responsible for
        draining the stash via ``take_stash()`` and routing the frames
        back through the dispatcher.
        """
        old_subs = dict(self._subscriptions)
        # F-P-03: clear sid->client mapping before sending any resubscribe
        # so stale in-flight frames with old sids can't mis-route.
        self._sid_to_client.clear()

        self._stashing = True
        try:
            for client_id, sub in old_subs.items():
                sub.server_sid = None  # Clear old sid
                try:
                    msg_id = self._get_msg_id()
                    # Re-subscribe with send_initial_snapshot for orderbook channels
                    params = sub.to_subscribe_params()
                    if sub.channel == "orderbook_delta":
                        params["send_initial_snapshot"] = True
                    cmd = {"id": msg_id, "cmd": "subscribe", "params": params}
                    await self._connection.send(cmd)

                    data = await self._wait_for_response(msg_id)
                    if data.get("type") == "error":
                        error_msg = data.get("msg", {})
                        raise KalshiSubscriptionError(
                            str(error_msg.get("msg", "Resubscribe failed")),
                            error_code=error_msg.get("code"),
                        )
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
                except Exception:
                    # F-P-01: per-sub failure is isolated. Push sentinel so the
                    # iterator exits cleanly, drop the subscription, continue with
                    # the rest. `exc_info=True` so an unexpected AttributeError /
                    # programming bug doesn't lose its traceback the way the
                    # earlier `: %s, e` formulation did.
                    logger.warning(
                        "Resubscribe failed for client_id=%d channel=%s",
                        client_id,
                        sub.channel,
                        exc_info=True,
                    )
                    await sub.queue.put_sentinel()
                    self._subscriptions.pop(client_id, None)
        finally:
            self._stashing = False

    def take_stash(self) -> dict[int, collections.deque[str]]:
        """Return and clear the resubscribe-window stash atomically (#176).

        Returns a ``{sid: deque[raw_frame]}`` mapping. The caller is
        responsible for replaying the raw frames through the dispatcher
        for each sid (typically via ``KalshiWebSocket._process_frame``).
        Frames whose sid did not get re-mapped during resubscribe should
        be dropped by the caller with a log.
        """
        stash, self._stash = self._stash, {}
        # Reset warning suppression so the next resubscribe cycle's overflow
        # warnings aren't accidentally muted by stale state.
        self._stash_warned.clear()
        return stash

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
