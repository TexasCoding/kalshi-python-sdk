"""Tests for KalshiWebSocket client."""

from __future__ import annotations

import asyncio
import gc
import logging
from decimal import Decimal
from typing import Any

import pytest

from kalshi.config import KalshiConfig
from kalshi.errors import KalshiConnectionError, KalshiSubscriptionError
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
        """#297: after a clean __aexit__, _connection (and the other managers)
        are cleared so the same instance can be reused for a fresh connect()."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect():
            pass
        assert ws._connection is None
        assert ws._running is False

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

    async def test_double_start_raises(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        """#297: re-entering connect() on an active session must fail loudly
        rather than silently clobbering the managers."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect():
            with pytest.raises(RuntimeError, match="already started"):
                async with ws.connect():
                    pass

    async def test_reconnect_after_stop_works(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        """#297: after a clean __aexit__, the same instance can be reused
        for a fresh connect() — the guard rejects overlap, not legitimate
        restart."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)

        async with ws.connect() as session:
            assert session._connection is not None
        # State cleared after exit
        assert ws._connection is None
        assert ws._sub_mgr is None
        assert ws._dispatcher is None
        assert ws._recv_task is None
        assert ws._running is False

        # Reuse same instance: subscribe and receive a frame.
        async with ws.connect() as session:
            assert session._connection is not None
            assert session._connection.state == ConnectionState.CONNECTED
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

    async def test_failed_connect_allows_retry(self, test_auth) -> None:  # type: ignore[no-untyped-def]
        """#297: a failed connect() must not brick the instance.

        ``__aexit__`` does not run if ``__aenter__`` raises, so ``_start()``
        is responsible for resetting any partially-assigned managers when
        ``ConnectionManager.connect()`` blows up. Otherwise the guard at the
        top of ``_start()`` permanently rejects every subsequent attempt.
        """
        # Unreachable port -> ConnectionManager.connect() will raise.
        config = KalshiConfig(ws_base_url="ws://127.0.0.1:1", timeout=1.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        with pytest.raises(Exception):  # noqa: B017 — any connect failure must clear state
            async with ws.connect():
                pass
        # Core invariant: state cleared so the guard doesn't trip on retry.
        assert ws._connection is None
        assert ws._sub_mgr is None
        assert ws._dispatcher is None
        assert ws._running is False


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


class TestSubscribeCFBenchmarks:
    async def test_subscribe_seeds_index_ids(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_cfbenchmarks_value(index_ids=["BRTI", "ETHUSD_RTI"])
            cmd = fake_ws.received_commands[0]
            assert cmd["cmd"] == "subscribe"
            assert "cfbenchmarks_value" in cmd["params"]["channels"]
            assert cmd["params"]["index_ids"] == ["BRTI", "ETHUSD_RTI"]
            # market_* params must NOT leak onto this channel.
            assert "market_tickers" not in cmd["params"]

    async def test_subscribe_without_index_ids_omits_key(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_cfbenchmarks_value()
            cmd = fake_ws.received_commands[0]
            assert "index_ids" not in cmd["params"]

    async def test_subscribe_all_indices_passthrough(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        # The spec's special ["all"] value is forwarded verbatim.
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_cfbenchmarks_value(index_ids=["all"])
            cmd = fake_ws.received_commands[0]
            assert cmd["params"]["index_ids"] == ["all"]

    async def test_receives_value_message(self, fake_ws, test_auth) -> None:  # type: ignore[no-untyped-def]
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_cfbenchmarks_value(index_ids=["BRTI"])
            await fake_ws.send_to_all(
                {
                    "type": "cfbenchmarks_value",
                    "sid": 1,
                    "seq": 1,
                    "msg": {
                        "index_id": "BRTI",
                        "received_at": 1715793600123,
                        "data": "{}",
                        "avg_60s_data": {
                            "value": "65000.12345678",
                            "window_size": 1,
                            "window_start_ts_ms": 1715793540123,
                            "window_end_ts_exclusive": 1715793600123,
                        },
                    },
                }
            )
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.index_id == "BRTI"
            assert msg.msg.avg_60s_data.value == Decimal("65000.12345678")


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


# ---------------------------------------------------------------------------
# #209 — pluggable JSON loader
# ---------------------------------------------------------------------------


class TestPluggableJsonLoads:
    async def test_custom_json_loads_called_for_recv_frames(
        self, fake_ws: Any, test_auth: Any
    ) -> None:
        """#209: ws_json_loads is used for incoming WS frames in the recv loop."""
        import json as _json

        calls: list[Any] = []

        def my_loads(raw: bytes | str) -> Any:
            calls.append(raw)
            return _json.loads(raw)

        config = KalshiConfig(
            ws_base_url=fake_ws.url, timeout=5.0, ws_json_loads=my_loads
        )
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
            await asyncio.wait_for(stream.__anext__(), timeout=2.0)
        # At minimum the ticker frame was parsed by our loader. The recv loop
        # parses every frame off the socket — assert non-empty.
        assert calls, "ws_json_loads was never invoked on recv frames"


# ---------------------------------------------------------------------------
# Regression — #314, #315
# ---------------------------------------------------------------------------


class TestIssue314WaitForResponseTimeout:
    async def test_issue_314_subscribe_raises_kalshi_subscription_error_on_timeout(
        self,
    ) -> None:
        """#314: ``asyncio.wait_for`` inside ``_wait_for_response`` raises a
        bare ``TimeoutError`` when the server never answers a subscribe ack.
        Before the fix it escaped to ``subscribe()`` callers as a plain
        ``TimeoutError``, losing the structured ``channel`` / ``client_id`` /
        ``op`` surface promised by #213. After the fix it surfaces as a
        ``KalshiSubscriptionError`` with those fields populated."""
        from kalshi.ws.channels import SubscriptionManager

        class NeverRecv:
            async def send(self, _cmd: Any) -> None:
                return None

            async def recv(self) -> str:
                # Hang forever; the wait_for inside _wait_for_response is
                # what must time out and surface as KalshiSubscriptionError.
                await asyncio.Event().wait()
                raise AssertionError("unreachable")  # pragma: no cover

        mgr = SubscriptionManager(NeverRecv())  # type: ignore[arg-type]

        with pytest.raises(KalshiSubscriptionError) as excinfo:
            await mgr._wait_for_response(
                msg_id=42,
                timeout=0.05,
                channel="orderbook_delta",
                client_id=7,
                op="subscribe",
            )

        err = excinfo.value
        assert err.channel == "orderbook_delta"
        assert err.client_id == 7
        assert err.op == "subscribe"
        assert "42" in str(err)


class TestIssue315ZombieSubscriptionCleanup:
    async def test_issue_315_failed_resubscribe_removes_zombie_subscription(
        self,
    ) -> None:
        """#315: ``broadcast_error`` must pop the dead ``Subscription`` so the
        next reconnect's ``resubscribe_all`` doesn't resurrect a zombie sub on
        the server (silent data loss + server-quota leak) and ``unsubscribe``
        doesn't short-circuit on a permanently-stuck entry."""
        from kalshi.errors import KalshiSequenceGapError
        from kalshi.ws.backpressure import MessageQueue, OverflowStrategy
        from kalshi.ws.channels import Subscription, SubscriptionManager

        recorded: list[Any] = []

        class StubConn:
            async def send(self, cmd: Any) -> None:
                recorded.append(cmd)

            async def recv(self) -> str:  # pragma: no cover - not used
                await asyncio.Event().wait()
                raise AssertionError("unreachable")

        mgr = SubscriptionManager(StubConn())  # type: ignore[arg-type]
        queue: MessageQueue[Any] = MessageQueue(
            maxsize=10,
            overflow=OverflowStrategy.ERROR,
            channel="orderbook_delta",
            client_id=7,
        )
        sub = Subscription(
            client_id=7,
            channel="orderbook_delta",
            params={"market_tickers": ["ABC-YES"]},
            queue=queue,
        )
        sub.server_sid = 314
        mgr._subscriptions[7] = sub
        mgr._sid_to_client[314] = 7

        # Simulate the gap-recovery failure path: ``_handle_seq_gap`` calls
        # broadcast_error on the live subscription (server_sid still set, sid
        # still in ``_sid_to_client``) after ``resubscribe_one`` raises. The
        # fix must clear *both* maps so the zombie can't resurrect.
        assert sub.server_sid == 314
        assert mgr._sid_to_client[314] == 7
        await mgr.broadcast_error(
            7,
            KalshiSequenceGapError(
                "Resubscribe failed for orderbook_delta after gap",
                channel="orderbook_delta",
                sid=314,
                client_id=7,
                last_seq=10,
                next_seq=12,
            ),
        )

        # Subscription is gone — no zombie left behind.
        assert 7 not in mgr._subscriptions
        assert 314 not in mgr._sid_to_client

        # The iterator surfaces the error sentinel.
        with pytest.raises(Exception) as excinfo:
            async for _ in queue:
                pass
        assert "Resubscribe failed" in str(excinfo.value)

        # A subsequent reconnect's resubscribe_all must be a no-op — no
        # subscribe command should hit the wire for the dead client_id.
        recorded.clear()
        await mgr.resubscribe_all()
        assert recorded == []
        assert mgr._subscriptions == {}

    async def test_issue_315_backpressure_path_also_removes_subscription(
        self,
    ) -> None:
        """#315: the ``KalshiBackpressureError`` rollback path in
        ``_process_frame`` routes through the same ``broadcast_error``, so the
        zombie cleanup must apply there too."""
        from kalshi.errors import KalshiBackpressureError
        from kalshi.ws.backpressure import MessageQueue, OverflowStrategy
        from kalshi.ws.channels import Subscription, SubscriptionManager

        class StubConn:
            async def send(self, _cmd: Any) -> None:
                return None

            async def recv(self) -> str:  # pragma: no cover - not used
                await asyncio.Event().wait()
                raise AssertionError("unreachable")

        mgr = SubscriptionManager(StubConn())  # type: ignore[arg-type]
        queue: MessageQueue[Any] = MessageQueue(
            maxsize=1,
            overflow=OverflowStrategy.ERROR,
            channel="orderbook_delta",
            client_id=11,
        )
        sub = Subscription(
            client_id=11,
            channel="orderbook_delta",
            params={},
            queue=queue,
        )
        sub.server_sid = 999
        mgr._subscriptions[11] = sub
        mgr._sid_to_client[999] = 11

        await mgr.broadcast_error(
            11,
            KalshiBackpressureError(
                "queue full",
                channel="orderbook_delta",
                client_id=11,
                maxsize=1,
            ),
        )

        assert 11 not in mgr._subscriptions
        assert 999 not in mgr._sid_to_client

# ---------------------------------------------------------------------------
# #332 — KalshiBackpressureError tears down the session cleanly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestIssue332BackpressureTeardown:
    async def test_issue_332_backpressure_closes_ws_cleanly(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#332: when the recv loop hits ``KalshiBackpressureError`` it must
        tear the session down — close the WS, flip ``_running=False``, and
        clear the manager refs. Without this, a subsequent ``subscribe_*``
        on the same instance resurrects a recv loop on top of orphaned
        server-side subscriptions whose queues are already closed.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta(tickers=["T1"], maxsize=1)
            assert session._sub_mgr is not None
            sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert sid is not None

            # Fill the queue with the snapshot.
            await fake_ws.send_to_all(
                {
                    "type": "orderbook_snapshot",
                    "sid": sid,
                    "seq": 1,
                    "msg": {
                        "market_ticker": "T1",
                        "market_id": "x",
                        "yes": [["0.50", "100"]],
                        "no": [],
                    },
                }
            )
            await asyncio.sleep(0.1)

            # Overflow: the recv loop's queue.put raises KalshiBackpressureError.
            await fake_ws.send_to_all(
                {
                    "type": "orderbook_delta",
                    "sid": sid,
                    "seq": 2,
                    "msg": {
                        "market_ticker": "T1",
                        "market_id": "x",
                        "price": "0.51",
                        "delta": "10",
                        "side": "yes",
                    },
                }
            )

            recv_task = session._recv_task
            assert recv_task is not None
            await asyncio.wait_for(recv_task, timeout=2.0)

            # #332: session is fully torn down inside the recv loop.
            assert session._running is False
            assert session._connection is None
            assert session._sub_mgr is None
            assert session._seq_tracker is None
            assert session._orderbook_mgr is None
            assert session._dispatcher is None

    async def test_issue_332_next_subscribe_after_backpressure_starts_fresh(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#332: after the recv loop tears down on backpressure, a follow-up
        ``subscribe_*`` on the SAME ``_WebSocketSession`` must fail fast
        with a clear ``RuntimeError`` rather than resurrecting a recv loop
        on top of orphaned server-side subscriptions. The user is expected
        to exit the ``async with`` block and start a fresh session for
        recovery — which is also exercised here.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            await session.subscribe_orderbook_delta(tickers=["T1"], maxsize=1)
            assert session._sub_mgr is not None
            sid = next(
                iter(session._sub_mgr.active_subscriptions.values())
            ).server_sid
            assert sid is not None

            # Snapshot fills the maxsize=1 queue, delta overflows.
            await fake_ws.send_to_all(
                {
                    "type": "orderbook_snapshot",
                    "sid": sid,
                    "seq": 1,
                    "msg": {
                        "market_ticker": "T1",
                        "market_id": "x",
                        "yes": [["0.50", "100"]],
                        "no": [],
                    },
                }
            )
            await asyncio.sleep(0.1)
            await fake_ws.send_to_all(
                {
                    "type": "orderbook_delta",
                    "sid": sid,
                    "seq": 2,
                    "msg": {
                        "market_ticker": "T1",
                        "market_id": "x",
                        "price": "0.51",
                        "delta": "10",
                        "side": "yes",
                    },
                }
            )
            recv_task = session._recv_task
            assert recv_task is not None
            await asyncio.wait_for(recv_task, timeout=2.0)

            # Subscribing again on the torn-down session must NOT silently
            # restart the recv loop. It must raise a clear error.
            with pytest.raises(RuntimeError, match="not active"):
                await session.subscribe_ticker(tickers=["T2"])

        # And after exiting the failed session, the same KalshiWebSocket
        # instance can be reused for a clean fresh session (#297 invariant
        # holds even though we tore down from the recv loop, not _stop).
        assert ws._connection is None
        assert ws._running is False
        assert ws._sub_mgr is None

        async with ws.connect() as session2:
            assert session2._connection is not None
            stream = await session2.subscribe_ticker(tickers=["T2"])
            assert session2._sub_mgr is not None
            sid2 = next(
                iter(session2._sub_mgr.active_subscriptions.values())
            ).server_sid
            await fake_ws.send_to_all(
                {
                    "type": "ticker",
                    "sid": sid2,
                    "msg": ticker_payload_dict(
                        market_ticker="T2", market_id="x", yes_bid_dollars="55"
                    ),
                }
            )
            msg = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert msg.msg.market_ticker == "T2"


@pytest.mark.asyncio
class TestIssue356RecvHotLoopTimeout:
    async def test_issue_356_recv_loop_uses_asyncio_timeout_not_wait_for(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#356: per-frame ``asyncio.wait_for`` is replaced by
        ``async with asyncio.timeout(...)`` in the recv hot loop. Verify
        the loop still drains frames correctly under the new construct.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])
            # Send a few frames in quick succession — the timeout-context
            # path must drain them all without TimeoutError leaking out.
            for i in range(5):
                await fake_ws.send_to_all(
                    {
                        "type": "ticker",
                        "sid": 1,
                        "msg": ticker_payload_dict(
                            market_ticker="T1",
                            market_id="x",
                            yes_bid_dollars=str(50 + i),
                        ),
                    }
                )
            received: list[Any] = []
            for _ in range(5):
                received.append(
                    await asyncio.wait_for(stream.__anext__(), timeout=2.0)
                )
            assert len(received) == 5

    async def test_issue_356_recv_loop_source_uses_asyncio_timeout(self) -> None:
        """#356 guard: ensure the source actually calls ``asyncio.timeout``
        and no longer wraps recv() in ``asyncio.wait_for``. Lock the
        intent in source so a future revert can't regress silently.
        """
        import inspect

        src = inspect.getsource(KalshiWebSocket._recv_loop)
        assert "asyncio.timeout(_RECV_POLL_S)" in src, (
            "_recv_loop must use asyncio.timeout for the per-frame poll"
        )
        assert "wait_for(self._connection.recv()" not in src, (
            "_recv_loop must NOT wrap recv() in asyncio.wait_for"
        )


@pytest.mark.asyncio
class TestIssue357StopOrdering:
    async def test_issue_357_stop_closes_connection_before_sentinels(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#357: ``_stop()`` must close the WS connection BEFORE broadcasting
        queue sentinels. Verified by recording the order in which
        ``ConnectionManager.close`` and ``MessageQueue.put_sentinel``
        run during teardown.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)

        order: list[str] = []
        async with ws.connect() as session:
            stream = await session.subscribe_ticker(tickers=["T1"])
            assert ws._connection is not None
            assert ws._sub_mgr is not None

            real_close = ws._connection.close

            async def tracking_close() -> None:
                order.append("close")
                await real_close()

            ws._connection.close = tracking_close  # type: ignore[method-assign]

            for sub in ws._sub_mgr.active_subscriptions.values():
                real_sentinel = sub.queue.put_sentinel

                async def tracking_sentinel(
                    _real: Any = real_sentinel,
                ) -> None:
                    order.append("sentinel")
                    await _real()

                sub.queue.put_sentinel = tracking_sentinel  # type: ignore[method-assign]

            # Drain the iterator so its task completes before teardown
            # races; one quick read is enough.
            assert stream is not None

        # On _stop teardown: close MUST run before any sentinel.
        assert order, "Expected at least close + sentinel to run during _stop"
        assert order[0] == "close", (
            f"_stop must close connection before broadcasting sentinels, got {order!r}"
        )

    async def test_issue_357_stop_source_close_precedes_broadcast(self) -> None:
        """#357 source-level guard: ``_stop()`` calls ``_connection.close``
        before ``_broadcast_sentinels`` (so a future reorder cannot regress
        the runtime ordering silently)."""
        import inspect

        src = inspect.getsource(KalshiWebSocket._stop)
        close_idx = src.find("self._connection.close()")
        broadcast_idx = src.find("self._broadcast_sentinels()")
        assert close_idx != -1, "_stop must close the connection"
        assert broadcast_idx != -1, "_stop must broadcast sentinels"
        assert close_idx < broadcast_idx, (
            "_stop must close the connection BEFORE broadcasting sentinels (#357)"
        )

    async def test_issue_357_stop_broadcasts_sentinels_when_close_raises(
        self,
        fake_ws,  # type: ignore[no-untyped-def]
        test_auth,  # type: ignore[no-untyped-def]
    ) -> None:
        """#357 round-2: ``_stop()`` must broadcast sentinels even when
        ``_connection.close()`` raises, otherwise iterator consumers hang
        on queues whose recv loop is dead. The close() call is wrapped in
        ``try/except``; the sentinel broadcast lives in ``finally``.
        """
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        ws = KalshiWebSocket(auth=test_auth, config=config)

        sentinels: list[str] = []

        async with ws.connect() as session:
            await session.subscribe_ticker(tickers=["T1"])
            assert ws._connection is not None
            assert ws._sub_mgr is not None

            async def raising_close() -> None:
                raise RuntimeError("transport boom")

            ws._connection.close = raising_close  # type: ignore[method-assign]

            for sid, sub in ws._sub_mgr.active_subscriptions.items():
                real_sentinel = sub.queue.put_sentinel

                async def tracking_sentinel(
                    _real: Any = real_sentinel, _sid: int = sid,
                ) -> None:
                    sentinels.append(f"sid={_sid}")
                    await _real()

                sub.queue.put_sentinel = tracking_sentinel  # type: ignore[method-assign]

        # __aexit__ -> _stop(); close() raises but sentinels MUST still fire.
        assert sentinels, (
            "Sentinels must broadcast even when _connection.close() raises; "
            "otherwise iterator consumers hang waiting on the closed queue."
        )


class TestIssue413StopRetrievesException:
    """#413: ``_stop()`` retrieves an already-finished recv task's exception."""

    async def test_stop_retrieves_dead_recv_task_exception(
        self,
        test_auth,  # type: ignore[no-untyped-def]
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # When the recv loop already finished with an exception (e.g. a permanent
        # close code), _stop must retrieve it — otherwise asyncio logs "Task
        # exception was never retrieved" when the task is garbage-collected.
        ws = KalshiWebSocket(auth=test_auth, config=KalshiConfig(timeout=5.0))

        async def _boom() -> None:
            raise KalshiConnectionError("permanent close")

        task: asyncio.Task[None] = asyncio.ensure_future(_boom())
        await asyncio.sleep(0)  # let it finish; exception now stored, unretrieved
        assert task.done()
        ws._recv_task = task

        with caplog.at_level(logging.ERROR, logger="asyncio"):
            await ws._stop()  # nils ws._recv_task, releasing its only other ref
            del task
            gc.collect()
        assert "never retrieved" not in caplog.text.lower()
