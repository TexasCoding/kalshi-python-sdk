"""User-facing WebSocket client."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from types import TracebackType
from typing import Any

from pydantic import BaseModel, ValidationError
from websockets.exceptions import ConnectionClosed

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import (
    KalshiBackpressureError,
    KalshiConnectionError,
    KalshiOrderbookUnavailableError,
    KalshiSequenceGapError,
    KalshiSubscriptionError,
)
from kalshi.models.markets import Orderbook
from kalshi.ws.backpressure import OverflowStrategy
from kalshi.ws.channels import SubscriptionManager
from kalshi.ws.connection import ConnectionManager, ConnectionState
from kalshi.ws.dispatch import MessageDispatcher
from kalshi.ws.models.base import ErrorMessage
from kalshi.ws.models.cfbenchmarks import (
    CFBenchmarksIndexListMessage,
    CFBenchmarksValueMessage,
)
from kalshi.ws.models.communications import CommunicationsMessage
from kalshi.ws.models.event_fee import EventFeeUpdateMessage
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
from kalshi.ws.sequence import SequenceGap, SequenceTracker

logger = logging.getLogger("kalshi.ws")

# Type alias for state-change callback (too long to inline)
_StateChangeCb = Callable[[ConnectionState, ConnectionState], Awaitable[None]]
_CallbackDecorator = Callable[
    [Callable[..., Awaitable[None]]], Callable[..., Awaitable[None]]
]

# #197: close codes that signal a permanent server-side rejection. Reconnect
# will fail every attempt for these (auth/protocol/policy/payload violations),
# so fast-fail instead of burning the 10-retry budget. App-specific 4xxx
# codes (notably 4001 = auth) are included wholesale per the Kalshi docs.
_PERMANENT_CLOSE_CODES: frozenset[int] = frozenset(
    {1002, 1003, 1007, 1008, 1009, 1010}
) | frozenset(range(4000, 5000))

# #245: cooperative-pause polling interval. Bounds the latency between a
# subscribe-driven pause request and the recv loop parking itself on a
# quiet channel. On a busy channel pause is granted between frames at
# zero added latency. 50ms is well under any subscribe ack timeout
# (5s default) and ~5x the typical Kalshi market-burst inter-frame
# spacing, so polling adds negligible CPU on idle.
_RECV_POLL_S: float = 0.05


class KalshiWebSocket:
    """WebSocket client for real-time Kalshi market data.

    Usage::

        ws = KalshiWebSocket(auth=auth, config=config)
        async with ws.connect() as session:
            async for msg in session.subscribe_ticker(tickers=["ECON-GDP-25Q1"]):
                print(msg.msg.yes_bid)
    """

    def __init__(
        self,
        auth: KalshiAuth,
        config: KalshiConfig,
        heartbeat_timeout: float = 30.0,
        on_state_change: _StateChangeCb | None = None,
        on_error: Callable[[ErrorMessage], Awaitable[None]] | None = None,
    ) -> None:
        self._auth = auth
        self._config = config
        self._heartbeat_timeout = heartbeat_timeout
        self._on_state_change = on_state_change
        self._on_error = on_error

        self._connection: ConnectionManager | None = None
        self._sub_mgr: SubscriptionManager | None = None
        self._dispatcher: MessageDispatcher | None = None
        self._seq_tracker: SequenceTracker | None = None
        self._orderbook_mgr: OrderbookManager | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self._running = False
        self._subscribe_lock = asyncio.Lock()
        self._pending_callbacks: list[tuple[str, Callable[..., Awaitable[None]]]] = []
        # #245: cooperative pause replaces the per-frame
        # ``asyncio.create_task + asyncio.shield`` that previously made
        # ``_process_frame`` uninterruptible. The recv loop now polls
        # ``connection.recv()`` with a short timeout so it can observe
        # ``_pause_pending`` between frames without an external cancel.
        # On a busy channel pause is granted in microseconds (between
        # frames); on a quiet channel it costs at most ``_RECV_POLL_S``
        # of latency. No Task / no shield Future / no contextvars copy
        # per frame.
        self._pause_pending = False
        self._pause_granted = asyncio.Event()
        self._resume_signal = asyncio.Event()
        # #209: pluggable JSON loader (None -> stdlib json.loads). Resolved
        # once here so the recv hot path doesn't keep dereferencing config.
        self._json_loads: Callable[[bytes | str], Any] = (
            config.ws_json_loads if config.ws_json_loads is not None else json.loads
        )

    def connect(self) -> _WebSocketSession:
        """Return an async context manager for the WebSocket session."""
        return _WebSocketSession(self)

    async def _start(self) -> None:
        """Connect and initialize managers. Does NOT start recv_loop yet."""
        if self._connection is not None or self._running:
            raise RuntimeError(
                "KalshiWebSocket session is already started. Each instance "
                "supports one active session at a time — await the existing "
                "`async with ws.connect()` to exit, or create a fresh "
                "KalshiWebSocket() for a new session."
            )
        try:
            self._connection = ConnectionManager(
                auth=self._auth,
                config=self._config,
                heartbeat_timeout=self._heartbeat_timeout,
                on_state_change=self._on_state_change,
            )
            await self._connection.connect()

            self._sub_mgr = SubscriptionManager(self._connection, json_loads=self._json_loads)
            self._seq_tracker = SequenceTracker(on_gap=self._handle_seq_gap)
            self._orderbook_mgr = OrderbookManager()
            self._dispatcher = MessageDispatcher(
                sub_mgr=self._sub_mgr,
                on_error=self._on_error,
                seq_tracker=self._seq_tracker,
                orderbook_mgr=self._orderbook_mgr,
            )
            self._running = True

            # Register any callbacks that were buffered before connect()
            # On failure mid-loop, _pending_callbacks is intentionally NOT cleared:
            # any unregistered tail replays on the next _start (already-registered
            # entries are discarded with the failed dispatcher).
            for channel, func in self._pending_callbacks:
                self._dispatcher.register_callback(channel, func)
            self._pending_callbacks.clear()
        except BaseException:
            # #297: partial-failure cleanup. __aexit__ won't run if __aenter__
            # raises, so reset state here to keep the instance reusable.
            # Belt-and-suspenders close: if connect() succeeded but a subsequent
            # step raised, drop the underlying socket explicitly rather than
            # relying on GC of the orphaned ConnectionManager.
            if self._connection is not None:
                with contextlib.suppress(Exception):
                    await self._connection.close()
            self._connection = None
            self._sub_mgr = None
            self._seq_tracker = None
            self._orderbook_mgr = None
            self._dispatcher = None
            self._running = False
            raise

    async def _stop(self) -> None:
        """Stop the receive loop and close the connection.

        #357: close-then-drain ordering. Closing the connection first
        unblocks any in-flight ``recv()`` via ``ConnectionClosed`` and
        lets the recv loop drain whatever frames the ``websockets``
        library has buffered before the close-ack arrives. Sentinels are
        broadcast LAST so iterator consumers see those final drained
        frames before the close sentinel, instead of having the recv
        task cancelled and the queues closed out from under them.
        """
        self._running = False
        # #245: wake the recv loop if it's parked on `_resume_signal`
        # (a pause request that never reached resume). Setting the
        # signal lets it observe ``_running=False`` and exit cleanly.
        self._resume_signal.set()

        # #357: close the connection FIRST. The in-flight ``recv()``
        # raises ``ConnectionClosed``; the loop drains any buffered
        # frames, sees ``_running=False``, and exits at the top of its
        # while. Guard the close in try/finally so a misbehaving
        # transport (e.g. ``close()`` raising) cannot strand iterator
        # consumers waiting on queues that never receive a sentinel.
        try:
            if self._connection:
                await self._connection.close()
        except Exception:
            logger.warning(
                "_connection.close() raised during _stop", exc_info=True
            )
        finally:
            if self._recv_task and not self._recv_task.done():
                # The poll-interval bounds the latency at ``_RECV_POLL_S``
                # even if close races the wait.
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.wait_for(self._recv_task, timeout=2.0)
                if not self._recv_task.done():
                    self._recv_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await self._recv_task
            elif self._recv_task is not None:
                # #413: task already finished (e.g. the recv loop raised on a
                # permanent close code). Retrieve the stored exception so asyncio
                # doesn't log "Task exception was never retrieved" when it is GC'd.
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    self._recv_task.exception()

            # Sentinels last (#357): iterator consumers have already seen
            # the post-close drained frames; the sentinel now terminates
            # their ``async for`` cleanly. Inside ``finally`` so a raising
            # close() still wakes consumers instead of hanging them.
            await self._broadcast_sentinels()

        # Reset state AFTER awaiting close so teardown still has manager refs (#297).
        self._connection = None
        self._sub_mgr = None
        self._seq_tracker = None
        self._orderbook_mgr = None
        self._dispatcher = None
        self._recv_task = None
        self._pause_pending = False
        self._pause_granted.clear()
        self._resume_signal.clear()

    async def _broadcast_sentinels(self) -> None:
        """Put a shutdown sentinel on every active subscription queue.

        Iterator consumers see the sentinel and exit their ``async for``
        loops. ``MessageQueue.put_sentinel`` is idempotent — once the
        queue is closed, subsequent calls are no-ops (no extra sentinel
        appended, no eviction of an in-flight item).

        Used by ``_stop()`` (post-cancel cleanup), the cooperative
        shutdown branch of ``run_forever(stop_event=...)`` (#177), and
        ``_recv_loop``'s fatal-error broadcast paths.
        """
        if self._sub_mgr is not None:
            for sub in self._sub_mgr.active_subscriptions.values():
                await sub.queue.put_sentinel()

    def _ensure_recv_loop(self) -> None:
        """Start the recv_loop background task or resume a parked one.

        #245: ``_pause_recv_loop`` cooperatively parks the loop on
        ``_resume_signal``; this method resumes it by setting the signal.
        Falls back to creating a fresh task when no loop is running
        (initial subscribe, or post-stop restart).
        """
        if self._pause_pending:
            self._pause_pending = False
            self._pause_granted.clear()
            self._resume_signal.set()
            return
        if self._recv_task is None or self._recv_task.done():
            self._recv_task = asyncio.create_task(self._recv_loop())

    async def _pause_recv_loop(self) -> None:
        """Cooperatively park the recv_loop so subscribe can call recv.

        #245: replaces the previous cancel-based pause (which required
        a per-frame ``asyncio.shield`` to keep the in-flight frame from
        being dropped). The recv loop polls ``connection.recv()`` with
        a ``_RECV_POLL_S`` timeout and checks ``_pause_pending`` between
        polls. On a busy channel pause is granted in microseconds; on a
        quiet channel the latency is bounded by ``_RECV_POLL_S``.

        F-P-04 invariant preserved: a frame in flight when pause is
        requested finishes dispatching before pause is granted, because
        the recv loop only sets ``_pause_granted`` at a safe point
        between frames (no shield required).
        """
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
            # #245: cooperative pause checkpoint. Set at a safe point
            # between frames so the F-P-04 invariant (no in-flight frame
            # dropped) holds without any shielding.
            if self._pause_pending:
                self._pause_granted.set()
                await self._resume_signal.wait()
                self._resume_signal.clear()
                if not self._running:
                    break
                continue

            try:
                # #356: ``asyncio.timeout`` (3.11+) reuses the loop's
                # underlying TimerHandle plumbing with a single context-
                # manager allocation, avoiding the per-frame Task wrap
                # that ``asyncio.wait_for`` performs on every iteration.
                # Poll with a short timeout so ``_pause_pending`` and
                # ``_running`` get re-checked on quiet channels. On a
                # busy channel the timeout is cancelled before firing,
                # so polling adds minimal overhead in the hot path.
                async with asyncio.timeout(_RECV_POLL_S):
                    raw = await self._connection.recv()
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                # External cancel (``_stop`` fallback). Exit cleanly.
                break
            except ConnectionClosed as e:
                # #197: classify the close code. The server returns codes
                # in the 4xxx range for app-specific failures (4001 auth,
                # ...) and RFC 6455 reserves 1002/3/7-10 for protocol
                # violations. None of these will recover on retry — fail
                # fast instead of burning the 10-retry budget under load.
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
                        "WS closed with permanent code %d (%s); not reconnecting",
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

            # #245: inline dispatch. No Task / no shield / no contextvars
            # copy per frame. F-P-04 protection comes from the cooperative
            # pause: ``_pause_recv_loop`` blocks until the recv loop
            # reaches the safe checkpoint above, so a pause request can
            # never cancel us in the middle of ``_process_frame``.
            try:
                await self._process_frame(raw)
            except asyncio.CancelledError:
                # Only ``_stop``'s fallback cancel can reach here. Exit
                # cleanly; sentinels are broadcast by the caller.
                break
            except (KalshiBackpressureError, KalshiSubscriptionError):
                # #83: consumer-visible problem. Broadcast sentinels so
                # iterators see the failure rather than spinning on the
                # same error. #332: also tear the session down — close the
                # WS connection and clear ``_running`` + manager refs so a
                # subsequent ``subscribe_*`` on this instance does not
                # resurrect a recv loop on top of orphaned server-side
                # subscriptions (the queues here are now closed; new
                # frames would silently drop or mis-route). Mirrors the
                # #297 reset done by ``_stop()``; we skip the recv-task
                # await because we ARE the recv task.
                logger.error(
                    "Fatal WS error in recv loop; tearing down session",
                    exc_info=True,
                )
                await self._broadcast_sentinels()
                self._running = False
                if self._connection is not None:
                    with contextlib.suppress(Exception):
                        await self._connection.close()
                self._connection = None
                self._sub_mgr = None
                self._seq_tracker = None
                self._orderbook_mgr = None
                self._dispatcher = None
                self._pause_pending = False
                # #332: wake any subscriber blocked on ``_pause_granted.wait()``;
                # ``Event.clear()`` does NOT unblock existing waiters, so a
                # pending ``_pause_recv_loop`` would deadlock here. ``set()``
                # releases the waiter; the post-pause guard in
                # ``_do_subscribe`` re-checks ``_running`` so the woken
                # subscriber sees the torn-down session and raises.
                self._pause_granted.set()
                self._resume_signal.set()
                break
            except (json.JSONDecodeError, ValidationError, KeyError):
                # #83: genuinely-non-fatal per-message errors. #241: when
                # the failing frame was on a sequenced channel, the seq
                # watermark was already rolled back inside
                # ``_process_frame``'s own except, so a next-seq gap will
                # still trigger a real resync.
                logger.warning("Skipping malformed WS frame", exc_info=True)
                continue
            except Exception:
                # #83 escape hatch: anything else (AttributeError from a
                # user-supplied callback, TypeError, programming bug, ...)
                # MUST broadcast sentinels before propagating — otherwise
                # consumers hang on their queues with no signal.
                logger.error(
                    "Unexpected error in recv loop; broadcasting sentinels",
                    exc_info=True,
                )
                await self._broadcast_sentinels()
                raise

    async def _process_frame(self, raw: str) -> None:
        """Parse, track seq, update orderbook, and dispatch a single frame.

        Seq tracking + orderbook-apply are provisional with respect to the
        downstream dispatch. If dispatch raises ``KalshiBackpressureError``
        (ERROR-strategy queue overflow), the seq watermark is rolled back
        so the dropped message stays visible as a future gap rather than
        being silently treated as already-seen. Orderbook state isn't
        rolled back — the recv loop tears down via sentinel broadcast on
        this error, so the local book becomes orphaned but is never
        desynced-and-still-consumed.
        """
        assert self._dispatcher is not None
        data = self._json_loads(raw)
        sid = data.get("sid")
        seq = data.get("seq")
        msg_type = data.get("type", "")

        # #255: stale orderbook frames arriving after a teardown
        # (resubscribe_one or server-initiated unsubscribe reaped the
        # sid) must not mutate the local book. The dispatcher already
        # drops unknown-sid frames at routing time, but the orderbook
        # apply paths below ran BEFORE that check, so a stale snapshot
        # could re-seed the manager under the old sid index and a stale
        # delta could clobber the freshly-resynced book. Gate ALL
        # downstream processing (seq tracking, validation, apply,
        # dispatch) on the sid being currently mapped. Frames without a
        # sid (control envelopes, untracked channels) fall through.
        if (
            msg_type in ("orderbook_snapshot", "orderbook_delta")
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
            # #330: sync fast path. Avoids per-frame coroutine allocation
            # on the happy path (seq == expected, the case on every
            # legitimate sequenced frame). Only await on_gap when the
            # tracker actually reports a gap.
            ok, gap = self._seq_tracker.track_sync(
                sid, seq, msg_type if msg_type else channel
            )
            if gap is not None:
                await self._seq_tracker.fire_gap(gap)
            if not ok:
                # Gap detected — skip dispatching this message.
                # The gap handler will trigger resync.
                return
            # Only meaningful once we know we'll dispatch (and might roll back).
            tracked = True

        # Pre-validate orderbook frames (so the manager applies typed data),
        # then dispatch. Both steps must roll the seq watermark back if they
        # fail — otherwise a malformed frame on a sequenced channel silently
        # advances the watermark and the next legitimate frame's gap is
        # missed, leaving the local orderbook desynced from the server (#241).
        pre_validated: BaseModel | None = None
        try:
            if msg_type == "orderbook_snapshot" and self._orderbook_mgr:
                snapshot = OrderbookSnapshotMessage.model_validate(data)
                # #199: mutate in place — skip the O(n log n) sort + 2N
                # OrderbookLevel allocation that the public ``apply_snapshot``
                # wrapper performs. Consumers materialize via ``get(ticker)``
                # on demand.
                # Record per-sid ticker ownership so all-markets subscriptions
                # can be torn down on gap recovery / unsubscribe (#189, #206).
                self._orderbook_mgr._apply_snapshot_inplace(snapshot, sid=snapshot.sid)
                pre_validated = snapshot
            elif msg_type == "orderbook_delta" and self._orderbook_mgr:
                delta = OrderbookDeltaMessage.model_validate(data)
                # #199: in-place mutation only — see snapshot branch above.
                self._orderbook_mgr._apply_delta_inplace(delta)
                pre_validated = delta

            await self._dispatcher.dispatch(data, pre_validated=pre_validated)
        except KalshiBackpressureError as exc:
            # Dispatch failed -> the consumer never saw this message. Roll
            # the seq watermark back so the dropped seq is treated as a
            # future gap (not silently as already-seen). Surface the error
            # to the affected sub's iterator (#207) so the consumer can
            # halt rather than see an indistinguishable-from-close
            # ``StopAsyncIteration``. Re-raise so the recv loop's existing
            # handler broadcasts sentinels to the OTHER subs and tears the
            # loop down — the affected queue's error sentinel was put
            # first, so it surfaces before the close sentinel.
            if tracked and sid is not None and self._seq_tracker:
                self._seq_tracker.rollback(sid, prev_seq)
            if sid is not None and self._sub_mgr is not None:
                affected = self._sub_mgr.get_subscription_by_sid(sid)
                if affected is not None:
                    await self._sub_mgr.broadcast_error(affected.client_id, exc)
            raise
        except Exception:
            # #241: ValidationError, KeyError, or any programming bug between
            # the seq advance and dispatch leaves the watermark over-advanced
            # past a frame that was NEVER applied locally and NEVER delivered
            # to the consumer. Roll back so the dropped seq surfaces as a
            # forward gap on the next legitimate frame (gap handler then
            # drives a real resubscribe + snapshot). Re-raise so the
            # recv-loop's existing malformed-frame handler logs + continues.
            if tracked and sid is not None and self._seq_tracker:
                self._seq_tracker.rollback(sid, prev_seq)
            raise

    async def _handle_reconnect(self) -> None:
        """Reconnect after ConnectionClosed and re-establish subscriptions.

        F-P-03: acquire `_subscribe_lock` for the entire reconnect+resubscribe
        sequence so any in-flight user-level `subscribe_*` blocks until we've
        rebuilt `_sid_to_client`. Without the lock, messages arriving on a
        freshly-assigned sid during the rebuild can mis-route.
        """
        assert self._connection is not None
        logger.warning("Connection lost, attempting reconnect...")
        async with self._subscribe_lock:
            try:
                await self._connection.reconnect()
                if self._sub_mgr:
                    if self._seq_tracker:
                        self._seq_tracker.reset_all()
                    if self._orderbook_mgr:
                        self._orderbook_mgr.clear()
                    await self._sub_mgr.resubscribe_all()
                    # #176: replay frames that the server sent on
                    # newly-assigned sids before the corresponding
                    # subscribe ack landed. SubscriptionManager stashed
                    # them keyed by sid during _wait_for_response; drain
                    # through _process_frame so seq tracking + orderbook
                    # state stay consistent with the natural arrival path.
                    await self._drain_resubscribe_stash()
                    # #88: use the public transition; no reach-through to
                    # ConnectionManager's name-mangled _set_state.
                    await self._connection.mark_streaming()
            except Exception as reconnect_err:
                logger.error(
                    "Reconnect failed: %s", reconnect_err, exc_info=True,
                )
                await self._broadcast_sentinels()
                self._running = False

    async def _drain_resubscribe_stash(self) -> None:
        """Replay frames captured during a resubscribe through dispatch.

        #176/#254: ``SubscriptionManager._wait_for_response`` captures
        non-matching data frames into a per-sid stash while ``_stashing``
        is set — which happens around both ``resubscribe_all`` (full
        reconnect) and ``resubscribe_one`` (single-sub gap recovery).
        Between ``_sid_to_client.clear()`` (or the per-sid teardown) and
        the new sid mapping landing, the dispatcher has no route for
        those frames. After the resubscribe completes, this method
        drains the stash via ``_process_frame`` so seq tracking and
        orderbook state stay consistent with the natural arrival path.

        Frames whose sid did not get re-mapped (subscription failed
        during ``resubscribe_all``, or the targeted sid was replaced
        without re-mapping in ``resubscribe_one``) are dropped with a
        debug log — there's no consumer to deliver them to.
        """
        if self._sub_mgr is None:
            return
        stash = self._sub_mgr.take_stash()
        for sid, raw_frames in stash.items():
            if self._sub_mgr.get_subscription_by_sid(sid) is None:
                logger.debug(
                    "Dropping %d stashed frames for unmapped sid %d "
                    "after resubscribe (subscription likely failed)",
                    len(raw_frames), sid,
                )
                continue
            for raw in raw_frames:
                try:
                    await self._process_frame(raw)
                except Exception:
                    # Per-frame failure during replay: log and continue.
                    # The recv-loop's own error-handling is bypassed here
                    # because we're in the orchestration path, not the loop.
                    logger.warning(
                        "Failed to replay stashed frame for sid %d",
                        sid, exc_info=True,
                    )

    async def _handle_seq_gap(self, gap: SequenceGap) -> None:
        """Handle a sequence gap or reset by driving a real resubscribe.

        Replaces the previous clear-and-pray behavior (#189). Works for
        any sequenced channel — orderbook_delta covers the canonical
        case, order_group_updates also reaches this path (#205).

        Steps:

        1. Tear down per-sid local state (orderbook books seeded by this
           sid via :meth:`OrderbookManager.remove_by_sid`; seq watermark
           via :meth:`SequenceTracker.reset`). All-markets orderbook
           subscriptions are handled correctly because the manager
           tracks ticker ownership by sid, not by the caller's params.
        2. Drive :meth:`SubscriptionManager.resubscribe_one`. The server
           assigns a new sid; for orderbook subs the resubscribe forces
           ``send_initial_snapshot=True`` so the book repopulates.
        3. If the resubscribe fails, surface ``KalshiSequenceGapError``
           to the consumer iterator via
           :meth:`SubscriptionManager.broadcast_error` (#207-style) so
           safety-critical strategies can halt rather than consume from
           a permanently-empty local book.
        """
        logger.warning(
            "Sequence %s on sid %d: expected %d, got %d. Triggering resync.",
            gap.kind, gap.sid, gap.expected, gap.received,
        )
        if self._sub_mgr is None:
            return
        sub = self._sub_mgr.get_subscription_by_sid(gap.sid)
        if sub is None:
            return

        # 1. Tear down per-sid local state.
        if self._orderbook_mgr is not None:
            cleared = self._orderbook_mgr.remove_by_sid(gap.sid)
            if cleared:
                logger.warning(
                    "Cleared %d orderbook entries for sid %d on %s",
                    len(cleared), gap.sid, gap.kind,
                )
        if self._seq_tracker is not None:
            self._seq_tracker.reset(gap.sid)

        client_id = sub.client_id
        channel = sub.channel

        # 2. Drive a real resubscribe so the server emits a fresh snapshot
        # (and a new sid). Surface failures to the consumer iterator.
        try:
            await self._sub_mgr.resubscribe_one(client_id)
        except KalshiSubscriptionError as e:
            logger.error(
                "Resubscribe after gap failed for client_id=%d channel=%s",
                client_id, channel, exc_info=True,
            )
            await self._sub_mgr.broadcast_error(
                client_id,
                KalshiSequenceGapError(
                    f"Resubscribe failed for {channel} after {gap.kind}: {e}",
                    channel=channel,
                    sid=gap.sid,
                    client_id=client_id,
                    last_seq=gap.expected - 1,
                    next_seq=gap.received,
                ),
            )
            return

        # 3. #254: drain the resubscribe-window stash. ``resubscribe_one``
        # toggles ``_stashing`` around its unsubscribe+subscribe pair, so
        # any data frames the server emitted during the sid handoff are
        # captured in ``_sub_mgr._stash``. Without this drain they sit
        # there until the next full reconnect, and the post-resubscribe
        # consumer can see a forward seq gap (delta with seq>1 arriving
        # before the snapshot it depends on). The shared helper replays
        # any sid that still has a mapping (covers the new sid and any
        # OTHER live subscriptions whose frames happened to land during
        # the resubscribe window) and drops frames for sids that no
        # longer route to a subscription, with a debug log.
        await self._drain_resubscribe_stash()

    # ------------------------------------------------------------------
    # Internal subscribe helper
    # ------------------------------------------------------------------

    async def _do_subscribe(
        self,
        channel: str,
        params: dict[str, Any] | None = None,
        overflow: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        maxsize: int = 1000,
    ) -> AsyncIterator[Any]:
        """Pause recv_loop, subscribe, resume recv_loop, return queue.

        Serialized with asyncio.Lock to prevent concurrent subscribe races.

        #332: when the recv loop has torn itself down on a fatal error
        (``KalshiBackpressureError`` / ``KalshiSubscriptionError``), the
        managers are cleared. Fail fast with a clear error instead of
        letting the assert below fire (or — worse — resurrecting a recv
        loop on top of orphaned server-side subscriptions).
        """
        if not self._running or self._sub_mgr is None or self._connection is None:
            raise RuntimeError(
                "KalshiWebSocket session is not active. The recv loop tore "
                "down after a fatal error (e.g. KalshiBackpressureError); "
                "exit the current `async with ws.connect()` block and start "
                "a fresh session before subscribing again."
            )
        async with self._subscribe_lock:
            await self._pause_recv_loop()
            # #332: ``_pause_recv_loop`` can return because the recv loop
            # tore the session down on backpressure (inline teardown sets
            # ``_pause_granted`` to release any waiter — ``Event.clear()``
            # alone does NOT unblock a coroutine already in ``.wait()``).
            # Re-check before proceeding so a woken-up subscriber doesn't
            # poke a dead session.
            if (
                not self._running
                or self._sub_mgr is None
                or self._connection is None
            ):
                raise RuntimeError(
                    "KalshiWebSocket session is not active. The recv loop "
                    "tore down after a fatal error (e.g. "
                    "KalshiBackpressureError); exit the current `async with "
                    "ws.connect()` block and start a fresh session before "
                    "subscribing again."
                )
            try:
                sub = await self._sub_mgr.subscribe(
                    channel, params=params, overflow=overflow, maxsize=maxsize,
                )
            finally:
                # Always restart/resume recv loop, even if subscribe fails.
                self._ensure_recv_loop()
        return sub.queue

    # ------------------------------------------------------------------
    # Per-channel typed subscribe methods
    # ------------------------------------------------------------------

    async def subscribe_ticker(
        self, *, tickers: list[str] | None = None, maxsize: int = 1000,
    ) -> AsyncIterator[TickerMessage]:
        params: dict[str, Any] = {}
        if tickers:
            params["market_tickers"] = tickers
        return await self._do_subscribe(
            "ticker", params=params,
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_orderbook_delta(
        self, *, tickers: list[str] | None = None, maxsize: int = 1000,
    ) -> AsyncIterator[OrderbookSnapshotMessage | OrderbookDeltaMessage]:
        """Subscribe to ``orderbook_delta`` for the given tickers.

        Note: ``OrderbookSnapshotMessage.msg.yes`` and ``.no`` are live dicts
        owned by the :class:`OrderbookManager` after this dispatch — they
        mutate on every delta. Use :meth:`orderbook` if you need an immutable
        snapshot view.
        """
        params: dict[str, Any] = {"send_initial_snapshot": True}
        if tickers:
            params["market_tickers"] = tickers
        return await self._do_subscribe(
            "orderbook_delta", params=params,
            overflow=OverflowStrategy.ERROR, maxsize=maxsize,
        )

    async def subscribe_trade(
        self, *, tickers: list[str] | None = None, maxsize: int = 1000,
    ) -> AsyncIterator[TradeMessage]:
        params: dict[str, Any] = {}
        if tickers:
            params["market_tickers"] = tickers
        return await self._do_subscribe(
            "trade", params=params,
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_fill(
        self, *, maxsize: int = 1000,
    ) -> AsyncIterator[FillMessage]:
        return await self._do_subscribe(
            "fill", overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_market_positions(
        self, *, maxsize: int = 1000,
    ) -> AsyncIterator[MarketPositionsMessage]:
        return await self._do_subscribe(
            "market_positions",
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_user_orders(
        self, *, maxsize: int = 1000,
    ) -> AsyncIterator[UserOrdersMessage]:
        return await self._do_subscribe(
            "user_orders",
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_order_group(
        self, *, maxsize: int = 1000,
    ) -> AsyncIterator[OrderGroupMessage]:
        return await self._do_subscribe(
            "order_group_updates",
            overflow=OverflowStrategy.ERROR, maxsize=maxsize,
        )

    async def subscribe_market_lifecycle(
        self, *, tickers: list[str] | None = None, maxsize: int = 1000,
    ) -> AsyncIterator[MarketLifecycleMessage | EventFeeUpdateMessage]:
        """Subscribe to the market_lifecycle_v2 channel.

        Yields :class:`MarketLifecycleMessage` for lifecycle events and
        :class:`EventFeeUpdateMessage` for ``event_fee_update`` frames — both
        ride this channel. Discriminate on the ``.type`` field.
        """
        params: dict[str, Any] = {}
        if tickers:
            params["market_tickers"] = tickers
        return await self._do_subscribe(
            "market_lifecycle_v2", params=params,
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_multivariate(
        self, *, maxsize: int = 1000,
    ) -> AsyncIterator[MultivariateMessage]:
        return await self._do_subscribe(
            "multivariate",
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_multivariate_lifecycle(
        self, *, maxsize: int = 1000,
    ) -> AsyncIterator[MultivariateLifecycleMessage]:
        return await self._do_subscribe(
            "multivariate_market_lifecycle",
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_communications(
        self,
        *,
        shard_factor: int | None = None,
        shard_key: int | None = None,
        maxsize: int = 1000,
    ) -> AsyncIterator[CommunicationsMessage]:
        params: dict[str, Any] = {}
        if shard_factor is not None:
            params["shard_factor"] = shard_factor
        if shard_key is not None:
            params["shard_key"] = shard_key
        return await self._do_subscribe(
            "communications", params=params,
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    async def subscribe_cfbenchmarks_value(
        self, *, index_ids: list[str] | None = None, maxsize: int = 1000,
    ) -> AsyncIterator[CFBenchmarksValueMessage | CFBenchmarksIndexListMessage]:
        """Subscribe to the auth-required ``cfbenchmarks_value`` index feed.

        Seed ``index_ids`` (e.g. ``["BRTI", "ETHUSD_RTI"]`` or ``["all"]``) to
        receive values immediately; subscribing with no ids yields nothing until
        indices are added. The stream yields both ``cfbenchmarks_value`` data
        messages and ``cfbenchmarks_value_indexlist`` control responses, so
        discriminate with ``isinstance(msg, CFBenchmarksValueMessage)`` (or check
        ``msg.type``) before reading ``msg.msg``.
        """
        params: dict[str, Any] = {}
        if index_ids:
            params["index_ids"] = index_ids
        return await self._do_subscribe(
            "cfbenchmarks_value", params=params,
            overflow=OverflowStrategy.DROP_OLDEST, maxsize=maxsize,
        )

    # ------------------------------------------------------------------
    # Generic subscribe
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        channel: str,
        *,
        params: dict[str, Any] | None = None,
        overflow: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        maxsize: int = 1000,
    ) -> AsyncIterator[BaseModel]:
        return await self._do_subscribe(
            channel, params=params, overflow=overflow, maxsize=maxsize,
        )

    # ------------------------------------------------------------------
    # Unsubscribe
    # ------------------------------------------------------------------

    async def unsubscribe(self, client_id: int) -> None:
        """Tear down a subscription and its associated local state (#206).

        Removes any local :class:`OrderbookManager` books seeded by the
        sub's current ``server_sid`` (works for both explicit-tickers
        and all-markets orderbook subscriptions via the manager's per-sid
        index), then delegates to
        :meth:`SubscriptionManager.unsubscribe` to send the wire command,
        push the consumer-iterator sentinel, and drop the bookkeeping.
        Resets the seq watermark too so any sid reuse after server-side
        renumber doesn't replay against a stale floor.
        """
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
                        "Cleared %d orderbook entries for sid %d on unsubscribe",
                        len(cleared), old_sid,
                    )
            if self._seq_tracker is not None:
                self._seq_tracker.reset(old_sid)
        await self._sub_mgr.unsubscribe(client_id)

    # ------------------------------------------------------------------
    # Callback API
    # ------------------------------------------------------------------

    def on(self, channel: str) -> _CallbackDecorator:
        """Decorator to register a callback for a channel.

        Works both before and after connect(). Callbacks registered before
        connect are buffered and applied when the session starts.
        """
        def decorator(
            func: Callable[..., Awaitable[None]],
        ) -> Callable[..., Awaitable[None]]:
            if self._dispatcher:
                self._dispatcher.register_callback(channel, func)
            else:
                self._pending_callbacks.append((channel, func))
            return func
        return decorator

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """Block until the recv loop terminates. Use with the callback API.

        Requires at least one prior ``subscribe_*`` (or generic
        :meth:`subscribe`) call in the same session — the recv loop is
        started lazily by the subscribe machinery, and without it there
        is nothing to drain. Registering an ``@ws.on(channel)`` callback
        does NOT subscribe; the server only sends frames for channels you
        have explicitly subscribed to, so a callback without a matching
        subscribe sees nothing.

        :param stop_event: optional ``asyncio.Event`` used to terminate
            ``run_forever()`` cooperatively (#177). When set — typically
            from a signal handler such as ``add_signal_handler(SIGINT,
            stop.set)`` — this method clears ``_running``, closes the
            connection, and drains the recv loop. The recv loop sees
            ``ConnectionClosed`` on its next read and exits via the
            normal ``not self._running`` branch, NOT via cancellation,
            so no ``CancelledError`` leaks out. When ``None`` (the
            default) the method blocks on ``_recv_task`` directly and
            external cancellation still propagates as before.

            External cancellation of ``run_forever()`` itself (e.g.,
            ``task.cancel()`` on the awaiting task) while ``stop_event``
            is provided still propagates — the cancellation cleans up the
            internal ``stop_waiter`` task but does NOT trigger the
            cooperative shutdown branch. ``_recv_task`` keeps running
            until the session's ``__aexit__`` calls ``_stop()`` for the
            full teardown. Use the event for graceful exit; rely on
            ``__aexit__`` for hard cancellation.

        :raises KalshiSubscriptionError: ``run_forever()`` was called
            before any ``subscribe_*`` request landed (formerly a silent
            no-op return — fixed in #175).
        """
        if self._recv_task is None:
            raise KalshiSubscriptionError(
                "run_forever() requires at least one active subscription. "
                "Call subscribe_ticker(...) / subscribe_trade(...) / etc. "
                "(or the generic subscribe(channel, ...)) before run_forever() "
                "so the recv loop has something to drain. Registering an "
                "@ws.on(channel) callback does not subscribe — the server "
                "only sends frames for channels you explicitly subscribe to."
            )
        if stop_event is None:
            await self._recv_task
            return

        # Race the recv loop against the stop event. Whichever finishes first
        # wins; if stop wins, signal the recv loop to exit cleanly (via
        # _running + connection.close()) so the loop's existing
        # ConnectionClosed handler breaks instead of attempting reconnect.
        # NOTE: we do NOT cancel _recv_task — cancellation would re-introduce
        # the very CancelledError leak this hook exists to avoid (#177).
        stop_waiter = asyncio.create_task(stop_event.wait())
        try:
            done, _ = await asyncio.wait(
                {self._recv_task, stop_waiter},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_waiter in done:
                # Cooperative shutdown takes priority — broadcast sentinels
                # at the end even if _recv_task happens to also be in
                # `done` (server-side close racing the stop signal). The
                # recv loop's clean `not self._running: break` exits do
                # NOT broadcast on their own; only its error paths do. So
                # the simultaneous-completion case (both tasks done in the
                # same wait round) MUST go through this branch to avoid
                # leaving iterator consumers hanging.
                #
                # Clearing _running first means a still-running recv loop's
                # ConnectionClosed branch hits `if not self._running:
                # break` instead of reconnecting. We do NOT cancel
                # _recv_task — cancellation would re-introduce the very
                # CancelledError leak this hook exists to avoid (#177).
                #
                # Nested try/finally so a close() exception still drains
                # the recv task AND broadcasts queue sentinels — otherwise
                # iterators hang on consumers' `async for` even though the
                # connection is gone. _stop() does the same sentinel
                # broadcast on __aexit__; duplicated here so cooperative
                # shutdown is complete even for callers who use
                # run_forever() outside an `async with` block.
                self._running = False
                try:
                    if self._connection is not None:
                        await self._connection.close()
                finally:
                    try:
                        if not self._recv_task.done():
                            await self._recv_task
                        else:
                            # Already done. .result() re-raises any
                            # exception, surfaced as run_forever's exception.
                            self._recv_task.result()
                    finally:
                        await self._broadcast_sentinels()
                # NOTE: _recv_task is intentionally NOT reset to None here —
                # session lifecycle state is owned by ``_stop()`` (called from
                # ``__aexit__``), which performs the full reset atomically.
            elif self._recv_task in done:
                # Server-side close / crash without stop event firing. The
                # recv loop's error paths broadcast sentinels themselves;
                # its clean ConnectionClosed break does not, but in that
                # case the user didn't request shutdown and __aexit__ will
                # handle the teardown. Just re-surface any exception.
                self._recv_task.result()
        finally:
            if not stop_waiter.done():
                stop_waiter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stop_waiter

    # ------------------------------------------------------------------
    # Orderbook convenience
    # ------------------------------------------------------------------

    async def orderbook(
        self, ticker: str, *, maxsize: int = 100,
    ) -> AsyncIterator[Orderbook]:
        """Subscribe to orderbook_delta and yield full Orderbook on each update."""
        assert self._orderbook_mgr is not None
        stream = await self.subscribe_orderbook_delta(
            tickers=[ticker], maxsize=maxsize,
        )
        return _OrderbookIterator(stream, self._orderbook_mgr, ticker)


class _OrderbookIterator:
    """Wraps orderbook delta stream, yielding full Orderbook on each update."""

    def __init__(
        self,
        stream: AsyncIterator[Any],
        mgr: OrderbookManager,
        ticker: str,
    ) -> None:
        self._stream = stream
        self._mgr = mgr
        self._ticker = ticker

    def __aiter__(self) -> AsyncIterator[Orderbook]:
        return self

    async def __anext__(self) -> Orderbook:
        await self._stream.__anext__()
        book = self._mgr.get(self._ticker)
        if book is None:
            # #257: between a gap-triggered ``remove_by_sid`` and the
            # resync snapshot landing in the manager, the underlying
            # stream can yield a frame while ``get(ticker)`` is still
            # None. Previously this iterator masked the gap by yielding
            # a fresh empty :class:`Orderbook` — indistinguishable from
            # a real market with zero liquidity. A strategy reading
            # bid/ask off the empty book might place orders against
            # nothing. Surface the absence as a typed error so callers
            # can halt (or wait for the next snapshot) explicitly.
            raise KalshiOrderbookUnavailableError(
                f"Local orderbook for {self._ticker!r} is unavailable "
                "(snapshot torn down, resync snapshot not yet applied). "
                "Halt or wait for the next snapshot before reading bid/ask.",
                ticker=self._ticker,
            )
        return book


class _WebSocketSession:
    """Async context manager for a WebSocket session."""

    def __init__(self, ws: KalshiWebSocket) -> None:
        self._ws = ws

    async def __aenter__(self) -> KalshiWebSocket:
        await self._ws._start()
        return self._ws

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._ws._stop()
