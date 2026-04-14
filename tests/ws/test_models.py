"""Tests for WebSocket message models."""
from __future__ import annotations

from kalshi.ws.models.base import (
    BaseMessage,
    ErrorMessage,
    OkMessage,
    SubscribedMessage,
    UnsubscribedMessage,
)
from kalshi.ws.models.communications import (
    CommunicationsMessage,
    QuoteAcceptedPayload,
    QuoteExecutedPayload,
    RfqCreatedPayload,
)
from kalshi.ws.models.fill import FillMessage
from kalshi.ws.models.market_lifecycle import MarketLifecycleMessage
from kalshi.ws.models.market_positions import MarketPositionsMessage
from kalshi.ws.models.multivariate import (
    MultivariateLifecycleMessage,
    MultivariateMessage,
)
from kalshi.ws.models.order_group import OrderGroupMessage
from kalshi.ws.models.orderbook_delta import (
    OrderbookDeltaMessage,
    OrderbookSnapshotMessage,
)
from kalshi.ws.models.ticker import TickerMessage
from kalshi.ws.models.trade import TradeMessage
from kalshi.ws.models.user_orders import UserOrdersMessage


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


# ---------- Ticker ----------


class TestTickerModel:
    def test_parse_ticker(self) -> None:
        raw = {
            "type": "ticker",
            "sid": 1,
            "msg": {
                "market_ticker": "ECON-GDP-25Q1",
                "market_id": "abc-123",
                "yes_bid": 55,
                "yes_ask": 60,
                "no_bid": 40,
                "no_ask": 45,
                "volume": "1000",
                "open_interest": "500",
                "ts": 1700000000,
            },
        }
        msg = TickerMessage.model_validate(raw)
        assert msg.type == "ticker"
        assert msg.sid == 1
        assert msg.msg.market_ticker == "ECON-GDP-25Q1"
        assert msg.msg.yes_bid == 55
        assert msg.msg.yes_ask == 60
        assert msg.msg.volume == "1000"

    def test_ticker_no_seq(self) -> None:
        raw = {
            "type": "ticker",
            "sid": 1,
            "msg": {"market_ticker": "T", "market_id": "x"},
        }
        msg = TickerMessage.model_validate(raw)
        assert msg.seq is None

    def test_ticker_minimal_payload(self) -> None:
        raw = {
            "type": "ticker",
            "sid": 1,
            "msg": {"market_ticker": "T"},
        }
        msg = TickerMessage.model_validate(raw)
        assert msg.msg.market_id is None
        assert msg.msg.yes_bid is None
        assert msg.msg.no_ask is None

    def test_ticker_extra_fields(self) -> None:
        raw = {
            "type": "ticker",
            "sid": 1,
            "msg": {"market_ticker": "T", "new_field": "surprise"},
        }
        msg = TickerMessage.model_validate(raw)
        assert msg.msg.market_ticker == "T"


# ---------- Trade ----------


class TestTradeModel:
    def test_parse_trade(self) -> None:
        raw = {
            "type": "trade",
            "sid": 2,
            "msg": {
                "trade_id": "trade-001",
                "market_ticker": "ECON-GDP-25Q1",
                "yes_price": 55,
                "no_price": 45,
                "count": "10",
                "taker_side": "yes",
                "ts": 1700000000,
            },
        }
        msg = TradeMessage.model_validate(raw)
        assert msg.type == "trade"
        assert msg.sid == 2
        assert msg.msg.trade_id == "trade-001"
        assert msg.msg.yes_price == 55
        assert msg.msg.count == "10"

    def test_trade_no_seq(self) -> None:
        raw = {
            "type": "trade",
            "sid": 2,
            "msg": {"trade_id": "t1", "market_ticker": "T"},
        }
        msg = TradeMessage.model_validate(raw)
        assert msg.seq is None

    def test_trade_minimal(self) -> None:
        raw = {
            "type": "trade",
            "sid": 1,
            "msg": {"trade_id": "t1", "market_ticker": "T"},
        }
        msg = TradeMessage.model_validate(raw)
        assert msg.msg.yes_price is None
        assert msg.msg.taker_side is None


# ---------- Fill ----------


class TestFillModel:
    def test_parse_fill(self) -> None:
        raw = {
            "type": "fill",
            "sid": 3,
            "msg": {
                "trade_id": "fill-001",
                "order_id": "ord-123",
                "market_ticker": "ECON-GDP-25Q1",
                "is_taker": True,
                "side": "yes",
                "yes_price": 55,
                "count": "5",
                "fee_cost": "0.50",
                "action": "buy",
                "ts": 1700000000,
                "post_position": "10",
                "purchased_side": "yes",
            },
        }
        msg = FillMessage.model_validate(raw)
        assert msg.type == "fill"
        assert msg.msg.trade_id == "fill-001"
        assert msg.msg.is_taker is True
        assert msg.msg.yes_price == 55
        assert msg.msg.fee_cost == "0.50"
        assert msg.msg.action == "buy"

    def test_fill_no_seq(self) -> None:
        raw = {
            "type": "fill",
            "sid": 3,
            "msg": {"trade_id": "f1"},
        }
        msg = FillMessage.model_validate(raw)
        assert msg.seq is None

    def test_fill_with_subaccount(self) -> None:
        raw = {
            "type": "fill",
            "sid": 3,
            "msg": {
                "trade_id": "f1",
                "subaccount": 42,
                "client_order_id": "my-order",
            },
        }
        msg = FillMessage.model_validate(raw)
        assert msg.msg.subaccount == 42
        assert msg.msg.client_order_id == "my-order"


# ---------- MarketPositions ----------


class TestMarketPositionsModel:
    def test_parse_market_positions(self) -> None:
        raw = {
            "type": "market_positions",
            "sid": 4,
            "msg": {
                "user_id": "user-1",
                "market_ticker": "ECON-GDP-25Q1",
                "position": "100",
                "position_cost": "55.00",
                "realized_pnl": "10.50",
                "fees_paid": "1.25",
                "volume": "200",
            },
        }
        msg = MarketPositionsMessage.model_validate(raw)
        assert msg.type == "market_positions"
        assert msg.msg.market_ticker == "ECON-GDP-25Q1"
        assert msg.msg.position == "100"
        assert msg.msg.realized_pnl == "10.50"

    def test_market_positions_no_seq(self) -> None:
        raw = {
            "type": "market_positions",
            "sid": 4,
            "msg": {"market_ticker": "T"},
        }
        msg = MarketPositionsMessage.model_validate(raw)
        assert msg.seq is None

    def test_market_positions_with_subaccount(self) -> None:
        raw = {
            "type": "market_positions",
            "sid": 4,
            "msg": {"market_ticker": "T", "subaccount": 7},
        }
        msg = MarketPositionsMessage.model_validate(raw)
        assert msg.msg.subaccount == 7


# ---------- UserOrders ----------


class TestUserOrdersModel:
    def test_parse_user_orders(self) -> None:
        raw = {
            "type": "user_orders",
            "sid": 5,
            "msg": {
                "order_id": "ord-001",
                "user_id": "user-1",
                "ticker": "ECON-GDP-25Q1",
                "status": "resting",
                "side": "yes",
                "is_yes": True,
                "yes_price": 55,
                "fill_count": "3",
                "remaining_count": "7",
                "initial_count": "10",
                "taker_fill_cost": "1.65",
                "maker_fill_cost": "0.00",
                "taker_fees": "0.05",
                "maker_fees": "0.00",
                "created_time": "2025-01-01T00:00:00Z",
            },
        }
        msg = UserOrdersMessage.model_validate(raw)
        assert msg.type == "user_orders"
        assert msg.msg.order_id == "ord-001"
        assert msg.msg.status == "resting"
        assert msg.msg.is_yes is True
        assert msg.msg.yes_price == 55
        assert msg.msg.fill_count == "3"

    def test_user_orders_no_seq(self) -> None:
        raw = {
            "type": "user_orders",
            "sid": 5,
            "msg": {"order_id": "ord-001"},
        }
        msg = UserOrdersMessage.model_validate(raw)
        assert msg.seq is None

    def test_user_orders_canceled(self) -> None:
        raw = {
            "type": "user_orders",
            "sid": 5,
            "msg": {
                "order_id": "ord-002",
                "status": "canceled",
                "remaining_count": "0",
                "last_update_time": "2025-01-02T00:00:00Z",
            },
        }
        msg = UserOrdersMessage.model_validate(raw)
        assert msg.msg.status == "canceled"
        assert msg.msg.remaining_count == "0"


# ---------- OrderGroup ----------


class TestOrderGroupModel:
    def test_parse_order_group(self) -> None:
        raw = {
            "type": "order_group_updates",
            "sid": 6,
            "seq": 10,
            "msg": {
                "event_type": "created",
                "order_group_id": "og-001",
                "contracts_limit": "100",
            },
        }
        msg = OrderGroupMessage.model_validate(raw)
        assert msg.type == "order_group_updates"
        assert msg.seq == 10  # required seq
        assert msg.msg.event_type == "created"
        assert msg.msg.order_group_id == "og-001"

    def test_order_group_has_required_seq(self) -> None:
        """OrderGroupMessage is one of the few channels with required seq."""
        import pydantic
        import pytest

        raw = {
            "type": "order_group_updates",
            "sid": 6,
            # no seq — should fail
            "msg": {"event_type": "deleted", "order_group_id": "og-002"},
        }
        with pytest.raises(pydantic.ValidationError):
            OrderGroupMessage.model_validate(raw)

    def test_order_group_triggered(self) -> None:
        raw = {
            "type": "order_group_updates",
            "sid": 6,
            "seq": 11,
            "msg": {
                "event_type": "triggered",
                "order_group_id": "og-003",
            },
        }
        msg = OrderGroupMessage.model_validate(raw)
        assert msg.msg.event_type == "triggered"
        assert msg.msg.contracts_limit is None


# ---------- MarketLifecycle ----------


class TestMarketLifecycleModel:
    def test_parse_market_lifecycle_created(self) -> None:
        raw = {
            "type": "market_lifecycle_v2",
            "sid": 7,
            "msg": {
                "event_type": "created",
                "market_ticker": "ECON-GDP-25Q1",
                "event_ticker": "ECON-GDP",
                "title": "GDP Q1 2025",
                "open_ts": 1700000000,
                "close_ts": 1700100000,
            },
        }
        msg = MarketLifecycleMessage.model_validate(raw)
        assert msg.type == "market_lifecycle_v2"
        assert msg.msg.event_type == "created"
        assert msg.msg.title == "GDP Q1 2025"
        assert msg.msg.open_ts == 1700000000

    def test_market_lifecycle_no_seq(self) -> None:
        raw = {
            "type": "market_lifecycle_v2",
            "sid": 7,
            "msg": {"event_type": "activated", "market_ticker": "T"},
        }
        msg = MarketLifecycleMessage.model_validate(raw)
        assert msg.seq is None

    def test_market_lifecycle_determined(self) -> None:
        raw = {
            "type": "market_lifecycle_v2",
            "sid": 7,
            "msg": {
                "event_type": "determined",
                "market_ticker": "T",
                "result": "yes",
                "determination_ts": 1700200000,
            },
        }
        msg = MarketLifecycleMessage.model_validate(raw)
        assert msg.msg.result == "yes"
        assert msg.msg.determination_ts == 1700200000

    def test_market_lifecycle_settled(self) -> None:
        raw = {
            "type": "market_lifecycle_v2",
            "sid": 7,
            "msg": {
                "event_type": "settled",
                "market_ticker": "T",
                "settlement_value": "1.00",
                "settled_ts": 1700300000,
            },
        }
        msg = MarketLifecycleMessage.model_validate(raw)
        assert msg.msg.settlement_value == "1.00"
        assert msg.msg.settled_ts == 1700300000


# ---------- Multivariate ----------


class TestMultivariateModel:
    def test_parse_multivariate(self) -> None:
        raw = {
            "type": "multivariate",
            "sid": 8,
            "msg": {
                "collection_ticker": "COL-1",
                "event_ticker": "EVT-1",
                "selected_markets": [
                    {
                        "event_ticker": "EVT-1",
                        "market_ticker": "MKT-A",
                        "side": "yes",
                    },
                    {
                        "event_ticker": "EVT-1",
                        "market_ticker": "MKT-B",
                        "side": "no",
                    },
                ],
            },
        }
        msg = MultivariateMessage.model_validate(raw)
        assert msg.type == "multivariate"
        assert msg.msg.collection_ticker == "COL-1"
        assert len(msg.msg.selected_markets) == 2
        assert msg.msg.selected_markets[0].market_ticker == "MKT-A"
        assert msg.msg.selected_markets[1].side == "no"

    def test_multivariate_no_seq(self) -> None:
        raw = {
            "type": "multivariate",
            "sid": 8,
            "msg": {"collection_ticker": "COL-1"},
        }
        msg = MultivariateMessage.model_validate(raw)
        assert msg.seq is None

    def test_multivariate_empty_selected_markets(self) -> None:
        raw = {
            "type": "multivariate",
            "sid": 8,
            "msg": {"collection_ticker": "COL-1", "selected_markets": []},
        }
        msg = MultivariateMessage.model_validate(raw)
        assert msg.msg.selected_markets == []

    def test_multivariate_lifecycle(self) -> None:
        raw = {
            "type": "multivariate_market_lifecycle",
            "sid": 9,
            "msg": {
                "event_type": "created",
                "market_ticker": "MKT-A",
                "event_ticker": "EVT-1",
                "title": "Test Market",
            },
        }
        msg = MultivariateLifecycleMessage.model_validate(raw)
        assert msg.type == "multivariate_market_lifecycle"
        assert msg.msg.event_type == "created"
        assert msg.msg.title == "Test Market"


# ---------- Communications ----------


class TestCommunicationsModel:
    def test_parse_rfq_created(self) -> None:
        raw = {
            "type": "communications",
            "sid": 10,
            "msg": {
                "id": "rfq-001",
                "creator_id": "user-1",
                "market_ticker": "T",
                "created_ts": 1700000000,
                "contracts": "50",
                "target_cost": "25.00",
            },
        }
        msg = CommunicationsMessage.model_validate(raw)
        assert msg.type == "communications"
        assert msg.msg["id"] == "rfq-001"
        assert msg.msg["creator_id"] == "user-1"

    def test_communications_no_seq(self) -> None:
        raw = {
            "type": "communications",
            "sid": 10,
            "msg": {"id": "rfq-001"},
        }
        msg = CommunicationsMessage.model_validate(raw)
        assert msg.seq is None

    def test_parse_quote_created(self) -> None:
        raw = {
            "type": "communications",
            "sid": 10,
            "msg": {
                "quote_id": "q-001",
                "rfq_id": "rfq-001",
                "quote_creator_id": "user-2",
                "market_ticker": "T",
                "yes_bid": "0.55",
                "no_bid": "0.45",
                "created_ts": 1700000000,
            },
        }
        msg = CommunicationsMessage.model_validate(raw)
        assert msg.msg["quote_id"] == "q-001"

    def test_rfq_created_payload_model(self) -> None:
        """Test the typed RfqCreatedPayload for users who want to parse it."""
        payload = RfqCreatedPayload.model_validate(
            {
                "id": "rfq-001",
                "creator_id": "user-1",
                "market_ticker": "T",
                "contracts": "50",
            }
        )
        assert payload.id == "rfq-001"
        assert payload.contracts == "50"

    def test_quote_accepted_payload_model(self) -> None:
        payload = QuoteAcceptedPayload.model_validate(
            {
                "quote_id": "q-001",
                "rfq_id": "rfq-001",
                "accepted_side": "yes",
                "contracts_accepted": "10",
            }
        )
        assert payload.quote_id == "q-001"
        assert payload.accepted_side == "yes"

    def test_quote_executed_payload_model(self) -> None:
        payload = QuoteExecutedPayload.model_validate(
            {
                "quote_id": "q-001",
                "rfq_id": "rfq-001",
                "order_id": "ord-001",
                "executed_ts": 1700000000,
            }
        )
        assert payload.order_id == "ord-001"
        assert payload.executed_ts == 1700000000
