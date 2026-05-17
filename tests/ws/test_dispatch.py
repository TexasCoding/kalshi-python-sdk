"""Tests for MessageDispatcher."""
from __future__ import annotations

import asyncio
import json

import pytest

from kalshi.ws.backpressure import MessageQueue
from kalshi.ws.channels import Subscription
from kalshi.ws.dispatch import CONTROL_TYPES, MESSAGE_MODELS, MessageDispatcher
from kalshi.ws.models.market_positions import MarketPositionsMessage
from kalshi.ws.models.multivariate import MultivariateMessage
from kalshi.ws.models.user_orders import UserOrdersMessage


class FakeSubManager:
    """Minimal subscription manager stub for dispatch testing."""

    def __init__(self) -> None:
        self._subs: dict[int, Subscription] = {}
        # Mirror the real manager so dispatcher's cleanup paths work.
        self._subscriptions: dict[int, Subscription] = self._subs
        self._sid_to_client: dict[int, int] = {}

    def add(self, sid: int, channel: str) -> Subscription:
        queue: MessageQueue[object] = MessageQueue(maxsize=100)
        sub = Subscription(client_id=sid, channel=channel, params={}, queue=queue)
        sub.server_sid = sid
        self._subs[sid] = sub
        self._sid_to_client[sid] = sid
        return sub

    def get_subscription_by_sid(self, sid: int) -> Subscription | None:
        client_id = self._sid_to_client.get(sid)
        if client_id is None:
            return None
        return self._subs.get(client_id)

    @property
    def active_subscriptions(self) -> dict[int, Subscription]:
        return dict(self._subs)


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
        """Callback AND queue both receive the message (fan-out, see #80)."""
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
        assert sub.queue.qsize() == 1  # also fanned out to the iterator queue

    async def test_callback_and_iterator_same_channel(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Regression for #80: callback + iterator on same channel.

        Both must receive every message; the iterator must not silently
        stop. A WARNING is logged at register time so the fan-out is not
        invisible.
        """
        import logging

        mgr = FakeSubManager()
        sub = mgr.add(1, "ticker")
        received: list[object] = []

        async def on_ticker(msg: object) -> None:
            received.append(msg)

        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        with caplog.at_level(logging.WARNING, logger="kalshi.ws"):
            dispatcher.register_callback("ticker", on_ticker)
        assert any("active subscription exists" in r.message for r in caplog.records)

        raw = json.dumps(
            {"type": "ticker", "sid": 1, "msg": {"market_ticker": "T", "market_id": "x"}}
        )
        await dispatcher.dispatch(raw)
        await dispatcher.dispatch(raw)

        # Both sinks observed both messages.
        assert len(received) == 2
        assert sub.queue.qsize() == 2

    async def test_register_callback_without_active_sub_no_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No warning when callback is registered before any subscription."""
        import logging

        mgr = FakeSubManager()  # no subs

        async def cb(msg: object) -> None:
            return None

        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        with caplog.at_level(logging.WARNING, logger="kalshi.ws"):
            dispatcher.register_callback("ticker", cb)
        assert not any(
            "active subscription exists" in r.message for r in caplog.records
        )

    async def test_error_callback(self) -> None:
        mgr = FakeSubManager()
        errors: list[object] = []

        async def on_error(err: object) -> None:
            errors.append(err)

        dispatcher = MessageDispatcher(sub_mgr=mgr, on_error=on_error)  # type: ignore[arg-type]
        raw = json.dumps({"type": "error", "id": 1, "msg": {"code": 5, "msg": "bad"}})
        await dispatcher.dispatch(raw)
        assert len(errors) == 1

    async def test_channel_level_error_routed_to_on_error(self) -> None:
        """Regression for #82: error semantics on a typed envelope reach on_error.

        Previously a message with type other than "error" but carrying an
        `error` payload fell through to the unknown-type log path and was
        silently dropped.
        """
        mgr = FakeSubManager()
        errors: list[object] = []

        async def on_error(err: object) -> None:
            errors.append(err)

        dispatcher = MessageDispatcher(sub_mgr=mgr, on_error=on_error)  # type: ignore[arg-type]
        raw = json.dumps(
            {
                "type": "ticker",
                "sid": 1,
                "error": {"code": 7, "msg": "schema violation"},
            }
        )
        await dispatcher.dispatch(raw)
        assert len(errors) == 1

    async def test_channel_level_error_logged_when_no_handler(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Without on_error, a channel-level error is logged at WARNING (#82)."""
        import logging

        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps(
            {"type": "ticker", "sid": 1, "error": {"code": 7, "msg": "boom"}}
        )
        with caplog.at_level(logging.WARNING, logger="kalshi.ws"):
            await dispatcher.dispatch(raw)
        assert any(
            "Channel-level error envelope" in r.message for r in caplog.records
        )

    async def test_channel_level_error_unrecognized_sid_still_surfaced(self) -> None:
        """Error with a sid the dispatcher no longer knows still reaches on_error."""
        mgr = FakeSubManager()  # no subs
        errors: list[object] = []

        async def on_error(err: object) -> None:
            errors.append(err)

        dispatcher = MessageDispatcher(sub_mgr=mgr, on_error=on_error)  # type: ignore[arg-type]
        raw = json.dumps(
            {
                "type": "ticker",
                "sid": 12345,  # post-unsubscribe race
                "error": {"code": 9, "msg": "stale sid"},
            }
        )
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
            "multivariate_lookup",
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

    async def test_server_unsubscribe_reaps_state(self) -> None:
        """Regression for #81: server-initiated unsubscribe reaps sid maps.

        Previously the dispatcher logged and dropped the unsubscribed
        envelope, leaking _sid_to_client entries. Now it must pop both
        the sid-mapping and the subscription, and push a sentinel so any
        held iterator exits cleanly.
        """
        mgr = FakeSubManager()
        sub = mgr.add(7, "ticker")
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        assert 7 in mgr._sid_to_client and 7 in mgr._subscriptions

        raw = json.dumps({"type": "unsubscribed", "msg": {"sid": 7}})
        await dispatcher.dispatch(raw)

        assert 7 not in mgr._sid_to_client
        assert 7 not in mgr._subscriptions

        # Held iterator exits cleanly via the pushed sentinel.
        with pytest.raises(StopAsyncIteration):
            await sub.queue.get()

    async def test_server_unsubscribe_top_level_sid(self) -> None:
        """Server can also send sid at the top level (UnsubscribedMessage shape)."""
        mgr = FakeSubManager()
        sub = mgr.add(8, "ticker")
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]

        raw = json.dumps({"type": "unsubscribed", "sid": 8, "seq": 0})
        await dispatcher.dispatch(raw)

        assert 8 not in mgr._sid_to_client
        assert 8 not in mgr._subscriptions
        with pytest.raises(StopAsyncIteration):
            await sub.queue.get()

    async def test_server_unsubscribe_resets_seq_tracker(self) -> None:
        """If a SequenceTracker is wired in, reset(sid) is called."""
        from kalshi.ws.sequence import SequenceTracker

        mgr = FakeSubManager()
        mgr.add(9, "orderbook_delta")
        tracker = SequenceTracker()
        # Seed the tracker as if a delta had been processed.
        await tracker.track(9, 5, "orderbook_delta")
        assert 9 in tracker._last_seq

        dispatcher = MessageDispatcher(
            sub_mgr=mgr,  # type: ignore[arg-type]
            seq_tracker=tracker,
        )
        raw = json.dumps({"type": "unsubscribed", "msg": {"sid": 9}})
        await dispatcher.dispatch(raw)

        assert 9 not in tracker._last_seq

    async def test_server_unsubscribe_unknown_sid_no_crash(self) -> None:
        """A late/duplicate unsubscribed for an already-reaped sid is a no-op."""
        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps({"type": "unsubscribed", "msg": {"sid": 999}})
        await dispatcher.dispatch(raw)  # should not crash

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
    pattern on the user_orders sibling channel.
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


@pytest.mark.asyncio
async def test_dispatch_routes_multivariate_lookup() -> None:
    """Spec emits `type: multivariate_lookup` on the multivariate channel.

    Regression guard. No direct live capture on demo (no active
    collections emitting); aligns to spec matching the user_orders
    pattern.
    """
    mgr = FakeSubManager()
    sub = mgr.add(17, "multivariate")
    dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
    raw = '{"type":"multivariate_lookup","sid":17,"msg":{"event_ticker":"E1"}}'
    await dispatcher.dispatch(raw)

    msg = await asyncio.wait_for(sub.queue.get(), timeout=1.0)
    assert isinstance(msg, MultivariateMessage)


def test_message_models_multivariate_lookup_key() -> None:
    """MESSAGE_MODELS must key on the spec-correct singular type string."""
    assert "multivariate_lookup" in MESSAGE_MODELS
    # multivariate_market_lifecycle is sibling (different message type) -- must stay
    assert "multivariate_market_lifecycle" in MESSAGE_MODELS
    assert "multivariate" not in MESSAGE_MODELS  # the original short form, now replaced
