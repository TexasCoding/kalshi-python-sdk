"""Tests for PerpsConnectionManager — handshake, state machine, reconnect."""

from __future__ import annotations

import pytest

from kalshi.errors import KalshiConnectionError
from kalshi.perps.config import PerpsConfig
from kalshi.perps.ws.connection import ConnectionState, PerpsConnectionManager

from .conftest import FakePerpsWS

pytestmark = pytest.mark.asyncio


async def test_connect_happy_path_builds_rsa_headers_and_transitions(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    states: list[tuple[ConnectionState, ConnectionState]] = []

    async def on_state(old: ConnectionState, new: ConnectionState) -> None:
        states.append((old, new))

    mgr = PerpsConnectionManager(
        auth=perps_auth, config=perps_ws_config, on_state_change=on_state
    )
    assert mgr.state is ConnectionState.DISCONNECTED
    await mgr.connect()
    assert mgr.state is ConnectionState.CONNECTED
    assert (ConnectionState.DISCONNECTED, ConnectionState.CONNECTING) in states
    assert (ConnectionState.CONNECTING, ConnectionState.CONNECTED) in states
    await mgr.close()
    assert mgr.state is ConnectionState.CLOSED


async def test_connect_failure_goes_to_closed_with_path_no_query(
    fake_perps_ws: FakePerpsWS, perps_auth
) -> None:
    fake_perps_ws.reject_auth = True
    config = PerpsConfig(
        base_url="https://external-api.demo.kalshi.co/trade-api/v2",
        ws_base_url=fake_perps_ws.ws_url,
        ws_max_retries=1,
    )
    mgr = PerpsConnectionManager(auth=perps_auth, config=config)
    with pytest.raises(KalshiConnectionError) as ei:
        await mgr.connect()
    assert mgr.state is ConnectionState.CLOSED
    # Path present, no query string / no leaked URL.
    assert "/trade-api/ws/v2/margin" in str(ei.value)
    assert "?" not in str(ei.value)


async def test_send_recv_roundtrip(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    mgr = PerpsConnectionManager(auth=perps_auth, config=perps_ws_config)
    await mgr.connect()
    await mgr.send({"id": 1, "cmd": "subscribe", "params": {"channels": ["ticker"]}})
    raw = await mgr.recv()
    assert '"subscribed"' in raw
    await mgr.close()


async def test_reconnect_fast_fails_on_permanent_close(
    fake_perps_ws: FakePerpsWS, perps_auth
) -> None:
    # reject_auth makes every reconnect attempt fail; with ws_max_retries=1 the
    # AWS-full-jitter loop exhausts quickly and raises KalshiConnectionError.
    fake_perps_ws.reject_auth = True
    config = PerpsConfig(
        base_url="https://external-api.demo.kalshi.co/trade-api/v2",
        ws_base_url=fake_perps_ws.ws_url,
        ws_max_retries=1,
        retry_base_delay=0.001,
        retry_max_delay=0.002,
    )
    mgr = PerpsConnectionManager(auth=perps_auth, config=config)
    with pytest.raises(KalshiConnectionError):
        await mgr.reconnect()
    assert mgr.state is ConnectionState.CLOSED
