"""User-facing perps (margin) WebSocket client.

Mirrors :class:`kalshi.ws.client.KalshiWebSocket` for the perps margin host.
Same session lifecycle (``connect()`` async context manager, ``_start`` /
``_stop`` / recv loop, ``on_state_change`` / ``on_error`` hooks, cooperative-
pause recv loop, ``_PERMANENT_CLOSE_CODES`` fast-fail, reconnect + resubscribe
+ stash replay, seq-gap resync).

This foundation issue (#397) exposes only the **generic** command surface —
``subscribe(channel, params)``, ``unsubscribe``, ``update_subscription``,
``update_subscription_single_sid``, ``list_subscriptions``. Per-channel typed
``subscribe_*`` convenience helpers (and the orderbook iterator) are deferred to
the ``perps: WS channels`` issue (#398), which also populates the dispatcher's
``MESSAGE_MODELS`` and the orderbook-apply seam wired here.

Timestamp convention: the recv path never coerces timestamps; #398's channel
payloads carry epoch-ms ``int`` ``*_ms`` fields that flow through as-is.
"""

from __future__ import annotations

import asyncio
import builtins
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from types import TracebackType
from typing import Any

from pydantic import BaseModel, ValidationError
from websockets.exceptions import ConnectionClosed

from kalshi.auth import KalshiAuth
from kalshi.errors import (
    KalshiBackpressureError,
    KalshiConnectionError,
    KalshiSequenceGapError,
    KalshiSubscriptionError,
)
from kalshi.perps.config import PerpsConfig
from kalshi.perps.ws.backpressure import OverflowStrategy
from kalshi.perps.ws.channels import PerpsSubscriptionManager
from kalshi.perps.ws.connection import ConnectionState, PerpsConnectionManager
from kalshi.perps.ws.dispatch import PerpsMessageDispatcher
from kalshi.perps.ws.models.control import PerpsErrorResponse, SubscriptionEntry
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
from kalshi.perps.ws.sequence import PerpsSequenceTracker, SequenceGap

logger = logging.getLogger("kalshi.perps.ws")

_StateChangeCb = Callable[[ConnectionState, ConnectionState], Awaitable[None]]

# Close codes that signal a permanent server-side rejection — fast-fail instead
# of burning the reconnect budget. App-specific 4xxx codes (4001 = auth) plus
# the RFC 6455 protocol-violation range.
_PERMANENT_CLOSE_CODES: frozenset[int] = frozenset(
    {1002, 1003, 1007, 1008, 1009, 1010}
) | frozenset(range(4000, 5000))

# Cooperative-pause polling interval for the recv loop.
_RECV_POLL_S: float = 0.05

# Message types that ride the perps margin order book and carry ``seq``. #398's
# concrete payload models plug into the dispatcher; this set lets the recv loop
# gate orderbook-apply + stale-sid checks without importing those models yet.
_ORDERBOOK_TYPES = ("orderbook_snapshot", "orderbook_delta")


class PerpsWebSocket:
    """WebSocket client for real-time Kalshi perps (margin) data.

    Usage::

        ws = PerpsWebSocket(auth=auth, config=PerpsConfig.demo())
        async with ws.connect() as session:
            stream = await session.subscribe("ticker", params={"market_tickers": ["BTC-PERP"]})
            async for frame in stream:
                ...
    """

    def __init__(
        self,
        auth: KalshiAuth,
        config: PerpsConfig,
        heartbeat_timeout: float = 30.0,
        on_state_change: _StateChangeCb | None = None,
        on_error: Callable[[PerpsErrorResponse], Awaitable[None]] | None = None,
    ) -> None:
        self._auth = auth
        self._config = config
        self._heartbeat_timeout = heartbeat_timeout
        self._on_state_change = on_state_change
        self._on_error = on_error

        self._connection: PerpsConnectionManager | None = None
        self._sub_mgr: PerpsSubscriptionManager | None = None
        self._dispatcher: PerpsMessageDispatcher | None = None
        self._seq_tracker: PerpsSequenceTracker | None = None
        self._orderbook_mgr: PerpsOrderbookManager | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self._running = False
        self._subscribe_lock = asyncio.Lock()
        # Cooperative recv-loop pause handshake. ``_pause_pending`` is set by a
        # command path that needs exclusive ``recv()`` access; the recv loop
        # observes it at the top of its loop, parks, and sets ``_pause_granted``.
        # ``_resume_signal`` releases it; ``_resume_ack`` is set by the recv
        # loop once it has actually left the parked state, so a back-to-back
        # second command cannot slip a pause request through the resume window
        # and end up with two concurrent ``recv()`` calls (websockets raises
        # ConcurrencyError on overlapping recv). All command paths are
        # serialized by ``_subscribe_lock`` anyway; the ack closes the
        # intra-handshake gap.
        self._pause_pending = False
        self._pause_granted = asyncio.Event()
        self._resume_signal = asyncio.Event()
        self._resume_ack = asyncio.Event()
        self._json_loads: Callable[[bytes | str], Any] = (
            config.ws_json_loads if config.ws_json_loads is not None else json.loads
        )

    def connect(self) -> _PerpsWebSocketSession:
        """Return an async context manager for the WebSocket session."""
        return _PerpsWebSocketSession(self)

    async def _start(self) -> None:
        """Connect and initialize managers. Does NOT start recv_loop yet."""
        if self._connection is not None or self._running:
            raise RuntimeError(
                "PerpsWebSocket session is already started. Each instance "
                "supports one active session at a time — await the existing "
                "`async with ws.connect()` to exit, or create a fresh "
                "PerpsWebSocket() for a new session."
            )
        try:
            self._connection = PerpsConnectionManager(
                auth=self._auth,
                config=self._config,
                heartbeat_timeout=self._heartbeat_timeout,
                on_state_change=self._on_state_change,
            )
            await self._connection.connect()

            self._sub_mgr = PerpsSubscriptionManager(
                self._connection, json_loads=self._json_loads
            )
            self._seq_tracker = PerpsSequenceTracker(on_gap=self._handle_seq_gap)
            self._orderbook_mgr = PerpsOrderbookManager()
            self._dispatcher = PerpsMessageDispatcher(
                sub_mgr=self._sub_mgr,
                on_error=self._on_error,
                seq_tracker=self._seq_tracker,
                orderbook_mgr=self._orderbook_mgr,
            )
            self._running = True
        except BaseException:
            if self._connection is not None:
                with contextlib.suppress(Exception):
                    await self._connection.close()
            self._clear_session_state()
            self._running = False
            raise

    async def _stop(self) -> None:
        """Stop the receive loop and close the connection (close-then-drain)."""
        self._running = False
        # Wake anything parked on the pause/resume handshake so teardown can't
        # hang: a recv loop on ``_resume_signal.wait()`` exits via ``_running``,
        # and a command awaiting ``_resume_ack`` is released.
        self._resume_signal.set()
        self._resume_ack.set()
        self._pause_granted.set()

        try:
            if self._connection:
                await self._connection.close()
        except Exception:
            logger.warning("_connection.close() raised during _stop", exc_info=True)
        finally:
            if self._recv_task and not self._recv_task.done():
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.wait_for(self._recv_task, timeout=2.0)
                if not self._recv_task.done():
                    self._recv_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await self._recv_task
            await self._broadcast_sentinels()

        self._clear_session_state()
        self._pause_granted.clear()
        self._resume_signal.clear()
        self._resume_ack.clear()

    async def _broadcast_sentinels(self) -> None:
        """Put a shutdown sentinel on every active subscription queue."""
        if self._sub_mgr is not None:
            for sub in self._sub_mgr.active_subscriptions.values():
                await sub.queue.put_sentinel()

    def _clear_session_state(self) -> None:
        """Nil the per-session managers + recv task.

        Shared by ``_start`` (failure), ``_stop``, and the recv-loop fatal-error
        teardown so they cannot diverge — the fatal path previously left
        ``_recv_task`` dangling. Callers own ``_running`` and the pause/resume
        event set/clear (which differs by path: ``_stop`` clears them, the
        fatal path sets them to wake parked waiters).
        """
        self._connection = None
        self._sub_mgr = None
        self._seq_tracker = None
        self._orderbook_mgr = None
        self._dispatcher = None
        self._recv_task = None
        self._pause_pending = False

    async def _ensure_recv_loop(self) -> None:
        """Start the recv_loop background task or resume a parked one.

        On resume, awaits ``_resume_ack`` so the recv loop has actually left
        the parked checkpoint (and is reading again) before returning. Without
        the ack, a back-to-back second command could set ``_pause_pending``
        during the resume window and then call ``recv()`` while the recv loop
        is also about to call ``recv()`` — websockets raises ConcurrencyError on
        overlapping recv. The ack closes that gap.
        """
        if self._pause_pending:
            self._pause_pending = False
            self._pause_granted.clear()
            self._resume_ack.clear()
            self._resume_signal.set()
            # Wait for the recv loop to confirm it resumed (or that the session
            # tore down, in which case the loop is gone and won't ack).
            if self._recv_task is not None and not self._recv_task.done():
                await self._resume_ack.wait()
            return
        if self._recv_task is None or self._recv_task.done():
            self._recv_task = asyncio.create_task(self._recv_loop())

    async def _pause_recv_loop(self) -> None:
        """Cooperatively park the recv_loop so a command can call recv."""
        if self._recv_task is None or self._recv_task.done():
            return
        self._pause_granted.clear()
        self._resume_signal.clear()
        self._pause_pending = True
        await self._pause_granted.wait()

    async def _recv_loop(self) -> None:
        """Background task: read frames, dispatch, handle reconnect."""
        assert self._connection is not None
        assert self._dispatcher is not None

        while self._running:
            if self._pause_pending:
                self._pause_granted.set()
                await self._resume_signal.wait()
                self._resume_signal.clear()
                # Acknowledge resume so a waiting ``_ensure_recv_loop`` knows the
                # checkpoint is cleared before it returns to the command path.
                self._resume_ack.set()
                if not self._running:
                    break
                continue

            try:
                async with asyncio.timeout(_RECV_POLL_S):
                    raw = await self._connection.recv()
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except ConnectionClosed as e:
                code = None
                rcvd = getattr(e, "rcvd", None)
                sent = getattr(e, "sent", None)
                if rcvd is not None:
                    code = rcvd.code
                if code is None and sent is not None:
                    code = sent.code
                if code in _PERMANENT_CLOSE_CODES:
                    reason = (rcvd.reason if rcvd is not None else "") or ""
                    logger.error(
                        "Perps WS closed with permanent code %d (%s); not reconnecting",
                        code, reason or "<no reason>",
                    )
                    await self._broadcast_sentinels()
                    raise KalshiConnectionError(
                        f"WebSocket closed with permanent code {code}: {reason}"
                    ) from e
                if not self._running:
                    break
                await self._handle_reconnect()
                if not self._running:
                    break
                continue

            try:
                await self._process_frame(raw)
            except asyncio.CancelledError:
                break
            except (KalshiBackpressureError, KalshiSubscriptionError):
                logger.error(
                    "Fatal perps WS error in recv loop; tearing down session",
                    exc_info=True,
                )
                await self._broadcast_sentinels()
                self._running = False
                if self._connection is not None:
                    with contextlib.suppress(Exception):
                        await self._connection.close()
                self._clear_session_state()
                self._pause_granted.set()
                self._resume_signal.set()
                self._resume_ack.set()
                break
            except (json.JSONDecodeError, ValidationError, KeyError):
                logger.warning("Skipping malformed perps WS frame", exc_info=True)
                continue
            except Exception:
                logger.error(
                    "Unexpected error in perps recv loop; broadcasting sentinels",
                    exc_info=True,
                )
                await self._broadcast_sentinels()
                raise

    async def _process_frame(self, raw: str) -> None:
        """Parse, track seq, (apply orderbook — #398), and dispatch a single frame.

        Seq tracking is provisional w.r.t. downstream dispatch: on a
        ``KalshiBackpressureError`` the watermark is rolled back so the dropped
        seq surfaces as a future gap rather than being treated as already-seen.

        The orderbook-apply seam (validate + ``_apply_*_inplace``) is wired for
        #398's concrete snapshot/delta payload models. Until those land,
        ``MESSAGE_MODELS`` is empty and there is no typed pre-validation to do;
        the stale-sid gate and seq tracking below still run for orderbook frames.
        """
        assert self._dispatcher is not None
        data = self._json_loads(raw)
        sid = data.get("sid")
        seq = data.get("seq")
        msg_type = data.get("type", "")

        # Stale orderbook frames arriving after teardown must not be processed.
        if (
            msg_type in _ORDERBOOK_TYPES
            and isinstance(sid, int)
            and self._sub_mgr is not None
            and self._sub_mgr.get_subscription_by_sid(sid) is None
        ):
            logger.debug(
                "Dropping stale %s for unmapped sid=%d (post-teardown race)",
                msg_type, sid,
            )
            return

        prev_seq: int | None = None
        tracked = False
        if sid is not None and seq is not None and self._seq_tracker:
            channel = ""
            sub = (
                self._sub_mgr.get_subscription_by_sid(sid)
                if self._sub_mgr
                else None
            )
            if sub:
                channel = sub.channel
            prev_seq = self._seq_tracker.peek(sid)
            ok, gap = self._seq_tracker.track_sync(
                sid, seq, msg_type if msg_type else channel
            )
            if gap is not None:
                await self._seq_tracker.fire_gap(gap)
            if not ok:
                return
            tracked = True

        # Pre-validate orderbook frames so the manager applies typed data, then
        # hand the same instance to the dispatcher (no double Pydantic). Both
        # apply + dispatch roll the seq watermark back on failure so a malformed
        # frame on a sequenced channel doesn't silently advance the watermark
        # and mask the next legitimate gap (mirrors the equities path, #241).
        pre_validated: BaseModel | None = None
        try:
            if msg_type == "orderbook_snapshot" and self._orderbook_mgr:
                snapshot = MarginOrderbookSnapshotMessage.model_validate(data)
                self._orderbook_mgr._apply_snapshot_inplace(
                    snapshot, sid=snapshot.sid
                )
                pre_validated = snapshot
            elif msg_type == "orderbook_delta" and self._orderbook_mgr:
                delta = MarginOrderbookDeltaMessage.model_validate(data)
                self._orderbook_mgr._apply_delta_inplace(delta)
                pre_validated = delta

            await self._dispatcher.dispatch(data, pre_validated=pre_validated)
        except KalshiBackpressureError as exc:
            if tracked and sid is not None and self._seq_tracker:
                self._seq_tracker.rollback(sid, prev_seq)
            if sid is not None and self._sub_mgr is not None:
                affected = self._sub_mgr.get_subscription_by_sid(sid)
                if affected is not None:
                    await self._broadcast_error(affected.client_id, exc)
            raise
        except Exception:
            if tracked and sid is not None and self._seq_tracker:
                self._seq_tracker.rollback(sid, prev_seq)
            raise

    async def _broadcast_error(self, client_id: int, exc: BaseException) -> None:
        """Surface ``exc`` to a subscription's iterator via an error sentinel."""
        if self._sub_mgr is None:
            return
        sub = self._sub_mgr.get_subscription(client_id)
        if sub is None:
            return
        if (
            isinstance(exc, KalshiBackpressureError)
            and exc.sid is None
            and sub.server_sid is not None
        ):
            exc.sid = sub.server_sid
        await sub.queue.put_error(exc)

    async def _handle_reconnect(self) -> None:
        """Reconnect after ConnectionClosed and re-establish subscriptions."""
        assert self._connection is not None
        logger.warning("Perps connection lost, attempting reconnect...")
        async with self._subscribe_lock:
            try:
                await self._connection.reconnect()
                if self._sub_mgr:
                    if self._seq_tracker:
                        self._seq_tracker.reset_all()
                    if self._orderbook_mgr:
                        self._orderbook_mgr.clear()
                    await self._sub_mgr.resubscribe_all()
                    await self._drain_resubscribe_stash()
                    await self._connection.mark_streaming()
            except Exception as reconnect_err:
                logger.error(
                    "Perps reconnect failed: %s", reconnect_err, exc_info=True
                )
                await self._broadcast_sentinels()
                self._running = False

    async def _drain_resubscribe_stash(self) -> None:
        """Replay frames captured during a resubscribe through dispatch."""
        if self._sub_mgr is None:
            return
        stash = self._sub_mgr.take_stash()
        for sid, raw_frames in stash.items():
            if self._sub_mgr.get_subscription_by_sid(sid) is None:
                logger.debug(
                    "Dropping %d stashed frames for unmapped sid %d after resubscribe",
                    len(raw_frames), sid,
                )
                continue
            for raw in raw_frames:
                try:
                    await self._process_frame(raw)
                except Exception:
                    logger.warning(
                        "Failed to replay stashed perps frame for sid %d",
                        sid, exc_info=True,
                    )

    async def _handle_seq_gap(self, gap: SequenceGap) -> None:
        """Handle a sequence gap/reset by tearing down per-sid state.

        Clears the per-sid orderbook books and seq watermark and surfaces a
        :class:`~kalshi.errors.KalshiSequenceGapError` to the affected
        consumer. (The single-sub gap-recovery resubscribe lands with #398's
        ``resubscribe_one`` once channel payloads exist; the foundation issue
        guarantees the consumer is signalled rather than silently desynced.)
        """
        logger.warning(
            "Perps sequence %s on sid %d: expected %d, got %d. Triggering resync.",
            gap.kind, gap.sid, gap.expected, gap.received,
        )
        if self._sub_mgr is None:
            return
        sub = self._sub_mgr.get_subscription_by_sid(gap.sid)
        if sub is None:
            return

        if self._orderbook_mgr is not None:
            cleared = self._orderbook_mgr.remove_by_sid(gap.sid)
            if cleared:
                logger.warning(
                    "Cleared %d margin orderbook entries for sid %d on %s",
                    len(cleared), gap.sid, gap.kind,
                )
        if self._seq_tracker is not None:
            self._seq_tracker.reset(gap.sid)

        await self._broadcast_error(
            sub.client_id,
            KalshiSequenceGapError(
                f"Sequence {gap.kind} on {sub.channel}; local state cleared. "
                "Resubscribe to resume.",
                channel=sub.channel,
                sid=gap.sid,
                client_id=sub.client_id,
                last_seq=gap.expected - 1,
                next_seq=gap.received,
            ),
        )

    # ------------------------------------------------------------------
    # Generic command surface (per-channel typed helpers deferred to #398)
    # ------------------------------------------------------------------

    async def _do_subscribe(
        self,
        channel: str,
        params: dict[str, Any] | None = None,
        overflow: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        maxsize: int = 1000,
    ) -> AsyncIterator[Any]:
        """Pause recv_loop, subscribe, resume recv_loop, return the queue."""
        if not self._running or self._sub_mgr is None or self._connection is None:
            raise RuntimeError(
                "PerpsWebSocket session is not active. The recv loop tore down "
                "after a fatal error (e.g. KalshiBackpressureError); exit the "
                "current `async with ws.connect()` block and start a fresh "
                "session before subscribing again."
            )
        async with self._subscribe_lock:
            await self._pause_recv_loop()
            # Precondition check lives INSIDE the try so the finally always
            # resumes the recv loop — an early raise here while the loop is
            # parked would otherwise abandon it (permanent inbound deadlock).
            try:
                if (
                    not self._running
                    or self._sub_mgr is None
                    or self._connection is None
                ):
                    raise RuntimeError(
                        "PerpsWebSocket session is not active. The recv loop tore "
                        "down after a fatal error (e.g. KalshiBackpressureError); "
                        "exit the current `async with ws.connect()` block and start "
                        "a fresh session before subscribing again."
                    )
                sub = await self._sub_mgr.subscribe(
                    channel, params=params, overflow=overflow, maxsize=maxsize,
                )
            finally:
                await self._ensure_recv_loop()
        return sub.queue

    async def subscribe(
        self,
        channel: str,
        *,
        params: dict[str, Any] | None = None,
        overflow: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        maxsize: int = 1000,
    ) -> AsyncIterator[BaseModel]:
        """Subscribe to a perps channel. Returns an async iterator of frames.

        Per-channel typed ``subscribe_*`` helpers are deferred to #398; use this
        generic entry point with ``channel`` (one of :class:`PerpsChannel`) and
        an optional ``params`` dict (``market_ticker`` / ``market_tickers`` /
        ``send_initial_snapshot`` / ``skip_ticker_ack``).
        """
        return await self._do_subscribe(
            channel, params=params, overflow=overflow, maxsize=maxsize,
        )

    # ------------------------------------------------------------------
    # Per-channel typed subscribe helpers (#398)
    #
    # The perps AsyncAPI defines exactly six data channels — all wired below.
    # The prediction-API channels ``market_positions``,
    # ``market_lifecycle_v2`` / ``event_fee_update``, ``multivariate``,
    # ``multivariate_market_lifecycle``, and ``communications`` have NO perps
    # counterpart and intentionally get NO ``subscribe_*`` helper here.
    #
    # ``builtins.list[str]`` is used for ``tickers`` params: the surrounding
    # API has a ``list_subscriptions`` method, so the ``list`` builtin is
    # shadowed by the CLAUDE.md convention applied across the perps WS layer.
    # ------------------------------------------------------------------

    async def subscribe_orderbook_delta(
        self,
        *,
        tickers: builtins.list[str] | None = None,
        maxsize: int = 1000,
    ) -> AsyncIterator[
        MarginOrderbookSnapshotMessage | MarginOrderbookDeltaMessage
    ]:
        """Subscribe to ``orderbook_delta`` (snapshot first, then deltas).

        Forces ``send_initial_snapshot`` so the server emits an
        ``orderbook_snapshot`` before incremental ``orderbook_delta`` frames.
        Sequenced + gap-sensitive: overflow is ``ERROR`` (a drop here would
        desync the local book rather than just lose a coalesced sample).

        Note: ``MarginOrderbookSnapshotMessage.msg.bid`` / ``.ask`` become live
        dicts owned by the :class:`PerpsOrderbookManager` after dispatch — they
        mutate on every subsequent delta.
        """
        params: dict[str, Any] = {"send_initial_snapshot": True}
        if tickers:
            params["market_tickers"] = tickers
        return await self._do_subscribe(
            "orderbook_delta", params=params,
            overflow=OverflowStrategy.ERROR, maxsize=maxsize,
        )

    async def subscribe_ticker(
        self,
        *,
        tickers: builtins.list[str] | None = None,
        send_initial_snapshot: bool = False,
        maxsize: int = 1000,
    ) -> AsyncIterator[MarginTickerMessage]:
        """Subscribe to ``ticker`` (coalesced ≤1/market/sec).

        Carries the perps-unique ``funding_rate`` and the
        reference/settlement/liquidation mark prices. Not sequence-gap
        sensitive (coalesced sampling), so overflow is ``DROP_OLDEST``.
        """
        params: dict[str, Any] = {}
        if tickers:
            params["market_tickers"] = tickers
        if send_initial_snapshot:
            params["send_initial_snapshot"] = True
        return await self._do_subscribe(
            "ticker", params=params,
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_trade(
        self,
        *,
        tickers: builtins.list[str] | None = None,
        maxsize: int = 1000,
    ) -> AsyncIterator[MarginTradeMessage]:
        """Subscribe to ``trade`` (public executed margin trades)."""
        params: dict[str, Any] = {}
        if tickers:
            params["market_tickers"] = tickers
        return await self._do_subscribe(
            "trade", params=params,
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_fill(
        self,
        *,
        tickers: builtins.list[str] | None = None,
        maxsize: int = 1000,
    ) -> AsyncIterator[MarginFillMessage]:
        """Subscribe to ``fill`` (private authenticated-user fills)."""
        params: dict[str, Any] = {}
        if tickers:
            params["market_tickers"] = tickers
        return await self._do_subscribe(
            "fill", params=params,
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_user_orders(
        self,
        *,
        tickers: builtins.list[str] | None = None,
        maxsize: int = 1000,
    ) -> AsyncIterator[MarginUserOrderMessage]:
        """Subscribe to ``user_orders`` (private order create/update).

        The subscribe channel is ``user_orders`` but the message envelope
        ``type`` is ``user_order`` (singular) — yields
        :class:`MarginUserOrderMessage`.
        """
        params: dict[str, Any] = {}
        if tickers:
            params["market_tickers"] = tickers
        return await self._do_subscribe(
            "user_orders", params=params,
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_order_group(
        self,
        *,
        maxsize: int = 1000,
    ) -> AsyncIterator[OrderGroupUpdatesMessage]:
        """Subscribe to ``order_group_updates`` (private group lifecycle/limits).

        Market spec is ignored for this channel. Sequenced + gap-sensitive, so
        overflow is ``ERROR``.
        """
        return await self._do_subscribe(
            "order_group_updates",
            overflow=OverflowStrategy.ERROR, maxsize=maxsize,
        )

    async def unsubscribe(self, client_id: int) -> None:
        """Tear down a subscription and its associated local state.

        Pauses the recv loop for the duration so the ``unsubscribed`` ack is
        read by the subscription manager rather than racing the recv loop's own
        ``recv()`` (websockets forbids concurrent recv).
        """
        if self._sub_mgr is None:
            return
        async with self._subscribe_lock:
            await self._pause_recv_loop()
            try:
                if self._sub_mgr is None:
                    return
                sub = self._sub_mgr.get_subscription(client_id)
                if sub is None:
                    return
                old_sid = sub.server_sid
                if old_sid is not None:
                    if self._orderbook_mgr is not None:
                        cleared = self._orderbook_mgr.remove_by_sid(old_sid)
                        if cleared:
                            logger.debug(
                                "Cleared %d margin orderbook entries for sid %d "
                                "on unsubscribe",
                                len(cleared), old_sid,
                            )
                    if self._seq_tracker is not None:
                        self._seq_tracker.reset(old_sid)
                await self._sub_mgr.unsubscribe(client_id)
            finally:
                await self._ensure_recv_loop()

    async def update_subscription(
        self,
        client_id: int,
        action: str,
        *,
        market_tickers: list[str] | None = None,
        send_initial_snapshot: bool | None = None,
    ) -> None:
        """Add/remove markets on an existing subscription (array-``sids`` form).

        Pauses the recv loop so the ``ok`` ack is read by the subscription
        manager rather than swallowed by the dispatcher.
        """
        if not self._running or self._sub_mgr is None:
            raise RuntimeError("PerpsWebSocket session is not active.")
        async with self._subscribe_lock:
            await self._pause_recv_loop()
            try:
                if not self._running or self._sub_mgr is None:
                    raise RuntimeError("PerpsWebSocket session is not active.")
                await self._sub_mgr.update_subscription(
                    client_id,
                    action,
                    market_tickers=market_tickers,
                    send_initial_snapshot=send_initial_snapshot,
                )
            finally:
                await self._ensure_recv_loop()

    async def update_subscription_single_sid(
        self,
        client_id: int,
        action: str,
        *,
        market_tickers: list[str] | None = None,
        send_initial_snapshot: bool | None = None,
    ) -> None:
        """Add/remove markets using the scalar-``sid`` form."""
        if not self._running or self._sub_mgr is None:
            raise RuntimeError("PerpsWebSocket session is not active.")
        async with self._subscribe_lock:
            await self._pause_recv_loop()
            try:
                if not self._running or self._sub_mgr is None:
                    raise RuntimeError("PerpsWebSocket session is not active.")
                await self._sub_mgr.update_subscription_single_sid(
                    client_id,
                    action,
                    market_tickers=market_tickers,
                    send_initial_snapshot=send_initial_snapshot,
                )
            finally:
                await self._ensure_recv_loop()

    async def list_subscriptions(self) -> list[SubscriptionEntry]:
        """List all active server-side subscriptions (parses the array ``msg``)."""
        if not self._running or self._sub_mgr is None:
            raise RuntimeError("PerpsWebSocket session is not active.")
        async with self._subscribe_lock:
            await self._pause_recv_loop()
            try:
                if not self._running or self._sub_mgr is None:
                    raise RuntimeError("PerpsWebSocket session is not active.")
                return await self._sub_mgr.list_subscriptions()
            finally:
                await self._ensure_recv_loop()


class _PerpsWebSocketSession:
    """Async context manager for a perps WebSocket session."""

    def __init__(self, ws: PerpsWebSocket) -> None:
        self._ws = ws

    async def __aenter__(self) -> PerpsWebSocket:
        await self._ws._start()
        return self._ws

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._ws._stop()
