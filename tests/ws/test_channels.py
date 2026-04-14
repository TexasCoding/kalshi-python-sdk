"""Tests for SubscriptionManager."""

from __future__ import annotations

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
    async def test_update_subscription_not_found_raises(
        self, sub_mgr: SubscriptionManager
    ) -> None:
        with pytest.raises(KalshiSubscriptionError):
            await sub_mgr.update_subscription(999, "add_markets", market_tickers=["T"])

    async def test_update_subscription_sends_command(
        self, sub_mgr: SubscriptionManager, fake_ws  # type: ignore[no-untyped-def]
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
        self, fake_ws, test_auth  # type: ignore[no-untyped-def]
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
        self, fake_ws, test_auth  # type: ignore[no-untyped-def]
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
        self, fake_ws, test_auth  # type: ignore[no-untyped-def]
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
        self, sub_mgr: SubscriptionManager, fake_ws  # type: ignore[no-untyped-def]
    ) -> None:
        await sub_mgr.subscribe("ticker")
        await sub_mgr.subscribe("fill")
        ids = [c["id"] for c in fake_ws.received_commands]
        assert ids == [1, 2]
