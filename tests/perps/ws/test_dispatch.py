"""Tests for PerpsMessageDispatcher — control routing, orphan/server unsubscribe."""

from __future__ import annotations

import asyncio

from kalshi.perps.config import PerpsConfig
from kalshi.perps.ws.channels import PerpsSubscriptionManager
from kalshi.perps.ws.connection import PerpsConnectionManager
from kalshi.perps.ws.dispatch import (
    CONTROL_TYPES,
    MESSAGE_MODELS,
    PerpsMessageDispatcher,
    classify_ok,
)
from kalshi.perps.ws.models.control import PerpsErrorResponse
from kalshi.perps.ws.orderbook import PerpsOrderbookManager
from kalshi.perps.ws.sequence import PerpsSequenceTracker

from .conftest import FakePerpsWS

# asyncio_mode = "auto" (pyproject) auto-collects the async tests; an explicit
# module-level asyncio mark would also (wrongly) tag the sync tests below.


def test_control_types_and_message_models() -> None:
    assert {"subscribed", "unsubscribed", "ok", "error"} == CONTROL_TYPES
    # #398 populated the type -> model registry; the seven data channels route here.
    assert set(MESSAGE_MODELS) >= {
        "orderbook_snapshot",
        "orderbook_delta",
        "ticker",
        "trade",
        "fill",
        "user_order",
        "order_group_updates",
    }


def test_classify_ok_branches_on_msg_shape() -> None:
    assert classify_ok({"type": "ok", "msg": []}) == "list_subscriptions"
    assert classify_ok({"type": "ok", "msg": {"market_tickers": []}}) == "update_ack"
    assert classify_ok({"type": "ok"}) == "update_ack"


async def test_error_frame_routes_to_on_error(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn = PerpsConnectionManager(auth=perps_auth, config=perps_ws_config)
    await conn.connect()
    sub_mgr = PerpsSubscriptionManager(conn)
    seen: list[PerpsErrorResponse] = []

    async def on_error(e: PerpsErrorResponse) -> None:
        seen.append(e)

    dispatcher = PerpsMessageDispatcher(sub_mgr=sub_mgr, on_error=on_error)
    await dispatcher.dispatch(
        {"type": "error", "id": 1, "msg": {"code": 7, "msg": "bad"}}
    )
    assert len(seen) == 1
    assert seen[0].msg.code == 7
    assert seen[0].msg.msg == "bad"
    await conn.close()


async def test_unknown_message_type_is_dropped(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn = PerpsConnectionManager(auth=perps_auth, config=perps_ws_config)
    await conn.connect()
    sub_mgr = PerpsSubscriptionManager(conn)
    dispatcher = PerpsMessageDispatcher(sub_mgr=sub_mgr)
    # No raise; an unregistered type just logs + returns. (Use a type that is
    # neither a CONTROL_TYPE nor in MESSAGE_MODELS — "ticker" is now registered.)
    await dispatcher.dispatch({"type": "not_a_real_channel", "sid": 1, "msg": {}})
    await conn.close()


async def test_server_unsubscribe_reaps_seq_and_orderbook(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn = PerpsConnectionManager(auth=perps_auth, config=perps_ws_config)
    await conn.connect()
    sub_mgr = PerpsSubscriptionManager(conn)
    seq = PerpsSequenceTracker()
    ob = PerpsOrderbookManager()
    dispatcher = PerpsMessageDispatcher(
        sub_mgr=sub_mgr, seq_tracker=seq, orderbook_mgr=ob
    )

    sub = await sub_mgr.subscribe("orderbook_delta", params={"market_tickers": ["X"]})
    sid = sub.server_sid
    assert sid is not None
    # Seed seq + orderbook state under the sid.
    seq.track_sync(sid, 1, "orderbook_delta")
    from kalshi.perps.ws.models.orderbook import MarginOrderbookSnapshotMessage

    snap = MarginOrderbookSnapshotMessage.model_validate(
        {
            "type": "orderbook_snapshot",
            "sid": sid,
            "seq": 1,
            "msg": {"market_ticker": "X", "bid": [["0.10", "5"]], "ask": []},
        }
    )
    ob._apply_snapshot_inplace(snap)
    assert ob.get("X") is not None

    await dispatcher._handle_server_unsubscribe(
        {"type": "unsubscribed", "sid": sid, "seq": 2}
    )
    assert sub_mgr.get_subscription_by_sid(sid) is None
    assert seq.peek(sid) is None
    assert ob.get("X") is None
    await conn.close()


async def test_orphan_subscribed_sends_unsubscribe(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    conn = PerpsConnectionManager(auth=perps_auth, config=perps_ws_config)
    await conn.connect()
    sub_mgr = PerpsSubscriptionManager(conn)
    dispatcher = PerpsMessageDispatcher(sub_mgr=sub_mgr)
    # Subscribed ack for a sid with no client mapping -> auto-unsubscribe.
    await dispatcher._handle_orphan_subscribed(
        {"type": "subscribed", "msg": {"channel": "ticker", "sid": 4242}}
    )
    assert 4242 in dispatcher._pending_orphan_unsub
    # The unsubscribe is best-effort fire-and-forget; yield so the fake server
    # reads it off the socket before we assert.
    await asyncio.sleep(0.1)
    cmd = fake_perps_ws.received_commands[-1]
    assert cmd["cmd"] == "unsubscribe"
    assert cmd["params"]["sids"] == [4242]
    await conn.close()
