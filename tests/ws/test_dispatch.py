"""Tests for MessageDispatcher."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from kalshi.ws.backpressure import MessageQueue
from kalshi.ws.channels import Subscription
from kalshi.ws.dispatch import CONTROL_TYPES, MESSAGE_MODELS, MessageDispatcher
from kalshi.ws.models.event_fee import EventFeeUpdateMessage
from kalshi.ws.models.market_positions import MarketPositionsMessage
from kalshi.ws.models.multivariate import MultivariateMessage
from kalshi.ws.models.user_orders import UserOrdersMessage
from kalshi.ws.sequence import SequenceTracker
from tests._model_fixtures import (
    market_positions_payload_dict,
    ticker_payload_dict,
    user_orders_payload_dict,
)


class FakeSubManager:
    """Minimal subscription manager stub for dispatch testing."""

    def __init__(self) -> None:
        self._subs: dict[int, Subscription] = {}
        # Mirror the real manager so dispatcher's cleanup paths work.
        self._subscriptions: dict[int, Subscription] = self._subs
        self._sid_to_client: dict[int, int] = {}

    def add(
        self,
        sid: int,
        channel: str,
        *,
        client_id: int | None = None,
    ) -> Subscription:
        """Add a sub. ``client_id`` defaults to ``sid`` for simple tests, but
        can be passed distinct to exercise the production mapping path
        (server-assigned sid != client-side id).
        """
        cid = sid if client_id is None else client_id
        queue: MessageQueue[object] = MessageQueue(maxsize=100)
        sub = Subscription(client_id=cid, channel=channel, params={}, queue=queue)
        sub.server_sid = sid
        self._subs[cid] = sub
        self._sid_to_client[sid] = cid
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
            {
                "type": "ticker",
                "sid": 1,
                "msg": ticker_payload_dict(market_ticker="T", market_id="x"),
            }
        )
        await dispatcher.dispatch(json.loads(raw))
        msg = await sub.queue.get()
        assert msg.msg.market_ticker == "T"

    async def test_dispatch_pre_validated_skips_revalidation(self) -> None:
        """Regression for #86: when recv loop hands us the typed message it
        already validated, we must NOT re-run model_validate. The same
        instance lands on the queue.
        """
        from kalshi.ws.models.orderbook_delta import OrderbookSnapshotMessage

        mgr = FakeSubManager()
        sub = mgr.add(2, "orderbook_delta")
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        data = {
            "type": "orderbook_snapshot",
            "sid": 2,
            "seq": 1,
            "msg": {"market_ticker": "M", "market_id": "x", "yes": [], "no": []},
        }
        pre_validated = OrderbookSnapshotMessage.model_validate(data)
        await dispatcher.dispatch(data, pre_validated=pre_validated)
        delivered = await sub.queue.get()
        assert delivered is pre_validated, "dispatcher re-validated instead of using pre_validated"

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
        await dispatcher.dispatch(json.loads(raw))
        msg = await sub.queue.get()
        assert msg.type == "orderbook_snapshot"

    async def test_dispatch_unknown_type_no_crash(self) -> None:
        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps({"type": "future_type", "sid": 1, "msg": {}})
        await dispatcher.dispatch(json.loads(raw))  # should not crash

    async def test_dispatch_event_fee_update(self) -> None:
        """v3.20.0 (#385): event_fee_update rides the market_lifecycle_v2 channel."""
        mgr = FakeSubManager()
        sub = mgr.add(5, "market_lifecycle_v2")
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps(
            {
                "type": "event_fee_update",
                "sid": 5,
                "msg": {
                    "event_ticker": "KXBTCD-26MAY2018",
                    "fee_type_override": "quadratic",
                    "fee_multiplier_override": 1,
                },
            }
        )
        await dispatcher.dispatch(json.loads(raw))
        msg = await sub.queue.get()
        assert isinstance(msg, EventFeeUpdateMessage)
        assert msg.type == "event_fee_update"
        assert msg.msg.event_ticker == "KXBTCD-26MAY2018"
        assert msg.msg.fee_type_override == "quadratic"

    async def test_dispatch_event_fee_update_cleared(self) -> None:
        """Override cleared: both override fields arrive present-but-null."""
        mgr = FakeSubManager()
        sub = mgr.add(5, "market_lifecycle_v2")
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps(
            {
                "type": "event_fee_update",
                "sid": 5,
                "msg": {
                    "event_ticker": "KXBTCD-26MAY2018",
                    "fee_type_override": None,
                    "fee_multiplier_override": None,
                },
            }
        )
        await dispatcher.dispatch(json.loads(raw))
        msg = await sub.queue.get()
        assert isinstance(msg, EventFeeUpdateMessage)
        assert msg.msg.fee_type_override is None
        assert msg.msg.fee_multiplier_override is None

    async def test_dispatch_control_message_skipped(self) -> None:
        mgr = FakeSubManager()
        sub = mgr.add(1, "ticker")
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps({"type": "subscribed", "id": 1, "msg": {"channel": "ticker", "sid": 1}})
        await dispatcher.dispatch(json.loads(raw))
        assert sub.queue.qsize() == 0  # control messages don't go to queue

    async def test_dispatch_unknown_sid(self) -> None:
        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps(
            {
                "type": "ticker",
                "sid": 999,
                "msg": ticker_payload_dict(market_ticker="T", market_id="x"),
            }
        )
        await dispatcher.dispatch(json.loads(raw))  # should not crash

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
            {
                "type": "ticker",
                "sid": 1,
                "msg": ticker_payload_dict(market_ticker="T", market_id="x"),
            }
        )
        await dispatcher.dispatch(json.loads(raw))
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
            {
                "type": "ticker",
                "sid": 1,
                "msg": ticker_payload_dict(market_ticker="T", market_id="x"),
            }
        )
        await dispatcher.dispatch(json.loads(raw))
        await dispatcher.dispatch(json.loads(raw))

        # Both sinks observed both messages.
        assert len(received) == 2
        assert sub.queue.qsize() == 2

    async def test_register_callback_without_active_sub_no_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No warning when callback is registered before any subscription."""

        mgr = FakeSubManager()  # no subs

        async def cb(msg: object) -> None:
            return None

        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        with caplog.at_level(logging.WARNING, logger="kalshi.ws"):
            dispatcher.register_callback("ticker", cb)
        assert not any("active subscription exists" in r.message for r in caplog.records)

    async def test_error_callback(self) -> None:
        mgr = FakeSubManager()
        errors: list[object] = []

        async def on_error(err: object) -> None:
            errors.append(err)

        dispatcher = MessageDispatcher(sub_mgr=mgr, on_error=on_error)  # type: ignore[arg-type]
        raw = json.dumps({"type": "error", "id": 1, "msg": {"code": 5, "msg": "bad"}})
        await dispatcher.dispatch(json.loads(raw))
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
        await dispatcher.dispatch(json.loads(raw))
        assert len(errors) == 1

    async def test_channel_level_error_logged_when_no_handler(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Without on_error, a channel-level error is logged at WARNING (#82)."""

        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps({"type": "ticker", "sid": 1, "error": {"code": 7, "msg": "boom"}})
        with caplog.at_level(logging.WARNING, logger="kalshi.ws"):
            await dispatcher.dispatch(json.loads(raw))
        assert any("Channel-level error envelope" in r.message for r in caplog.records)

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
        await dispatcher.dispatch(json.loads(raw))
        assert len(errors) == 1

    async def test_null_error_field_not_misrouted(self) -> None:
        """Regression: `"error": null` on a typed envelope must parse normally.

        The dispatcher uses `data.get("error") is not None`, not
        `"error" in data`, so a legitimate optional error field set to null
        doesn't trip the channel-level-error path.
        """
        mgr = FakeSubManager()
        sub = mgr.add(1, "ticker")
        errors: list[object] = []

        async def on_error(err: object) -> None:
            errors.append(err)

        dispatcher = MessageDispatcher(sub_mgr=mgr, on_error=on_error)  # type: ignore[arg-type]
        raw = json.dumps(
            {
                "type": "ticker",
                "sid": 1,
                "error": None,
                "msg": ticker_payload_dict(market_ticker="T", market_id="x"),
            }
        )
        await dispatcher.dispatch(json.loads(raw))
        assert errors == [], "null error field misrouted as channel error"
        # Normal ticker flow happened: message landed on the queue.
        assert sub.queue.qsize() == 1

    async def test_channel_level_error_validation_failure_still_fires_handler(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If the error payload fails strict ErrorMessage validation, on_error
        still fires with a model_construct'd fallback so handlers always see
        a signal. The dispatcher also logs at ERROR (not WARNING) because a
        registered handler was almost-not-called.
        """
        mgr = FakeSubManager()
        errors: list[object] = []

        async def on_error(err: object) -> None:
            errors.append(err)

        dispatcher = MessageDispatcher(sub_mgr=mgr, on_error=on_error)  # type: ignore[arg-type]
        # Error field is a non-dict, non-string sentinel that fails ErrorPayload validation.
        raw = json.dumps({"type": "ticker", "sid": 1, "error": 42})
        with caplog.at_level(logging.ERROR, logger="kalshi.ws"):
            await dispatcher.dispatch(json.loads(raw))
        assert len(errors) == 1, "on_error not called on validation failure"
        assert any("failed strict ErrorMessage validation" in r.message for r in caplog.records)

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
            "event_fee_update",
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
            {
                "type": "ticker",
                "sid": 1,
                "msg": ticker_payload_dict(market_ticker="T", market_id="x"),
            }
        )
        await dispatcher.dispatch(json.loads(raw))
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
        await dispatcher.dispatch(json.loads(raw))

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
        await dispatcher.dispatch(json.loads(raw))

        assert 8 not in mgr._sid_to_client
        assert 8 not in mgr._subscriptions
        with pytest.raises(StopAsyncIteration):
            await sub.queue.get()

    async def test_server_unsubscribe_resets_seq_tracker(self) -> None:
        """If a SequenceTracker is wired in, reset(sid) is called."""

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
        await dispatcher.dispatch(json.loads(raw))

        assert 9 not in tracker._last_seq

    async def test_server_unsubscribe_with_distinct_client_id(self) -> None:
        """Server-assigned sid != client-side id is the production case.

        Exercises the two-step lookup: server's `sid` → `_sid_to_client[sid]`
        gives `client_id`, then `_subscriptions.pop(client_id)`. Collapsing
        sid == client_id (default) lets the test pass by accident even if
        the lookup is wrong.
        """
        mgr = FakeSubManager()
        sub = mgr.add(sid=500, channel="ticker", client_id=1)
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        assert 500 in mgr._sid_to_client
        assert 1 in mgr._subscriptions
        assert 500 not in mgr._subscriptions  # not keyed by server sid

        raw = json.dumps({"type": "unsubscribed", "msg": {"sid": 500}})
        await dispatcher.dispatch(json.loads(raw))

        assert 500 not in mgr._sid_to_client
        assert 1 not in mgr._subscriptions
        with pytest.raises(StopAsyncIteration):
            await sub.queue.get()

    async def test_server_unsubscribe_unknown_sid_no_crash(self) -> None:
        """A late/duplicate unsubscribed for an already-reaped sid is a no-op."""
        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        raw = json.dumps({"type": "unsubscribed", "msg": {"sid": 999}})
        await dispatcher.dispatch(json.loads(raw))  # should not crash

    async def test_dispatch_malformed_message_raises_for_seq_rollback(self) -> None:
        """#241: dispatch must propagate ValidationError so `_process_frame`
        can roll back the seq watermark for sequenced channels. Previously
        the dispatcher swallowed the error and returned, which silently
        advanced the watermark past a never-delivered frame.
        """
        from pydantic import ValidationError
        mgr = FakeSubManager()
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]
        # ticker requires `sid`; omitting it triggers ValidationError.
        raw = json.dumps(
            {"type": "ticker", "msg": ticker_payload_dict(market_ticker="T", market_id="x")}
        )
        with pytest.raises(ValidationError):
            await dispatcher.dispatch(json.loads(raw))

    async def test_orphan_subscribed_sends_unsubscribe(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """#268: A `subscribed` ack with no client_id mapping is the cancel-
        mid-subscribe race. The dispatcher must release the server-side sid
        by emitting an `unsubscribe` so the leak doesn't persist for the
        lifetime of the connection.
        """
        sent: list[dict[str, object]] = []

        class _FakeConnection:
            async def send(self, msg: dict[str, object]) -> None:
                sent.append(msg)

        mgr = FakeSubManager()
        mgr._connection = _FakeConnection()  # type: ignore[attr-defined]
        mgr._next_msg_id = 42  # type: ignore[attr-defined]

        def _get_msg_id() -> int:
            mid = mgr._next_msg_id  # type: ignore[attr-defined]
            mgr._next_msg_id += 1  # type: ignore[attr-defined]
            return mid

        mgr._get_msg_id = _get_msg_id  # type: ignore[attr-defined]
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]

        raw = json.dumps({"type": "subscribed", "id": 1, "msg": {"sid": 777}})
        with caplog.at_level(logging.WARNING, logger="kalshi.ws"):
            await dispatcher.dispatch(json.loads(raw))

        assert sent == [
            {"id": 42, "cmd": "unsubscribe", "params": {"sids": [777]}}
        ]
        assert any(
            "Orphan subscribed ack for sid=777" in rec.message
            for rec in caplog.records
        )

    async def test_orphan_subscribed_with_known_sid_is_noop(self) -> None:
        """When `subscribed` arrives for a sid already in _sid_to_client,
        the orphan handler must NOT send a spurious unsubscribe (#268).
        """
        sent: list[dict[str, object]] = []

        class _FakeConnection:
            async def send(self, msg: dict[str, object]) -> None:
                sent.append(msg)

        mgr = FakeSubManager()
        mgr.add(123, "ticker")
        mgr._connection = _FakeConnection()  # type: ignore[attr-defined]
        mgr._get_msg_id = lambda: 1  # type: ignore[attr-defined]
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]

        raw = json.dumps({"type": "subscribed", "id": 1, "msg": {"sid": 123}})
        await dispatcher.dispatch(json.loads(raw))
        assert sent == []

    async def test_orphan_subscribed_top_level_sid(self) -> None:
        """`subscribed` envelope can also carry sid at the top level (#268)."""
        sent: list[dict[str, object]] = []

        class _FakeConnection:
            async def send(self, msg: dict[str, object]) -> None:
                sent.append(msg)

        mgr = FakeSubManager()
        mgr._connection = _FakeConnection()  # type: ignore[attr-defined]
        mgr._get_msg_id = lambda: 99  # type: ignore[attr-defined]
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]

        raw = json.dumps({"type": "subscribed", "id": 1, "sid": 555})
        await dispatcher.dispatch(json.loads(raw))
        assert sent == [
            {"id": 99, "cmd": "unsubscribe", "params": {"sids": [555]}}
        ]

    async def test_orphan_subscribed_send_failure_swallowed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Send failure during orphan-unsubscribe is best-effort: log only,
        do not propagate (the socket is likely already gone) (#268).
        """

        class _BrokenConnection:
            async def send(self, msg: dict[str, object]) -> None:
                raise ConnectionError("socket closed")

        mgr = FakeSubManager()
        mgr._connection = _BrokenConnection()  # type: ignore[attr-defined]
        mgr._get_msg_id = lambda: 1  # type: ignore[attr-defined]
        dispatcher = MessageDispatcher(sub_mgr=mgr)  # type: ignore[arg-type]

        raw = json.dumps({"type": "subscribed", "id": 1, "msg": {"sid": 888}})
        with caplog.at_level(logging.WARNING, logger="kalshi.ws"):
            await dispatcher.dispatch(json.loads(raw))  # must not raise
        assert any(
            "Failed to send orphan-unsubscribe for sid=888" in rec.message
            for rec in caplog.records
        )


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
    raw = (
        '{"type":"user_order","sid":42,"msg":'
        + json.dumps(user_orders_payload_dict(order_id="ORD1"))
        + "}"
    )
    await dispatcher.dispatch(json.loads(raw))

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
    raw = (
        '{"type":"market_position","sid":42,"msg":'
        + json.dumps(market_positions_payload_dict(market_ticker="X"))
        + "}"
    )
    await dispatcher.dispatch(json.loads(raw))

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
    raw = (
        '{"type":"multivariate_lookup","sid":17,"msg":'
        + json.dumps(
            {
                "collection_ticker": "C1",
                "selected_markets": [],
                "market_ticker": "M1",
                "event_ticker": "E1",
            }
        )
        + "}"
    )
    await dispatcher.dispatch(json.loads(raw))

    msg = await asyncio.wait_for(sub.queue.get(), timeout=1.0)
    assert isinstance(msg, MultivariateMessage)


def test_message_models_multivariate_lookup_key() -> None:
    """MESSAGE_MODELS must key on the spec-correct singular type string."""
    assert "multivariate_lookup" in MESSAGE_MODELS
    # multivariate_market_lifecycle is sibling (different message type) -- must stay
    assert "multivariate_market_lifecycle" in MESSAGE_MODELS
    assert "multivariate" not in MESSAGE_MODELS  # the original short form, now replaced


@pytest.mark.asyncio
async def test_issue_354_orphan_unsubscribe_ack_does_not_clobber_reused_sid() -> None:
    """#354: An orphan-subscribe ack triggers an unsubscribe; the server's
    eventual ``unsubscribed`` for that orphan sid MUST NOT tear down state
    if the server has since reused the sid for a freshly-completed
    subscribe. The dispatcher correlates by tracking orphan unsubscribes
    in a pending set; the second ``unsubscribed`` arrives, sees the
    marker, and short-circuits without resetting the now-owned sid.
    """
    sent: list[dict[str, object]] = []

    class _FakeConnection:
        async def send(self, msg: dict[str, object]) -> None:
            sent.append(msg)

    mgr = FakeSubManager()
    mgr._connection = _FakeConnection()  # type: ignore[attr-defined]
    mgr._get_msg_id = lambda: 1  # type: ignore[attr-defined]
    tracker = SequenceTracker()
    dispatcher = MessageDispatcher(
        sub_mgr=mgr,  # type: ignore[arg-type]
        seq_tracker=tracker,
    )

    # Step 1: orphan subscribed for sid=42 — dispatcher marks it pending
    # and emits unsubscribe.
    await dispatcher.dispatch(
        {"type": "subscribed", "id": 1, "msg": {"sid": 42}}
    )
    assert 42 in dispatcher._pending_orphan_unsub
    assert sent and sent[-1]["params"] == {"sids": [42]}

    # Step 2: server reuses sid=42 for a new (legitimate) subscription;
    # client now owns it and the seq tracker has fresh state.
    new_sub = mgr.add(42, "orderbook_delta", client_id=99)
    tracker.track_sync(42, 5, "orderbook_delta")
    assert tracker.peek(42) == 5

    # Step 3: late ``unsubscribed`` for the orphan sid lands. The guard
    # must short-circuit instead of resetting the seq watermark or
    # popping the new mapping.
    await dispatcher.dispatch(
        {"type": "unsubscribed", "id": 0, "msg": {"sid": 42}}
    )
    assert 42 not in dispatcher._pending_orphan_unsub  # marker consumed
    assert mgr._sid_to_client.get(42) == 99  # mapping preserved
    assert tracker.peek(42) == 5  # seq state preserved
    assert new_sub.queue._closed is False  # iterator NOT terminated


@pytest.mark.asyncio
async def test_issue_354_legitimate_server_unsubscribe_still_tears_down() -> None:
    """#354 regression guard: the orphan-correlation guard MUST NOT
    short-circuit a legitimate server-initiated unsubscribe for a sid we
    own. The cleanup path (seq reset, sentinel) must still run.
    """
    mgr = FakeSubManager()
    sub = mgr.add(7, "orderbook_delta")
    tracker = SequenceTracker()
    tracker.track_sync(7, 3, "orderbook_delta")
    dispatcher = MessageDispatcher(
        sub_mgr=mgr,  # type: ignore[arg-type]
        seq_tracker=tracker,
    )

    await dispatcher.dispatch(
        {"type": "unsubscribed", "id": 0, "msg": {"sid": 7}}
    )

    assert 7 not in mgr._sid_to_client
    assert tracker.peek(7) is None  # seq state reset
    # Sentinel pushed so any iterator on `sub.queue` exits.
    assert sub.queue._closed is True
