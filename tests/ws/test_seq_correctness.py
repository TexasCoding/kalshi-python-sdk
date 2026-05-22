"""Regression tests for WS seq-tracker correctness (#78).

#78: ERROR-overflow backpressure must not silently advance the seq
watermark past a dropped message.

Determinism: scenarios drive the seq tracker via the public API so we
don't rely on asyncio.sleep to race the recv loop. For the end-to-end
backpressure test, we await ``session._recv_task`` — the recv loop
completes once dispatch raises BackpressureError, no sleep required.
"""
from __future__ import annotations

import asyncio

import pytest

from kalshi.config import KalshiConfig
from kalshi.errors import KalshiBackpressureError
from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.sequence import SequenceTracker


@pytest.mark.asyncio
class TestSequenceTrackerRollback:
    """#78: peek + rollback let callers undo a track() that downstream rejected."""

    async def test_peek_returns_none_for_unknown_sid(self) -> None:
        tracker = SequenceTracker()
        assert tracker.peek(42) is None

    async def test_peek_returns_last_seq(self) -> None:
        tracker = SequenceTracker()
        await tracker.track(1, 5, "orderbook_delta")
        assert tracker.peek(1) == 5

    async def test_rollback_restores_prior_seq(self) -> None:
        tracker = SequenceTracker()
        await tracker.track(1, 5, "orderbook_delta")
        prev = tracker.peek(1)
        await tracker.track(1, 6, "orderbook_delta")
        assert tracker.peek(1) == 6
        tracker.rollback(1, prev)
        assert tracker.peek(1) == 5

    async def test_rollback_to_none_removes_entry(self) -> None:
        tracker = SequenceTracker()
        # First message ever; prev is None.
        prev = tracker.peek(1)
        await tracker.track(1, 1, "orderbook_delta")
        assert tracker.peek(1) == 1
        tracker.rollback(1, prev)
        assert tracker.peek(1) is None
        # And the next track is treated as the first message again.
        assert await tracker.track(1, 1, "orderbook_delta") is True


@pytest.mark.asyncio
class TestBackpressureDoesNotAdvanceSeq:
    """#78 end-to-end: ERROR-overflow on a full queue must not advance _last_seq."""

    async def test_dropped_delta_keeps_seq_watermark_unchanged(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """ERROR-strategy queue at maxsize -> send N+1 messages -> tracker's
        last_seq reflects only successfully-landed messages.

        Setup: subscribe with maxsize=1, send snapshot (seq=1) — lands in
        queue. Send delta (seq=2) — backpressure raises. The recv loop
        exits via sentinel broadcast. Tracker's last_seq for the sid must
        still be 1, not 2.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_orderbook_delta(
                tickers=["T1"], maxsize=1,
            )

            assert session._sub_mgr is not None
            assert session._seq_tracker is not None
            sid = next(iter(session._sub_mgr.active_subscriptions.values())).server_sid
            assert sid is not None

            # Snapshot fills the queue (maxsize=1).
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": sid, "seq": 1,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })
            # Deterministic wait: poll the seq tracker until it observes the
            # snapshot, bounded by wait_for. Avoids CI flakes under load.
            async def snapshot_landed() -> None:
                while session._seq_tracker.peek(sid) != 1:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(snapshot_landed(), timeout=2.0)

            assert session._seq_tracker.peek(sid) == 1

            # This delta overflows -> BackpressureError -> recv loop tears
            # down via sentinel broadcast.
            await fake_ws.send_to_all({
                "type": "orderbook_delta", "sid": sid, "seq": 2,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "price": "0.51", "delta": "10", "side": "yes",
                },
            })

            recv_task = session._recv_task
            assert recv_task is not None
            # #332: the recv loop now clears manager refs on
            # ``KalshiBackpressureError`` teardown (close the WS and reset
            # state so the next subscribe doesn't resurrect a dead session).
            # Snapshot the tracker BEFORE awaiting the task so we can still
            # validate the #78 invariant on the now-detached object.
            seq_tracker = session._seq_tracker
            await asyncio.wait_for(recv_task, timeout=2.0)

            # #78: the seq watermark MUST still be 1, not 2. If it were 2,
            # a post-reconnect message with seq=2 would be treated as a
            # duplicate (silent desync); a message with seq=3 would not
            # be detected as a gap.
            assert seq_tracker.peek(sid) == 1, (
                "#78 regression: ERROR-overflow advanced last_seq past a "
                "dropped message; orderbook is now silently desynced."
            )

            # #207: iterator now raises KalshiBackpressureError after the
            # snapshot lands. Previously the iterator exited silently with
            # StopAsyncIteration — indistinguishable from a clean shutdown.
            collected: list[object] = []
            with pytest.raises(KalshiBackpressureError):
                async for msg in stream:
                    collected.append(msg)
            assert len(collected) == 1  # only the snapshot landed
