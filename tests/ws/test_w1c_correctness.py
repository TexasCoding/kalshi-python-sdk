"""Regression tests for the W1-C correctness sweep.

Covers:
- #189 orderbook resync after gap (CRITICAL)
- #195 generic subscribe param validation
- #196 seq reset detection (three-way)
- #197 reconnect on permanent close codes
- #205 order_group_updates gap recovery
- #206 unsubscribe orderbook leak
- #207 backpressure ERROR strategy raises through iterator
- #213 raise-site kwarg population

Determinism: where possible, drive state directly via public hooks and
poll on observable conditions. Avoid arbitrary sleeps that would race
the recv loop.
"""
from __future__ import annotations

import asyncio

import pytest

from kalshi.config import KalshiConfig
from kalshi.errors import (
    KalshiBackpressureError,
    KalshiConnectionError,
    KalshiSequenceGapError,
    KalshiSubscriptionError,
)
from kalshi.ws.backpressure import MessageQueue, OverflowStrategy
from kalshi.ws.channels import SubscriptionManager
from kalshi.ws.client import _PERMANENT_CLOSE_CODES, KalshiWebSocket
from kalshi.ws.connection import ConnectionManager
from kalshi.ws.sequence import SequenceGap, SequenceTracker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


# ---------------------------------------------------------------------------
# #195 — generic subscribe param validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGenericSubscribeParamValidation:
    async def test_generic_subscribe_rejects_unknown_param_keys(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#195: a typo'd or unknown key fails at submission with context."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect():
            with pytest.raises(KalshiSubscriptionError) as excinfo:
                await ws.subscribe(
                    "orderbook_delta",
                    params={"tickerz": ["X"]},  # typo'd key
                )
        assert excinfo.value.channel == "orderbook_delta"
        assert excinfo.value.op == "subscribe"


# ---------------------------------------------------------------------------
# #196 — seq three-way distinction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSeqResetDistinction:
    async def test_seq_equal_to_last_dropped_not_dispatched(self) -> None:
        gaps: list[SequenceGap] = []

        async def on_gap(gap: SequenceGap) -> None:
            gaps.append(gap)

        tracker = SequenceTracker(on_gap=on_gap)
        await tracker.track(1, 5, "orderbook_delta")
        # Exact duplicate: drop, do NOT fire on_gap.
        result = await tracker.track(1, 5, "orderbook_delta")
        assert result is False
        assert gaps == []
        assert tracker.peek(1) == 5

    async def test_seq_below_last_triggers_reset_recovery(self) -> None:
        gaps: list[SequenceGap] = []

        async def on_gap(gap: SequenceGap) -> None:
            gaps.append(gap)

        tracker = SequenceTracker(on_gap=on_gap)
        await tracker.track(1, 10, "orderbook_delta")
        # seq < last: server-side reset. Fire on_gap with kind="reset".
        result = await tracker.track(1, 3, "orderbook_delta")
        assert result is False
        assert len(gaps) == 1
        assert gaps[0].kind == "reset"
        assert gaps[0].received == 3
        # Watermark rewound to 3 so subsequent post-reset frames aren't
        # silently dropped as "still old".
        assert tracker.peek(1) == 3

    async def test_seq_1_after_high_watermark_treated_as_reset(self) -> None:
        gaps: list[SequenceGap] = []

        async def on_gap(gap: SequenceGap) -> None:
            gaps.append(gap)

        tracker = SequenceTracker(on_gap=on_gap)
        await tracker.track(1, 42, "orderbook_delta")
        result = await tracker.track(1, 1, "orderbook_delta")
        assert result is False
        assert len(gaps) == 1
        assert gaps[0].kind == "reset"
        assert tracker.peek(1) == 1


# ---------------------------------------------------------------------------
# #197 — permanent close code classification
# ---------------------------------------------------------------------------


class TestPermanentCloseCodes:
    def test_permanent_set_includes_4xxx(self) -> None:
        assert 4001 in _PERMANENT_CLOSE_CODES
        assert 4999 in _PERMANENT_CLOSE_CODES
        assert 5000 not in _PERMANENT_CLOSE_CODES

    def test_permanent_set_includes_rfc6455_codes(self) -> None:
        for code in (1002, 1003, 1007, 1008, 1009, 1010):
            assert code in _PERMANENT_CLOSE_CODES

    def test_recoverable_codes_excluded(self) -> None:
        # 1006 abnormal close, 1011 server error, 1001 going away — all recoverable.
        for code in (1001, 1006, 1011):
            assert code not in _PERMANENT_CLOSE_CODES


@pytest.mark.asyncio
class TestCloseCodeBehavior:
    async def test_close_4001_does_not_reconnect_and_raises(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#197: close code 4001 (auth) raises KalshiConnectionError, no retry."""
        config = KalshiConfig(
            ws_base_url=fake_ws.url, timeout=5.0,
            retry_base_delay=0.01, retry_max_delay=0.05, ws_max_retries=3,
        )
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])
            # Server closes with 4001.
            for sub in list(fake_ws.connections):
                await sub.close(code=4001, reason="auth failure")
            # Recv task must raise KalshiConnectionError.
            recv_task = session._recv_task
            assert recv_task is not None
            with pytest.raises(KalshiConnectionError) as excinfo:
                await asyncio.wait_for(recv_task, timeout=2.0)
            assert "4001" in str(excinfo.value)
            # Iterator terminated cleanly via the broadcast sentinel.
            with pytest.raises(StopAsyncIteration):
                await stream.__anext__()

    async def test_close_1008_does_not_reconnect(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#197: policy violation (1008) raises, doesn't retry."""
        config = KalshiConfig(
            ws_base_url=fake_ws.url, timeout=5.0,
            retry_base_delay=0.01, retry_max_delay=0.05, ws_max_retries=3,
        )
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_ticker(tickers=["T1"])
            for sub in list(fake_ws.connections):
                await sub.close(code=1008, reason="policy")
            recv_task = session._recv_task
            assert recv_task is not None
            with pytest.raises(KalshiConnectionError):
                await asyncio.wait_for(recv_task, timeout=2.0)

    async def test_close_1006_reconnects(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#197: abnormal closure (1006) is recoverable — reconnect path runs.

        We assert by checking the connection state ends in STREAMING after
        the reconnect completes; if 1006 had been classified permanent the
        recv loop would raise KalshiConnectionError instead.
        """
        config = KalshiConfig(
            ws_base_url=fake_ws.url, timeout=5.0,
            retry_base_delay=0.01, retry_max_delay=0.05, ws_max_retries=3,
        )
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_ticker(tickers=["T1"])
            # Drop the underlying socket without sending a close frame —
            # websockets surfaces this as code 1006.
            for sub in list(fake_ws.connections):
                # transport-level abrupt close
                sub.transport.close()
            # Give the recv loop a chance to reconnect.
            from kalshi.ws.connection import ConnectionState
            await _wait_for(
                lambda: ws._connection is not None
                and ws._connection.state in (
                    ConnectionState.STREAMING,
                    ConnectionState.CONNECTED,
                ),
                timeout=3.0,
            )
            assert ws._connection is not None
            assert ws._connection.state in (
                ConnectionState.STREAMING, ConnectionState.CONNECTED,
            )

    async def test_close_4001_broadcasts_sentinels(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#197: permanent close fans out sentinels so iterators terminate."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])
            for sub in list(fake_ws.connections):
                await sub.close(code=4001, reason="auth")
            # Iterator terminates within bounded time via sentinel.
            collected: list[object] = []
            with pytest.raises(StopAsyncIteration):
                async with asyncio.timeout(2.0):
                    while True:
                        collected.append(await stream.__anext__())
            # Retrieve the recv task's exception so the test doesn't leak
            # an unretrieved-task warning at GC time.
            recv_task = session._recv_task
            assert recv_task is not None
            with pytest.raises(KalshiConnectionError):
                await asyncio.wait_for(recv_task, timeout=1.0)


# ---------------------------------------------------------------------------
# #189 — orderbook resync after gap (CRITICAL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestOrderbookResync:
    async def test_orderbook_resync_after_gap_repopulates_book(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#189: forced gap on per-ticker sub -> book is repopulated after resync.

        Subscribe to ["T1"], seed via snapshot, force a gap, verify the
        book is repopulated by a fresh snapshot on the new sid.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta(tickers=["T1"])
            assert session._sub_mgr is not None
            assert session._orderbook_mgr is not None
            assert session._seq_tracker is not None
            old_sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert old_sid is not None

            # Seed snapshot via the wire so seq tracker sees seq=1.
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": old_sid, "seq": 1,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })
            await _wait_for(
                lambda: session._orderbook_mgr.get("T1") is not None  # type: ignore[union-attr]
            )

            # Pre-arrange: when the resubscribe creates a new sid, the server
            # should send a fresh snapshot. fake_ws doesn't auto-snapshot, so
            # we'll send it once we observe the new sid.
            # Force a gap by sending seq=N+2 (expected 2, got 5).
            await fake_ws.send_to_all({
                "type": "orderbook_delta", "sid": old_sid, "seq": 5,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "price": "0.51", "delta": "10", "side": "yes",
                },
            })

            # Wait for the resubscribe to land: subscription gets a new sid.
            def resubscribed() -> bool:
                sub = session._sub_mgr.get_subscription(1)  # type: ignore[union-attr]
                return (
                    sub is not None
                    and sub.server_sid is not None
                    and sub.server_sid != old_sid
                )

            await _wait_for(resubscribed, timeout=3.0)

            # The book was cleared on gap (remove_by_sid).
            assert session._orderbook_mgr.get("T1") is None

            # Send a fresh snapshot on the new sid; book repopulates.
            sub = session._sub_mgr.get_subscription(1)
            assert sub is not None
            new_sid = sub.server_sid
            assert new_sid is not None
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": new_sid, "seq": 1,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "yes": [["0.55", "200"]], "no": [],
                },
            })
            await _wait_for(
                lambda: session._orderbook_mgr.get("T1") is not None  # type: ignore[union-attr]
            )
            book = session._orderbook_mgr.get("T1")
            assert book is not None
            assert len(book.yes) == 1

    async def test_orderbook_resync_works_for_all_markets_sub(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#189: all-markets sub (no tickers=) — gap clears all per-sid books."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta()  # no tickers
            assert session._sub_mgr is not None
            assert session._orderbook_mgr is not None
            old_sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert old_sid is not None

            # Seed two tickers under the same sid.
            for i, ticker in enumerate(["A", "B"], start=1):
                await fake_ws.send_to_all({
                    "type": "orderbook_snapshot", "sid": old_sid, "seq": i,
                    "msg": {
                        "market_ticker": ticker, "market_id": "x",
                        "yes": [["0.50", "100"]], "no": [],
                    },
                })
            await _wait_for(
                lambda: session._orderbook_mgr.get("A") is not None  # type: ignore[union-attr]
                and session._orderbook_mgr.get("B") is not None  # type: ignore[union-attr]
            )
            # Confirm per-sid tracking is populated.
            assert session._orderbook_mgr.tickers_for_sid(old_sid) == {"A", "B"}

            # Force a gap.
            await fake_ws.send_to_all({
                "type": "orderbook_delta", "sid": old_sid, "seq": 99,
                "msg": {
                    "market_ticker": "A", "market_id": "x",
                    "price": "0.51", "delta": "10", "side": "yes",
                },
            })

            def resubscribed() -> bool:
                sub = session._sub_mgr.get_subscription(1)  # type: ignore[union-attr]
                return (
                    sub is not None
                    and sub.server_sid is not None
                    and sub.server_sid != old_sid
                )

            await _wait_for(resubscribed, timeout=3.0)

            # Both books cleared via remove_by_sid even though the gap
            # envelope didn't identify any specific ticker.
            assert session._orderbook_mgr.get("A") is None
            assert session._orderbook_mgr.get("B") is None

    async def test_order_group_updates_gap_triggers_resubscribe(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#205: order_group_updates gap routes through generic resubscribe."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_order_group()
            assert session._sub_mgr is not None
            assert session._seq_tracker is not None
            old_sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert old_sid is not None

            # Pause recv loop so we can manipulate seq tracker and re-inject
            # without racing.
            await session._pause_recv_loop()
            session._seq_tracker._last_seq[old_sid] = 5

            # Drive the gap handler directly (the gap-detected path inside
            # _process_frame is exercised by sequence-tracker tests).
            await session._handle_seq_gap(
                SequenceGap(sid=old_sid, expected=6, received=10)
            )

            # Subscription was resubscribed: new server_sid.
            sub = session._sub_mgr.get_subscription(1)
            assert sub is not None
            assert sub.server_sid is not None
            assert sub.server_sid != old_sid


# ---------------------------------------------------------------------------
# #206 — unsubscribe leak (orderbook teardown)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUnsubscribeOrderbookTeardown:
    async def test_unsubscribe_removes_orderbook_state_for_subscribed_tickers(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta(tickers=["X"])
            assert session._sub_mgr is not None
            assert session._orderbook_mgr is not None
            sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert sid is not None
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": sid, "seq": 1,
                "msg": {
                    "market_ticker": "X", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })
            await _wait_for(
                lambda: session._orderbook_mgr.get("X") is not None  # type: ignore[union-attr]
            )

            # Unsubscribe via the public API.
            await session._pause_recv_loop()
            await session.unsubscribe(client_id=1)
            assert session._orderbook_mgr.get("X") is None

    async def test_unsubscribe_works_for_all_markets_sub(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta()
            assert session._sub_mgr is not None
            assert session._orderbook_mgr is not None
            sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert sid is not None
            for i, ticker in enumerate(["P", "Q", "R"], start=1):
                await fake_ws.send_to_all({
                    "type": "orderbook_snapshot", "sid": sid, "seq": i,
                    "msg": {
                        "market_ticker": ticker, "market_id": "x",
                        "yes": [["0.5", "1"]], "no": [],
                    },
                })
            await _wait_for(
                lambda: all(
                    session._orderbook_mgr.get(t) is not None  # type: ignore[union-attr]
                    for t in ("P", "Q", "R")
                )
            )

            await session._pause_recv_loop()
            await session.unsubscribe(client_id=1)
            for t in ("P", "Q", "R"):
                assert session._orderbook_mgr.get(t) is None

    async def test_get_after_unsubscribe_returns_none_not_stale_book(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta(tickers=["Y"])
            assert session._sub_mgr is not None
            assert session._orderbook_mgr is not None
            sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert sid is not None
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": sid, "seq": 1,
                "msg": {
                    "market_ticker": "Y", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })
            await _wait_for(
                lambda: session._orderbook_mgr.get("Y") is not None  # type: ignore[union-attr]
            )
            await session._pause_recv_loop()
            await session.unsubscribe(client_id=1)
            assert session._orderbook_mgr.get("Y") is None


# ---------------------------------------------------------------------------
# #207 — backpressure ERROR raises through iterator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBackpressureErrorThroughIterator:
    async def test_error_strategy_overflow_raises_kalshi_backpressure_error(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#207: iterator raises KalshiBackpressureError, not silent close."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_orderbook_delta(
                tickers=["T1"], maxsize=1,
            )
            assert session._sub_mgr is not None
            sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert sid is not None

            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": sid, "seq": 1,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })
            await asyncio.sleep(0.1)
            await fake_ws.send_to_all({
                "type": "orderbook_delta", "sid": sid, "seq": 2,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "price": "0.51", "delta": "10", "side": "yes",
                },
            })

            recv_task = session._recv_task
            assert recv_task is not None
            await asyncio.wait_for(recv_task, timeout=2.0)

            collected: list[object] = []
            with pytest.raises(KalshiBackpressureError):
                async for msg in stream:
                    collected.append(msg)
            assert len(collected) == 1

    async def test_clean_close_still_raises_stop_async_iteration(self) -> None:
        """Regression: a clean shutdown via put_sentinel still yields
        StopAsyncIteration (not BackpressureError)."""
        q: MessageQueue[str] = MessageQueue(maxsize=4, overflow=OverflowStrategy.ERROR)
        await q.put("a")
        await q.put_sentinel()
        collected: list[str] = []
        async for msg in q:
            collected.append(msg)
        assert collected == ["a"]

    async def test_put_error_is_idempotent_after_close(self) -> None:
        """Second put_error is a no-op; iterator still raises the first error."""
        q: MessageQueue[int] = MessageQueue(maxsize=4)
        await q.put(1)
        first = KalshiBackpressureError("first")
        second = KalshiBackpressureError("second")
        await q.put_error(first)
        await q.put_error(second)  # ignored
        await q.put_sentinel()      # also ignored (already closed)
        collected: list[int] = []
        raised: BaseException | None = None
        try:
            async for msg in q:
                collected.append(msg)
        except KalshiBackpressureError as e:
            raised = e
        assert collected == [1]
        assert raised is first  # not `second`


# ---------------------------------------------------------------------------
# #213 — raise-site kwarg population
# ---------------------------------------------------------------------------


class TestErrorContextKwargs:
    def test_seq_gap_error_includes_channel_sid_seq_kwargs(self) -> None:
        err = KalshiSequenceGapError(
            "boom", channel="orderbook_delta",
            sid=42, client_id=7, last_seq=5, next_seq=10,
        )
        assert err.channel == "orderbook_delta"
        assert err.sid == 42
        assert err.client_id == 7
        assert err.last_seq == 5
        assert err.next_seq == 10

    def test_subscription_error_includes_channel_op_kwargs(self) -> None:
        err = KalshiSubscriptionError(
            "boom", channel="ticker", client_id=3, op="subscribe",
        )
        assert err.channel == "ticker"
        assert err.client_id == 3
        assert err.op == "subscribe"


@pytest.mark.asyncio
class TestRaiseSiteKwargs:
    async def test_subscribe_error_populates_kwargs(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#213: subscribe-ack error carries channel/op context."""
        fake_ws._force_error = True
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect():
            with pytest.raises(KalshiSubscriptionError) as excinfo:
                await ws.subscribe_ticker(tickers=["T1"])
        assert excinfo.value.channel == "ticker"
        assert excinfo.value.op == "subscribe"
        assert excinfo.value.client_id is not None

    async def test_update_subscription_error_populates_kwargs(
        self, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """update_subscription on missing client_id raises with op kwarg."""
        # Stand up a connection manager but feed update_subscription a bad id.
        # We don't need the fake server for this -- only the lookup miss path.
        config = KalshiConfig(ws_base_url="ws://localhost:1")
        conn = ConnectionManager(auth=test_auth, config=config)
        mgr = SubscriptionManager(conn)
        with pytest.raises(KalshiSubscriptionError) as excinfo:
            await mgr.update_subscription(99, action="add_markets")
        assert excinfo.value.op == "update_subscription"
        assert excinfo.value.client_id == 99
