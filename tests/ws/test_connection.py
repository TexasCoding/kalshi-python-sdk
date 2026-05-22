"""Tests for ConnectionManager."""

from __future__ import annotations

import json

import pytest

from kalshi.config import KalshiConfig
from kalshi.errors import KalshiConnectionError
from kalshi.ws.connection import ConnectionManager, ConnectionState

from .conftest import FakeKalshiWS

# ---------------------------------------------------------------------------
# ConnectionState enum
# ---------------------------------------------------------------------------


class TestConnectionState:
    def test_all_states_exist(self) -> None:
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.STREAMING.value == "streaming"
        assert ConnectionState.RECONNECTING.value == "reconnecting"
        assert ConnectionState.CLOSED.value == "closed"

    def test_state_count(self) -> None:
        assert len(ConnectionState) == 6


# ---------------------------------------------------------------------------
# ConnectionManager — connect / close
# ---------------------------------------------------------------------------


class TestConnectionManagerConnect:
    async def test_connect_to_fake_server(self, fake_ws: FakeKalshiWS, test_auth: object) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        assert mgr.state == ConnectionState.CONNECTED
        await mgr.close()
        # Re-read state to avoid mypy type-narrowing overlap after close()
        closed_state: ConnectionState = mgr.state
        assert closed_state == ConnectionState.CLOSED

    async def test_initial_state_is_disconnected(self, test_auth: object) -> None:
        config = KalshiConfig(timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        assert mgr.state == ConnectionState.DISCONNECTED

    async def test_auth_rejection(self, fake_ws: FakeKalshiWS, test_auth: object) -> None:
        fake_ws.reject_auth = True
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError, match="connection failed"):
            await mgr.connect()
        assert mgr.state == ConnectionState.CLOSED

    async def test_connect_invalid_url(self, test_auth: object) -> None:
        config = KalshiConfig(ws_base_url="ws://127.0.0.1:1", timeout=1.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError):
            await mgr.connect()
        assert mgr.state == ConnectionState.CLOSED

    async def test_mark_streaming_transitions_state(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        """Issue #88: public mark_streaming() transitions CONNECTED ->
        STREAMING and fires the state-change callback."""
        states: list[tuple[ConnectionState, ConnectionState]] = []

        async def on_state(old: ConnectionState, new: ConnectionState) -> None:
            states.append((old, new))

        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(
            auth=test_auth,
            config=config,
            on_state_change=on_state,  # type: ignore[arg-type]
        )
        await mgr.connect()
        states.clear()
        await mgr.mark_streaming()
        assert mgr.state == ConnectionState.STREAMING
        assert states == [(ConnectionState.CONNECTED, ConnectionState.STREAMING)]
        await mgr.close()

    async def test_connect_error_does_not_leak_url(self, test_auth: object) -> None:
        """Issue #84 F-O-09: connection-failure str() must not include the
        ws URL (which may contain token-like query params)."""
        # URL with a sensitive-looking query param
        config = KalshiConfig(
            ws_base_url="ws://127.0.0.1:1?secret=SUPER_SECRET_TOKEN",
            timeout=1.0,
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError) as exc_info:
            await mgr.connect()
        msg = str(exc_info.value)
        assert "SUPER_SECRET_TOKEN" not in msg
        assert "127.0.0.1" not in msg
        # The ws path (no query) is safe context and SHOULD appear.
        # Our test config sets ws_base_url to a URL without an explicit path,
        # so urlparse returns "" — assert by not crashing rather than substring.
        assert "WebSocket connection failed" in msg

    async def test_close_when_already_disconnected(self, test_auth: object) -> None:
        config = KalshiConfig(timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        # Should not raise
        await mgr.close()
        assert mgr.state == ConnectionState.CLOSED

    async def test_double_close(self, fake_ws: FakeKalshiWS, test_auth: object) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        await mgr.close()
        # Second close should not raise
        await mgr.close()
        assert mgr.state == ConnectionState.CLOSED


# ---------------------------------------------------------------------------
# ConnectionManager — send / recv
# ---------------------------------------------------------------------------


class TestConnectionManagerSendRecv:
    async def test_send_and_recv(self, fake_ws: FakeKalshiWS, test_auth: object) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        # Send a subscribe command
        await mgr.send(
            {
                "id": 1,
                "cmd": "subscribe",
                "params": {"channels": ["ticker"]},
            }
        )
        # Receive the subscribed response
        raw = await mgr.recv()
        data = json.loads(raw)
        assert data["type"] == "subscribed"
        assert data["msg"]["channel"] == "ticker"
        await mgr.close()

    async def test_send_when_not_connected_raises(self, test_auth: object) -> None:
        config = KalshiConfig(timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError, match="Not connected"):
            await mgr.send({"cmd": "subscribe"})

    async def test_recv_when_not_connected_raises(self, test_auth: object) -> None:
        config = KalshiConfig(timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError, match="Not connected"):
            await mgr.recv()

    async def test_subscribe_multiple_channels(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        await mgr.send(
            {
                "id": 1,
                "cmd": "subscribe",
                "params": {"channels": ["ticker", "orderbook_delta"]},
            }
        )
        # Should get two subscribed messages
        raw1 = await mgr.recv()
        raw2 = await mgr.recv()
        data1 = json.loads(raw1)
        data2 = json.loads(raw2)
        channels = {data1["msg"]["channel"], data2["msg"]["channel"]}
        assert channels == {"ticker", "orderbook_delta"}
        await mgr.close()

    async def test_unsubscribe(self, fake_ws: FakeKalshiWS, test_auth: object) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        # Subscribe
        await mgr.send(
            {
                "id": 1,
                "cmd": "subscribe",
                "params": {"channels": ["ticker"]},
            }
        )
        raw = await mgr.recv()
        sid = json.loads(raw)["msg"]["sid"]
        # Unsubscribe
        await mgr.send({"id": 2, "cmd": "unsubscribe", "params": {"sids": [sid]}})
        raw = await mgr.recv()
        data = json.loads(raw)
        assert data["type"] == "unsubscribed"
        assert data["sid"] == sid
        await mgr.close()

    async def test_list_subscriptions(self, fake_ws: FakeKalshiWS, test_auth: object) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        # Subscribe first
        await mgr.send(
            {
                "id": 1,
                "cmd": "subscribe",
                "params": {"channels": ["ticker"]},
            }
        )
        await mgr.recv()  # consume subscribed response
        # List subscriptions
        await mgr.send({"id": 2, "cmd": "list_subscriptions"})
        raw = await mgr.recv()
        data = json.loads(raw)
        assert data["type"] == "ok"
        assert len(data["msg"]) == 1
        assert data["msg"][0]["channel"] == "ticker"
        await mgr.close()


# ---------------------------------------------------------------------------
# ConnectionManager — state change callback
# ---------------------------------------------------------------------------


class TestConnectionManagerStateCallback:
    async def test_state_change_callback_on_connect_close(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        states: list[tuple[str, str]] = []

        async def on_change(old: ConnectionState, new: ConnectionState) -> None:
            states.append((old.value, new.value))

        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(
            auth=test_auth,  # type: ignore[arg-type]
            config=config,
            on_state_change=on_change,
        )
        await mgr.connect()
        await mgr.close()
        assert ("disconnected", "connecting") in states
        assert ("connecting", "connected") in states
        assert ("connected", "closed") in states

    async def test_state_change_callback_on_failed_connect(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        fake_ws.reject_auth = True
        states: list[tuple[str, str]] = []

        async def on_change(old: ConnectionState, new: ConnectionState) -> None:
            states.append((old.value, new.value))

        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(
            auth=test_auth,  # type: ignore[arg-type]
            config=config,
            on_state_change=on_change,
        )
        with pytest.raises(KalshiConnectionError):
            await mgr.connect()
        assert ("disconnected", "connecting") in states
        assert ("connecting", "closed") in states

    async def test_no_callback_when_none(self, fake_ws: FakeKalshiWS, test_auth: object) -> None:
        """Ensure no error when on_state_change is None."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(
            auth=test_auth,  # type: ignore[arg-type]
            config=config,
            on_state_change=None,
        )
        await mgr.connect()
        await mgr.close()


# ---------------------------------------------------------------------------
# ConnectionManager — ws property
# ---------------------------------------------------------------------------


class TestConnectionManagerWsProperty:
    async def test_ws_property_raises_when_not_connected(self, test_auth: object) -> None:
        config = KalshiConfig(timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError, match="Not connected"):
            _ = mgr.ws

    async def test_ws_property_returns_connection(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        ws = mgr.ws
        assert ws is not None
        await mgr.close()


# ---------------------------------------------------------------------------
# ConnectionManager — reconnect
# ---------------------------------------------------------------------------


class TestConnectionManagerReconnect:
    async def test_reconnect_succeeds(self, fake_ws: FakeKalshiWS, test_auth: object) -> None:
        config = KalshiConfig(
            ws_base_url=fake_ws.url,
            timeout=5.0,
            retry_base_delay=0.01,
            retry_max_delay=0.05,
            ws_max_retries=3,
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.reconnect()
        assert mgr.state == ConnectionState.CONNECTED
        await mgr.close()

    async def test_reconnect_state_transitions(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        states: list[tuple[str, str]] = []

        async def on_change(old: ConnectionState, new: ConnectionState) -> None:
            states.append((old.value, new.value))

        config = KalshiConfig(
            ws_base_url=fake_ws.url,
            timeout=5.0,
            retry_base_delay=0.01,
            retry_max_delay=0.05,
            ws_max_retries=3,
        )
        mgr = ConnectionManager(
            auth=test_auth,  # type: ignore[arg-type]
            config=config,
            on_state_change=on_change,
        )
        await mgr.reconnect()
        assert ("disconnected", "reconnecting") in states
        assert ("reconnecting", "connecting") in states
        assert ("connecting", "connected") in states
        await mgr.close()

    async def test_reconnect_max_retries_exceeded(
        self,
        test_auth: object,
    ) -> None:
        """When the server is unreachable, reconnect should fail after max retries."""
        config = KalshiConfig(
            ws_base_url="ws://127.0.0.1:1",
            timeout=1.0,
            retry_base_delay=0.01,
            retry_max_delay=0.05,
            ws_max_retries=2,
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError, match="Max reconnect attempts"):
            await mgr.reconnect()
        assert mgr.state == ConnectionState.CLOSED

    async def test_issue_355_reconnect_logs_exc_info_and_chains_last_exc(
        self,
        test_auth: object,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """#355: Per-attempt DEBUG log MUST include ``exc_info`` and the
        final ``KalshiConnectionError`` MUST chain the last attempt's
        exception via ``__cause__`` — without it operators cannot tell
        DNS vs TLS vs auth from a ten-retry burn.
        """
        import logging as _logging

        config = KalshiConfig(
            ws_base_url="ws://127.0.0.1:1",
            timeout=1.0,
            retry_base_delay=0.001,
            retry_max_delay=0.005,
            ws_max_retries=2,
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with (
            caplog.at_level(_logging.DEBUG, logger="kalshi.ws"),
            pytest.raises(KalshiConnectionError) as excinfo,
        ):
            await mgr.reconnect()

        # The final raise chains the last attempt's exception.
        assert excinfo.value.__cause__ is not None, (
            "Max-retries raise must chain the last attempt's exception"
        )

        # Each attempt log carries exc_info (LogRecord.exc_info populated).
        attempt_records = [
            r for r in caplog.records
            if "Reconnect attempt" in r.getMessage() and "failed" in r.getMessage()
        ]
        assert attempt_records, "Expected DEBUG 'Reconnect attempt N/M failed' records"
        assert all(r.exc_info is not None for r in attempt_records), (
            "Per-attempt failure log MUST include exc_info=True"
        )

    async def test_reconnect_eventually_succeeds(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        """Reject auth initially, then allow it to succeed on retry.

        The fake server's _process_request checks reject_auth dynamically,
        so toggling it between attempts simulates a flaky server.
        We use the state change callback to flip the flag after the first
        failed attempt transitions to CONNECTING the second time.
        """
        fake_ws.reject_auth = True
        attempt_count = 0

        async def on_change(old: ConnectionState, new: ConnectionState) -> None:
            nonlocal attempt_count
            if new == ConnectionState.CONNECTING:
                attempt_count += 1
                if attempt_count >= 2:
                    fake_ws.reject_auth = False

        config = KalshiConfig(
            ws_base_url=fake_ws.url,
            timeout=5.0,
            retry_base_delay=0.01,
            retry_max_delay=0.05,
            ws_max_retries=5,
        )
        mgr = ConnectionManager(
            auth=test_auth,  # type: ignore[arg-type]
            config=config,
            on_state_change=on_change,
        )
        await mgr.reconnect()
        assert mgr.state == ConnectionState.CONNECTED
        await mgr.close()


# ---------------------------------------------------------------------------
# ConnectionManager — auth headers
# ---------------------------------------------------------------------------


class TestConnectionManagerAuth:
    async def test_auth_headers_sent(self, fake_ws: FakeKalshiWS, test_auth: object) -> None:
        """Verify the connection succeeds (auth headers accepted by the server)."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        assert mgr.state == ConnectionState.CONNECTED
        # The fake server accepted us (no 401 rejection)
        await mgr.close()

    async def test_build_auth_headers_uses_ws_path(self, test_auth: object) -> None:
        """_build_auth_headers should sign with the WS URL path."""
        config = KalshiConfig(
            ws_base_url="wss://api.elections.kalshi.com/trade-api/ws/v2",
            timeout=5.0,
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        headers = await mgr._build_auth_headers()
        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers


# ---------------------------------------------------------------------------
# FakeKalshiWS — server-side broadcast / disconnect_after
# ---------------------------------------------------------------------------


class TestFakeKalshiWSBroadcast:
    async def test_send_to_all(self, fake_ws: FakeKalshiWS, test_auth: object) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        await fake_ws.send_to_all({"type": "test", "data": "hello"})
        raw = await mgr.recv()
        data = json.loads(raw)
        assert data["type"] == "test"
        assert data["data"] == "hello"
        await mgr.close()

    async def test_received_commands_recorded(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        await mgr.send(
            {
                "id": 1,
                "cmd": "subscribe",
                "params": {"channels": ["ticker"]},
            }
        )
        await mgr.recv()  # consume response
        assert len(fake_ws.received_commands) == 1
        assert fake_ws.received_commands[0]["cmd"] == "subscribe"
        await mgr.close()


# ---------------------------------------------------------------------------
# #208 — ws_ping_interval / ws_close_timeout pluming, #209 ws_json_dumps,
# #221 P2.1 Full Jitter
# ---------------------------------------------------------------------------


class TestPingCloseTimeoutPlumbing:
    async def test_ws_ping_interval_from_config_passed_through(
        self, fake_ws: FakeKalshiWS, test_auth: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#208: ws_ping_interval forwarded into websockets.connect()."""
        captured: dict[str, object] = {}
        from kalshi.ws import connection as conn_mod

        real_connect = conn_mod.connect

        async def spy(*args: object, **kwargs: object) -> object:
            captured.update(kwargs)
            return await real_connect(*args, **kwargs)  # type: ignore[misc]

        monkeypatch.setattr(conn_mod, "connect", spy)

        config = KalshiConfig(
            ws_base_url=fake_ws.url, timeout=5.0, ws_ping_interval=42.5
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        try:
            assert captured["ping_interval"] == 42.5
        finally:
            await mgr.close()

    async def test_ws_close_timeout_from_config_passed_through(
        self, fake_ws: FakeKalshiWS, test_auth: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#208: ws_close_timeout forwarded into websockets.connect()."""
        captured: dict[str, object] = {}
        from kalshi.ws import connection as conn_mod

        real_connect = conn_mod.connect

        async def spy(*args: object, **kwargs: object) -> object:
            captured.update(kwargs)
            return await real_connect(*args, **kwargs)  # type: ignore[misc]

        monkeypatch.setattr(conn_mod, "connect", spy)

        config = KalshiConfig(
            ws_base_url=fake_ws.url, timeout=5.0, ws_close_timeout=2.25
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        try:
            assert captured["close_timeout"] == 2.25
        finally:
            await mgr.close()


class TestCustomJsonDumps:
    async def test_custom_json_dumps_called_for_subscribe_commands(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        """#209: ws_json_dumps used for outbound frame serialization."""
        calls: list[object] = []

        def my_dumps(obj: object) -> str:
            calls.append(obj)
            return json.dumps(obj)

        config = KalshiConfig(
            ws_base_url=fake_ws.url, timeout=5.0, ws_json_dumps=my_dumps
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        try:
            await mgr.send({"id": 1, "cmd": "subscribe", "params": {}})
            assert any(
                isinstance(c, dict) and c.get("cmd") == "subscribe" for c in calls
            )
        finally:
            await mgr.close()


class TestReconnectFullJitter:
    async def test_reconnect_uses_full_jitter(
        self, test_auth: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#221 P2.1: reconnect delay sampled via random.uniform(0, min(cap, base*2**n))
        — matching the REST transport's Full Jitter formula. Old formula was
        base*2**n + uniform(0, 0.5) capped at retry_max_delay.
        """
        from kalshi.ws import connection as conn_mod

        upper_bounds: list[float] = []

        def fake_uniform(lo: float, hi: float) -> float:
            upper_bounds.append(hi)
            assert lo == 0
            return 0.0  # zero delay so the test doesn't sleep

        async def fake_sleep(_: float) -> None:
            return None

        async def failing_connect(*_a: object, **_kw: object) -> object:
            raise RuntimeError("simulated connect failure")

        monkeypatch.setattr(conn_mod.random, "uniform", fake_uniform)
        monkeypatch.setattr(conn_mod.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(conn_mod, "connect", failing_connect)

        config = KalshiConfig(
            ws_base_url="ws://127.0.0.1:1",
            timeout=1.0,
            ws_max_retries=4,
            retry_base_delay=0.5,
            retry_max_delay=8.0,
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError):
            await mgr.reconnect()

        # Expected upper bounds per Full Jitter formula across 4 attempts:
        #   attempt 0: min(8.0, 0.5*1)  = 0.5
        #   attempt 1: min(8.0, 0.5*2)  = 1.0
        #   attempt 2: min(8.0, 0.5*4)  = 2.0
        #   attempt 3: min(8.0, 0.5*8)  = 4.0
        assert upper_bounds == [0.5, 1.0, 2.0, 4.0]
