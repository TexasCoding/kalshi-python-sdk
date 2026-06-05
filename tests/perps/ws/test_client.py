"""Tests for the PerpsWebSocket facade — generic command surface + session lifecycle."""

from __future__ import annotations

import asyncio

import pytest

from kalshi.perps.config import PerpsConfig
from kalshi.perps.ws import PerpsWebSocket
from kalshi.perps.ws.models.control import SubscriptionEntry

from .conftest import FakePerpsWS

pytestmark = pytest.mark.asyncio


async def test_exported_from_package() -> None:
    from kalshi.perps.ws import (
        ConnectionState,
        MessageQueue,
        OverflowStrategy,
        PerpsConnectionManager,
        PerpsWebSocket,
    )

    assert ConnectionState is not None
    assert MessageQueue is not None
    assert OverflowStrategy is not None
    assert PerpsConnectionManager is not None
    assert PerpsWebSocket is not None


async def test_session_connect_and_subscribe(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        stream = await session.subscribe(
            "ticker", params={"market_tickers": ["BTC-PERP"]}
        )
        assert stream is not None
        cmd = fake_perps_ws.received_commands[-1]
        assert cmd["cmd"] == "subscribe"
        assert cmd["params"]["channels"] == ["ticker"]


async def test_subscribe_then_receive_dispatched_frame(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    # Register a fake ticker model so the dispatcher routes the frame to the
    # queue (foundation issue ships MESSAGE_MODELS empty; #398 fills it).
    from pydantic import BaseModel

    from kalshi.perps.ws import dispatch as dmod

    class _Ticker(BaseModel):
        type: str
        sid: int
        model_config = {"extra": "allow"}

    # Save/restore the real registration (#398 populates "ticker" -> the real
    # MarginTickerMessage); popping it would pollute later MESSAGE_MODELS tests.
    _orig_ticker = dmod.MESSAGE_MODELS.get("ticker")
    dmod.MESSAGE_MODELS["ticker"] = _Ticker
    try:
        ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
        async with ws.connect() as session:
            stream = await session.subscribe("ticker")
            # Find the assigned sid.
            sid = next(iter(fake_perps_ws.subscriptions))
            await fake_perps_ws.send_to_all(
                {"type": "ticker", "sid": sid, "msg": {"price": "1.00"}}
            )
            frame = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert frame.sid == sid
    finally:
        if _orig_ticker is not None:
            dmod.MESSAGE_MODELS["ticker"] = _orig_ticker
        else:
            dmod.MESSAGE_MODELS.pop("ticker", None)


async def test_update_subscription_via_facade(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        await session.subscribe("ticker")
        client_id = next(iter(session._sub_mgr.active_subscriptions))  # type: ignore[union-attr]
        await session.update_subscription(
            client_id, "add_markets", market_tickers=["ETH-PERP"]
        )
        cmd = fake_perps_ws.received_commands[-1]
        assert cmd["cmd"] == "update_subscription"
        assert cmd["params"]["action"] == "add_markets"
        assert "sids" in cmd["params"]


async def test_update_subscription_single_sid_via_facade(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        await session.subscribe("ticker")
        client_id = next(iter(session._sub_mgr.active_subscriptions))  # type: ignore[union-attr]
        await session.update_subscription_single_sid(
            client_id, "delete_markets", market_tickers=["ETH-PERP"]
        )
        cmd = fake_perps_ws.received_commands[-1]
        assert cmd["cmd"] == "update_subscription"
        assert "sid" in cmd["params"]
        assert "sids" not in cmd["params"]


async def test_list_subscriptions_via_facade(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        await session.subscribe("ticker")
        await session.subscribe("trade")
        entries = await session.list_subscriptions()
        assert all(isinstance(e, SubscriptionEntry) for e in entries)
        assert {e.channel for e in entries} == {"ticker", "trade"}


async def test_unsubscribe_via_facade_tears_down(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        await session.subscribe("ticker")
        client_id = next(iter(session._sub_mgr.active_subscriptions))  # type: ignore[union-attr]
        await session.unsubscribe(client_id)
        assert session._sub_mgr.get_subscription(client_id) is None  # type: ignore[union-attr]


async def test_double_start_raises(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect():
        with pytest.raises(RuntimeError):
            await ws._start()


async def test_subscribe_on_inactive_session_raises(
    perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    with pytest.raises(RuntimeError):
        await ws.subscribe("ticker")
