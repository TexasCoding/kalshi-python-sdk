"""Tests for KalshiWebSocket client."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from kalshi.config import KalshiConfig
from kalshi.errors import KalshiSubscriptionError
from kalshi.ws.client import KalshiWebSocket, _WebSocketSession
from kalshi.ws.connection import ConnectionState
from tests._model_fixtures import (
    fill_payload_dict,
    ticker_payload_dict,
    trade_payload_dict,
)

# ---------------------------------------------------------------------------
# Context manager lifecycle
# ---------------------------------------------------------------------------


class TestWebSocketLifecycle:
    async def test_connect_and_close(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            assert session._connection is not None
            assert session._connection.state == ConnectionState.CONNECTED

    async def test_close_sets_state(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect():
            pass
        assert ws._connection is not None
        assert ws._connection.state == ConnectionState.CLOSED

    async def test_connect_returns_session(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        session = ws.connect()
        assert isinstance(session, _WebSocketSession)

    async def test_state_change_callback(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        states: list[tuple[ConnectionState, ConnectionState]] = []

        async def on_state(old: ConnectionState, new: ConnectionState) -> None:
            states.append((old, new))

        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config, on_state_change=on_state)
        async with ws.connect():
            pass
        # Should have at least DISCONNECTED->CONNECTING and CONNECTING->CONNECTED
        assert any(new == ConnectionState.CONNECTED for _, new in states)


# ---------------------------------------------------------------------------
# Typed subscribe methods
# ---------------------------------------------------------------------------


class TestSubscribeTicker:
    async def test_subscribe_sends_command(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_ticker(tickers=["T1"])
            assert len(fake_ws.received_commands) == 1
            cmd = fake_ws.received_commands[0]
            assert cmd["cmd"] == "subscribe"
            assert "ticker" in cmd["params"]["channels"]
            assert cmd["params"]["market_tickers"] == ["T1"]

    async def test_subscribe_receives_messages(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])

            await fake_ws.send_to_all(
                {
                    "type": "ticker",
                    "sid": 1,
                    "msg": ticker_payload_dict(
                        market_ticker="T1", market_id="x", yes_bid_dollars="55"
                    ),
                }
            )

            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.market_ticker == "T1"
            assert msg.msg.yes_bid == 55

    async def test_subscribe_ticker_no_tickers(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_ticker()
            cmd = fake_ws.received_commands[0]
            assert "market_tickers" not in cmd["params"]


class TestSubscribeOrderbookDelta:
    async def test_sets_snapshot_flag(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta(tickers=["T1"])
            cmd = fake_ws.received_commands[0]
            assert cmd["params"]["send_initial_snapshot"] is True

    async def test_receives_snapshot(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_orderbook_delta(tickers=["T1"])
            await fake_ws.send_to_all(
                {
                    "type": "orderbook_snapshot",
                    "sid": 1,
                    "seq": 1,
                    "msg": {
                        "market_ticker": "T1",
                        "market_id": "x",
                        "yes": [["0.50", "100"]],
                        "no": [],
                    },
                }
            )
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.type == "orderbook_snapshot"


class TestSubscribeTrade:
    async def test_subscribe_trade(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_trade(tickers=["T1"])
            await fake_ws.send_to_all(
                {
                    "type": "trade",
                    "sid": 1,
                    "msg": trade_payload_dict(trade_id="t1", market_ticker="T1"),
                }
            )
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.trade_id == "t1"


class TestSubscribeFill:
    async def test_subscribe_fill(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_fill()
            await fake_ws.send_to_all(
                {
                    "type": "fill",
                    "sid": 1,
                    "msg": fill_payload_dict(trade_id="t1", order_id="o1"),
                }
            )
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.trade_id == "t1"


# ---------------------------------------------------------------------------
# Generic subscribe
# ---------------------------------------------------------------------------


class TestGenericSubscribe:
    async def test_subscribe_arbitrary_channel(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe("fill")
            await fake_ws.send_to_all(
                {
                    "type": "fill",
                    "sid": 1,
                    "msg": fill_payload_dict(trade_id="t1", order_id="o1"),
                }
            )
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.trade_id == "t1"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Orderbook convenience
# ---------------------------------------------------------------------------


class TestOrderbookConvenience:
    async def test_orderbook_yields_full_book(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.orderbook("T1")

            await fake_ws.send_to_all(
                {
                    "type": "orderbook_snapshot",
                    "sid": 1,
                    "seq": 1,
                    "msg": {
                        "market_ticker": "T1",
                        "market_id": "x",
                        "yes": [["0.50", "100"]],
                        "no": [],
                    },
                }
            )

            book = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert book.ticker == "T1"
            assert len(book.yes) == 1


# ---------------------------------------------------------------------------
# Callback API
# ---------------------------------------------------------------------------


class TestCallbackAPI:
    async def test_on_decorator_registers(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            received: list[object] = []
            got_one = asyncio.Event()

            @session.on("fill")
            async def on_fill(msg: object) -> None:
                received.append(msg)
                got_one.set()

            await session.subscribe_fill()
            await fake_ws.send_to_all(
                {
                    "type": "fill",
                    "sid": 1,
                    "msg": fill_payload_dict(trade_id="t1", order_id="o1"),
                }
            )

            # Deterministic wait: the callback signals us; we don't sleep blindly.
            await asyncio.wait_for(got_one.wait(), timeout=2.0)
            assert len(received) == 1


# ---------------------------------------------------------------------------
# Multiple channels
# ---------------------------------------------------------------------------


class TestMultipleChannels:
    async def test_two_channels_on_same_connection(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            ticker_stream = await session.subscribe_ticker(tickers=["T1"])
            fill_stream = await session.subscribe_fill()

            # Server assigns sid=1 to ticker, sid=2 to fill
            await fake_ws.send_to_all(
                {
                    "type": "ticker",
                    "sid": 1,
                    "msg": ticker_payload_dict(
                        market_ticker="T1", market_id="x", yes_bid_dollars="55"
                    ),
                }
            )
            await fake_ws.send_to_all(
                {
                    "type": "fill",
                    "sid": 2,
                    "msg": fill_payload_dict(trade_id="t1", order_id="o1"),
                }
            )

            ticker_msg = await asyncio.wait_for(ticker_stream.__anext__(), timeout=2.0)
            fill_msg = await asyncio.wait_for(fill_stream.__anext__(), timeout=2.0)
            assert ticker_msg.msg.market_ticker == "T1"
            assert fill_msg.msg.trade_id == "t1"

    async def test_two_subs_same_channel_distinct_params(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        """Two subs to the same channel (orderbook_delta) with different tickers.

        Pins that the SDK treats each ``subscribe`` call as an independent
        subscription with its own ``server_sid`` and its own iterator queue —
        even when channel name collides. Messages with sid=A go only to the
        first iterator; sid=B only to the second.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream_a = await session.subscribe_orderbook_delta(tickers=["T1"])
            stream_b = await session.subscribe_orderbook_delta(tickers=["T2"])

            # Two distinct subscribes -> two distinct server sids
            assert session._sub_mgr is not None
            sids = [sub.server_sid for sub in session._sub_mgr.active_subscriptions.values()]
            assert len(sids) == 2
            assert sids[0] != sids[1]
            sid_a, sid_b = sids[0], sids[1]
            assert sid_a is not None and sid_b is not None

            # Push one message to each sid
            await fake_ws.send_to_all(
                {
                    "type": "orderbook_snapshot",
                    "sid": sid_a,
                    "seq": 1,
                    "msg": {
                        "market_ticker": "T1",
                        "market_id": "x",
                        "yes": [["0.50", "100"]],
                        "no": [],
                    },
                }
            )
            await fake_ws.send_to_all(
                {
                    "type": "orderbook_snapshot",
                    "sid": sid_b,
                    "seq": 1,
                    "msg": {
                        "market_ticker": "T2",
                        "market_id": "y",
                        "yes": [["0.60", "200"]],
                        "no": [],
                    },
                }
            )

            msg_a = await asyncio.wait_for(stream_a.__anext__(), timeout=2.0)
            msg_b = await asyncio.wait_for(stream_b.__anext__(), timeout=2.0)
            assert msg_a.msg.market_ticker == "T1"
            assert msg_b.msg.market_ticker == "T2"


# ---------------------------------------------------------------------------
# run_forever
# ---------------------------------------------------------------------------


class TestRunForever:
    async def test_run_forever_blocks_until_close(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            # Subscribe first so recv_loop is started
            await session.subscribe_ticker(tickers=["T1"])
            # run_forever should block; verify it doesn't return immediately
            # by running it as a task and checking it's still pending
            run_task = asyncio.create_task(session.run_forever())
            await asyncio.sleep(0.1)
            assert not run_task.done()
            # Stopping the session (via context manager exit) will end run_forever

    async def test_run_forever_without_subscription_raises(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#175: run_forever() without a prior subscribe used to silently
        return because _recv_task was None. The recv loop only starts inside
        the subscribe machinery; registering an @ws.on() callback alone does
        NOT cause the server to send frames, so the callback would never fire
        and run_forever would return immediately with no signal.

        Post-#175 the foot-gun is loud: KalshiSubscriptionError at the call
        site instead of a silent no-op.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            with pytest.raises(KalshiSubscriptionError, match="at least one active subscription"):
                await session.run_forever()

    async def test_run_forever_with_stop_event_returns_cleanly(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#177: stop_event signals cooperative shutdown. run_forever()
        closes the connection and drains the recv loop without raising
        CancelledError. The loop exits via its existing `not _running`
        branch on the next ConnectionClosed, NOT via cancellation."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_ticker(tickers=["T1"])
            stop = asyncio.Event()
            run_task = asyncio.create_task(session.run_forever(stop_event=stop))
            # Give the loop a tick to settle on the recv await. 100 ms is
            # generous enough for resource-constrained CI runners while
            # still keeping the test fast.
            await asyncio.sleep(0.1)
            assert not run_task.done()
            # Trigger cooperative shutdown.
            stop.set()
            # Returns cleanly, no exception leaked.
            await asyncio.wait_for(run_task, timeout=2.0)
            assert run_task.exception() is None
            assert session._connection is not None
            assert session._connection.state == ConnectionState.CLOSED

    async def test_run_forever_with_pre_set_stop_event_returns_immediately(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#177: a stop_event already set before run_forever() runs should
        fire on the first scheduling tick — same cooperative-shutdown path,
        just no wait. Guards against the race-free case being broken by
        future refactors of the asyncio.wait() arrangement."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_ticker(tickers=["T1"])
            stop = asyncio.Event()
            stop.set()
            await asyncio.wait_for(session.run_forever(stop_event=stop), timeout=2.0)
            assert session._connection is not None
            assert session._connection.state == ConnectionState.CLOSED

    async def test_run_forever_with_stop_event_broadcasts_sentinels(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#177 review fix: cooperative shutdown must broadcast queue
        sentinels so iterator consumers exit `async for` cleanly. Without
        this an iterator outside an `async with` block would hang on the
        empty queue after the connection closed."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])
            stop = asyncio.Event()
            run_task = asyncio.create_task(session.run_forever(stop_event=stop))
            await asyncio.sleep(0.05)
            stop.set()
            await asyncio.wait_for(run_task, timeout=2.0)

            # The iterator must terminate without further input. Pre-fix it
            # would block on the empty queue waiting for a sentinel that
            # only _stop() (on __aexit__) was sending.
            collected: list[Any] = []
            async def drain() -> None:
                async for msg in stream:
                    collected.append(msg)
            await asyncio.wait_for(drain(), timeout=2.0)
            # No frames ever sent through fake_ws, so the iterator should
            # have terminated immediately on the sentinel.
            assert collected == []


# ---------------------------------------------------------------------------
# Error callback
# ---------------------------------------------------------------------------


class TestErrorCallback:
    async def test_on_error_called(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        errors: list[object] = []
        got_one = asyncio.Event()

        async def on_err(err: object) -> None:
            errors.append(err)
            got_one.set()

        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config, on_error=on_err)
        async with ws.connect() as session:
            # Subscribe to get the recv loop going
            await session.subscribe_ticker(tickers=["T1"])

            # Send an error message
            await fake_ws.send_to_all(
                {
                    "type": "error",
                    "msg": {"code": 400, "msg": "bad request"},
                }
            )
            # Deterministic wait: the callback signals us; we don't sleep blindly.
            await asyncio.wait_for(got_one.wait(), timeout=2.0)
            assert len(errors) == 1
