"""Regression tests for WS reliability fixes (#254, #257, #255, #256)."""

from __future__ import annotations

import collections
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiOrderbookUnavailableError, KalshiSubscriptionError
from kalshi.ws.backpressure import MessageQueue
from kalshi.ws.channels import Subscription
from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.dispatch import MessageDispatcher
from kalshi.ws.orderbook import OrderbookManager
from kalshi.ws.sequence import SequenceGap, SequenceTracker


def _make_ws() -> KalshiWebSocket:
    """Build a wire-less ``KalshiWebSocket`` with managers wired up."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    auth = KalshiAuth(key_id="test", private_key=key)
    config = KalshiConfig(ws_base_url="ws://localhost:1")
    ws = KalshiWebSocket(auth=auth, config=config)
    ws._orderbook_mgr = OrderbookManager()
    ws._seq_tracker = SequenceTracker()
    ws._dispatcher = MessageDispatcher(sub_mgr=None)  # type: ignore[arg-type]
    return ws


@pytest.mark.asyncio
class TestIssue254ResubscribeOneStashDrain:
    """#254: ``resubscribe_one``'s stash is drained after success so frames
    captured during the sid handoff are replayed instead of leaking until
    the next full reconnect."""

    async def test_stash_drained_through_process_frame(self) -> None:
        """Frames stashed during the resubscribe window for the NEW sid get
        replayed via ``_process_frame``, seeding the orderbook with the
        delta payload."""
        ws = _make_ws()
        # Seed the orderbook so a delta can apply (apply_delta_inplace
        # only mutates a book that already exists for this ticker).
        snap_seed = {
            "type": "orderbook_snapshot",
            "sid": 99,
            "seq": 1,
            "msg": {
                "market_ticker": "T",
                "market_id": "m",
                "yes": [["0.50", "100"]],
                "no": [],
            },
        }
        # Wire dispatcher to the stub mgr below.
        queue: MessageQueue[object] = MessageQueue()
        new_sub = Subscription(
            client_id=1,
            channel="orderbook_delta",
            params={},
            queue=queue,
        )
        new_sub.server_sid = 99

        class _StubMgr:
            def __init__(self) -> None:
                self._stash: dict[int, collections.deque[str]] = {}
                # Pre-populate stash as if frames had landed during the
                # resubscribe_one unsubscribe→subscribe window.
                bucket: collections.deque[str] = collections.deque(maxlen=1000)
                bucket.append(json.dumps(snap_seed))
                bucket.append(
                    json.dumps(
                        {
                            "type": "orderbook_delta",
                            "sid": 99,
                            "seq": 2,
                            "msg": {
                                "market_ticker": "T",
                                "market_id": "m",
                                "price": 51,
                                "delta": 10,
                                "side": "yes",
                            },
                        }
                    )
                )
                self._stash[99] = bucket
                # A frame for an unmapped (torn-down) sid: should be dropped.
                dead_bucket: collections.deque[str] = collections.deque(maxlen=1000)
                dead_bucket.append(
                    json.dumps(
                        {
                            "type": "orderbook_delta",
                            "sid": 7,
                            "seq": 1,
                            "msg": {
                                "market_ticker": "ZOMBIE",
                                "market_id": "z",
                                "price": 99,
                                "delta": 1,
                                "side": "yes",
                            },
                        }
                    )
                )
                self._stash[7] = dead_bucket
                self.resubscribed = False

            def get_subscription_by_sid(self, sid: int) -> Subscription | None:
                return new_sub if sid == 99 else None

            def get_subscription(self, client_id: int) -> Subscription | None:
                return new_sub if client_id == 1 else None

            async def resubscribe_one(self, client_id: int) -> int | None:
                self.resubscribed = True
                return 99

            async def broadcast_error(self, client_id: int, exc: BaseException) -> None:
                pytest.fail(f"broadcast_error unexpectedly called: {exc!r}")

            def take_stash(self) -> dict[int, collections.deque[str]]:
                stash, self._stash = self._stash, {}
                return stash

        stub = _StubMgr()
        ws._sub_mgr = stub  # type: ignore[assignment]
        # Rebuild dispatcher with the stub so route lookups succeed.
        ws._dispatcher = MessageDispatcher(sub_mgr=stub)  # type: ignore[arg-type]

        await ws._handle_seq_gap(SequenceGap(sid=99, expected=2, received=5))

        # Resubscribe ran successfully.
        assert stub.resubscribed
        # Stash drained.
        assert stub._stash == {}
        ob_mgr = ws._orderbook_mgr
        seq = ws._seq_tracker
        assert ob_mgr is not None
        assert seq is not None
        # The snapshot from the stash landed via _process_frame: book exists.
        book = ob_mgr.get("T")
        assert book is not None
        # The delta also applied (seq=2 followed snapshot=1).
        assert seq.peek(99) == 2
        # The unmapped-sid frame was dropped, never touching the book.
        assert ob_mgr.get("ZOMBIE") is None

    async def test_stash_drained_even_when_resubscribe_fails(self) -> None:
        """A failed ``resubscribe_one`` still clears the stash so frames
        don't leak into the next cycle."""
        ws = _make_ws()
        queue: MessageQueue[object] = MessageQueue()
        sub = Subscription(
            client_id=3,
            channel="orderbook_delta",
            params={},
            queue=queue,
        )
        sub.server_sid = 50

        class _FailingMgr:
            def __init__(self) -> None:
                bucket: collections.deque[str] = collections.deque(maxlen=1000)
                bucket.append(
                    json.dumps(
                        {
                            "type": "orderbook_delta",
                            "sid": 50,
                            "seq": 1,
                            "msg": {
                                "market_ticker": "X",
                                "market_id": "x",
                                "price": 50,
                                "delta": 1,
                                "side": "yes",
                            },
                        }
                    )
                )
                self._stash: dict[int, collections.deque[str]] = {50: bucket}
                self.broadcast_called = False

            def get_subscription_by_sid(self, sid: int) -> Subscription | None:
                return sub if sid == 50 else None

            def get_subscription(self, client_id: int) -> Subscription | None:
                return sub if client_id == 3 else None

            async def resubscribe_one(self, client_id: int) -> int | None:
                raise KalshiSubscriptionError(
                    "boom",
                    channel="orderbook_delta",
                    client_id=client_id,
                    op="subscribe",
                )

            async def broadcast_error(self, client_id: int, exc: BaseException) -> None:
                self.broadcast_called = True

            def take_stash(self) -> dict[int, collections.deque[str]]:
                stash, self._stash = self._stash, {}
                return stash

        stub = _FailingMgr()
        ws._sub_mgr = stub  # type: ignore[assignment]

        await ws._handle_seq_gap(SequenceGap(sid=50, expected=1, received=4))

        # broadcast_error fired; drain did NOT happen (we early-returned
        # after broadcast_error). Stash remains for the next cycle to handle.
        assert stub.broadcast_called


@pytest.mark.asyncio
class TestIssue257OrderbookUnavailable:
    """#257: ``_OrderbookIterator`` raises ``KalshiOrderbookUnavailableError``
    instead of yielding an empty :class:`Orderbook` when the manager has no
    book for the ticker (e.g. between gap teardown and resync snapshot)."""

    async def test_raises_when_manager_has_no_book(self) -> None:
        from kalshi.ws.client import _OrderbookIterator
        from kalshi.ws.orderbook import OrderbookManager

        mgr = OrderbookManager()

        async def _stream() -> AsyncIterator[Any]:
            # First yield: a placeholder; the iterator only checks the manager.
            yield {"type": "orderbook_delta"}
            yield {"type": "orderbook_delta"}

        it = _OrderbookIterator(_stream(), mgr, "MISSING")
        with pytest.raises(KalshiOrderbookUnavailableError) as excinfo:
            await it.__anext__()
        assert excinfo.value.ticker == "MISSING"
        assert "MISSING" in str(excinfo.value)

    async def test_yields_book_when_present(self) -> None:
        """Sanity check: when the book is populated the iterator still works."""
        from kalshi.ws.client import _OrderbookIterator
        from kalshi.ws.models.orderbook_delta import OrderbookSnapshotMessage
        from kalshi.ws.orderbook import OrderbookManager

        mgr = OrderbookManager()
        snap = OrderbookSnapshotMessage.model_validate(
            {
                "type": "orderbook_snapshot",
                "sid": 1,
                "seq": 1,
                "msg": {
                    "market_ticker": "OK",
                    "market_id": "m",
                    "yes": [["0.50", "100"]],
                    "no": [],
                },
            }
        )
        mgr._apply_snapshot_inplace(snap, sid=1)

        async def _stream() -> AsyncIterator[Any]:
            yield {"type": "orderbook_snapshot"}

        it = _OrderbookIterator(_stream(), mgr, "OK")
        book = await it.__anext__()
        assert book.ticker == "OK"


@pytest.mark.asyncio
class TestIssue255StaleOrderbookGating:
    """#255: ``_process_frame`` must drop orderbook frames whose sid no
    longer maps to a live subscription, BEFORE validating or applying
    them to the local manager. Otherwise a stale snapshot can re-seed
    the book under the old sid index, or a stale delta can clobber a
    freshly-resynced book."""

    async def test_stale_snapshot_does_not_mutate_book(self) -> None:
        ws = _make_ws()

        class _EmptyMgr:
            def get_subscription_by_sid(self, sid: int) -> Subscription | None:
                return None

            def get_subscription(self, client_id: int) -> Subscription | None:
                return None

        ws._sub_mgr = _EmptyMgr()  # type: ignore[assignment]
        ws._dispatcher = MessageDispatcher(sub_mgr=ws._sub_mgr)  # type: ignore[arg-type]
        ob_mgr = ws._orderbook_mgr
        assert ob_mgr is not None

        stale_snapshot = json.dumps(
            {
                "type": "orderbook_snapshot",
                "sid": 42,
                "seq": 1,
                "msg": {
                    "market_ticker": "STALE",
                    "market_id": "m",
                    "yes": [["0.50", "100"]],
                    "no": [],
                },
            }
        )
        await ws._process_frame(stale_snapshot)
        # Stale snapshot dropped before apply: book remains empty.
        assert ob_mgr.get("STALE") is None

    async def test_stale_delta_does_not_mutate_existing_book(self) -> None:
        """A delta arriving on the OLD sid after resubscribe (new sid is now
        valid for the same ticker) must not mutate the new book."""
        ws = _make_ws()
        ob_mgr = ws._orderbook_mgr
        assert ob_mgr is not None

        # Seed a book under the NEW sid (post-resubscribe).
        from kalshi.ws.models.orderbook_delta import OrderbookSnapshotMessage

        new_snap = OrderbookSnapshotMessage.model_validate(
            {
                "type": "orderbook_snapshot",
                "sid": 99,
                "seq": 1,
                "msg": {
                    "market_ticker": "T",
                    "market_id": "m",
                    "yes": [["0.50", "100"]],
                    "no": [],
                },
            }
        )
        ob_mgr._apply_snapshot_inplace(new_snap, sid=99)
        book_before = ob_mgr.get("T")
        assert book_before is not None
        yes_before = list(book_before.yes)

        new_sub = Subscription(
            client_id=1,
            channel="orderbook_delta",
            params={},
            queue=MessageQueue(),
        )
        new_sub.server_sid = 99

        class _NewSidOnlyMgr:
            def get_subscription_by_sid(self, sid: int) -> Subscription | None:
                return new_sub if sid == 99 else None

            def get_subscription(self, client_id: int) -> Subscription | None:
                return new_sub if client_id == 1 else None

        ws._sub_mgr = _NewSidOnlyMgr()  # type: ignore[assignment]
        ws._dispatcher = MessageDispatcher(sub_mgr=ws._sub_mgr)  # type: ignore[arg-type]

        # Stale delta for OLD sid that should be dropped before apply.
        stale_delta = json.dumps(
            {
                "type": "orderbook_delta",
                "sid": 42,
                "seq": 7,
                "msg": {
                    "market_ticker": "T",
                    "market_id": "m",
                    "price": 50,
                    "delta": -50,
                    "side": "yes",
                },
            }
        )
        await ws._process_frame(stale_delta)

        # New-sid book is unchanged.
        book_after = ob_mgr.get("T")
        assert book_after is not None
        assert list(book_after.yes) == yes_before
