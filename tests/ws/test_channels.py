"""Tests for SubscriptionManager."""

from __future__ import annotations

import collections
import json
import logging

import pytest

from kalshi.config import KalshiConfig
from kalshi.errors import KalshiSubscriptionError
from kalshi.ws.backpressure import MessageQueue, OverflowStrategy
from kalshi.ws.channels import Subscription, SubscriptionManager
from kalshi.ws.connection import ConnectionManager


@pytest.fixture
async def connected_mgr(fake_ws, test_auth):  # type: ignore[no-untyped-def]
    """A connected ConnectionManager against the fake server."""
    config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
    mgr = ConnectionManager(auth=test_auth, config=config)
    await mgr.connect()
    yield mgr
    await mgr.close()


@pytest.fixture
def sub_mgr(connected_mgr):  # type: ignore[no-untyped-def]
    return SubscriptionManager(connected_mgr)


# ---------------------------------------------------------------------------
# Subscription model
# ---------------------------------------------------------------------------


class TestSubscription:
    def test_to_subscribe_params_basic(self) -> None:
        queue: MessageQueue[object] = MessageQueue(maxsize=10)
        sub = Subscription(
            client_id=1,
            channel="ticker",
            params={"market_tickers": ["ABC-YES"]},
            queue=queue,
        )
        result = sub.to_subscribe_params()
        assert result == {"channels": ["ticker"], "market_tickers": ["ABC-YES"]}

    def test_to_subscribe_params_no_extra(self) -> None:
        queue: MessageQueue[object] = MessageQueue(maxsize=10)
        sub = Subscription(client_id=1, channel="fill", params={}, queue=queue)
        result = sub.to_subscribe_params()
        assert result == {"channels": ["fill"]}

    def test_to_subscribe_params_all_keys(self) -> None:
        queue: MessageQueue[object] = MessageQueue(maxsize=10)
        params = {
            "market_ticker": "T1",
            "market_tickers": ["T1", "T2"],
            "market_id": "id1",
            "market_ids": ["id1", "id2"],
            "shard_factor": 2,
            "shard_key": "k",
            "send_initial_snapshot": True,
            "skip_ticker_ack": True,
        }
        sub = Subscription(client_id=1, channel="orderbook_delta", params=params, queue=queue)
        result = sub.to_subscribe_params()
        assert result["channels"] == ["orderbook_delta"]
        assert result["market_ticker"] == "T1"
        assert result["market_tickers"] == ["T1", "T2"]
        assert result["shard_factor"] == 2
        assert result["send_initial_snapshot"] is True

    def test_initial_server_sid_is_none(self) -> None:
        queue: MessageQueue[object] = MessageQueue(maxsize=10)
        sub = Subscription(client_id=1, channel="ticker", params={}, queue=queue)
        assert sub.server_sid is None


# ---------------------------------------------------------------------------
# SubscriptionManager — subscribe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSubscribe:
    async def test_subscribe_returns_subscription(self, sub_mgr: SubscriptionManager) -> None:
        sub = await sub_mgr.subscribe("ticker", params={"market_tickers": ["T1"]})
        assert sub.client_id == 1
        assert sub.channel == "ticker"
        assert sub.server_sid is not None

    async def test_subscribe_assigns_sequential_client_ids(
        self, sub_mgr: SubscriptionManager
    ) -> None:
        sub1 = await sub_mgr.subscribe("ticker")
        sub2 = await sub_mgr.subscribe("fill")
        assert sub1.client_id == 1
        assert sub2.client_id == 2

    async def test_subscribe_stores_in_active(self, sub_mgr: SubscriptionManager) -> None:
        sub = await sub_mgr.subscribe("ticker")
        assert sub_mgr.get_subscription(sub.client_id) is sub

    async def test_subscribe_creates_default_queue(self, sub_mgr: SubscriptionManager) -> None:
        sub = await sub_mgr.subscribe("ticker")
        assert sub.queue is not None
        assert isinstance(sub.queue, MessageQueue)


# ---------------------------------------------------------------------------
# SubscriptionManager — custom queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCustomQueue:
    async def test_custom_queue_is_used(self, sub_mgr: SubscriptionManager) -> None:
        queue: MessageQueue[object] = MessageQueue(maxsize=50, overflow=OverflowStrategy.ERROR)
        sub = await sub_mgr.subscribe("orderbook_delta", queue=queue)
        assert sub.queue is queue


# ---------------------------------------------------------------------------
# SubscriptionManager — unsubscribe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUnsubscribe:
    async def test_unsubscribe_removes_subscription(self, sub_mgr: SubscriptionManager) -> None:
        sub = await sub_mgr.subscribe("ticker")
        await sub_mgr.unsubscribe(sub.client_id)
        assert sub_mgr.get_subscription(sub.client_id) is None

    async def test_unsubscribe_clears_sid_mapping(self, sub_mgr: SubscriptionManager) -> None:
        sub = await sub_mgr.subscribe("ticker")
        server_sid = sub.server_sid
        assert server_sid is not None
        await sub_mgr.unsubscribe(sub.client_id)
        assert sub_mgr.get_subscription_by_sid(server_sid) is None

    async def test_unsubscribe_unknown_id_is_noop(self, sub_mgr: SubscriptionManager) -> None:
        # Should not raise
        await sub_mgr.unsubscribe(999)


# ---------------------------------------------------------------------------
# SubscriptionManager — lookup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLookup:
    async def test_get_subscription_by_sid(self, sub_mgr: SubscriptionManager) -> None:
        sub = await sub_mgr.subscribe("ticker")
        found = sub_mgr.get_subscription_by_sid(sub.server_sid)  # type: ignore[arg-type]
        assert found is not None
        assert found.client_id == sub.client_id

    async def test_get_subscription_by_unknown_sid(self, sub_mgr: SubscriptionManager) -> None:
        assert sub_mgr.get_subscription_by_sid(999) is None

    async def test_active_subscriptions(self, sub_mgr: SubscriptionManager) -> None:
        await sub_mgr.subscribe("ticker")
        await sub_mgr.subscribe("fill")
        active = sub_mgr.active_subscriptions
        assert len(active) == 2
        # Should be a copy
        active[999] = None  # type: ignore[assignment]
        assert len(sub_mgr.active_subscriptions) == 2


# ---------------------------------------------------------------------------
# SubscriptionManager — update_subscription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpdateSubscription:
    async def test_update_subscription_not_found_raises(self, sub_mgr: SubscriptionManager) -> None:
        with pytest.raises(KalshiSubscriptionError):
            await sub_mgr.update_subscription(999, "add_markets", market_tickers=["T"])

    async def test_update_subscription_sends_command(
        self,
        sub_mgr: SubscriptionManager,
        fake_ws,  # type: ignore[no-untyped-def]
    ) -> None:
        sub = await sub_mgr.subscribe("ticker")
        await sub_mgr.update_subscription(
            sub.client_id,
            "add_markets",
            market_tickers=["T2"],
        )
        # Find the update_subscription command in the fake server's received commands
        update_cmds = [
            c for c in fake_ws.received_commands if c.get("cmd") == "update_subscription"
        ]
        assert len(update_cmds) == 1
        assert update_cmds[0]["params"]["sids"] == [sub.server_sid]
        assert update_cmds[0]["params"]["action"] == "add_markets"
        assert update_cmds[0]["params"]["market_tickers"] == ["T2"]


# ---------------------------------------------------------------------------
# SubscriptionManager — resubscribe_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResubscribeAll:
    async def test_resubscribe_all_after_reconnect(
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """Simulate reconnect: subscribe, disconnect, reconnect, resubscribe."""
        config = KalshiConfig(
            ws_base_url=fake_ws.url,
            timeout=5.0,
            retry_base_delay=0.01,
            retry_max_delay=0.05,
        )
        conn = ConnectionManager(auth=test_auth, config=config)
        await conn.connect()
        sub_mgr = SubscriptionManager(conn)

        # Subscribe to 2 channels
        sub1 = await sub_mgr.subscribe("ticker")
        sub2 = await sub_mgr.subscribe("fill")
        old_sid1 = sub1.server_sid
        old_sid2 = sub2.server_sid

        # Simulate disconnect + reconnect
        await conn.close()
        fake_ws._next_sid = 100  # Server assigns new sids
        await conn.connect()

        # Resubscribe
        await sub_mgr.resubscribe_all()

        # Client IDs should be the same
        assert sub1.client_id == 1
        assert sub2.client_id == 2
        # Server sids should be NEW
        assert sub1.server_sid != old_sid1
        assert sub2.server_sid != old_sid2
        assert sub1.server_sid is not None
        assert sub2.server_sid is not None
        # Lookup by new sid should work
        assert sub_mgr.get_subscription_by_sid(sub1.server_sid) is sub1
        assert sub_mgr.get_subscription_by_sid(sub2.server_sid) is sub2
        # Old sids should NOT work
        assert sub_mgr.get_subscription_by_sid(old_sid1) is None  # type: ignore[arg-type]
        assert sub_mgr.get_subscription_by_sid(old_sid2) is None  # type: ignore[arg-type]

        await conn.close()

    async def test_resubscribe_empty_is_noop(self, sub_mgr: SubscriptionManager) -> None:
        """Resubscribing with no active subscriptions does nothing."""
        await sub_mgr.resubscribe_all()
        assert len(sub_mgr.active_subscriptions) == 0

    async def test_resubscribe_orderbook_gets_snapshot(
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """orderbook_delta channels get send_initial_snapshot on resubscribe."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        conn = ConnectionManager(auth=test_auth, config=config)
        await conn.connect()
        sub_mgr = SubscriptionManager(conn)

        await sub_mgr.subscribe("orderbook_delta", params={"market_tickers": ["T1"]})

        # Disconnect + reconnect
        await conn.close()
        fake_ws._next_sid = 50
        fake_ws.received_commands.clear()
        await conn.connect()

        await sub_mgr.resubscribe_all()

        # Find the resubscribe command
        sub_cmds = [c for c in fake_ws.received_commands if c.get("cmd") == "subscribe"]
        assert len(sub_cmds) == 1
        assert sub_cmds[0]["params"]["send_initial_snapshot"] is True

        await conn.close()


# ---------------------------------------------------------------------------
# SubscriptionManager — subscribe error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSubscribeError:
    async def test_subscribe_error_response_raises(
        self,
        fake_ws,
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """When the server returns an error response, subscribe should raise."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        conn = ConnectionManager(auth=test_auth, config=config)
        await conn.connect()

        # Override the handler to return an error
        fake_ws._force_error = True
        sub_mgr = SubscriptionManager(conn)

        with pytest.raises(KalshiSubscriptionError):
            await sub_mgr.subscribe("bad_channel")

        await conn.close()


# ---------------------------------------------------------------------------
# SubscriptionManager — msg_id auto-increment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMsgIdAutoIncrement:
    async def test_msg_ids_are_sequential(
        self,
        sub_mgr: SubscriptionManager,
        fake_ws,  # type: ignore[no-untyped-def]
    ) -> None:
        await sub_mgr.subscribe("ticker")
        await sub_mgr.subscribe("fill")
        ids = [c["id"] for c in fake_ws.received_commands]
        assert ids == [1, 2]


# ---------------------------------------------------------------------------
# SubscriptionManager — resubscribe-window stash (#176)
# ---------------------------------------------------------------------------


class TestResubscribeStash:
    def test_maybe_stash_collects_by_sid(
        self, sub_mgr: SubscriptionManager
    ) -> None:
        """Frames carrying a sid land in the per-sid deque in arrival order."""
        sub_mgr._maybe_stash('{"sid": 1, "seq": 1}', {"sid": 1, "seq": 1})
        sub_mgr._maybe_stash('{"sid": 2, "seq": 1}', {"sid": 2, "seq": 1})
        sub_mgr._maybe_stash('{"sid": 1, "seq": 2}', {"sid": 1, "seq": 2})
        assert set(sub_mgr._stash.keys()) == {1, 2}
        assert list(sub_mgr._stash[1]) == [
            '{"sid": 1, "seq": 1}',
            '{"sid": 1, "seq": 2}',
        ]
        assert list(sub_mgr._stash[2]) == ['{"sid": 2, "seq": 1}']

    def test_maybe_stash_drops_frame_without_sid(
        self, sub_mgr: SubscriptionManager
    ) -> None:
        """Control envelopes without a sid have nowhere to replay to — drop."""
        sub_mgr._maybe_stash('{"type": "ok"}', {"type": "ok"})
        assert sub_mgr._stash == {}

    def test_maybe_stash_maxlen_evicts_oldest_with_one_warning_per_fill(
        self, connected_mgr, caplog  # type: ignore[no-untyped-def]
    ) -> None:
        """Per-sid deque is bounded; on overflow, oldest evicts and EXACTLY
        ONE WARNING fires per (sid, resubscribe cycle) — not one per frame
        (#187 review fix). Without the per-sid gate, every append after the
        deque fills would log, producing per-frame spam on high-volume
        channels during a prolonged stall."""
        mgr = SubscriptionManager(connected_mgr, stash_maxlen=3)
        with caplog.at_level(logging.WARNING, logger="kalshi.ws"):
            for i in range(10):
                mgr._maybe_stash(f'{{"sid": 7, "seq": {i}}}', {"sid": 7, "seq": i})
        bucket = mgr._stash[7]
        # maxlen=3 → only the last 3 survive (oldest 0..6 evicted)
        assert len(bucket) == 3
        assert [json.loads(r)["seq"] for r in bucket] == [7, 8, 9]
        # EXACTLY one WARNING for sid 7 across 10 appends.
        warns = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "Stash for sid 7 is full" in r.message
        ]
        assert len(warns) == 1
        # take_stash() clears the warning suppression so the next cycle
        # gets fresh warnings.
        mgr.take_stash()
        with caplog.at_level(logging.WARNING, logger="kalshi.ws"):
            for i in range(10, 15):
                mgr._maybe_stash(f'{{"sid": 7, "seq": {i}}}', {"sid": 7, "seq": i})
        warns2 = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "Stash for sid 7 is full" in r.message
        ]
        # Two cycles → two warnings total (the original + one for the new fill).
        assert len(warns2) == 2

    def test_take_stash_returns_and_clears(
        self, sub_mgr: SubscriptionManager
    ) -> None:
        """take_stash atomically returns the current stash and resets to empty."""
        sub_mgr._maybe_stash('{"sid": 9, "seq": 1}', {"sid": 9, "seq": 1})
        sub_mgr._maybe_stash('{"sid": 9, "seq": 2}', {"sid": 9, "seq": 2})
        taken = sub_mgr.take_stash()
        assert list(taken[9]) == [
            '{"sid": 9, "seq": 1}',
            '{"sid": 9, "seq": 2}',
        ]
        assert sub_mgr._stash == {}
        # Second take is empty
        assert sub_mgr.take_stash() == {}

    def test_stashing_flag_off_by_default(
        self, sub_mgr: SubscriptionManager
    ) -> None:
        """_wait_for_response only stashes when explicitly toggled by
        resubscribe_all (or future opt-in callers). Default is off so
        normal subscribe paths don't accumulate stale state."""
        assert sub_mgr._stashing is False

    async def test_resubscribe_clears_stale_stash_at_start(
        self,
        sub_mgr: SubscriptionManager,
        fake_ws,  # type: ignore[no-untyped-def]
    ) -> None:
        """#187 review: if a prior resubscribe raised before take_stash()
        ran, _stash + _stash_warned could survive into the next cycle and
        replay stale frames or muddy overflow warnings. resubscribe_all
        now defensively clears both at the start.

        Simulates the leak by injecting stale stash state, then runs a
        clean resubscribe (no active subs → loop body skipped, but the
        clear runs)."""
        # Inject stale state from a hypothetical prior cycle that failed
        # before draining.
        sub_mgr._stash[42] = collections.deque(['{"sid": 42, "stale": true}'])
        sub_mgr._stash_warned.add(42)
        assert sub_mgr._stash != {}
        assert sub_mgr._stash_warned == {42}

        await sub_mgr.resubscribe_all()

        # Stash + warned-set are both empty regardless of what the
        # subscriptions loop did.
        assert sub_mgr._stash == {}
        assert sub_mgr._stash_warned == set()
