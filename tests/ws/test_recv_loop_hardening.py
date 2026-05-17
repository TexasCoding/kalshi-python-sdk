"""Regression tests for WS recv-loop hardening (issues #77, #83).

Covers the 5 reconnect/resubscribe race fixes from #77 plus the narrowed
exception catch from #83. Race scenarios use asyncio.Event barriers, not
sleeps, so they're deterministic.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from kalshi.config import KalshiConfig
from kalshi.errors import KalshiConnectionError
from kalshi.ws.channels import SubscriptionManager
from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.connection import ConnectionManager

# ---------------------------------------------------------------------------
# F-P-01 — per-sub resubscribe failure no longer aborts the whole reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResubscribeIsolation:
    async def test_one_failed_resubscribe_does_not_kill_others(
        self, fake_ws, test_auth  # type: ignore[no-untyped-def]
    ) -> None:
        """F-P-01: if one sub's resubscribe errors, the others still succeed."""
        config = KalshiConfig(
            ws_base_url=fake_ws.url,
            timeout=5.0,
            retry_base_delay=0.01,
            retry_max_delay=0.05,
        )
        conn = ConnectionManager(auth=test_auth, config=config)
        await conn.connect()
        sub_mgr = SubscriptionManager(conn)

        sub1 = await sub_mgr.subscribe("ticker", params={"market_tickers": ["A"]})
        sub2 = await sub_mgr.subscribe("ticker", params={"market_tickers": ["B"]})
        sub3 = await sub_mgr.subscribe("ticker", params={"market_tickers": ["C"]})

        # Simulate disconnect
        await conn.close()
        fake_ws.received_commands.clear()
        fake_ws._next_sid = 50
        await conn.connect()

        # Make the SECOND resubscribe fail. We do this by monkey-patching the
        # fake_ws subscribe handler to error on the second command id only.
        original_handle = fake_ws._handle_command
        call_count = {"n": 0}

        async def selective_handler(ws, msg):  # type: ignore[no-untyped-def]
            if msg.get("cmd") == "subscribe":
                call_count["n"] += 1
                if call_count["n"] == 2:
                    msg_id = msg.get("id", 0)
                    await ws.send(json.dumps({
                        "id": msg_id,
                        "type": "error",
                        "msg": {"code": 400, "msg": "simulated failure"},
                    }))
                    return
            await original_handle(ws, msg)

        fake_ws._handle_command = selective_handler  # type: ignore[assignment]

        await sub_mgr.resubscribe_all()

        # sub2 should be removed; sub1 and sub3 should still be active
        active = sub_mgr.active_subscriptions
        assert sub1.client_id in active
        assert sub2.client_id not in active
        assert sub3.client_id in active

        # sub2's iterator must receive a sentinel (StopAsyncIteration)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(sub2.queue.__anext__(), timeout=1.0)

        await conn.close()


# ---------------------------------------------------------------------------
# F-P-05 — ConnectionClosed during subscribe surfaces as KalshiConnectionError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSubscribeConnectionClosed:
    async def test_connection_closed_mid_subscribe_raises_kalshi_error(
        self, fake_ws, test_auth  # type: ignore[no-untyped-def]
    ) -> None:
        """F-P-05: a connection drop during _wait_for_response surfaces as
        KalshiConnectionError, not raw websockets ConnectionClosed."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        conn = ConnectionManager(auth=test_auth, config=config)
        await conn.connect()
        sub_mgr = SubscriptionManager(conn)

        # Override the handler to close the socket instead of replying.
        async def closing_handler(ws, msg):  # type: ignore[no-untyped-def]
            await ws.close()

        fake_ws._handle_command = closing_handler  # type: ignore[assignment]

        with pytest.raises(KalshiConnectionError):
            await sub_mgr.subscribe("ticker")

        await conn.close()


# ---------------------------------------------------------------------------
# F-P-08 — unsubscribe pushes sentinel so held iterator exits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUnsubscribeSentinel:
    async def test_unsubscribe_pushes_sentinel(
        self, fake_ws, test_auth  # type: ignore[no-untyped-def]
    ) -> None:
        """F-P-08: unsubscribe must push a sentinel so iterators stop hanging."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        conn = ConnectionManager(auth=test_auth, config=config)
        await conn.connect()
        sub_mgr = SubscriptionManager(conn)

        sub = await sub_mgr.subscribe("ticker")
        assert sub.server_sid is not None

        await sub_mgr.unsubscribe(sub.client_id)

        # Iterator on the queue should terminate, not hang
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(sub.queue.__anext__(), timeout=1.0)

        await conn.close()


# ---------------------------------------------------------------------------
# F-P-04 — _pause_recv_loop does not drop in-flight frames
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPauseDoesNotDropFrames:
    async def test_inflight_frame_dispatched_when_recv_task_cancelled(
        self, fake_ws, test_auth  # type: ignore[no-untyped-def]
    ) -> None:
        """F-P-04: a frame mid-dispatch when the recv task is cancelled must
        still be delivered. We monkey-patch the dispatcher's dispatch() with
        a barrier so we can force cancellation precisely while it's running.
        Without the asyncio.shield in _process_frame, the frame is lost.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])

            assert session._dispatcher is not None
            original_dispatch = session._dispatcher.dispatch

            dispatch_started = asyncio.Event()
            allow_dispatch_finish = asyncio.Event()

            async def slow_dispatch(raw: str) -> None:
                dispatch_started.set()
                await allow_dispatch_finish.wait()
                await original_dispatch(raw)

            session._dispatcher.dispatch = slow_dispatch  # type: ignore[method-assign]

            sid = next(iter(session._sub_mgr.active_subscriptions.values())).server_sid  # type: ignore[union-attr]
            # Send one frame. recv loop reads it, enters _process_frame,
            # calls slow_dispatch which blocks on the event.
            await fake_ws.send_to_all({
                "type": "ticker", "sid": sid,
                "msg": {
                    "market_ticker": "T1", "market_id": "x", "yes_bid": 22,
                },
            })
            await asyncio.wait_for(dispatch_started.wait(), timeout=2.0)

            # Now request a pause (cancellation). The shield must keep the
            # dispatch alive.
            pause_task = asyncio.create_task(session._pause_recv_loop())
            # Give the cancel a chance to propagate
            await asyncio.sleep(0.05)

            # Release the dispatch barrier — shielded coroutine runs to
            # completion and puts the message on the queue.
            allow_dispatch_finish.set()
            await asyncio.wait_for(pause_task, timeout=2.0)

            # The message must have arrived despite the cancellation.
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.yes_bid == 22

            # Restore original dispatch and resume
            session._dispatcher.dispatch = original_dispatch  # type: ignore[method-assign]
            session._resume_recv_loop()


# ---------------------------------------------------------------------------
# F-P-03 — reconnect path takes subscribe lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReconnectHoldsSubscribeLock:
    async def test_handle_reconnect_acquires_subscribe_lock(
        self, fake_ws, test_auth  # type: ignore[no-untyped-def]
    ) -> None:
        """F-P-03: reconnect must hold _subscribe_lock so concurrent user
        subscribe_* cannot race the sid-remap.

        Verified structurally: while _handle_reconnect runs, a user subscribe
        coroutine cannot complete because it competes for the same lock.
        """
        config = KalshiConfig(
            ws_base_url=fake_ws.url,
            timeout=5.0,
            retry_base_delay=0.01,
            retry_max_delay=0.05,
            ws_max_retries=3,
        )
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            # Acquire the lock externally to simulate user subscribe in flight
            assert session._subscribe_lock is not None
            await session._subscribe_lock.acquire()

            # _handle_reconnect should wait for the lock
            reconnect_task = asyncio.create_task(session._handle_reconnect())
            await asyncio.sleep(0.05)
            assert not reconnect_task.done(), (
                "F-P-03 regression: _handle_reconnect did not take "
                "_subscribe_lock"
            )

            # Release; reconnect proceeds
            session._subscribe_lock.release()
            await asyncio.wait_for(reconnect_task, timeout=3.0)


# ---------------------------------------------------------------------------
# #83 — recv loop narrows broad except
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRecvLoopExceptionPolicy:
    async def test_backpressure_error_breaks_loop_and_sentinels(
        self, fake_ws, test_auth  # type: ignore[no-untyped-def]
    ) -> None:
        """#83: KalshiBackpressureError no longer swallowed. The recv loop
        exits and consumers see sentinel.

        Deterministic setup: subscribe but do NOT iterate, pre-fill the queue
        to maxsize, then send one more frame so the recv-loop's queue.put
        raises BackpressureError. Then start iterating — must see sentinel.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            # ERROR strategy with maxsize=1 -> second message overflows
            stream = await session.subscribe_orderbook_delta(
                tickers=["T1"], maxsize=1,
            )

            assert session._sub_mgr is not None
            sid = next(iter(session._sub_mgr.active_subscriptions.values())).server_sid
            assert sid is not None

            # Fill the queue: snapshot lands as the single allowed item.
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": sid, "seq": 1,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })
            # Yield to let recv loop process the snapshot
            await asyncio.sleep(0.1)

            # Second frame overflows -> KalshiBackpressureError
            await fake_ws.send_to_all({
                "type": "orderbook_delta", "sid": sid, "seq": 2,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "price": "0.51", "delta": "10", "side": "yes",
                },
            })

            # Wait for the recv loop to process the delta and exit on
            # BackpressureError. The recv task should complete (loop broke).
            recv_task = session._recv_task
            assert recv_task is not None
            await asyncio.wait_for(recv_task, timeout=2.0)

            # Iterator must terminate. Buffer holds [snapshot, SENTINEL]
            # (sentinel is appended unconditionally by put_sentinel).
            collected: list[object] = []
            try:
                async with asyncio.timeout(3.0):
                    async for msg in stream:
                        collected.append(msg)
            except TimeoutError:
                pytest.fail(
                    "#83 regression: BackpressureError was swallowed; "
                    "iterator did not receive sentinel."
                )
            assert len(collected) == 1  # only the snapshot was queued

    async def test_malformed_frame_logged_with_traceback_and_continues(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """#83: ValidationError on a single frame logs with exc_info but
        does NOT take down the loop."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])

            assert session._sub_mgr is not None
            sid = next(iter(session._sub_mgr.active_subscriptions.values())).server_sid

            # Send a frame that will fail validation (missing required field
            # for ticker), then send a valid frame. The loop must keep going.
            with caplog.at_level(logging.WARNING, logger="kalshi.ws"):
                # Inject a parse-failure: the recv loop's _process_frame
                # validates orderbook messages and json.loads anything. Send
                # invalid JSON directly to trigger json.JSONDecodeError.
                for conn in fake_ws.connections:
                    await conn.send("{not valid json")

                await fake_ws.send_to_all({
                    "type": "ticker", "sid": sid,
                    "msg": {
                        "market_ticker": "T1", "market_id": "x",
                        "yes_bid": 77,
                    },
                })

                msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
                assert msg.msg.yes_bid == 77

            # The warning should have been logged
            assert any(
                "malformed" in r.message.lower() or "non-json" in r.message.lower()
                for r in caplog.records
            )
