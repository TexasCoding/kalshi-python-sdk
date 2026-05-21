"""Tests for WebSocket message models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from kalshi.models.orders import Fill, Order
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
    QuoteCreatedPayload,
    QuoteExecutedPayload,
    RfqCreatedPayload,
)
from kalshi.ws.models.fill import FillMessage, FillPayload
from kalshi.ws.models.market_lifecycle import MarketLifecycleMessage
from kalshi.ws.models.market_positions import MarketPositionsMessage, MarketPositionsPayload
from kalshi.ws.models.multivariate import (
    MultivariateLifecycleMessage,
    MultivariateMessage,
)
from kalshi.ws.models.order_group import OrderGroupMessage, OrderGroupPayload
from kalshi.ws.models.orderbook_delta import (
    OrderbookDeltaMessage,
    OrderbookSnapshotMessage,
)
from kalshi.ws.models.ticker import TickerMessage, TickerPayload
from kalshi.ws.models.trade import TradeMessage, TradePayload
from kalshi.ws.models.user_orders import UserOrdersMessage, UserOrdersPayload
from tests._model_fixtures import (
    fill_payload_dict,
    market_positions_payload_dict,
    ticker_payload_dict,
    trade_payload_dict,
    user_orders_payload_dict,
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
                "yes": [["0.50", "100.00"], ["0.55", "200.00"]],
                "no": [["0.45", "150.00"]],
            },
        }
        msg = OrderbookSnapshotMessage.model_validate(raw)
        assert msg.type == "orderbook_snapshot"
        assert msg.sid == 3
        assert msg.seq == 1
        assert msg.msg.market_ticker == "ECON-GDP-25Q1"
        assert len(msg.msg.yes) == 2
        assert msg.msg.yes[0] == (Decimal("0.50"), Decimal("100.00"))

    def test_parse_delta(self) -> None:
        raw = {
            "type": "orderbook_delta",
            "sid": 3,
            "seq": 2,
            "msg": {
                "market_ticker": "ECON-GDP-25Q1",
                "market_id": "abc-123",
                "price_dollars": "0.55",
                "delta_fp": "50",
                "side": "yes",
            },
        }
        msg = OrderbookDeltaMessage.model_validate(raw)
        assert msg.type == "orderbook_delta"
        assert msg.seq == 2
        assert msg.msg.price == Decimal("0.55")
        assert msg.msg.delta == Decimal("50")
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
                "price_dollars": "0.50",
                "delta_fp": "-20",
                "side": "no",
                "client_order_id": "my-order",
                "ts": "2026-04-19T18:43:37.662364Z",
            },
        }
        msg = OrderbookDeltaMessage.model_validate(raw)
        assert msg.msg.client_order_id == "my-order"
        assert msg.msg.ts == "2026-04-19T18:43:37.662364Z"
        assert msg.msg.delta == Decimal("-20")  # negative delta = removal


# ---------- Ticker ----------


class TestTickerModel:
    def test_parse_ticker(self) -> None:
        raw = {
            "type": "ticker",
            "sid": 1,
            "msg": ticker_payload_dict(
                market_ticker="ECON-GDP-25Q1",
                market_id="abc-123",
                yes_bid_dollars="0.55",
                yes_ask_dollars="0.60",
                volume_fp="1000",
                open_interest_fp="500",
                ts=1700000000,
            ),
        }
        msg = TickerMessage.model_validate(raw)
        assert msg.type == "ticker"
        assert msg.sid == 1
        assert msg.msg.market_ticker == "ECON-GDP-25Q1"
        assert msg.msg.yes_bid == Decimal("0.55")
        assert msg.msg.yes_ask == Decimal("0.60")
        assert msg.msg.volume == Decimal("1000")

    def test_ticker_no_seq(self) -> None:
        raw = {
            "type": "ticker",
            "sid": 1,
            "msg": ticker_payload_dict(market_ticker="T", market_id="x"),
        }
        msg = TickerMessage.model_validate(raw)
        assert msg.seq is None

    def test_ticker_missing_required_raises(self) -> None:
        """Post-#172: TickerPayload requires `yes_bid`, `yes_ask`, etc.
        A minimal payload omitting them must raise instead of defaulting to None."""
        raw = {"type": "ticker", "sid": 1, "msg": {"market_ticker": "T"}}
        with pytest.raises(ValidationError):
            TickerMessage.model_validate(raw)

    def test_ticker_extra_fields(self) -> None:
        """Extra fields are tolerated via `extra="allow"` on the envelope+payload."""
        raw = {
            "type": "ticker",
            "sid": 1,
            "msg": ticker_payload_dict(market_ticker="T", market_id="x", new_field="surprise"),
        }
        msg = TickerMessage.model_validate(raw)
        assert msg.msg.market_ticker == "T"

    def test_dollar_volume_and_open_interest_decimalized(self) -> None:
        """#258: dollar_volume/dollar_open_interest must coerce to Decimal (not str)."""
        raw = {
            "type": "ticker",
            "sid": 1,
            "msg": ticker_payload_dict(
                market_ticker="T",
                market_id="x",
                dollar_volume="123456.7890",
                dollar_open_interest="42.50",
            ),
        }
        msg = TickerMessage.model_validate(raw)
        assert isinstance(msg.msg.dollar_volume, Decimal)
        assert isinstance(msg.msg.dollar_open_interest, Decimal)
        assert msg.msg.dollar_volume == Decimal("123456.7890")
        assert msg.msg.dollar_open_interest == Decimal("42.50")
        # Arithmetic without manual Decimal(...) wrapping (#258 motivation).
        total = msg.msg.dollar_volume + msg.msg.dollar_open_interest
        assert total == Decimal("123499.2890")

    def test_dollar_fields_reject_bool(self) -> None:
        """#258: DollarDecimal coercion rejects bool (an int subclass)."""
        with pytest.raises(TypeError, match="bool"):
            TickerMessage.model_validate(
                {
                    "type": "ticker",
                    "sid": 1,
                    "msg": ticker_payload_dict(
                        market_ticker="T",
                        market_id="x",
                        dollar_volume=True,
                    ),
                }
            )


# ---------- Trade ----------


class TestTradeModel:
    def test_parse_trade(self) -> None:
        raw = {
            "type": "trade",
            "sid": 2,
            "msg": trade_payload_dict(
                trade_id="trade-001",
                market_ticker="ECON-GDP-25Q1",
                yes_price_dollars="0.55",
                no_price_dollars="0.45",
                count_fp="10",
                taker_side="yes",
                ts=1700000000,
            ),
        }
        msg = TradeMessage.model_validate(raw)
        assert msg.type == "trade"
        assert msg.sid == 2
        assert msg.msg.trade_id == "trade-001"
        assert msg.msg.yes_price == Decimal("0.55")
        assert msg.msg.count == Decimal("10")

    def test_trade_no_seq(self) -> None:
        raw = {
            "type": "trade",
            "sid": 2,
            "msg": trade_payload_dict(trade_id="t1", market_ticker="T"),
        }
        msg = TradeMessage.model_validate(raw)
        assert msg.seq is None

    def test_trade_missing_required_raises(self) -> None:
        """Post-#172: TradePayload requires yes_price/taker_side/etc.
        A minimal payload must raise instead of defaulting to None."""
        raw = {"type": "trade", "sid": 1, "msg": {"trade_id": "t1", "market_ticker": "T"}}
        with pytest.raises(ValidationError):
            TradeMessage.model_validate(raw)


# ---------- Fill ----------


class TestFillModel:
    def test_parse_fill(self) -> None:
        raw = {
            "type": "fill",
            "sid": 3,
            "msg": fill_payload_dict(
                trade_id="fill-001",
                order_id="ord-123",
                market_ticker="ECON-GDP-25Q1",
                is_taker=True,
                side="yes",
                yes_price_dollars="0.55",
                count_fp="5",
                fee_cost="0.50",
                action="buy",
                ts=1700000000,
                post_position_fp="10",
                purchased_side="yes",
            ),
        }
        msg = FillMessage.model_validate(raw)
        assert msg.type == "fill"
        assert msg.msg.trade_id == "fill-001"
        assert msg.msg.is_taker is True
        assert msg.msg.yes_price == Decimal("0.55")
        assert msg.msg.fee_cost == Decimal("0.50")
        assert msg.msg.action == "buy"

    def test_fill_no_seq(self) -> None:
        raw = {
            "type": "fill",
            "sid": 3,
            "msg": fill_payload_dict(trade_id="f1"),
        }
        msg = FillMessage.model_validate(raw)
        assert msg.seq is None

    def test_fill_with_subaccount(self) -> None:
        raw = {
            "type": "fill",
            "sid": 3,
            "msg": fill_payload_dict(
                trade_id="f1",
                subaccount=42,
                client_order_id="my-order",
            ),
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
            "msg": market_positions_payload_dict(
                user_id="user-1",
                market_ticker="ECON-GDP-25Q1",
                position_fp="100",
                position_cost_dollars="55.00",
                realized_pnl_dollars="10.50",
                fees_paid_dollars="1.25",
                volume_fp="200",
            ),
        }
        msg = MarketPositionsMessage.model_validate(raw)
        assert msg.type == "market_positions"
        assert msg.msg.market_ticker == "ECON-GDP-25Q1"
        assert msg.msg.position == Decimal("100")
        assert msg.msg.realized_pnl == Decimal("10.50")

    def test_market_positions_no_seq(self) -> None:
        raw = {
            "type": "market_positions",
            "sid": 4,
            "msg": market_positions_payload_dict(market_ticker="T"),
        }
        msg = MarketPositionsMessage.model_validate(raw)
        assert msg.seq is None

    def test_market_positions_with_subaccount(self) -> None:
        raw = {
            "type": "market_positions",
            "sid": 4,
            "msg": market_positions_payload_dict(
                market_ticker="T",
                subaccount=7,
            ),
        }
        msg = MarketPositionsMessage.model_validate(raw)
        assert msg.msg.subaccount == 7


# ---------- UserOrders ----------


class TestUserOrdersModel:
    def test_parse_user_orders(self) -> None:
        raw = {
            "type": "user_orders",
            "sid": 5,
            "msg": user_orders_payload_dict(
                order_id="ord-001",
                user_id="user-1",
                ticker="ECON-GDP-25Q1",
                status="resting",
                side="yes",
                is_yes=True,
                yes_price_dollars="0.55",
                fill_count_fp="3",
                remaining_count_fp="7",
                initial_count_fp="10",
                taker_fill_cost_dollars="1.65",
                maker_fill_cost_dollars="0.00",
                taker_fees_dollars="0.05",
                maker_fees_dollars="0.00",
                created_time="2025-01-01T00:00:00Z",
            ),
        }
        msg = UserOrdersMessage.model_validate(raw)
        assert msg.type == "user_orders"
        assert msg.msg.order_id == "ord-001"
        assert msg.msg.status == "resting"
        assert msg.msg.is_yes is True
        assert msg.msg.yes_price == Decimal("0.55")
        assert msg.msg.fill_count == Decimal("3")

    def test_user_orders_no_seq(self) -> None:
        raw = {
            "type": "user_orders",
            "sid": 5,
            "msg": user_orders_payload_dict(order_id="ord-001"),
        }
        msg = UserOrdersMessage.model_validate(raw)
        assert msg.seq is None

    def test_user_orders_canceled(self) -> None:
        raw = {
            "type": "user_orders",
            "sid": 5,
            "msg": user_orders_payload_dict(
                order_id="ord-002",
                status="canceled",
                remaining_count_fp="0",
                created_time="2025-01-02T00:00:00Z",
            ),
        }
        msg = UserOrdersMessage.model_validate(raw)
        assert msg.msg.status == "canceled"
        assert msg.msg.remaining_count == Decimal("0")


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
                "ts_ms": 1700000000000,
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
                "ts_ms": 1700000000000,
            },
        }
        msg = OrderGroupMessage.model_validate(raw)
        assert msg.msg.event_type == "triggered"
        assert msg.msg.contracts_limit is None

    def test_contracts_limit_decimalized_via_fp_alias(self) -> None:
        """#258: contracts_limit/_fp coerces to Decimal (was raw str pre-#258)."""
        raw = {
            "type": "order_group_updates",
            "sid": 6,
            "seq": 12,
            "msg": {
                "event_type": "limit_updated",
                "order_group_id": "og-004",
                "contracts_limit_fp": "250.50",
                "ts_ms": 1700000000000,
            },
        }
        msg = OrderGroupMessage.model_validate(raw)
        assert isinstance(msg.msg.contracts_limit, Decimal)
        assert msg.msg.contracts_limit == Decimal("250.50")
        assert msg.msg.contracts_limit * 2 == Decimal("501.00")

    def test_contracts_limit_rejects_bool(self) -> None:
        """#258: FixedPointCount coercion rejects bool (an int subclass)."""
        raw = {
            "type": "order_group_updates",
            "sid": 6,
            "seq": 13,
            "msg": {
                "event_type": "created",
                "order_group_id": "og-005",
                "contracts_limit": True,
                "ts_ms": 1700000000000,
            },
        }
        with pytest.raises(TypeError, match="bool"):
            OrderGroupMessage.model_validate(raw)


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
        assert msg.msg.settlement_value == Decimal("1.00")
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
                "market_ticker": "MKT-A",
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
        """`seq` is optional on this channel — full payload must still parse without it."""
        raw = {
            "type": "multivariate",
            "sid": 8,
            "msg": {
                "collection_ticker": "COL-1",
                "selected_markets": [],
                "market_ticker": "MKT-A",
                "event_ticker": "EVT-1",
            },
        }
        msg = MultivariateMessage.model_validate(raw)
        assert msg.seq is None

    def test_multivariate_missing_required_raises(self) -> None:
        """Post-#172: MultivariatePayload requires market_ticker / event_ticker.
        Omitting them must raise instead of leaving them None."""
        raw = {
            "type": "multivariate",
            "sid": 8,
            "msg": {"collection_ticker": "COL-1", "selected_markets": []},
        }
        with pytest.raises(ValidationError):
            MultivariateMessage.model_validate(raw)

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
                "created_ts": "2026-01-01T00:00:00Z",
                "contracts": "50",
            }
        )
        assert payload.id == "rfq-001"
        assert payload.contracts == Decimal("50")

    def test_quote_accepted_payload_model(self) -> None:
        payload = QuoteAcceptedPayload.model_validate(
            {
                "quote_id": "q-001",
                "rfq_id": "rfq-001",
                "quote_creator_id": "user-2",
                "market_ticker": "T",
                "yes_bid_dollars": "0.55",
                "no_bid_dollars": "0.45",
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
                "quote_creator_id": "user-2",
                "rfq_creator_id": "user-1",
                "client_order_id": "cli-001",
                "market_ticker": "T",
                "executed_ts": "2026-04-19T18:43:37Z",
            }
        )
        assert payload.order_id == "ord-001"
        assert payload.executed_ts == datetime(2026, 4, 19, 18, 43, 37, tzinfo=UTC)


# ---------- v0.14+ backfill (#162): one (de)serialization test per payload ----------


class TestWsV0140Backfill:
    """Verify the v0.14+ AsyncAPI backfill fields parse end-to-end.

    One assertion per payload covering at least one of the newly-added
    fields. Defaults-to-None paths are already exercised by the existing
    ``test_*_minimal`` tests in each per-payload class.
    """

    def test_ticker_price_and_ts_ms(self) -> None:
        msg = TickerMessage.model_validate(
            {
                "type": "ticker",
                "sid": 1,
                "msg": ticker_payload_dict(
                    market_ticker="T", price_dollars="0.5500", ts_ms=1700000000000
                ),
            }
        )
        assert msg.msg.price == Decimal("0.5500")
        assert msg.msg.ts_ms == 1700000000000

    def test_fill_outcome_book_side_and_ts_ms(self) -> None:
        msg = FillMessage.model_validate(
            {
                "type": "fill",
                "sid": 1,
                "msg": fill_payload_dict(
                    trade_id="t1",
                    outcome_side="yes",
                    book_side="bid",
                    ts_ms=1700000000000,
                ),
            }
        )
        assert msg.msg.outcome_side == "yes"
        assert msg.msg.book_side == "bid"
        assert msg.msg.ts_ms == 1700000000000

    def test_orderbook_delta_ts_ms(self) -> None:
        msg = OrderbookDeltaMessage.model_validate(
            {
                "type": "orderbook_delta",
                "sid": 1,
                "seq": 1,
                "msg": {
                    "market_ticker": "T",
                    "market_id": "x",
                    "price_dollars": "0.5500",
                    "delta_fp": "10.00",
                    "side": "yes",
                    "ts_ms": 1700000000000,
                },
            }
        )
        assert msg.msg.ts_ms == 1700000000000

    def test_trade_taker_outcome_book_side_and_ts_ms(self) -> None:
        msg = TradeMessage.model_validate(
            {
                "type": "trade",
                "sid": 1,
                "msg": trade_payload_dict(
                    trade_id="t1",
                    market_ticker="T",
                    taker_outcome_side="no",
                    taker_book_side="ask",
                    ts_ms=1700000000000,
                ),
            }
        )
        assert msg.msg.taker_outcome_side == "no"
        assert msg.msg.taker_book_side == "ask"
        assert msg.msg.ts_ms == 1700000000000

    def test_user_orders_outcome_book_stp_and_ts_ms_trio(self) -> None:
        msg = UserOrdersMessage.model_validate(
            {
                "type": "user_order",
                "sid": 1,
                "msg": user_orders_payload_dict(
                    order_id="o1",
                    outcome_side="yes",
                    book_side="bid",
                    self_trade_prevention_type="taker_at_cross",
                    created_ts_ms=1700000000000,
                    last_updated_ts_ms=1700000001000,
                    expiration_ts_ms=1700000002000,
                ),
            }
        )
        assert msg.msg.outcome_side == "yes"
        assert msg.msg.book_side == "bid"
        assert msg.msg.self_trade_prevention_type == "taker_at_cross"
        assert msg.msg.created_ts_ms == 1700000000000
        assert msg.msg.last_updated_ts_ms == 1700000001000
        assert msg.msg.expiration_ts_ms == 1700000002000

    def test_market_lifecycle_metadata_strike_structure_subtitle(self) -> None:
        msg = MarketLifecycleMessage.model_validate(
            {
                "type": "market_lifecycle_v2",
                "sid": 1,
                "msg": {
                    "event_type": "metadata_updated",
                    "market_ticker": "T",
                    "additional_metadata": {"title": "Updated", "rules_primary": "rules"},
                    "floor_strike": 50.5,
                    "price_level_structure": "linear_cent",
                    "yes_sub_title": "Will it happen?",
                },
            }
        )
        assert msg.msg.additional_metadata == {"title": "Updated", "rules_primary": "rules"}
        assert msg.msg.floor_strike == Decimal("50.5")
        assert msg.msg.price_level_structure == "linear_cent"
        assert msg.msg.yes_sub_title == "Will it happen?"

    def test_order_group_ts_ms(self) -> None:
        msg = OrderGroupMessage.model_validate(
            {
                "type": "order_group_updates",
                "sid": 1,
                "seq": 1,
                "msg": {
                    "event_type": "created",
                    "order_group_id": "g1",
                    "ts_ms": 1700000000000,
                },
            }
        )
        assert msg.msg.ts_ms == 1700000000000

    def test_rfq_created_mve_fields(self) -> None:
        payload = RfqCreatedPayload.model_validate(
            {
                "id": "rfq-1",
                "creator_id": "user-1",
                "market_ticker": "MKT-1",
                "created_ts": "2026-01-01T00:00:00Z",
                "mve_collection_ticker": "COLL-001",
                "mve_selected_legs": [
                    {"event_ticker": "EVT-1", "market_ticker": "MKT-1", "side": "yes"},
                ],
            }
        )
        assert payload.mve_collection_ticker == "COLL-001"
        assert payload.mve_selected_legs is not None
        assert payload.mve_selected_legs[0]["event_ticker"] == "EVT-1"

    def test_rfq_deleted_rfq_context(self) -> None:
        from kalshi.ws.models.communications import RfqDeletedPayload

        payload = RfqDeletedPayload.model_validate(
            {
                "id": "rfq-1",
                "creator_id": "user-1",
                "market_ticker": "MKT-1",
                "deleted_ts": "2026-01-01T00:00:00Z",
                "event_ticker": "EVT-1",
                "contracts_fp": "10.00",
                "target_cost_dollars": "5.5000",
            }
        )
        assert payload.event_ticker == "EVT-1"
        assert payload.contracts == Decimal("10.00")
        assert payload.target_cost == Decimal("5.5000")

    def test_quote_created_rfq_context(self) -> None:
        payload = QuoteCreatedPayload.model_validate(
            {
                "quote_id": "q-1",
                "quote_creator_id": "user-2",
                "rfq_id": "rfq-001",
                "created_ts": "2026-01-01T00:00:00Z",
                "market_ticker": "T",
                "yes_bid_dollars": "0.55",
                "no_bid_dollars": "0.45",
                "event_ticker": "EVT-1",
                "yes_contracts_offered_fp": "5.00",
                "no_contracts_offered_fp": "3.00",
                "rfq_target_cost_dollars": "1.5000",
            }
        )
        assert payload.event_ticker == "EVT-1"
        assert payload.yes_contracts_offered == Decimal("5.00")
        assert payload.no_contracts_offered == Decimal("3.00")
        assert payload.rfq_target_cost == Decimal("1.5000")

    def test_quote_accepted_rfq_context(self) -> None:
        payload = QuoteAcceptedPayload.model_validate(
            {
                "quote_id": "q-1",
                "quote_creator_id": "user-2",
                "rfq_id": "rfq-001",
                "market_ticker": "T",
                "yes_bid_dollars": "0.55",
                "no_bid_dollars": "0.45",
                "event_ticker": "EVT-1",
                "yes_contracts_offered_fp": "5.00",
                "no_contracts_offered_fp": "3.00",
                "rfq_target_cost_dollars": "1.5000",
            }
        )
        assert payload.event_ticker == "EVT-1"
        assert payload.yes_contracts_offered == Decimal("5.00")
        assert payload.no_contracts_offered == Decimal("3.00")
        assert payload.rfq_target_cost == Decimal("1.5000")


# ---------- #198: count/size/volume/timestamp type coercion ----------


class TestWsPayloadDecimalCoercion:
    """Counts/sizes/volumes parse as Decimal (FixedPointCount), not str.

    The wire format is unchanged — values still arrive as JSON strings — but
    the Pydantic BeforeValidator coerces them into Decimal so consumers
    don't have to manually wrap. Regression guard for #198.
    """

    def test_ticker_volume_parses_as_decimal_not_str(self) -> None:
        msg = TickerMessage.model_validate(
            {
                "type": "ticker",
                "sid": 1,
                "msg": ticker_payload_dict(
                    volume_fp="1000",
                    open_interest_fp="500",
                    yes_bid_size_fp="40",
                    yes_ask_size_fp="60",
                    last_trade_size_fp="7",
                ),
            }
        )
        assert isinstance(msg.msg.volume, Decimal)
        assert isinstance(msg.msg.open_interest, Decimal)
        assert isinstance(msg.msg.yes_bid_size, Decimal)
        assert isinstance(msg.msg.yes_ask_size, Decimal)
        assert isinstance(msg.msg.last_trade_size, Decimal)
        assert msg.msg.volume == Decimal("1000")

    def test_trade_count_parses_as_decimal(self) -> None:
        msg = TradeMessage.model_validate(
            {"type": "trade", "sid": 1, "msg": trade_payload_dict(count_fp="10")}
        )
        assert isinstance(msg.msg.count, Decimal)
        assert msg.msg.count == Decimal("10")

    def test_fill_count_post_position_parse_as_decimal(self) -> None:
        msg = FillMessage.model_validate(
            {
                "type": "fill",
                "sid": 1,
                "msg": fill_payload_dict(count_fp="5", post_position_fp="12"),
            }
        )
        assert isinstance(msg.msg.count, Decimal)
        assert isinstance(msg.msg.post_position, Decimal)
        assert msg.msg.count == Decimal("5")
        assert msg.msg.post_position == Decimal("12")

    def test_user_orders_counts_parse_as_decimal(self) -> None:
        msg = UserOrdersMessage.model_validate(
            {
                "type": "user_orders",
                "sid": 1,
                "msg": user_orders_payload_dict(
                    fill_count_fp="3",
                    remaining_count_fp="7",
                    initial_count_fp="10",
                ),
            }
        )
        assert isinstance(msg.msg.fill_count, Decimal)
        assert isinstance(msg.msg.remaining_count, Decimal)
        assert isinstance(msg.msg.initial_count, Decimal)
        assert msg.msg.fill_count + msg.msg.remaining_count == msg.msg.initial_count

    def test_market_positions_position_volume_parse_as_decimal(self) -> None:
        msg = MarketPositionsMessage.model_validate(
            {
                "type": "market_positions",
                "sid": 1,
                "msg": market_positions_payload_dict(position_fp="100", volume_fp="200"),
            }
        )
        assert isinstance(msg.msg.position, Decimal)
        assert isinstance(msg.msg.volume, Decimal)
        assert msg.msg.position == Decimal("100")
        assert msg.msg.volume == Decimal("200")

    def test_orderbook_snapshot_yes_no_parse_as_decimal_tuples(self) -> None:
        msg = OrderbookSnapshotMessage.model_validate(
            {
                "type": "orderbook_snapshot",
                "sid": 1,
                "seq": 1,
                "msg": {
                    "market_ticker": "T",
                    "market_id": "x",
                    "yes": [["0.50", "100.00"], ["0.55", "200.00"]],
                    "no": [["0.45", "150.00"]],
                },
            }
        )
        assert msg.msg.yes[0] == (Decimal("0.50"), Decimal("100.00"))
        assert isinstance(msg.msg.yes[0][0], Decimal)
        assert isinstance(msg.msg.yes[0][1], Decimal)
        assert isinstance(msg.msg.no[0][0], Decimal)
        assert isinstance(msg.msg.no[0][1], Decimal)

    def test_rfq_created_contracts_parses_as_decimal(self) -> None:
        payload = RfqCreatedPayload.model_validate(
            {
                "id": "rfq-1",
                "creator_id": "u1",
                "market_ticker": "T",
                "created_ts": "2026-01-01T00:00:00Z",
                "contracts_fp": "50",
            }
        )
        assert isinstance(payload.contracts, Decimal)
        assert payload.contracts == Decimal("50")

    def test_quote_accepted_contracts_accepted_parses_as_decimal(self) -> None:
        payload = QuoteAcceptedPayload.model_validate(
            {
                "quote_id": "q-1",
                "rfq_id": "rfq-1",
                "quote_creator_id": "u2",
                "market_ticker": "T",
                "yes_bid_dollars": "0.55",
                "no_bid_dollars": "0.45",
                "contracts_accepted_fp": "10",
            }
        )
        assert isinstance(payload.contracts_accepted, Decimal)
        assert payload.contracts_accepted == Decimal("10")


class TestWsPayloadDatetimeCoercion:
    """RFC3339 timestamps parse into tz-aware datetime, matching REST. Regression guard for #198."""

    def test_user_orders_timestamps_parse_as_datetime(self) -> None:
        msg = UserOrdersMessage.model_validate(
            {
                "type": "user_orders",
                "sid": 1,
                "msg": user_orders_payload_dict(
                    created_time="2026-01-01T00:00:00Z",
                    last_update_time="2026-01-02T00:00:00Z",
                    expiration_time="2026-01-03T00:00:00Z",
                ),
            }
        )
        assert isinstance(msg.msg.created_time, datetime)
        assert msg.msg.created_time == datetime(2026, 1, 1, tzinfo=UTC)
        assert isinstance(msg.msg.last_update_time, datetime)
        assert isinstance(msg.msg.expiration_time, datetime)

    def test_communications_timestamps_parse_as_datetime(self) -> None:
        rfq_created = RfqCreatedPayload.model_validate(
            {
                "id": "rfq-1",
                "creator_id": "u1",
                "market_ticker": "T",
                "created_ts": "2026-04-19T18:43:37Z",
            }
        )
        assert isinstance(rfq_created.created_ts, datetime)

        quote_created = QuoteCreatedPayload.model_validate(
            {
                "quote_id": "q-1",
                "rfq_id": "rfq-1",
                "quote_creator_id": "u2",
                "market_ticker": "T",
                "yes_bid_dollars": "0.55",
                "no_bid_dollars": "0.45",
                "created_ts": "2026-04-19T18:43:37Z",
            }
        )
        assert isinstance(quote_created.created_ts, datetime)

        quote_executed = QuoteExecutedPayload.model_validate(
            {
                "quote_id": "q-1",
                "rfq_id": "rfq-1",
                "order_id": "o1",
                "quote_creator_id": "u2",
                "rfq_creator_id": "u1",
                "client_order_id": "c1",
                "market_ticker": "T",
                "executed_ts": "2026-04-19T18:43:37Z",
            }
        )
        assert isinstance(quote_executed.executed_ts, datetime)


@pytest.mark.parametrize(
    "rest_field, ws_field",
    [
        # FixedPointCount symmetry on count fields
        (Fill.model_fields["count"].annotation, FillPayload.model_fields["count"].annotation),
        (
            Order.model_fields["initial_count"].annotation,
            UserOrdersPayload.model_fields["initial_count"].annotation,
        ),
        (
            Order.model_fields["remaining_count"].annotation,
            UserOrdersPayload.model_fields["remaining_count"].annotation,
        ),
        (
            Order.model_fields["fill_count"].annotation,
            UserOrdersPayload.model_fields["fill_count"].annotation,
        ),
        # DollarDecimal symmetry on price fields
        (
            Order.model_fields["yes_price"].annotation,
            UserOrdersPayload.model_fields["yes_price"].annotation,
        ),
        (
            Fill.model_fields["yes_price"].annotation,
            FillPayload.model_fields["yes_price"].annotation,
        ),
    ],
)
def test_rest_ws_field_type_symmetry(rest_field: object, ws_field: object) -> None:
    """REST and WS payloads MUST agree on the annotation for shared logical fields (#198)."""
    assert rest_field == ws_field


class TestOrderbookDeltaPayloadSideLiteral:
    """#221 P2.2: OrderbookDeltaPayload.side typed as Literal['yes','no']."""

    def test_orderbook_delta_payload_side_accepts_yes(self) -> None:
        from kalshi.ws.models.orderbook_delta import OrderbookDeltaPayload

        payload = OrderbookDeltaPayload.model_validate(
            {
                "market_ticker": "T",
                "market_id": "id",
                "price": "0.50",
                "delta": "10.00",
                "side": "yes",
            }
        )
        assert payload.side == "yes"

    def test_orderbook_delta_payload_side_accepts_no(self) -> None:
        from kalshi.ws.models.orderbook_delta import OrderbookDeltaPayload

        payload = OrderbookDeltaPayload.model_validate(
            {
                "market_ticker": "T",
                "market_id": "id",
                "price": "0.50",
                "delta": "10.00",
                "side": "no",
            }
        )
        assert payload.side == "no"

    def test_orderbook_delta_payload_side_rejects_invalid_string(self) -> None:
        from kalshi.ws.models.orderbook_delta import OrderbookDeltaPayload

        with pytest.raises(ValidationError):
            OrderbookDeltaPayload.model_validate(
                {
                    "market_ticker": "T",
                    "market_id": "id",
                    "price": "0.50",
                    "delta": "10.00",
                    "side": "maybe",
                }
            )

    def test_orderbook_delta_payload_side_rejects_trailing_whitespace(self) -> None:
        from kalshi.ws.models.orderbook_delta import OrderbookDeltaPayload

        with pytest.raises(ValidationError):
            OrderbookDeltaPayload.model_validate(
                {
                    "market_ticker": "T",
                    "market_id": "id",
                    "price": "0.50",
                    "delta": "10.00",
                    "side": "yes ",
                }
            )


# ---------- P2#3: populate_by_name across every WS payload model ----------

_SDK_NAME_PAYLOADS: list[tuple[type, dict[str, object]]] = [
    (
        TickerPayload,
        {
            "market_ticker": "MKT-A",
            "market_id": "mid-1",
            "yes_bid": Decimal("0.50"),
            "yes_ask": Decimal("0.51"),
            "volume": Decimal("100.00"),
            "open_interest": Decimal("200.00"),
            "dollar_volume": Decimal("50.00"),
            "dollar_open_interest": Decimal("100.00"),
            "yes_bid_size": Decimal("10.00"),
            "yes_ask_size": Decimal("10.00"),
            "last_trade_size": Decimal("1.00"),
            "ts": 1_700_000_000,
            "price": Decimal("0.5050"),
            "ts_ms": 1_700_000_000_000,
        },
    ),
    (
        FillPayload,
        {
            "trade_id": "t1",
            "order_id": "o1",
            "market_ticker": "MKT-A",
            "is_taker": True,
            "side": "yes",
            "yes_price": Decimal("0.50"),
            "count": Decimal("1.00"),
            "fee_cost": Decimal("0.01"),
            "action": "buy",
            "ts": 1_700_000_000,
            "post_position": Decimal("1.00"),
            "purchased_side": "yes",
            "outcome_side": "yes",
            "book_side": "bid",
            "ts_ms": 1_700_000_000_000,
        },
    ),
    (
        TradePayload,
        {
            "trade_id": "t1",
            "market_ticker": "MKT-A",
            "yes_price": Decimal("0.50"),
            "no_price": Decimal("0.50"),
            "count": Decimal("1.00"),
            "taker_side": "yes",
            "ts": 1_700_000_000,
            "taker_outcome_side": "yes",
            "taker_book_side": "bid",
            "ts_ms": 1_700_000_000_000,
        },
    ),
    (
        UserOrdersPayload,
        {
            "order_id": "o1",
            "user_id": "u1",
            "ticker": "MKT-A",
            "status": "resting",
            "side": "yes",
            "is_yes": True,
            "yes_price": Decimal("0.50"),
            "fill_count": Decimal("0.00"),
            "remaining_count": Decimal("10.00"),
            "initial_count": Decimal("10.00"),
            "taker_fill_cost": Decimal("0.00"),
            "maker_fill_cost": Decimal("0.00"),
            "taker_fees": Decimal("0.00"),
            "maker_fees": Decimal("0.00"),
            "client_order_id": "cid-1",
            "created_time": datetime(2026, 1, 1, tzinfo=UTC),
            "outcome_side": "yes",
            "book_side": "bid",
            "created_ts_ms": 1_700_000_000_000,
        },
    ),
    (
        MarketPositionsPayload,
        {
            "user_id": "u1",
            "market_ticker": "MKT-A",
            "position": Decimal("1.00"),
            "position_cost": Decimal("0.50"),
            "realized_pnl": Decimal("0.00"),
            "fees_paid": Decimal("0.00"),
            "position_fee_cost": Decimal("0.00"),
            "volume": Decimal("1.00"),
        },
    ),
    (
        OrderGroupPayload,
        {
            "event_type": "created",
            "order_group_id": "og-1",
            "contracts_limit": Decimal("10.00"),
            "ts_ms": 1_700_000_000_000,
        },
    ),
    (
        RfqCreatedPayload,
        {
            "id": "rfq-1",
            "creator_id": "u1",
            "market_ticker": "MKT-A",
            "created_ts": datetime(2026, 1, 1, tzinfo=UTC),
            "contracts": Decimal("100.00"),
            "target_cost": Decimal("50.00"),
        },
    ),
    (
        QuoteCreatedPayload,
        {
            "quote_id": "q-1",
            "rfq_id": "rfq-1",
            "quote_creator_id": "u2",
            "market_ticker": "MKT-A",
            "yes_bid": Decimal("0.50"),
            "no_bid": Decimal("0.50"),
            "created_ts": datetime(2026, 1, 1, tzinfo=UTC),
        },
    ),
]


@pytest.mark.parametrize(
    ("payload_cls", "kwargs"),
    _SDK_NAME_PAYLOADS,
    ids=lambda v: v.__name__ if isinstance(v, type) else "kwargs",
)
def test_ws_payload_constructable_with_sdk_field_names(
    payload_cls: type, kwargs: dict[str, object]
) -> None:
    """Every WS payload model accepts SDK (short) field names — populate_by_name=True."""
    payload = payload_cls(**kwargs)
    for key, value in kwargs.items():
        assert getattr(payload, key) == value, key


class TestMarketLifecycleFloorStrikeDecimal:
    """#259: WS MarketLifecyclePayload.floor_strike uses DollarDecimal."""

    def test_float_floor_strike_routed_through_str(self) -> None:
        raw = {
            "type": "market_lifecycle_v2",
            "sid": 1,
            "msg": {
                "event_type": "metadata_updated",
                "market_ticker": "T",
                "floor_strike": 95000.65,
            },
        }
        msg = MarketLifecycleMessage.model_validate(raw)
        assert isinstance(msg.msg.floor_strike, Decimal)
        assert msg.msg.floor_strike == Decimal("95000.65")

    def test_floor_strike_rejects_bool(self) -> None:
        raw = {
            "type": "market_lifecycle_v2",
            "sid": 1,
            "msg": {
                "event_type": "metadata_updated",
                "market_ticker": "T",
                "floor_strike": True,
            },
        }
        with pytest.raises(TypeError, match="bool"):
            MarketLifecycleMessage.model_validate(raw)
