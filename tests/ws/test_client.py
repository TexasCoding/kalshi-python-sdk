"""Tests for KalshiWebSocket client."""
from __future__ import annotations

import asyncio

from kalshi.config import KalshiConfig
from kalshi.ws.client import KalshiWebSocket, _WebSocketSession
from kalshi.ws.connection import ConnectionState

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

            await fake_ws.send_to_all({
                "type": "ticker", "sid": 1,
                "msg": {"market_ticker": "T1", "market_id": "x", "yes_bid": 55},
            })

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
            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": 1, "seq": 1,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.type == "orderbook_snapshot"


class TestSubscribeTrade:
    async def test_subscribe_trade(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_trade(tickers=["T1"])
            await fake_ws.send_to_all({
                "type": "trade", "sid": 1,
                "msg": {"trade_id": "t1", "market_ticker": "T1"},
            })
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.trade_id == "t1"


class TestSubscribeFill:
    async def test_subscribe_fill(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_fill()
            await fake_ws.send_to_all({
                "type": "fill", "sid": 1,
                "msg": {"trade_id": "t1", "order_id": "o1"},
            })
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
            await fake_ws.send_to_all({
                "type": "fill", "sid": 1,
                "msg": {"trade_id": "t1", "order_id": "o1"},
            })
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

            await fake_ws.send_to_all({
                "type": "orderbook_snapshot", "sid": 1, "seq": 1,
                "msg": {
                    "market_ticker": "T1", "market_id": "x",
                    "yes": [["0.50", "100"]], "no": [],
                },
            })

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

            @session.on("fill")
            async def on_fill(msg: object) -> None:
                received.append(msg)

            await session.subscribe_fill()
            await fake_ws.send_to_all({
                "type": "fill", "sid": 1,
                "msg": {"trade_id": "t1", "order_id": "o1"},
            })

            # Give recv_loop time to dispatch
            await asyncio.sleep(0.2)
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
            await fake_ws.send_to_all({
                "type": "ticker", "sid": 1,
                "msg": {"market_ticker": "T1", "market_id": "x", "yes_bid": 55},
            })
            await fake_ws.send_to_all({
                "type": "fill", "sid": 2,
                "msg": {"trade_id": "t1", "order_id": "o1"},
            })

            ticker_msg = await asyncio.wait_for(ticker_stream.__anext__(), timeout=2.0)
            fill_msg = await asyncio.wait_for(fill_stream.__anext__(), timeout=2.0)
            assert ticker_msg.msg.market_ticker == "T1"
            assert fill_msg.msg.trade_id == "t1"


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

    async def test_run_forever_returns_immediately_without_subscribe(
        self, fake_ws, test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            # No subscribe, so no recv_task; run_forever returns immediately
            await asyncio.wait_for(session.run_forever(), timeout=1.0)


# ---------------------------------------------------------------------------
# Error callback
# ---------------------------------------------------------------------------


class TestErrorCallback:
    async def test_on_error_called(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        errors: list[object] = []

        async def on_err(err: object) -> None:
            errors.append(err)

        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config, on_error=on_err)
        async with ws.connect() as session:
            # Subscribe to get the recv loop going
            await session.subscribe_ticker(tickers=["T1"])

            # Send an error message
            await fake_ws.send_to_all({
                "type": "error",
                "msg": {"code": 400, "msg": "bad request"},
            })
            await asyncio.sleep(0.2)
            assert len(errors) == 1
