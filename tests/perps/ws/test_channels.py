"""Tests for PerpsSubscriptionManager — the perps command grammar."""

from __future__ import annotations

import pytest

from kalshi.errors import KalshiSubscriptionError
from kalshi.perps.config import PerpsConfig
from kalshi.perps.ws.channels import PerpsSubscriptionManager
from kalshi.perps.ws.connection import PerpsConnectionManager
from kalshi.perps.ws.models.control import SubscriptionEntry

from .conftest import FakePerpsWS

pytestmark = pytest.mark.asyncio


async def _connected_mgr(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> tuple[PerpsConnectionManager, PerpsSubscriptionManager]:
    conn = PerpsConnectionManager(auth=perps_auth, config=perps_ws_config)
    await conn.connect()
    return conn, PerpsSubscriptionManager(conn)


async def test_subscribe_happy_sends_channels_and_installs_sid(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    sub = await mgr.subscribe("ticker", params={"market_tickers": ["BTC-PERP"]})
    assert sub.server_sid is not None
    assert mgr.get_subscription_by_sid(sub.server_sid) is sub
    cmd = fake_perps_ws.received_commands[-1]
    assert cmd["cmd"] == "subscribe"
    assert cmd["params"]["channels"] == ["ticker"]
    assert cmd["params"]["market_tickers"] == ["BTC-PERP"]
    await conn.close()


async def test_subscribe_error_raises_subscription_error(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    fake_perps_ws.force_error = True
    fake_perps_ws.error_code = 6
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    with pytest.raises(KalshiSubscriptionError) as ei:
        await mgr.subscribe("ticker")
    assert ei.value.error_code == 6
    await conn.close()


async def test_subscribe_rejects_unknown_param_key(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    with pytest.raises(KalshiSubscriptionError):
        await mgr.subscribe("ticker", params={"bogus_key": 1})
    await conn.close()


async def test_unsubscribe_sends_sids_and_tears_down(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    sub = await mgr.subscribe("ticker")
    sid = sub.server_sid
    await mgr.unsubscribe(sub.client_id)
    cmd = fake_perps_ws.received_commands[-1]
    assert cmd["cmd"] == "unsubscribe"
    assert cmd["params"]["sids"] == [sid]
    assert mgr.get_subscription(sub.client_id) is None
    await conn.close()


async def test_unsubscribe_unknown_client_id_is_noop(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    await mgr.unsubscribe(999)  # no raise
    await conn.close()


async def test_update_subscription_array_sids_form(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    sub = await mgr.subscribe("ticker")
    await mgr.update_subscription(
        sub.client_id, "add_markets", market_tickers=["ETH-PERP"]
    )
    cmd = fake_perps_ws.received_commands[-1]
    assert cmd["cmd"] == "update_subscription"
    assert cmd["params"]["action"] == "add_markets"
    assert cmd["params"]["sids"] == [sub.server_sid]
    assert "sid" not in cmd["params"]
    assert cmd["params"]["market_tickers"] == ["ETH-PERP"]
    await conn.close()


async def test_update_subscription_single_sid_form(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    sub = await mgr.subscribe("ticker")
    await mgr.update_subscription_single_sid(
        sub.client_id, "delete_markets", market_tickers=["ETH-PERP"]
    )
    cmd = fake_perps_ws.received_commands[-1]
    assert cmd["cmd"] == "update_subscription"
    assert cmd["params"]["action"] == "delete_markets"
    assert cmd["params"]["sid"] == sub.server_sid
    assert "sids" not in cmd["params"]
    await conn.close()


async def test_update_subscription_no_active_sub_raises(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    with pytest.raises(KalshiSubscriptionError):
        await mgr.update_subscription(123, "add_markets")
    await conn.close()


async def test_list_subscriptions_parses_array_msg(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    await mgr.subscribe("ticker")
    await mgr.subscribe("trade")
    entries = await mgr.list_subscriptions()
    assert all(isinstance(e, SubscriptionEntry) for e in entries)
    channels = {e.channel for e in entries}
    assert channels == {"ticker", "trade"}
    cmd = fake_perps_ws.received_commands[-1]
    assert cmd["cmd"] == "list_subscriptions"
    assert "params" not in cmd
    await conn.close()


async def test_list_subscriptions_empty(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    entries = await mgr.list_subscriptions()
    assert entries == []
    await conn.close()


async def test_resubscribe_all_reassigns_sids(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn, mgr = await _connected_mgr(fake_perps_ws, perps_ws_config, perps_auth)
    sub = await mgr.subscribe("ticker")
    old_sid = sub.server_sid
    await mgr.resubscribe_all()
    assert sub.server_sid is not None
    assert sub.server_sid != old_sid
    assert mgr.get_subscription_by_sid(sub.server_sid) is sub
    await conn.close()
