"""End-to-end integration tests for WebSocket client.

These tests exercise the full stack: ConnectionManager, SubscriptionManager,
MessageDispatcher, SequenceTracker, OrderbookManager, and KalshiWebSocket
all wired together against the FakeKalshiWS test server.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.connection import ConnectionState
from kalshi.ws.models.base import ErrorMessage
from kalshi.ws.sequence import SequenceGap

from .conftest import FakeKalshiWS


@pytest.fixture
def ws_config(fake_ws: FakeKalshiWS) -> KalshiConfig:
    """Config pointing at the fake WS server with fast retry."""
    return KalshiConfig(
        ws_base_url=fake_ws.url,
        timeout=5.0,
        retry_base_delay=0.01,
        retry_max_delay=0.05,
        ws_max_retries=3,
    )


# ---------------------------------------------------------------------------
# 1. Full trading bot flow: connect -> subscribe ticker -> receive typed msgs
# ---------------------------------------------------------------------------


class TestIntegrationTickerFlow:
    async def test_subscribe_and_receive_ticker(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Full flow: connect, subscribe, receive typed message."""
        ws = KalshiWebSocket(auth=test_auth, config=ws_config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["ECON-GDP-25Q1"])

            await fake_ws.send_to_all({
                "type": "ticker",
                "sid": 1,
                "msg": {
                    "market_ticker": "ECON-GDP-25Q1",
                    "market_id": "x",
                    "yes_bid": 55,
                    "yes_ask": 58,
                },
            })

            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.type == "ticker"
            assert msg.msg.market_ticker == "ECON-GDP-25Q1"
            assert msg.msg.yes_bid == 55
            assert msg.msg.yes_ask == 58

    async def test_multiple_ticker_updates(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Receive multiple ticker updates in sequence."""
        ws = KalshiWebSocket(auth=test_auth, config=ws_config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])

            for price in [50, 55, 60]:
                await fake_ws.send_to_all({
                    "type": "ticker",
                    "sid": 1,
                    "msg": {"market_ticker": "T1", "market_id": "x", "yes_bid": price},
                })

            received: list[Any] = []
            for _ in range(3):
                msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
                received.append(msg.msg.yes_bid)

            assert received == [50, 55, 60]


# ---------------------------------------------------------------------------
# 2. Orderbook lifecycle: snapshot initializes, delta updates
# ---------------------------------------------------------------------------


class TestIntegrationOrderbook:
    async def test_orderbook_snapshot_and_delta(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Orderbook: snapshot initializes, delta updates local book state."""
        ws = KalshiWebSocket(auth=test_auth, config=ws_config)
        async with ws.connect() as session:
            stream = await session.orderbook("T1")

            # Server sends snapshot: yes side has two levels
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot",
                "sid": 1,
                "seq": 1,
                "msg": {
                    "market_ticker": "T1",
                    "market_id": "x",
                    "yes": [[50, 100], [55, 200]],
                    "no": [],
                },
            })

            book = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert book.ticker == "T1"
            assert len(book.yes) == 2
            # 100 cents = $1.00
            assert book.yes[0].quantity == Decimal("1.00")
            # 200 cents = $2.00
            assert book.yes[1].quantity == Decimal("2.00")

            # Server sends delta: add 50 cents to price level 50
            await fake_ws.send_to_all({
                "type": "orderbook_delta",
                "sid": 1,
                "seq": 2,
                "msg": {
                    "market_ticker": "T1",
                    "market_id": "x",
                    "price": 50,
                    "delta": 50,
                    "side": "yes",
                },
            })

            book2 = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            # 100 + 50 = 150 cents = $1.50
            assert book2.yes[0].quantity == Decimal("1.50")

    async def test_orderbook_delta_removes_level(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Delta that brings quantity to zero removes the level."""
        ws = KalshiWebSocket(auth=test_auth, config=ws_config)
        async with ws.connect() as session:
            stream = await session.orderbook("T1")

            # Snapshot with one yes level of 100 cents
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot",
                "sid": 1,
                "seq": 1,
                "msg": {
                    "market_ticker": "T1",
                    "market_id": "x",
                    "yes": [[50, 100]],
                    "no": [],
                },
            })
            book = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert len(book.yes) == 1

            # Delta: subtract 100 cents (removes level)
            await fake_ws.send_to_all({
                "type": "orderbook_delta",
                "sid": 1,
                "seq": 2,
                "msg": {
                    "market_ticker": "T1",
                    "market_id": "x",
                    "price": 50,
                    "delta": -100,
                    "side": "yes",
                },
            })
            book2 = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert len(book2.yes) == 0


# ---------------------------------------------------------------------------
# 3. Multi-channel: ticker AND fill on the same connection
# ---------------------------------------------------------------------------


class TestIntegrationMultiChannel:
    async def test_two_channels_same_connection(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Multiple channels on the same connection work independently."""
        ws = KalshiWebSocket(auth=test_auth, config=ws_config)
        async with ws.connect() as session:
            ticker_stream = await session.subscribe_ticker(tickers=["T1"])
            fill_stream = await session.subscribe_fill()

            # Ticker goes to sid=1, fill goes to sid=2
            await fake_ws.send_to_all({
                "type": "ticker",
                "sid": 1,
                "msg": {
                    "market_ticker": "T1",
                    "market_id": "x",
                    "yes_bid": 50,
                },
            })
            await fake_ws.send_to_all({
                "type": "fill",
                "sid": 2,
                "msg": {"trade_id": "t1", "order_id": "o1"},
            })

            ticker_msg = await asyncio.wait_for(
                ticker_stream.__anext__(), timeout=2.0,
            )
            fill_msg = await asyncio.wait_for(
                fill_stream.__anext__(), timeout=2.0,
            )

            assert ticker_msg.msg.market_ticker == "T1"
            assert ticker_msg.msg.yes_bid == 50
            assert fill_msg.msg.trade_id == "t1"
            assert fill_msg.msg.order_id == "o1"

    async def test_three_channels(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Three channels on the same connection all receive independently."""
        ws = KalshiWebSocket(auth=test_auth, config=ws_config)
        async with ws.connect() as session:
            ticker_stream = await session.subscribe_ticker(tickers=["T1"])
            fill_stream = await session.subscribe_fill()
            trade_stream = await session.subscribe_trade(tickers=["T1"])

            await fake_ws.send_to_all({
                "type": "ticker",
                "sid": 1,
                "msg": {"market_ticker": "T1", "market_id": "x", "yes_bid": 42},
            })
            await fake_ws.send_to_all({
                "type": "fill",
                "sid": 2,
                "msg": {"trade_id": "f1", "order_id": "o1"},
            })
            await fake_ws.send_to_all({
                "type": "trade",
                "sid": 3,
                "msg": {"trade_id": "tr1", "market_ticker": "T1"},
            })

            t = await asyncio.wait_for(ticker_stream.__anext__(), timeout=2.0)
            f = await asyncio.wait_for(fill_stream.__anext__(), timeout=2.0)
            tr = await asyncio.wait_for(trade_stream.__anext__(), timeout=2.0)

            assert t.msg.yes_bid == 42
            assert f.msg.trade_id == "f1"
            assert tr.msg.trade_id == "tr1"


# ---------------------------------------------------------------------------
# 4. Disconnect / reconnect
# ---------------------------------------------------------------------------


class TestIntegrationReconnect:
    async def test_reconnect_after_server_disconnect(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Client auto-reconnects after server forces a disconnect.

        Flow: connect -> subscribe -> server disconnects after 1 broadcast
        -> client reconnects -> resubscribes -> receives new messages.
        """
        fake_ws.disconnect_after = 1  # Close after first broadcast

        ws = KalshiWebSocket(auth=test_auth, config=ws_config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])

            # First message triggers disconnect_after
            await fake_ws.send_to_all({
                "type": "ticker",
                "sid": 1,
                "msg": {"market_ticker": "T1", "market_id": "x", "yes_bid": 50},
            })

            # Read the first message
            msg1 = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg1.msg.yes_bid == 50

            # Wait for reconnect + resubscribe to complete
            # The recv_loop detects the closed connection, reconnects, and resubscribes
            await asyncio.sleep(1.0)

            # Disable disconnect_after for subsequent messages
            fake_ws.disconnect_after = None
            fake_ws._msg_count = 0

            # After reconnect, server assigns new sids starting from where it left off
            # Resubscribe gets a new sid. Find the latest sid.
            latest_sid = (
                max(fake_ws.subscriptions.keys())
                if fake_ws.subscriptions
                else 1
            )

            await fake_ws.send_to_all({
                "type": "ticker",
                "sid": latest_sid,
                "msg": {"market_ticker": "T1", "market_id": "x", "yes_bid": 75},
            })

            msg2 = await asyncio.wait_for(stream.__anext__(), timeout=3.0)
            assert msg2.msg.yes_bid == 75


# ---------------------------------------------------------------------------
# 5. Sequence gap detection
# ---------------------------------------------------------------------------


class TestIntegrationSequenceGap:
    async def test_gap_detection_fires_callback(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Sequence gap: server sends seq 1, 2, 5 (skipping 3, 4)."""
        gaps: list[SequenceGap] = []

        async def on_gap(gap: SequenceGap) -> None:
            gaps.append(gap)

        ws = KalshiWebSocket(auth=test_auth, config=ws_config)
        async with ws.connect() as session:
            # Override the gap handler
            assert session._seq_tracker is not None
            session._seq_tracker._on_gap = on_gap

            stream = await session.subscribe_orderbook_delta(tickers=["T1"])

            # Send snapshot (seq=1)
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot",
                "sid": 1,
                "seq": 1,
                "msg": {
                    "market_ticker": "T1",
                    "market_id": "x",
                    "yes": [[50, 100]],
                    "no": [],
                },
            })
            await asyncio.wait_for(stream.__anext__(), timeout=2.0)

            # Send seq=2 (OK)
            await fake_ws.send_to_all({
                "type": "orderbook_delta",
                "sid": 1,
                "seq": 2,
                "msg": {
                    "market_ticker": "T1",
                    "market_id": "x",
                    "price": 50,
                    "delta": 10,
                    "side": "yes",
                },
            })
            await asyncio.wait_for(stream.__anext__(), timeout=2.0)

            # Send seq=5 (skip 3, 4 -> gap!)
            await fake_ws.send_to_all({
                "type": "orderbook_delta",
                "sid": 1,
                "seq": 5,
                "msg": {
                    "market_ticker": "T1",
                    "market_id": "x",
                    "price": 55,
                    "delta": 20,
                    "side": "yes",
                },
            })
            await asyncio.wait_for(stream.__anext__(), timeout=2.0)

            # Give recv loop time to invoke the gap callback
            await asyncio.sleep(0.1)

            assert len(gaps) == 1
            assert gaps[0].sid == 1
            assert gaps[0].expected == 3
            assert gaps[0].received == 5


# ---------------------------------------------------------------------------
# 6. Callback + iterator coexistence
# ---------------------------------------------------------------------------


class TestIntegrationCallbackAndIterator:
    async def test_callback_and_iterator_coexist(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Iterator for ticker, callback for fill -- both receive messages."""
        ws = KalshiWebSocket(auth=test_auth, config=ws_config)
        callback_received: list[object] = []

        async with ws.connect() as session:
            # Register callback for fill BEFORE subscribing
            @session.on("fill")
            async def on_fill(msg: object) -> None:
                callback_received.append(msg)

            # Subscribe to ticker via iterator
            ticker_stream = await session.subscribe_ticker(tickers=["T1"])
            # Subscribe to fill (callback will intercept, not the queue)
            await session.subscribe_fill()

            # Send ticker (goes to iterator queue)
            await fake_ws.send_to_all({
                "type": "ticker",
                "sid": 1,
                "msg": {"market_ticker": "T1", "market_id": "x", "yes_bid": 55},
            })
            # Send fill (goes to callback)
            await fake_ws.send_to_all({
                "type": "fill",
                "sid": 2,
                "msg": {"trade_id": "t1", "order_id": "o1"},
            })

            # Read ticker from iterator
            ticker_msg = await asyncio.wait_for(
                ticker_stream.__anext__(), timeout=2.0,
            )
            assert ticker_msg.msg.market_ticker == "T1"
            assert ticker_msg.msg.yes_bid == 55

            # Wait for callback to fire
            await asyncio.sleep(0.3)
            assert len(callback_received) == 1


# ---------------------------------------------------------------------------
# 7. Graceful shutdown
# ---------------------------------------------------------------------------


class TestIntegrationShutdown:
    async def test_graceful_shutdown_stops_iterators(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Exiting async-with closes connection and stops iterators."""
        ws = KalshiWebSocket(auth=test_auth, config=ws_config)

        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])
            # Session is active, send a message to prove it works
            await fake_ws.send_to_all({
                "type": "ticker",
                "sid": 1,
                "msg": {"market_ticker": "T1", "market_id": "x", "yes_bid": 42},
            })
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.yes_bid == 42
            # Context manager exit happens here

        # After exit, the connection should be closed
        assert ws._connection is not None
        assert ws._connection.state == ConnectionState.CLOSED

        # Sentinel was pushed; iteration should stop immediately
        items: list[object] = []
        async for item in stream:
            items.append(item)
        assert items == []

    async def test_shutdown_cancels_recv_loop(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Recv loop task is cancelled on shutdown."""
        ws = KalshiWebSocket(auth=test_auth, config=ws_config)
        async with ws.connect() as session:
            await session.subscribe_ticker(tickers=["T1"])
            assert session._recv_task is not None
            assert not session._recv_task.done()

        # After context exit, recv task should be done
        assert ws._recv_task is None or ws._recv_task.done()


# ---------------------------------------------------------------------------
# 8. Error message from server
# ---------------------------------------------------------------------------


class TestIntegrationErrorCallback:
    async def test_error_message_triggers_callback(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Server error message fires the on_error callback."""
        errors: list[ErrorMessage] = []

        async def on_error(err: ErrorMessage) -> None:
            errors.append(err)

        ws = KalshiWebSocket(
            auth=test_auth, config=ws_config, on_error=on_error,
        )
        async with ws.connect() as session:
            # Subscribe to start the recv loop
            await session.subscribe_ticker(tickers=["T1"])

            await fake_ws.send_to_all({
                "type": "error",
                "id": 0,
                "msg": {"code": 5, "msg": "something went wrong"},
            })

            await asyncio.sleep(0.3)
            assert len(errors) == 1
            assert errors[0].msg.code == 5
            assert errors[0].msg.msg == "something went wrong"

    async def test_error_without_callback_does_not_crash(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Server error message with no on_error callback is handled gracefully."""
        ws = KalshiWebSocket(auth=test_auth, config=ws_config)  # no on_error
        async with ws.connect() as session:
            await session.subscribe_ticker(tickers=["T1"])

            await fake_ws.send_to_all({
                "type": "error",
                "id": 0,
                "msg": {"code": 99, "msg": "ignored error"},
            })

            # Should not crash; just ignored. Verify recv loop is still alive.
            await fake_ws.send_to_all({
                "type": "ticker",
                "sid": 1,
                "msg": {"market_ticker": "T1", "market_id": "x", "yes_bid": 30},
            })
            # Wait a bit then check recv loop is still operational
            await asyncio.sleep(0.2)


# ---------------------------------------------------------------------------
# State tracking integration
# ---------------------------------------------------------------------------


class TestIntegrationStateTracking:
    async def test_state_transitions_during_session(
        self,
        fake_ws: FakeKalshiWS,
        test_auth: KalshiAuth,
        ws_config: KalshiConfig,
    ) -> None:
        """Track state transitions through a full session lifecycle."""
        states: list[tuple[ConnectionState, ConnectionState]] = []

        async def on_state(
            old: ConnectionState, new: ConnectionState,
        ) -> None:
            states.append((old, new))

        ws = KalshiWebSocket(
            auth=test_auth, config=ws_config, on_state_change=on_state,
        )
        async with ws.connect() as session:
            # Should have transitioned to CONNECTED
            assert any(new == ConnectionState.CONNECTED for _, new in states)
            await session.subscribe_ticker(tickers=["T1"])

        # After exit, should be CLOSED
        assert any(new == ConnectionState.CLOSED for _, new in states)
