"""Regression tests for multi-ticker orderbook_delta gap clear (#79, #189).

A single ``orderbook_delta`` subscription can cover multiple tickers
under one sid. The gap envelope does not identify which ticker missed
an update, so the safe option is to clear EVERY ticker for the affected
subscription. Previously only ``tickers[0]`` was cleared, leaving the
other books diverged from server truth (#79). Since #189 the handler
also drives a real resubscribe; these tests pause the recv loop before
invoking the handler so its inner ``_wait_for_response`` doesn't race
the live recv task on ``connection.recv()``.

Determinism: scenarios drive the gap handler directly via the public
API (``session._handle_seq_gap``) so we don't race the recv loop forcing
a real gap on the wire.
"""
from __future__ import annotations

import asyncio
import collections

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiSubscriptionError
from kalshi.ws.backpressure import MessageQueue
from kalshi.ws.channels import Subscription
from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.orderbook import OrderbookManager
from kalshi.ws.sequence import SequenceGap, SequenceTracker


@pytest.mark.asyncio
class TestMultiTickerGapClear:
    """#79/#189: gap on a multi-ticker orderbook_delta sub clears every ticker
    AND drives a resubscribe to refetch the snapshot.
    """

    async def test_gap_clears_all_tickers_in_sub(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """Subscribe to tickers=["A","B","C"], seed all three books via
        snapshots, then fire a gap on the shared sid -> all three books
        must be cleared and the subscription resubscribed.
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
            old_sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert old_sid is not None

            # Seed all three books via individual snapshots on the same sid.
            for i, ticker in enumerate(["A", "B", "C"], start=1):
                await fake_ws.send_to_all({
                    "type": "orderbook_snapshot", "sid": old_sid, "seq": i,
                    "msg": {
                        "market_ticker": ticker, "market_id": "x",
                        "yes": [["0.50", "100"]], "no": [],
                    },
                })

            async def all_seeded() -> bool:
                return all(
                    session._orderbook_mgr.get(t) is not None  # type: ignore[union-attr]
                    for t in ("A", "B", "C")
                )

            async with asyncio.timeout(2.0):
                while not await all_seeded():
                    await asyncio.sleep(0.01)

            # Pause the recv loop so resubscribe_one can own connection.recv()
            # without racing the background task. In production the gap
            # handler fires from inside the recv loop's frame-processing path
            # so there is no concurrency issue; the direct-call test must
            # simulate that quiescence explicitly.
            await session._pause_recv_loop()
            await session._handle_seq_gap(
                SequenceGap(sid=old_sid, expected=4, received=10)
            )

            # All three books cleared via remove_by_sid.
            assert session._orderbook_mgr.get("A") is None
            assert session._orderbook_mgr.get("B") is None
            assert session._orderbook_mgr.get("C") is None
            # Seq tracker is also reset for the old sid.
            assert session._seq_tracker.peek(old_sid) is None
            # #189: resubscribe issued; subscription has a new sid (fake_ws
            # increments sids monotonically).
            sub = session._sub_mgr.get_subscription(1)
            assert sub is not None
            assert sub.server_sid is not None
            assert sub.server_sid != old_sid

    async def test_single_ticker_sub_still_cleared(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """Single-ticker case still clears the (only) ticker and resubscribes."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta(tickers=["SOLO"])

            assert session._sub_mgr is not None
            assert session._orderbook_mgr is not None
            old_sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert old_sid is not None

            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": old_sid, "seq": 1,
                "msg": {
                    "market_ticker": "SOLO", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })

            async with asyncio.timeout(2.0):
                while session._orderbook_mgr.get("SOLO") is None:
                    await asyncio.sleep(0.01)

            await session._pause_recv_loop()
            await session._handle_seq_gap(
                SequenceGap(sid=old_sid, expected=2, received=5)
            )
            assert session._orderbook_mgr.get("SOLO") is None


@pytest.mark.asyncio
class TestGapHandlerWithoutTickers:
    """#79/#189 edge case: an orderbook_delta sub with no market_tickers param
    (subscribe-to-all) shouldn't crash the gap handler.
    """

    async def test_no_tickers_param_does_not_raise(self) -> None:
        # KalshiWebSocket instance with the managers wired up directly — no
        # real connection. Stubbed _sub_mgr exposes only the subset of
        # SubscriptionManager methods the gap handler uses.
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        auth = KalshiAuth(key_id="test", private_key=key)
        config = KalshiConfig(ws_base_url="ws://localhost:1")
        ws = KalshiWebSocket(auth=auth, config=config)

        ws._orderbook_mgr = OrderbookManager()
        ws._seq_tracker = SequenceTracker()

        class _StubMgr:
            def __init__(self) -> None:
                queue: MessageQueue[object] = MessageQueue()
                self._sub = Subscription(
                    client_id=1, channel="orderbook_delta",
                    params={},  # no market_tickers
                    queue=queue,
                )
                self._sub.server_sid = 42
                self.resubscribe_called = False
                self.broadcast_called = False

            def get_subscription_by_sid(self, sid: int) -> Subscription | None:
                return self._sub if sid == 42 else None

            def get_subscription(self, client_id: int) -> Subscription | None:
                return self._sub if client_id == self._sub.client_id else None

            async def resubscribe_one(self, client_id: int) -> int | None:
                self.resubscribe_called = True
                # Simulate a successful resubscribe with a fresh sid.
                self._sub.server_sid = 99
                return 99

            async def broadcast_error(
                self, client_id: int, exc: BaseException
            ) -> None:
                self.broadcast_called = True

            def take_stash(self) -> dict[int, collections.deque[str]]:
                return {}

        stub = _StubMgr()
        ws._sub_mgr = stub  # type: ignore[assignment]

        await ws._handle_seq_gap(SequenceGap(sid=42, expected=1, received=5))
        assert stub.resubscribe_called
        assert not stub.broadcast_called

    async def test_resubscribe_failure_broadcasts_error(self) -> None:
        """If resubscribe_one raises KalshiSubscriptionError, the gap handler
        surfaces it to the consumer iterator via broadcast_error (#189/#207)."""
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        auth = KalshiAuth(key_id="test", private_key=key)
        config = KalshiConfig(ws_base_url="ws://localhost:1")
        ws = KalshiWebSocket(auth=auth, config=config)
        ws._orderbook_mgr = OrderbookManager()
        ws._seq_tracker = SequenceTracker()

        class _FailingMgr:
            def __init__(self) -> None:
                queue: MessageQueue[object] = MessageQueue()
                self._sub = Subscription(
                    client_id=7, channel="orderbook_delta",
                    params={}, queue=queue,
                )
                self._sub.server_sid = 11
                self.broadcast_args: tuple[int, BaseException] | None = None

            def get_subscription_by_sid(self, sid: int) -> Subscription | None:
                return self._sub if sid == 11 else None

            def get_subscription(self, client_id: int) -> Subscription | None:
                return self._sub if client_id == 7 else None

            async def resubscribe_one(self, client_id: int) -> int | None:
                raise KalshiSubscriptionError(
                    "boom", channel="orderbook_delta",
                    client_id=client_id, op="subscribe",
                )

            async def broadcast_error(
                self, client_id: int, exc: BaseException
            ) -> None:
                self.broadcast_args = (client_id, exc)

            def take_stash(self) -> dict[int, collections.deque[str]]:
                return {}

        stub = _FailingMgr()
        ws._sub_mgr = stub  # type: ignore[assignment]

        await ws._handle_seq_gap(SequenceGap(sid=11, expected=5, received=10))
        assert stub.broadcast_args is not None
        cid, exc = stub.broadcast_args
        assert cid == 7
        from kalshi.errors import KalshiSequenceGapError
        assert isinstance(exc, KalshiSequenceGapError)
        assert exc.channel == "orderbook_delta"
        assert exc.sid == 11
        assert exc.client_id == 7
        assert exc.last_seq == 4
        assert exc.next_seq == 10
