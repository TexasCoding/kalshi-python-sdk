"""Regression tests for multi-ticker orderbook_delta gap clear (#79).

A single ``orderbook_delta`` subscription can cover multiple tickers
under one sid. The gap envelope does not identify which ticker missed
an update, so the safe option is to clear EVERY ticker for the affected
subscription. Previously only ``tickers[0]`` was cleared, leaving the
other books diverged from server truth.

Determinism: scenarios drive the gap handler directly via the public
API (``session._handle_seq_gap``) so we don't race the recv loop forcing
a real gap on the wire.
"""
from __future__ import annotations

import asyncio

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.ws.backpressure import MessageQueue
from kalshi.ws.channels import Subscription
from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.orderbook import OrderbookManager
from kalshi.ws.sequence import SequenceGap, SequenceTracker


@pytest.mark.asyncio
class TestMultiTickerGapClear:
    """#79: gap on a multi-ticker orderbook_delta sub clears EVERY ticker."""

    async def test_gap_clears_all_tickers_in_sub(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """Subscribe to tickers=["A","B","C"], seed all three books via
        snapshots, then fire a gap on the shared sid -> all three books
        must be cleared (previously only "A" was cleared).
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta(
                tickers=["A", "B", "C"],
            )

            assert session._sub_mgr is not None
            assert session._orderbook_mgr is not None
            assert session._seq_tracker is not None
            sid = next(iter(session._sub_mgr.active_subscriptions.values())).server_sid
            assert sid is not None

            # Seed all three books via individual snapshots on the same sid.
            for i, ticker in enumerate(["A", "B", "C"], start=1):
                await fake_ws.send_to_all({
                    "type": "orderbook_snapshot", "sid": sid, "seq": i,
                    "msg": {
                        "market_ticker": ticker, "market_id": "x",
                        "yes": [["0.50", "100"]], "no": [],
                    },
                })

            # Wait for all three to land in the manager via an async-event
            # poll (no fixed sleep timing).
            async def all_seeded() -> bool:
                return all(
                    session._orderbook_mgr.get(t) is not None  # type: ignore[union-attr]
                    for t in ("A", "B", "C")
                )

            async with asyncio.timeout(2.0):
                while not await all_seeded():
                    await asyncio.sleep(0.01)

            # Directly invoke the gap handler — equivalent to the seq
            # tracker firing on_gap on its own. Doing it directly removes
            # any flakiness around forcing a real gap through the wire.
            await session._handle_seq_gap(
                SequenceGap(sid=sid, expected=4, received=10)
            )

            # #79: every ticker in the sub must be cleared.
            assert session._orderbook_mgr.get("A") is None, (
                "#79: A was cleared (already worked pre-fix)"
            )
            assert session._orderbook_mgr.get("B") is None, (
                "#79 regression: B's book was not cleared; only tickers[0] "
                "was cleared, leaving B diverged from server truth."
            )
            assert session._orderbook_mgr.get("C") is None, (
                "#79 regression: C's book was not cleared; only tickers[0] "
                "was cleared, leaving C diverged from server truth."
            )

            # Seq tracker is also reset for the sid.
            assert session._seq_tracker.peek(sid) is None

    async def test_single_ticker_sub_still_cleared(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """Sanity check: single-ticker case still clears the (only) ticker."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta(tickers=["SOLO"])

            assert session._sub_mgr is not None
            assert session._orderbook_mgr is not None
            sid = next(iter(session._sub_mgr.active_subscriptions.values())).server_sid
            assert sid is not None

            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": sid, "seq": 1,
                "msg": {
                    "market_ticker": "SOLO", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })

            async with asyncio.timeout(2.0):
                while session._orderbook_mgr.get("SOLO") is None:
                    await asyncio.sleep(0.01)

            await session._handle_seq_gap(
                SequenceGap(sid=sid, expected=2, received=5)
            )
            assert session._orderbook_mgr.get("SOLO") is None


@pytest.mark.asyncio
class TestGapHandlerWithoutTickers:
    """#79 edge case: an orderbook_delta sub with no market_tickers param
    (subscribe-to-all) shouldn't crash the gap handler.
    """

    async def test_no_tickers_param_does_not_raise(self) -> None:
        # We just need a KalshiWebSocket instance with the managers wired
        # up directly — no real connection.
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        auth = KalshiAuth(key_id="test", private_key=key)
        config = KalshiConfig(ws_base_url="ws://localhost:1")
        ws = KalshiWebSocket(auth=auth, config=config)

        ws._orderbook_mgr = OrderbookManager()
        ws._seq_tracker = SequenceTracker()

        # Hand-build a SubscriptionManager-shaped object with one sub.
        class _StubMgr:
            def __init__(self) -> None:
                queue: MessageQueue[object] = MessageQueue()
                self._sub = Subscription(
                    client_id=1, channel="orderbook_delta",
                    params={},  # no market_tickers
                    queue=queue,
                )
                self._sub.server_sid = 42

            def get_subscription_by_sid(self, sid: int) -> Subscription | None:
                return self._sub if sid == 42 else None

        ws._sub_mgr = _StubMgr()  # type: ignore[assignment]

        # Should not raise — no tickers to iterate, just reset seq.
        await ws._handle_seq_gap(SequenceGap(sid=42, expected=1, received=5))
