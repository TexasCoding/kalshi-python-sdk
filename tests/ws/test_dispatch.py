"""Tests for MessageDispatcher."""
from __future__ import annotations

import asyncio
import json

import pytest

from kalshi.ws.backpressure import MessageQueue
from kalshi.ws.channels import Subscription
from kalshi.ws.dispatch import CONTROL_TYPES, MESSAGE_MODELS, MessageDispatcher
from kalshi.ws.models.market_positions import MarketPositionsMessage
from kalshi.ws.models.user_orders import UserOrdersMessage


class FakeSubManager:
    """Minimal subscription manager stub for dispatch testing."""

    def __init__(self) -> None:
        self._subs: dict[int, Subscription] = {}

    def add(self, sid: int, channel: str) -> Subscription:
        queue: MessageQueue[object] = MessageQueue(maxsize=100)
        sub = Subscription(client_id=sid, channel=channel, params={}, queue=queue)
        sub.server_sid = sid
        self._subs[sid] = sub
        return sub

    def get_subscription_by_sid(self, sid: int) -> Subscription | None:
        return self._subs.get(sid)


@pytest.mark.asyncio
class TestMessageDispatcher:
    async def test_dispatch_ticker(self) -> None:
        mgr = FakeSubManager()
        sub = mgr.add(1, "ticker")
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps(
            {"type": "ticker", "sid": 1, "msg": {"market_ticker": "T", "market_id": "x"}}
        )
        await dispatcher.dispatch(raw)
        msg = await sub.queue.get()
        assert msg.msg.market_ticker == "T"

    async def test_dispatch_orderbook_snapshot(self) -> None:
        mgr = FakeSubManager()
        sub = mgr.add(2, "orderbook_delta")
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps(
            {
                "type": "orderbook_snapshot",
                "sid": 2,
                "seq": 1,
                "msg": {"market_ticker": "M", "market_id": "x", "yes": [], "no": []},
            }
        )
        await dispatcher.dispatch(raw)
        msg = await sub.queue.get()
        assert msg.type == "orderbook_snapshot"

    async def test_dispatch_unknown_type_no_crash(self) -> None:
        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps({"type": "future_type", "sid": 1, "msg": {}})
        await dispatcher.dispatch(raw)  # should not crash

    async def test_dispatch_control_message_skipped(self) -> None:
        mgr = FakeSubManager()
        sub = mgr.add(1, "ticker")
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps(
            {"type": "subscribed", "id": 1, "msg": {"channel": "ticker", "sid": 1}}
        )
        await dispatcher.dispatch(raw)
        assert sub.queue.qsize() == 0  # control messages don't go to queue

    async def test_dispatch_invalid_json(self) -> None:
        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        await dispatcher.dispatch("not json at all")  # should not crash

    async def test_dispatch_unknown_sid(self) -> None:
        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps(
            {"type": "ticker", "sid": 999, "msg": {"market_ticker": "T", "market_id": "x"}}
        )
        await dispatcher.dispatch(raw)  # should not crash

    async def test_callback_mode(self) -> None:
        mgr = FakeSubManager()
        sub = mgr.add(1, "ticker")
        received: list[object] = []

        async def on_ticker(msg: object) -> None:
            received.append(msg)

        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        dispatcher.register_callback("ticker", on_ticker)
        raw = json.dumps(
            {"type": "ticker", "sid": 1, "msg": {"market_ticker": "T", "market_id": "x"}}
        )
        await dispatcher.dispatch(raw)
        assert len(received) == 1
        assert sub.queue.qsize() == 0  # callback consumed it, not queue

    async def test_error_callback(self) -> None:
        mgr = FakeSubManager()
        errors: list[object] = []

        async def on_error(err: object) -> None:
            errors.append(err)

        dispatcher = MessageDispatcher(sub_mgr=mgr, on_error=on_error)  # type: ignore[arg-type]
        raw = json.dumps({"type": "error", "id": 1, "msg": {"code": 5, "msg": "bad"}})
        await dispatcher.dispatch(raw)
        assert len(errors) == 1

    async def test_all_channel_types_have_models(self) -> None:
        """Verify every expected channel type is in the dispatch map."""
        expected = {
            "orderbook_snapshot",
            "orderbook_delta",
            "ticker",
            "trade",
            "fill",
            "market_position",
            "user_order",
            "order_group_updates",
            "market_lifecycle_v2",
            "multivariate",
            "multivariate_market_lifecycle",
            "communications",
        }
        assert expected == set(MESSAGE_MODELS.keys())

    async def test_control_types(self) -> None:
        assert {"subscribed", "unsubscribed", "ok", "error"} == CONTROL_TYPES

    async def test_unregister_callback(self) -> None:
        """Verify unregister_callback removes the callback and routes to queue."""
        mgr = FakeSubManager()
        sub = mgr.add(1, "ticker")
        received: list[object] = []

        async def on_ticker(msg: object) -> None:
            received.append(msg)

        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        dispatcher.register_callback("ticker", on_ticker)
        dispatcher.unregister_callback("ticker")

        raw = json.dumps(
            {"type": "ticker", "sid": 1, "msg": {"market_ticker": "T", "market_id": "x"}}
        )
        await dispatcher.dispatch(raw)
        assert len(received) == 0  # callback was removed
        assert sub.queue.qsize() == 1  # routed to queue instead

    async def test_dispatch_message_without_sid(self) -> None:
        """Messages without sid are logged but don't crash."""
        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps({"type": "ticker", "msg": {"market_ticker": "T", "market_id": "x"}})
        await dispatcher.dispatch(raw)  # should not crash


@pytest.mark.asyncio
async def test_dispatch_routes_user_order_singular() -> None:
    """Spec emits `type: user_order` (singular) on the user_orders channel.

    Regression guard: dispatcher must parse singular form and route to
    the user_orders subscription queue. Confirmed via live capture
    against demo on 2026-04-19.
    """
    mgr = FakeSubManager()
    sub = mgr.add(42, "user_orders")
    dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
    raw = '{"type":"user_order","sid":42,"msg":{"order_id":"ORD1"}}'
    await dispatcher.dispatch(raw)

    msg = await asyncio.wait_for(sub.queue.get(), timeout=1.0)
    assert isinstance(msg, UserOrdersMessage)
    assert msg.msg.order_id == "ORD1"


def test_message_models_user_order_key_is_singular() -> None:
    """MESSAGE_MODELS must key on the spec-correct singular type string."""
    assert "user_order" in MESSAGE_MODELS
    assert "user_orders" not in MESSAGE_MODELS


@pytest.mark.asyncio
async def test_dispatch_routes_market_position_singular() -> None:
    """Spec emits `type: market_position` (singular) on the market_positions channel.

    Regression guard: dispatcher must parse singular form. No direct live
    capture on demo 2026-04-19 (demo account had no open positions during
    the capture window), but aligns to the spec, matching the confirmed
    pattern on the user_orders sibling channel. See
    docs/superpowers/plans/2026-04-19-ws-parity-v0.14.0-capture-notes.md.
    """
    mgr = FakeSubManager()
    sub = mgr.add(42, "market_positions")
    dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
    raw = '{"type":"market_position","sid":42,"msg":{"ticker":"X","market_ticker":"X"}}'
    await dispatcher.dispatch(raw)

    msg = await asyncio.wait_for(sub.queue.get(), timeout=1.0)
    assert isinstance(msg, MarketPositionsMessage)


def test_message_models_market_position_key_is_singular() -> None:
    """MESSAGE_MODELS must key on the spec-correct singular type string."""
    assert "market_position" in MESSAGE_MODELS
    assert "market_positions" not in MESSAGE_MODELS
