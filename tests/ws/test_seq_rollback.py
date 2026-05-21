"""Regression tests for seq-rollback on pre-validation failure (#241).

#241: a malformed sequenced frame (ValidationError, KeyError, ...) must
NOT advance the seq watermark — otherwise the next legitimate frame's
seq matches the (over-advanced) expected value and gap detection
silently skips, leaving the local orderbook desynced from the server.

These tests drive the fake server end-to-end so the actual
`_recv_loop` + `_process_frame` interaction is exercised, not a mocked
shape. Determinism: poll on observable state with bounded wait_for
rather than fixed sleeps.
"""
from __future__ import annotations

import asyncio

import pytest

from kalshi.config import KalshiConfig
from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.sequence import SequenceGap


@pytest.mark.asyncio
class TestValidationErrorDoesNotAdvanceSeq:
    """#241: ValidationError on sequenced frame must roll back the watermark."""

    async def test_malformed_orderbook_delta_keeps_watermark(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """Snapshot seq=1, malformed delta seq=2, good delta seq=3.

        With the bug: seq=2's track() advanced last_seq to 2 BEFORE the
        ValidationError raised, so seq=3 == expected and gap detection
        never fires. The local orderbook is now silently desynced.

        With the fix: ValidationError rolls last_seq back to 1, so seq=3
        > expected=2 triggers a forward gap and the resync handler runs.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            # Capture gaps WITHOUT triggering the real resubscribe machinery
            # (would race the test for sids and resubscribe acks).
            gaps: list[SequenceGap] = []

            async def capture(gap: SequenceGap) -> None:
                gaps.append(gap)

            assert session._seq_tracker is not None
            session._seq_tracker._on_gap = capture

            await session.subscribe_orderbook_delta(
                tickers=["T1"], maxsize=100,
            )
            assert session._sub_mgr is not None
            sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert sid is not None

            # 1. Clean snapshot, seq=1.
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": sid, "seq": 1,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })

            async def snapshot_landed() -> None:
                while session._seq_tracker.peek(sid) != 1:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(snapshot_landed(), timeout=2.0)

            # 2. Malformed delta seq=2 — bad `side` fails the Literal check.
            await fake_ws.send_to_all({
                "type": "orderbook_delta", "sid": sid, "seq": 2,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "price": "0.51", "delta": "10", "side": "invalid",
                },
            })

            # 3. Good delta seq=3. Without #241 fix, last_seq is already 2
            # so seq=3 == expected — no gap, silent desync. With the fix,
            # last_seq is still 1 → expected=2, received=3 → forward gap.
            await fake_ws.send_to_all({
                "type": "orderbook_delta", "sid": sid, "seq": 3,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "price": "0.52", "delta": "5", "side": "yes",
                },
            })

            async def gap_fired() -> None:
                while not gaps:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(gap_fired(), timeout=2.0)

            assert len(gaps) == 1, (
                "#241 regression: malformed sequenced frame silently "
                "advanced the seq watermark; next legitimate frame's "
                "gap was missed."
            )
            gap = gaps[0]
            assert gap.sid == sid
            assert gap.kind == "gap"
            assert gap.expected == 2
            assert gap.received == 3

    async def test_malformed_order_group_update_keeps_watermark(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """Same shape for order_group_updates — dispatch-layer mirror (#241).

        order_group_updates is sequenced but validated inside the
        dispatcher (no orderbook pre-validation), so the dispatcher
        must propagate the ValidationError up to `_process_frame` for
        rollback. Previously the dispatcher swallowed it -> silent
        seq advance.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            gaps: list[SequenceGap] = []

            async def capture(gap: SequenceGap) -> None:
                gaps.append(gap)

            assert session._seq_tracker is not None
            session._seq_tracker._on_gap = capture

            await session._do_subscribe(
                "order_group_updates", params={}, maxsize=100,
            )
            assert session._sub_mgr is not None
            sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert sid is not None

            # First good message, seq=1 — establishes the watermark.
            # OrderGroupMessage requires `msg` with a typed payload; send a
            # minimal-but-valid envelope.
            await fake_ws.send_to_all({
                "type": "order_group_updates", "sid": sid, "seq": 1,
                "msg": {
                    "event_type": "created",
                    "order_group_id": "g1",
                    "ts_ms": 1700000000000,
                },
            })

            async def first_landed() -> None:
                while session._seq_tracker.peek(sid) != 1:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(first_landed(), timeout=2.0)

            # Malformed seq=2 — wrong `msg` shape (string where dict expected).
            await fake_ws.send_to_all({
                "type": "order_group_updates", "sid": sid, "seq": 2,
                "msg": "garbage-not-a-dict",
            })

            # Good seq=3 — should trigger gap detection iff seq=2 didn't
            # advance the watermark.
            await fake_ws.send_to_all({
                "type": "order_group_updates", "sid": sid, "seq": 3,
                "msg": {
                    "event_type": "limit_updated",
                    "order_group_id": "g1",
                    "ts_ms": 1700000000001,
                },
            })

            async def gap_fired() -> None:
                while not gaps:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(gap_fired(), timeout=2.0)

            assert len(gaps) == 1
            assert gaps[0].expected == 2
            assert gaps[0].received == 3
