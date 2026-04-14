"""Tests for WebSocket message models."""
from __future__ import annotations

from kalshi.ws.models.base import (
    BaseMessage,
    ErrorMessage,
    OkMessage,
    SubscribedMessage,
    UnsubscribedMessage,
)
from kalshi.ws.models.orderbook_delta import (
    OrderbookDeltaMessage,
    OrderbookSnapshotMessage,
)


class TestBaseMessage:
    def test_parse_subscribed(self) -> None:
        raw = {"id": 1, "type": "subscribed", "msg": {"channel": "ticker", "sid": 5}}
        msg = SubscribedMessage.model_validate(raw)
        assert msg.id == 1
        assert msg.type == "subscribed"
        assert msg.msg.channel == "ticker"
        assert msg.msg.sid == 5

    def test_parse_unsubscribed(self) -> None:
        raw = {"id": 2, "sid": 5, "seq": 42, "type": "unsubscribed"}
        msg = UnsubscribedMessage.model_validate(raw)
        assert msg.sid == 5
        assert msg.seq == 42

    def test_parse_error(self) -> None:
        raw = {"id": 1, "type": "error", "msg": {"code": 5, "msg": "invalid channel"}}
        msg = ErrorMessage.model_validate(raw)
        assert msg.msg.code == 5
        assert msg.msg.msg == "invalid channel"

    def test_parse_ok(self) -> None:
        raw = {"id": 3, "type": "ok", "msg": [{"channel": "ticker", "sid": 1}]}
        msg = OkMessage.model_validate(raw)
        assert msg.type == "ok"
        assert isinstance(msg.msg, list)

    def test_base_message_extra_fields(self) -> None:
        raw = {"type": "ticker", "sid": 1, "msg": {"foo": "bar"}, "unknown_field": 99}
        msg = BaseMessage.model_validate(raw)
        assert msg.type == "ticker"


class TestOrderbookModels:
    def test_parse_snapshot(self) -> None:
        raw = {
            "type": "orderbook_snapshot",
            "sid": 3,
            "seq": 1,
            "msg": {
                "market_ticker": "ECON-GDP-25Q1",
                "market_id": "abc-123",
                "yes": [[50, 100], [55, 200]],
                "no": [[45, 150]],
            },
        }
        msg = OrderbookSnapshotMessage.model_validate(raw)
        assert msg.type == "orderbook_snapshot"
        assert msg.sid == 3
        assert msg.seq == 1
        assert msg.msg.market_ticker == "ECON-GDP-25Q1"
        assert len(msg.msg.yes) == 2
        assert msg.msg.yes[0] == [50, 100]

    def test_parse_delta(self) -> None:
        raw = {
            "type": "orderbook_delta",
            "sid": 3,
            "seq": 2,
            "msg": {
                "market_ticker": "ECON-GDP-25Q1",
                "market_id": "abc-123",
                "price": 55,
                "delta": 50,
                "side": "yes",
            },
        }
        msg = OrderbookDeltaMessage.model_validate(raw)
        assert msg.type == "orderbook_delta"
        assert msg.seq == 2
        assert msg.msg.price == 55
        assert msg.msg.delta == 50
        assert msg.msg.side == "yes"

    def test_snapshot_empty_book(self) -> None:
        raw = {
            "type": "orderbook_snapshot",
            "sid": 1,
            "seq": 1,
            "msg": {"market_ticker": "T", "market_id": "x", "yes": [], "no": []},
        }
        msg = OrderbookSnapshotMessage.model_validate(raw)
        assert msg.msg.yes == []
        assert msg.msg.no == []

    def test_delta_with_optional_fields(self) -> None:
        raw = {
            "type": "orderbook_delta",
            "sid": 3,
            "seq": 5,
            "msg": {
                "market_ticker": "T",
                "market_id": "x",
                "price": 50,
                "delta": -20,
                "side": "no",
                "client_order_id": "my-order",
                "ts": 1700000000,
            },
        }
        msg = OrderbookDeltaMessage.model_validate(raw)
        assert msg.msg.client_order_id == "my-order"
        assert msg.msg.ts == 1700000000
        assert msg.msg.delta == -20  # negative delta = removal
