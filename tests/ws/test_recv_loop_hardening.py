"""Regression tests for WS recv-loop hardening (issues #77, #83).

Covers the 5 reconnect/resubscribe race fixes from #77 plus the narrowed
exception catch from #83. Race scenarios use asyncio.Event barriers, not
sleeps, so they're deterministic.
"""

from __future__ import annotations

import asyncio
import collections
import json
import logging
from decimal import Decimal
from typing import Any

import pytest

from kalshi.config import KalshiConfig
from kalshi.errors import KalshiConnectionError
from kalshi.ws.channels import SubscriptionManager
from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.connection import ConnectionManager
from tests._model_fixtures import ticker_payload_dict

# ---------------------------------------------------------------------------
# F-P-01 — per-sub resubscribe failure no longer aborts the whole reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResubscribeIsolation:
    async def test_one_failed_resubscribe_does_not_kill_others(
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
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
                    await ws.send(
                        json.dumps(
                            {
                                "id": msg_id,
                                "type": "error",
                                "msg": {"code": 400, "msg": "simulated failure"},
                            }
                        )
                    )
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
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
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
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
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
    async def test_inflight_frame_dispatched_when_pause_requested(
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """F-P-04: a frame mid-dispatch when pause is requested must still
        be delivered. Pre-#245 this was enforced by an ``asyncio.shield``
        wrapping every frame; post-#245 the recv loop only sets
        ``_pause_granted`` at the top-of-loop checkpoint, so
        ``_pause_recv_loop`` cooperatively waits for the in-flight frame
        to finish before returning — no shield, no per-frame Task.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])

            assert session._dispatcher is not None
            original_dispatch = session._dispatcher.dispatch

            dispatch_started = asyncio.Event()
            allow_dispatch_finish = asyncio.Event()

            async def slow_dispatch(
                data: dict[str, Any],
                *,
                pre_validated: Any = None,
            ) -> None:
                dispatch_started.set()
                await allow_dispatch_finish.wait()
                await original_dispatch(data, pre_validated=pre_validated)

            session._dispatcher.dispatch = slow_dispatch  # type: ignore[method-assign]

            sid = next(iter(session._sub_mgr.active_subscriptions.values())).server_sid  # type: ignore[union-attr]
            # Send one frame. recv loop reads it, enters _process_frame,
            # calls slow_dispatch which blocks on the event.
            await fake_ws.send_to_all(
                {
                    "type": "ticker",
                    "sid": sid,
                    "msg": ticker_payload_dict(market_ticker="T1", yes_bid_dollars="22"),
                }
            )
            await asyncio.wait_for(dispatch_started.wait(), timeout=2.0)

            # Now request a pause cooperatively. ``_pause_recv_loop`` must
            # block until the recv loop reaches its safe checkpoint, which
            # cannot happen until ``slow_dispatch`` returns.
            pause_task = asyncio.create_task(session._pause_recv_loop())
            # Give the pause request a chance to propagate.
            await asyncio.sleep(0.05)
            assert not pause_task.done(), (
                "#245: pause must wait for the in-flight frame to finish "
                "dispatching before being granted"
            )

            # Release the dispatch barrier — process_frame returns, recv
            # loop reaches the safe checkpoint, pause is granted.
            allow_dispatch_finish.set()
            await asyncio.wait_for(pause_task, timeout=2.0)

            # The message must have arrived despite the cancellation.
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.yes_bid == 22

            # Restore original dispatch and resume
            session._dispatcher.dispatch = original_dispatch  # type: ignore[method-assign]
            session._ensure_recv_loop()


# ---------------------------------------------------------------------------
# F-P-03 — reconnect path takes subscribe lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReconnectHoldsSubscribeLock:
    async def test_handle_reconnect_acquires_subscribe_lock(
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
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

            # Deterministic: yield until reconnect_task is parked on the lock
            # (lock._waiters is non-empty). Bounded by wait_for so a regression
            # where _handle_reconnect doesn't take the lock fails loudly within
            # 2s rather than passing vacuously after a fixed sleep.
            async def wait_for_lock_contention() -> None:
                while not session._subscribe_lock._waiters:  # type: ignore[attr-defined]
                    await asyncio.sleep(0)

            await asyncio.wait_for(wait_for_lock_contention(), timeout=2.0)
            assert not reconnect_task.done(), (
                "F-P-03 regression: _handle_reconnect did not take _subscribe_lock"
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
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
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
                tickers=["T1"],
                maxsize=1,
            )

            assert session._sub_mgr is not None
            sid = next(iter(session._sub_mgr.active_subscriptions.values())).server_sid
            assert sid is not None

            # Fill the queue: snapshot lands as the single allowed item.
            await fake_ws.send_to_all(
                {
                    "type": "orderbook_snapshot",
                    "sid": sid,
                    "seq": 1,
                    "msg": {
                        "market_ticker": "T1",
                        "market_id": "x",
                        "yes": [["0.50", "100"]],
                        "no": [],
                    },
                }
            )
            # Yield to let recv loop process the snapshot
            await asyncio.sleep(0.1)

            # Second frame overflows -> KalshiBackpressureError
            await fake_ws.send_to_all(
                {
                    "type": "orderbook_delta",
                    "sid": sid,
                    "seq": 2,
                    "msg": {
                        "market_ticker": "T1",
                        "market_id": "x",
                        "price": "0.51",
                        "delta": "10",
                        "side": "yes",
                    },
                }
            )

            # Wait for the recv loop to process the delta and exit on
            # BackpressureError. The recv task should complete (loop broke).
            recv_task = session._recv_task
            assert recv_task is not None
            await asyncio.wait_for(recv_task, timeout=2.0)

            # #207: iterator yields the snapshot, then raises
            # KalshiBackpressureError so the consumer can distinguish data
            # loss from a clean shutdown. Previously the error was
            # swallowed and the iterator exited with StopAsyncIteration.
            from kalshi.errors import KalshiBackpressureError
            collected: list[object] = []
            try:
                async with asyncio.timeout(3.0):
                    with pytest.raises(KalshiBackpressureError):
                        async for msg in stream:
                            collected.append(msg)
            except TimeoutError:
                pytest.fail(
                    "#83 regression: iterator did not terminate after "
                    "BackpressureError."
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

                await fake_ws.send_to_all(
                    {
                        "type": "ticker",
                        "sid": sid,
                        "msg": ticker_payload_dict(market_ticker="T1", yes_bid_dollars="77"),
                    }
                )

                msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
                assert msg.msg.yes_bid == 77

            # The warning should have been logged
            assert any(
                "malformed" in r.message.lower() or "non-json" in r.message.lower()
                for r in caplog.records
            )

    async def test_unexpected_exception_broadcasts_sentinels_before_raising(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """#83 escape hatch: a TypeError/AttributeError/etc. from inside
        dispatch (e.g. a buggy user callback) must broadcast sentinels to
        every consumer before propagating so iterators don't hang.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])
            assert session._sub_mgr is not None
            sid = next(iter(session._sub_mgr.active_subscriptions.values())).server_sid

            # Monkey-patch dispatch to raise an unexpected exception class
            # (AttributeError is neither in the JSON/Validation/Key bucket
            # nor in the KalshiBackpressure/Subscription bucket).
            async def boom(_data: dict[str, Any], **_kw: Any) -> None:
                raise AttributeError("simulated user-callback bug")

            session._dispatcher.dispatch = boom  # type: ignore[method-assign]

            with caplog.at_level(logging.ERROR, logger="kalshi.ws"):
                await fake_ws.send_to_all(
                    {
                        "type": "ticker",
                        "sid": sid,
                        "msg": ticker_payload_dict(market_ticker="T1", yes_bid_dollars="1"),
                    }
                )

                # Iterator must see sentinel (StopAsyncIteration) within timeout.
                with pytest.raises(StopAsyncIteration):
                    await asyncio.wait_for(stream.__anext__(), timeout=2.0)

            assert any("Unexpected error in recv loop" in r.message for r in caplog.records)
            # Recv task is in failed state (we re-raised after sentinel).
            recv_task = session._recv_task
            assert recv_task is not None
            assert recv_task.done()
            assert isinstance(recv_task.exception(), AttributeError)


# ---------------------------------------------------------------------------
# #176 — resubscribe-window stash: data frames sent before subscribe ack
# are stashed by sid and replayed after the new sid mapping lands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResubscribeStashIntegration:
    async def test_stash_drain_replays_through_dispatch(
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#176: a frame stashed by sid during resubscribe must replay
        through `_process_frame` → dispatch so the iterator receives it
        and the seq tracker treats it as the natural first frame on the
        new sid (no spurious gap on the next live frame).

        Directly exercises `_drain_resubscribe_stash` rather than racing
        a real server: race timing is hardware-dependent and the value
        is the post-drain dispatch path, not the race detector itself.
        Other tests in this file already exercise the close→reconnect→
        resubscribe pipeline.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])
            assert session._sub_mgr is not None
            sub = next(iter(session._sub_mgr.active_subscriptions.values()))
            sid = sub.server_sid
            assert sid is not None

            # Inject a stashed frame for the live sid, then drain.
            stashed_frame = json.dumps({
                "type": "ticker",
                "sid": sid,
                "seq": 1,
                "msg": ticker_payload_dict(
                    market_ticker="T1",
                    market_id="m1",
                    yes_bid_dollars="0.4500",
                ),
            })
            session._sub_mgr._stash[sid] = collections.deque([stashed_frame])

            await session._drain_resubscribe_stash()

            # The replayed frame reached the iterator queue.
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.market_ticker == "T1"
            assert msg.msg.yes_bid == Decimal("0.4500")
            # Stash is empty after drain.
            assert session._sub_mgr._stash == {}

    async def test_stash_drain_advances_seq_tracker_on_sequenced_channels(
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#176 + #139: a stashed orderbook_delta frame must advance the
        seq tracker via the normal `_process_frame → seq_tracker.track`
        path, so the next live frame on the same sid (seq+1) doesn't
        trip a spurious gap.

        Without the drain going through `_process_frame`, the seq tracker
        would never see the stashed seq, and the first live frame after
        resubscribe would look like a gap from seq 0 → seq 2.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_orderbook_delta(tickers=["T1"])
            assert session._sub_mgr is not None
            sub = next(iter(session._sub_mgr.active_subscriptions.values()))
            sid = sub.server_sid
            assert sid is not None

            # Inject a stashed snapshot (seq=1) for the live sid.
            stashed_frame = json.dumps({
                "type": "orderbook_snapshot",
                "sid": sid,
                "seq": 1,
                "msg": {
                    "market_ticker": "T1",
                    "market_id": "m1",
                    "yes": [["0.50", "100"]],
                    "no": [],
                },
            })
            session._sub_mgr._stash[sid] = collections.deque([stashed_frame])

            await session._drain_resubscribe_stash()

            # Replay drained the frame to the iterator…
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.market_ticker == "T1"
            # …and advanced the seq tracker watermark, so seq=2 on the
            # next live frame won't look like a gap from 0 -> 2.
            assert session._seq_tracker is not None
            assert session._seq_tracker.peek(sid) == 1

    async def test_resubscribe_stash_skips_unmapped_sids(
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
        caplog,
    ) -> None:
        """If a sub fails during resubscribe (no new sid mapped), any
        frames stashed under a sid that the server did emit but that's
        no longer in `_sid_to_client` get dropped with a debug log
        rather than crashing the drain or routing to nowhere."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_ticker(tickers=["T1"])
            assert session._sub_mgr is not None

            # Pre-populate the stash with a frame for an unknown sid as
            # if resubscribe had captured it but the sub failed.
            session._sub_mgr._stash[999] = collections.deque(
                ['{"type": "ticker", "sid": 999, "seq": 1, "msg": {}}']
            )

            with caplog.at_level(logging.DEBUG, logger="kalshi.ws"):
                await session._drain_resubscribe_stash()

            # Stash is cleared.
            assert session._sub_mgr._stash == {}
            # Drop was logged.
            assert any(
                "Dropping 1 stashed frames for unmapped sid 999" in r.message
                for r in caplog.records
            )
