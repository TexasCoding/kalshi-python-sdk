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
    async def test_connect_to_fake_server(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        assert mgr.state == ConnectionState.CONNECTED
        await mgr.close()
        # Re-read state to avoid mypy type-narrowing overlap after close()
        closed_state: ConnectionState = mgr.state
        assert closed_state == ConnectionState.CLOSED

    async def test_initial_state_is_disconnected(
        self, test_auth: object
    ) -> None:
        config = KalshiConfig(timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        assert mgr.state == ConnectionState.DISCONNECTED

    async def test_auth_rejection(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        fake_ws.reject_auth = True
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError, match="connection failed"):
            await mgr.connect()
        assert mgr.state == ConnectionState.CLOSED

    async def test_connect_invalid_url(self, test_auth: object) -> None:
        config = KalshiConfig(
            ws_base_url="ws://127.0.0.1:1", timeout=1.0
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError):
            await mgr.connect()
        assert mgr.state == ConnectionState.CLOSED

    async def test_close_when_already_disconnected(
        self, test_auth: object
    ) -> None:
        config = KalshiConfig(timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        # Should not raise
        await mgr.close()
        assert mgr.state == ConnectionState.CLOSED

    async def test_double_close(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
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
    async def test_send_and_recv(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
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

    async def test_send_when_not_connected_raises(
        self, test_auth: object
    ) -> None:
        config = KalshiConfig(timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        with pytest.raises(KalshiConnectionError, match="Not connected"):
            await mgr.send({"cmd": "subscribe"})

    async def test_recv_when_not_connected_raises(
        self, test_auth: object
    ) -> None:
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

    async def test_unsubscribe(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
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
        await mgr.send(
            {"id": 2, "cmd": "unsubscribe", "params": {"sids": [sid]}}
        )
        raw = await mgr.recv()
        data = json.loads(raw)
        assert data["type"] == "unsubscribed"
        assert data["sid"] == sid
        await mgr.close()

    async def test_list_subscriptions(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
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

        async def on_change(
            old: ConnectionState, new: ConnectionState
        ) -> None:
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

        async def on_change(
            old: ConnectionState, new: ConnectionState
        ) -> None:
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

    async def test_no_callback_when_none(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
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
    async def test_ws_property_raises_when_not_connected(
        self, test_auth: object
    ) -> None:
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
    async def test_reconnect_succeeds(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
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

        async def on_change(
            old: ConnectionState, new: ConnectionState
        ) -> None:
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
        self, test_auth: object,
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
        with pytest.raises(
            KalshiConnectionError, match="Max reconnect attempts"
        ):
            await mgr.reconnect()
        assert mgr.state == ConnectionState.CLOSED

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

        async def on_change(
            old: ConnectionState, new: ConnectionState
        ) -> None:
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
    async def test_auth_headers_sent(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
        """Verify the connection succeeds (auth headers accepted by the server)."""
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        await mgr.connect()
        assert mgr.state == ConnectionState.CONNECTED
        # The fake server accepted us (no 401 rejection)
        await mgr.close()

    async def test_build_auth_headers_uses_ws_path(
        self, test_auth: object
    ) -> None:
        """_build_auth_headers should sign with the WS URL path."""
        config = KalshiConfig(
            ws_base_url="wss://api.elections.kalshi.com/trade-api/ws/v2",
            timeout=5.0,
        )
        mgr = ConnectionManager(auth=test_auth, config=config)  # type: ignore[arg-type]
        headers = mgr._build_auth_headers()
        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers


# ---------------------------------------------------------------------------
# FakeKalshiWS — server-side broadcast / disconnect_after
# ---------------------------------------------------------------------------


class TestFakeKalshiWSBroadcast:
    async def test_send_to_all(
        self, fake_ws: FakeKalshiWS, test_auth: object
    ) -> None:
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
