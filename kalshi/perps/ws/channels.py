"""Perps subscription management with client-side durable IDs and sid remapping.

Mirrors :class:`kalshi.ws.channels.SubscriptionManager` but with the **perps
margin command grammar**: ``subscribe`` (``params.channels``), ``unsubscribe``
(``params.sids``), ``update_subscription`` in two shapes (array ``sids`` and
scalar ``sid``), and ``list_subscriptions`` (no params; array ``msg`` reply).

Command frames are built from the ``extra="forbid"`` params/command models in
:mod:`kalshi.perps.ws.models.control` and serialized via
``model_dump(exclude_none=True, by_alias=True, mode="json")`` so a typo'd key
fails at build time rather than silently on the wire.

The ``.list``-shadowing convention from CLAUDE.md applies: this surrounding API
has a ``list_subscriptions`` method, so list type annotations use
``builtins.list[T]`` throughout.
"""

from __future__ import annotations

import asyncio
import builtins
import collections
import json
import logging
from collections.abc import Callable
from typing import Any

from websockets.exceptions import ConnectionClosed

from kalshi.errors import KalshiConnectionError, KalshiSubscriptionError
from kalshi.perps.ws.backpressure import MessageQueue, OverflowStrategy
from kalshi.perps.ws.connection import PerpsConnectionManager
from kalshi.perps.ws.models.control import (
    ListSubscriptionsCommand,
    SubscribeCommand,
    SubscribeParams,
    SubscriptionEntry,
    UnsubscribeCommand,
    UnsubscribeParams,
    UpdateSubscriptionAction,
    UpdateSubscriptionCommand,
    UpdateSubscriptionParams,
)

logger = logging.getLogger("kalshi.perps.ws")

class PerpsSubscription:
    """A single perps channel subscription with durable identity."""

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
        """Build the validated ``params`` dict for the subscribe command.

        Forwarded keys are validated through :class:`SubscribeParams`
        (``extra="forbid"``); an unknown key raises
        :class:`~kalshi.errors.KalshiSubscriptionError` at submit time rather
        than being silently dropped on the wire.
        """
        # Validate the FULL user-supplied params (not just the known keys) so an
        # unknown key trips SubscribeParams' extra="forbid" and fails fast at
        # submit time rather than being silently dropped on the wire.
        forward: dict[str, Any] = {"channels": [self.channel], **self.params}
        try:
            model = SubscribeParams.model_validate(forward)
        except Exception as exc:
            raise KalshiSubscriptionError(
                f"Invalid subscribe params for channel {self.channel!r}: {exc}",
                channel=self.channel,
                op="subscribe",
            ) from exc
        return model.model_dump(exclude_none=True, by_alias=True, mode="json")


class PerpsSubscriptionManager:
    """Manages perps WebSocket subscriptions with durable client-side IDs.

    Server-assigned sids change on reconnect. This manager maintains:

    - ``client_id -> PerpsSubscription`` (durable)
    - ``server_sid -> client_id`` (rebuilt on reconnect)
    """

    def __init__(
        self,
        connection: PerpsConnectionManager,
        *,
        stash_maxlen: int = 1000,
        json_loads: Callable[[bytes | str], Any] | None = None,
    ) -> None:
        self._connection = connection
        self._json_loads: Callable[[bytes | str], Any] = (
            json_loads if json_loads is not None else json.loads
        )
        self._subscriptions: dict[int, PerpsSubscription] = {}
        self._sid_to_client: dict[int, int] = {}
        self._next_client_id = 1
        self._next_msg_id = 1
        # Resubscribe-window stash (see SubscriptionManager #176): data frames
        # arriving during ``resubscribe_all`` while ``_stashing`` is True are
        # captured by sid for post-resubscribe replay.
        self._stash: dict[int, collections.deque[str]] = {}
        self._stashing: bool = False
        self._stash_maxlen: int = stash_maxlen
        self._stash_warned: set[int] = set()

    def _get_msg_id(self) -> int:
        mid = self._next_msg_id
        self._next_msg_id += 1
        return mid

    async def _wait_for_response(
        self,
        msg_id: int,
        timeout: float = 5.0,
        *,
        channel: str | None = None,
        client_id: int | None = None,
        op: str | None = None,
    ) -> dict[str, Any]:
        """Read frames until we get the response matching our command id.

        Non-matching frames are stashed by sid during ``resubscribe_all``
        (``_stashing``) for replay, otherwise discarded.

        A matching frame whose ``type`` is ``error`` raises
        :class:`~kalshi.errors.KalshiSubscriptionError` here so *every* command
        (subscribe / unsubscribe / update / list) fails loudly on a server-side
        error instead of mutating local state as if it had succeeded.
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise KalshiSubscriptionError(
                    f"Timed out waiting for response to command {msg_id}",
                    channel=channel,
                    client_id=client_id,
                    op=op,  # type: ignore[arg-type]
                )
            try:
                raw = await asyncio.wait_for(
                    self._connection.recv(), timeout=remaining
                )
            except ConnectionClosed as e:
                raise KalshiConnectionError(
                    f"Connection closed while awaiting response to command {msg_id}"
                ) from e
            except TimeoutError:
                raise KalshiSubscriptionError(
                    f"Timed out waiting for response to command {msg_id}",
                    channel=channel,
                    client_id=client_id,
                    op=op,  # type: ignore[arg-type]
                ) from None
            data: dict[str, Any] = self._json_loads(raw)
            if data.get("id") == msg_id:
                if data.get("type") == "error":
                    raw_msg = data.get("msg", {})
                    detail = raw_msg.get("msg") if isinstance(raw_msg, dict) else None
                    code = raw_msg.get("code") if isinstance(raw_msg, dict) else None
                    raise KalshiSubscriptionError(
                        str(detail or f"{op or 'command'} failed"),
                        error_code=code,
                        channel=channel,
                        client_id=client_id,
                        op=op,  # type: ignore[arg-type]
                    )
                return data
            if self._stashing:
                self._maybe_stash(raw, data)
            else:
                # By design (#405): non-matching data frames are stashed only
                # during resubscribe_all (rebuilding a book from scratch, where a
                # lost frame would corrupt the fresh book with no baseline to
                # gap-detect against). During a normal command the book is
                # already established, so a dropped sequenced frame surfaces as a
                # sequence gap on the next frame and is recovered — not silently
                # lost. Discarding here avoids accumulating stale state.
                logger.debug(
                    "Discarding non-matching frame during command: type=%s",
                    data.get("type"),
                )

    def _maybe_stash(self, raw: str, data: dict[str, Any]) -> None:
        """Save a raw data frame to the per-sid stash, if it carries an int sid."""
        sid = data.get("sid")
        if not isinstance(sid, int):
            logger.debug(
                "Stash mode: dropping non-matching frame with non-int sid: "
                "type=%s sid=%r",
                data.get("type"), sid,
            )
            return
        bucket = self._stash.get(sid)
        if bucket is None:
            bucket = collections.deque(maxlen=self._stash_maxlen)
            self._stash[sid] = bucket
        elif len(bucket) == self._stash_maxlen and sid not in self._stash_warned:
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
    ) -> PerpsSubscription:
        """Subscribe to a channel. Returns a PerpsSubscription with a durable client_id."""
        client_id = self._next_client_id
        self._next_client_id += 1
        if queue is None:
            queue = MessageQueue(
                maxsize=maxsize,
                overflow=overflow,
                channel=channel,
                client_id=client_id,
            )

        sub_params = params or {}
        sub = PerpsSubscription(
            client_id=client_id, channel=channel, params=sub_params, queue=queue
        )

        msg_id = self._get_msg_id()
        cmd = SubscribeCommand(
            id=msg_id,
            params=SubscribeParams.model_validate(sub.to_subscribe_params()),
        )
        await self._connection.send(
            cmd.model_dump(exclude_none=True, by_alias=True, mode="json")
        )

        # An error ack is raised inside _wait_for_response (centralized), so a
        # returned frame here is always a success.
        data = await self._wait_for_response(
            msg_id, channel=channel, client_id=client_id, op="subscribe",
        )
        server_sid = data.get("msg", {}).get("sid")
        if server_sid is not None:
            sub.server_sid = server_sid
            self._sid_to_client[server_sid] = client_id

        self._subscriptions[client_id] = sub
        logger.debug(
            "Subscribed to %s: client_id=%d, server_sid=%s",
            channel, client_id, server_sid,
        )
        return sub

    async def unsubscribe(self, client_id: int) -> None:
        """Unsubscribe by durable client_id. Sends ``params.sids``."""
        sub = self._subscriptions.get(client_id)
        if not sub or sub.server_sid is None:
            return

        msg_id = self._get_msg_id()
        cmd = UnsubscribeCommand(
            id=msg_id, params=UnsubscribeParams(sids=[sub.server_sid])
        )
        await self._connection.send(
            cmd.model_dump(exclude_none=True, by_alias=True, mode="json")
        )

        await self._wait_for_response(
            msg_id, channel=sub.channel, client_id=client_id, op="unsubscribe",
        )
        await sub.queue.put_sentinel()
        self._sid_to_client.pop(sub.server_sid, None)
        del self._subscriptions[client_id]
        logger.debug(
            "Unsubscribed client_id=%d (server_sid=%d)", client_id, sub.server_sid
        )

    @staticmethod
    def _apply_market_delta(
        sub: PerpsSubscription,
        action: str,
        market_tickers: builtins.list[str] | None,
    ) -> None:
        """Persist an add/remove of markets onto ``sub.params``.

        Without this, a later :meth:`resubscribe_all` rebuilds the subscribe
        command from the *original* ``params`` and silently reverts the update
        after a reconnect (added markets vanish, removed markets return).
        """
        if not market_tickers:
            return
        current: builtins.list[str] = list(sub.params.get("market_tickers") or [])
        if action == UpdateSubscriptionAction.ADD_MARKETS:
            current.extend(t for t in market_tickers if t not in current)
            sub.params["market_tickers"] = current
        elif action == UpdateSubscriptionAction.DELETE_MARKETS:
            remove = set(market_tickers)
            sub.params["market_tickers"] = [t for t in current if t not in remove]

    async def update_subscription(
        self,
        client_id: int,
        action: str,
        market_tickers: builtins.list[str] | None = None,
        send_initial_snapshot: bool | None = None,
    ) -> None:
        """Add or remove markets from an existing subscription (array-``sids`` form).

        Builds ``updateSubscriptionCommandPayload`` with ``params.sids`` as a
        single-element array (spec ``maxItems: 1``).
        """
        sub = self._subscriptions.get(client_id)
        if not sub or sub.server_sid is None:
            raise KalshiSubscriptionError(
                "Subscription not found or not active",
                channel=sub.channel if sub else None,
                client_id=client_id,
                op="update_subscription",
            )

        msg_id = self._get_msg_id()
        cmd = UpdateSubscriptionCommand(
            id=msg_id,
            params=UpdateSubscriptionParams(
                action=UpdateSubscriptionAction(action),
                sids=[sub.server_sid],
                market_tickers=market_tickers,
                send_initial_snapshot=send_initial_snapshot,
            ),
        )
        await self._connection.send(
            cmd.model_dump(exclude_none=True, by_alias=True, mode="json")
        )
        await self._wait_for_response(
            msg_id, channel=sub.channel, client_id=client_id,
            op="update_subscription",
        )
        self._apply_market_delta(sub, action, market_tickers)
        logger.debug(
            "Updated subscription (sids) client_id=%d action=%s", client_id, action
        )

    async def update_subscription_single_sid(
        self,
        client_id: int,
        action: str,
        market_tickers: builtins.list[str] | None = None,
        send_initial_snapshot: bool | None = None,
    ) -> None:
        """Add or remove markets using the scalar-``sid`` form.

        Builds ``updateSubscriptionCommandPayload`` with ``params.sid`` (scalar)
        rather than the ``params.sids`` array — the
        ``updateSubscriptionSingleSidCommand`` spec variant.
        """
        sub = self._subscriptions.get(client_id)
        if not sub or sub.server_sid is None:
            raise KalshiSubscriptionError(
                "Subscription not found or not active",
                channel=sub.channel if sub else None,
                client_id=client_id,
                op="update_subscription",
            )

        msg_id = self._get_msg_id()
        cmd = UpdateSubscriptionCommand(
            id=msg_id,
            params=UpdateSubscriptionParams(
                action=UpdateSubscriptionAction(action),
                sid=sub.server_sid,
                market_tickers=market_tickers,
                send_initial_snapshot=send_initial_snapshot,
            ),
        )
        await self._connection.send(
            cmd.model_dump(exclude_none=True, by_alias=True, mode="json")
        )
        await self._wait_for_response(
            msg_id, channel=sub.channel, client_id=client_id,
            op="update_subscription",
        )
        self._apply_market_delta(sub, action, market_tickers)
        logger.debug(
            "Updated subscription (single sid) client_id=%d action=%s",
            client_id, action,
        )

    async def list_subscriptions(self) -> builtins.list[SubscriptionEntry]:
        """Send ``list_subscriptions`` and parse the array ``msg`` reply.

        The reply uses ``type: "ok"`` with ``msg`` as an array of
        ``{channel, sid}`` entries (disambiguated from the scalar update ack by
        ``msg`` being a list). Returns the parsed entries; an empty list when
        no subscriptions are active.
        """
        msg_id = self._get_msg_id()
        cmd = ListSubscriptionsCommand(id=msg_id)
        await self._connection.send(
            cmd.model_dump(exclude_none=True, by_alias=True, mode="json")
        )
        data = await self._wait_for_response(msg_id, op="list_subscriptions")
        raw_entries = data.get("msg")
        if not isinstance(raw_entries, list):
            return []
        return [SubscriptionEntry.model_validate(entry) for entry in raw_entries]

    async def resubscribe_all(self) -> None:
        """Re-subscribe all active subscriptions after reconnect.

        Gets new server sids and updates the mapping; iterators/callbacks keep
        working because they reference client_ids. Each resubscribe is
        independent — a failed one is removed (its iterator gets a sentinel) and
        the rest continue. ``_stashing`` is enabled so non-matching data frames
        are captured by sid for post-resubscribe replay by the client facade.
        """
        old_subs = dict(self._subscriptions)
        self._sid_to_client.clear()
        self._stash.clear()
        self._stash_warned.clear()

        self._stashing = True
        try:
            for client_id, sub in old_subs.items():
                sub.server_sid = None
                try:
                    msg_id = self._get_msg_id()
                    params = sub.to_subscribe_params()
                    if sub.channel == "orderbook_delta":
                        params["send_initial_snapshot"] = True
                    cmd = SubscribeCommand(
                        id=msg_id,
                        params=SubscribeParams.model_validate(params),
                    )
                    await self._connection.send(
                        cmd.model_dump(
                            exclude_none=True, by_alias=True, mode="json"
                        )
                    )

                    # An error ack raises inside _wait_for_response and is caught
                    # by the per-sub ``except`` below (sentinel + drop).
                    data = await self._wait_for_response(
                        msg_id, channel=sub.channel,
                        client_id=client_id, op="subscribe",
                    )
                    new_sid = data.get("msg", {}).get("sid")
                    if new_sid is not None:
                        sub.server_sid = new_sid
                        self._sid_to_client[new_sid] = client_id
                    logger.debug(
                        "Resubscribed %s: client_id=%d, new_sid=%s",
                        sub.channel, client_id, new_sid,
                    )
                except Exception:
                    logger.warning(
                        "Resubscribe failed for client_id=%d channel=%s",
                        client_id, sub.channel, exc_info=True,
                    )
                    await sub.queue.put_sentinel()
                    self._subscriptions.pop(client_id, None)
        finally:
            self._stashing = False

    def take_stash(self) -> dict[int, collections.deque[str]]:
        """Return and clear the resubscribe-window stash atomically."""
        stash, self._stash = self._stash, {}
        self._stash_warned.clear()
        return stash

    def get_subscription_by_sid(self, server_sid: int) -> PerpsSubscription | None:
        """Look up a subscription by current server sid."""
        client_id = self._sid_to_client.get(server_sid)
        if client_id is None:
            return None
        return self._subscriptions.get(client_id)

    def get_subscription(self, client_id: int) -> PerpsSubscription | None:
        """Look up a subscription by durable client id."""
        return self._subscriptions.get(client_id)

    @property
    def active_subscriptions(self) -> dict[int, PerpsSubscription]:
        """All active subscriptions keyed by client_id."""
        return dict(self._subscriptions)
