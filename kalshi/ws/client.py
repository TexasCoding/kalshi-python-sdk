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
    KalshiSubscriptionError,
)
from kalshi.models.markets import Orderbook
from kalshi.ws.backpressure import OverflowStrategy
from kalshi.ws.channels import SubscriptionManager
from kalshi.ws.connection import ConnectionManager, ConnectionState
from kalshi.ws.dispatch import MessageDispatcher
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
from kalshi.ws.orderbook import OrderbookManager
from kalshi.ws.sequence import SequenceGap, SequenceTracker

logger = logging.getLogger("kalshi.ws")

# Type alias for state-change callback (too long to inline)
_StateChangeCb = Callable[[ConnectionState, ConnectionState], Awaitable[None]]
_CallbackDecorator = Callable[
    [Callable[..., Awaitable[None]]], Callable[..., Awaitable[None]]
]


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

    def connect(self) -> _WebSocketSession:
        """Return an async context manager for the WebSocket session."""
        return _WebSocketSession(self)

    async def _start(self) -> None:
        """Connect and initialize managers. Does NOT start recv_loop yet."""
        self._connection = ConnectionManager(
            auth=self._auth,
            config=self._config,
            heartbeat_timeout=self._heartbeat_timeout,
            on_state_change=self._on_state_change,
        )
        await self._connection.connect()

        self._sub_mgr = SubscriptionManager(self._connection)
        self._seq_tracker = SequenceTracker(on_gap=self._handle_seq_gap)
        self._orderbook_mgr = OrderbookManager()
        self._dispatcher = MessageDispatcher(
            sub_mgr=self._sub_mgr,
            on_error=self._on_error,
            seq_tracker=self._seq_tracker,
        )
        self._running = True

        # Register any callbacks that were buffered before connect()
        for channel, func in self._pending_callbacks:
            self._dispatcher.register_callback(channel, func)
        self._pending_callbacks.clear()

    async def _stop(self) -> None:
        """Stop the receive loop and close the connection."""
        self._running = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._recv_task

        # Send sentinels to all active queues
        if self._sub_mgr:
            for sub in self._sub_mgr.active_subscriptions.values():
                await sub.queue.put_sentinel()

        if self._connection:
            await self._connection.close()

    def _ensure_recv_loop(self) -> None:
        """Start the recv_loop background task if not already running."""
        if self._recv_task is None or self._recv_task.done():
            self._recv_task = asyncio.create_task(self._recv_loop())

    async def _pause_recv_loop(self) -> None:
        """Cancel the recv_loop so subscribe can safely call recv.

        F-P-04: cancellation only fires while the loop is awaiting
        ``connection.recv()``. The recv-then-process critical section is
        shielded from cancellation so any frame already off the socket is
        fully dispatched before the loop exits.
        """
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._recv_task
            self._recv_task = None

    async def _recv_loop(self) -> None:
        """Background task: read frames, dispatch, handle reconnect."""
        assert self._connection is not None
        assert self._dispatcher is not None

        while self._running:
            try:
                raw = await self._connection.recv()
            except asyncio.CancelledError:
                # F-P-04: cancellation while awaiting recv = no frame read,
                # no data lost. Safe to exit.
                break
            except ConnectionClosed:
                if not self._running:
                    break
                await self._handle_reconnect()
                if not self._running:
                    break
                continue

            # F-P-04: shield the recv->dispatch critical section. Once a
            # frame has been read off the socket, we MUST dispatch it before
            # honoring cancellation, otherwise the frame is silently dropped
            # (seq trackers miss the gap, ticker frames vanish, etc.).
            #
            # IMPORTANT: hold the inner task in a local. `asyncio.shield(coro)`
            # creates a detached background task and returns control on outer
            # cancel — without the explicit `await inner`, dispatch keeps
            # running after `break` and races a subsequent subscribe.
            inner = asyncio.create_task(self._process_frame(raw))
            try:
                await asyncio.shield(inner)
            except asyncio.CancelledError:
                # Block until the shielded dispatch actually finishes, then
                # honor cancellation. Loop exit now strictly post-dispatch.
                # KalshiBackpressureError / KalshiSubscriptionError must
                # still broadcast sentinels even when we're being cancelled —
                # the consumer-visible invariant (no hanging iterators) holds
                # unconditionally. Parse errors are best-effort logged.
                try:
                    await inner
                except (KalshiBackpressureError, KalshiSubscriptionError):
                    if self._sub_mgr:
                        for sub in self._sub_mgr.active_subscriptions.values():
                            await sub.queue.put_sentinel()
                except Exception:
                    logger.debug(
                        "Shielded dispatch raised during cancel cleanup",
                        exc_info=True,
                    )
                break
            except (KalshiBackpressureError, KalshiSubscriptionError):
                # #83: these signal real consumer-visible problems. Propagate
                # via sentinel-broadcast so iterators see the failure and the
                # loop exits cleanly rather than spinning on the same error.
                logger.error(
                    "Fatal WS error in recv loop", exc_info=True,
                )
                if self._sub_mgr:
                    for sub in self._sub_mgr.active_subscriptions.values():
                        await sub.queue.put_sentinel()
                break
            except (json.JSONDecodeError, ValidationError, KeyError):
                # #83: genuinely-non-fatal per-message errors. Log with
                # traceback so users can debug, then continue.
                logger.warning(
                    "Skipping malformed WS frame", exc_info=True,
                )
                continue
            except Exception:
                # #83 escape hatch: anything else (AttributeError from a
                # user-supplied callback, TypeError, programming bug, ...)
                # MUST broadcast sentinels before propagating — otherwise
                # consumers hang on their queues with no signal. Re-raise
                # after broadcast so the task failure is still visible.
                logger.error(
                    "Unexpected error in recv loop; broadcasting sentinels",
                    exc_info=True,
                )
                if self._sub_mgr:
                    for sub in self._sub_mgr.active_subscriptions.values():
                        await sub.queue.put_sentinel()
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
        data = json.loads(raw)
        sid = data.get("sid")
        seq = data.get("seq")
        msg_type = data.get("type", "")

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
            ok = await self._seq_tracker.track(
                sid, seq, msg_type if msg_type else channel
            )
            if not ok:
                # Gap detected — skip dispatching this message.
                # The gap handler will trigger resync.
                return
            # Only meaningful once we know we'll dispatch (and might roll back).
            tracked = True

        # Check for orderbook messages — validate ONCE for the local
        # manager, then hand the typed message off to dispatch via
        # pre_validated so the dispatcher routes the same instance to
        # the queue without re-running Pydantic.
        pre_validated: BaseModel | None = None
        if msg_type == "orderbook_snapshot" and self._orderbook_mgr:
            snapshot = OrderbookSnapshotMessage.model_validate(data)
            self._orderbook_mgr.apply_snapshot(snapshot)
            pre_validated = snapshot
        elif msg_type == "orderbook_delta" and self._orderbook_mgr:
            delta = OrderbookDeltaMessage.model_validate(data)
            self._orderbook_mgr.apply_delta(delta)
            pre_validated = delta

        try:
            await self._dispatcher.dispatch(data, pre_validated=pre_validated)
        except KalshiBackpressureError:
            # Dispatch failed -> the consumer never saw this message. Roll
            # the seq watermark back so the dropped seq is treated as a
            # future gap (not silently as already-seen). Re-raise so the
            # recv loop's existing handler broadcasts sentinels and tears
            # the loop down.
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
                    # #88: use the public transition; no reach-through to
                    # ConnectionManager's name-mangled _set_state.
                    await self._connection.mark_streaming()
            except Exception as reconnect_err:
                logger.error(
                    "Reconnect failed: %s", reconnect_err, exc_info=True,
                )
                if self._sub_mgr:
                    for sub in self._sub_mgr.active_subscriptions.values():
                        await sub.queue.put_sentinel()
                self._running = False

    async def _handle_seq_gap(self, gap: SequenceGap) -> None:
        """Handle a sequence gap by logging and triggering resync.

        A single ``orderbook_delta`` subscription can cover multiple tickers
        under one sid. The gap envelope doesn't identify which ticker
        missed an update, so we clear EVERY ticker on the affected
        subscription — clearing only ``tickers[0]`` would leave the other
        books silently diverged from server truth.
        """
        logger.warning(
            "Sequence gap on sid %d: expected %d, got %d. Triggering resync.",
            gap.sid, gap.expected, gap.received,
        )
        if self._sub_mgr:
            sub = self._sub_mgr.get_subscription_by_sid(gap.sid)
            if sub and sub.channel == "orderbook_delta":
                # Clear orderbook state for ALL tickers in the sub and reset
                # sequence tracking so the next snapshot rebootstraps cleanly.
                tickers = sub.params.get("market_tickers", [])
                if self._orderbook_mgr:
                    for ticker in tickers:
                        self._orderbook_mgr.remove(ticker)
                if self._seq_tracker:
                    self._seq_tracker.reset(gap.sid)

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
        """
        assert self._sub_mgr is not None
        async with self._subscribe_lock:
            await self._pause_recv_loop()
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
    ) -> AsyncIterator[MarketLifecycleMessage]:
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

    async def run_forever(self) -> None:
        """Block until the connection is closed. Use with callback API."""
        if self._recv_task:
            await self._recv_task

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
            # This shouldn't happen after snapshot, but handle gracefully
            return Orderbook(ticker=self._ticker)
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
