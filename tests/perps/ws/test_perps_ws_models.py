"""Perps WS channel payload models: payload-parity, drift guard, behavior.

Loads the committed ``specs/perps_asyncapi.yaml`` and asserts each
``Margin*Message`` / ``OrderGroupUpdatesMessage`` model parses a frame built
from the schema's ``required`` fields (plus the inline ``orderGroupUpdates``
example), that decimals land as ``Decimal`` (not ``float``), and that a new
``required`` field on an owned payload schema the model lacks would fail
(drift guard). Per-channel behavior tests cover the happy/edge/error cases
from #398.

This is the WS analog of the REST ``TestRequestParamDrift`` — but for inbound
read models, so it asserts *required-coverage* (every spec-required field is
accepted by the model) rather than no-extra-kwargs (these models are
``extra="allow"``).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from kalshi.perps.ws.models.fill import MarginFillMessage, MarginFillPayload
from kalshi.perps.ws.models.order_group import (
    OrderGroupUpdatesMessage,
    OrderGroupUpdatesPayload,
)
from kalshi.perps.ws.models.orderbook import (
    MarginOrderbookDeltaMessage,
    MarginOrderbookDeltaPayload,
    MarginOrderbookSnapshotMessage,
    MarginOrderbookSnapshotPayload,
)
from kalshi.perps.ws.models.ticker import (
    FundingRate,
    MarginTickerMessage,
    MarginTickerPayload,
    TickerPrice,
)
from kalshi.perps.ws.models.trade import MarginTradeMessage, MarginTradePayload
from kalshi.perps.ws.models.user_orders import (
    MarginUserOrderMessage,
    MarginUserOrderPayload,
)

_SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "perps_asyncapi.yaml"


def _load_spec() -> dict[str, Any]:
    import yaml

    with _SPEC_PATH.open() as f:
        return yaml.safe_load(f)


# Owned envelope payload schema -> (envelope model, msg-payload model).
_PAYLOAD_MODELS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
    "marginOrderbookSnapshotPayload": (
        MarginOrderbookSnapshotMessage,
        MarginOrderbookSnapshotPayload,
    ),
    "marginOrderbookDeltaPayload": (
        MarginOrderbookDeltaMessage,
        MarginOrderbookDeltaPayload,
    ),
    "marginTickerPayload": (MarginTickerMessage, MarginTickerPayload),
    "marginTradePayload": (MarginTradeMessage, MarginTradePayload),
    "marginFillPayload": (MarginFillMessage, MarginFillPayload),
    "marginUserOrderPayload": (MarginUserOrderMessage, MarginUserOrderPayload),
    "orderGroupUpdatesPayload": (
        OrderGroupUpdatesMessage,
        OrderGroupUpdatesPayload,
    ),
}


def _accepted_names(model: type[BaseModel]) -> set[str]:
    """Every wire name the model accepts: field names + their validation aliases."""
    names: set[str] = set()
    for field_name, info in model.model_fields.items():
        names.add(field_name)
        alias = info.validation_alias
        if isinstance(alias, str):
            names.add(alias)
        elif alias is not None:
            # AliasChoices.choices is a list of str | AliasPath.
            for choice in getattr(alias, "choices", []):
                if isinstance(choice, str):
                    names.add(choice)
    return names


class TestPayloadDriftGuard:
    """Fail if the AsyncAPI marks a field ``required`` the model can't accept."""

    @pytest.mark.parametrize("schema_name", sorted(_PAYLOAD_MODELS))
    def test_required_msg_fields_covered(self, schema_name: str) -> None:
        spec = _load_spec()
        schema = spec["components"]["schemas"][schema_name]
        msg_schema = schema["properties"]["msg"]
        required = set(msg_schema.get("required", []))
        _envelope, payload_model = _PAYLOAD_MODELS[schema_name]
        accepted = _accepted_names(payload_model)
        missing = required - accepted
        assert not missing, (
            f"{payload_model.__name__} is missing spec-required field(s) "
            f"{sorted(missing)} on {schema_name}.msg"
        )

    @pytest.mark.parametrize("schema_name", sorted(_PAYLOAD_MODELS))
    def test_envelope_required_top_level_fields_covered(
        self, schema_name: str
    ) -> None:
        spec = _load_spec()
        schema = spec["components"]["schemas"][schema_name]
        required = set(schema.get("required", []))
        envelope_model, _payload = _PAYLOAD_MODELS[schema_name]
        accepted = _accepted_names(envelope_model)
        missing = required - accepted
        assert not missing, (
            f"{envelope_model.__name__} is missing spec-required envelope "
            f"field(s) {sorted(missing)} on {schema_name}"
        )

    def test_sequenced_envelopes_require_seq(self) -> None:
        # orderbook_* + order_group_updates mark seq required; ticker/trade/
        # fill/user_order do not.
        spec = _load_spec()
        for schema_name in (
            "marginOrderbookSnapshotPayload",
            "marginOrderbookDeltaPayload",
            "orderGroupUpdatesPayload",
        ):
            assert "seq" in spec["components"]["schemas"][schema_name]["required"]
        for schema_name in (
            "marginTickerPayload",
            "marginTradePayload",
            "marginFillPayload",
            "marginUserOrderPayload",
        ):
            assert "seq" not in spec["components"]["schemas"][schema_name][
                "required"
            ]


class TestOrderGroupExampleParity:
    """The spec ships an inline orderGroupLimitUpdated example — parse it.

    SPEC DISCREPANCY: the inline ``orderGroupLimitUpdated`` example omits
    ``ts_ms`` from its ``msg`` even though ``orderGroupUpdatesPayload.msg``
    marks ``ts_ms`` as ``required``. The model (correctly) follows the schema's
    required list, so this test back-fills the schema-required ``ts_ms`` the
    example left out and asserts that detail explicitly, rather than relaxing
    the model to match an incomplete example.
    """

    def test_inline_example_omits_required_ts_ms(self) -> None:
        spec = _load_spec()
        example = spec["components"]["messages"]["orderGroupUpdates"]["examples"][0][
            "payload"
        ]
        required = spec["components"]["schemas"]["orderGroupUpdatesPayload"][
            "properties"
        ]["msg"]["required"]
        # Documents the discrepancy: schema requires ts_ms, example omits it.
        assert "ts_ms" in required
        assert "ts_ms" not in example["msg"]

    def test_inline_example_validates_with_ts_ms_backfilled(self) -> None:
        spec = _load_spec()
        example = spec["components"]["messages"]["orderGroupUpdates"]["examples"][0][
            "payload"
        ]
        frame = {**example, "msg": {**example["msg"], "ts_ms": 1700000000000}}
        msg = OrderGroupUpdatesMessage.model_validate(frame)
        assert msg.type == "order_group_updates"
        assert msg.sid == 21
        assert msg.seq == 7
        assert msg.msg.event_type == "limit_updated"
        assert msg.msg.order_group_id == "og_123"
        assert msg.msg.contracts_limit == Decimal("150.00")
        assert isinstance(msg.msg.contracts_limit, Decimal)


# ---------------------------------------------------------------------------
# Per-channel behavior tests
# ---------------------------------------------------------------------------


class TestOrderbookDelta:
    def test_snapshot_levels_collapse_to_decimal_dicts(self) -> None:
        frame = {
            "type": "orderbook_snapshot",
            "sid": 1,
            "seq": 1,
            "msg": {
                "market_ticker": "BTC-PERP",
                "bid": [["100.5000", "10.00"], ["100.0000", "5.00"]],
                "ask": [["101.0000", "7.00"]],
            },
        }
        msg = MarginOrderbookSnapshotMessage.model_validate(frame)
        assert msg.msg.bid == {Decimal("100.5000"): Decimal("10.00"),
                               Decimal("100.0000"): Decimal("5.00")}
        assert msg.msg.ask == {Decimal("101.0000"): Decimal("7.00")}
        for k, v in msg.msg.bid.items():
            assert isinstance(k, Decimal) and isinstance(v, Decimal)

    def test_delta_bid_negative(self) -> None:
        frame = {
            "type": "orderbook_delta",
            "sid": 1,
            "seq": 2,
            "msg": {
                "market_ticker": "BTC-PERP",
                "price": "100.5000",
                "delta": "-3.00",
                "side": "bid",
                "ts_ms": 1700000000000,
            },
        }
        msg = MarginOrderbookDeltaMessage.model_validate(frame)
        assert msg.msg.side == "bid"
        assert msg.msg.delta == Decimal("-3.00")
        assert msg.msg.price == Decimal("100.5000")
        assert msg.msg.ts_ms == 1700000000000
        assert isinstance(msg.msg.ts_ms, int)

    def test_snapshot_omitted_sides_default_empty(self) -> None:
        # Perps allows a partial book (unlike equities #268 both-required).
        frame = {
            "type": "orderbook_snapshot",
            "sid": 1,
            "seq": 1,
            "msg": {"market_ticker": "BTC-PERP", "bid": [["100.0000", "5.00"]]},
        }
        msg = MarginOrderbookSnapshotMessage.model_validate(frame)
        assert msg.msg.bid == {Decimal("100.0000"): Decimal("5.00")}
        assert msg.msg.ask == {}

    def test_snapshot_both_sides_omitted_default_empty(self) -> None:
        frame = {
            "type": "orderbook_snapshot",
            "sid": 1,
            "seq": 1,
            "msg": {"market_ticker": "BTC-PERP"},
        }
        msg = MarginOrderbookSnapshotMessage.model_validate(frame)
        assert msg.msg.bid == {} and msg.msg.ask == {}

    def test_malformed_level_raises(self) -> None:
        frame = {
            "type": "orderbook_snapshot",
            "sid": 1,
            "seq": 1,
            "msg": {
                "market_ticker": "BTC-PERP",
                "bid": [["not-a-number", "10.00"]],
            },
        }
        with pytest.raises(ValidationError):
            MarginOrderbookSnapshotMessage.model_validate(frame)

    def test_snapshot_missing_seq_raises(self) -> None:
        frame = {
            "type": "orderbook_snapshot",
            "sid": 1,
            "msg": {"market_ticker": "BTC-PERP"},
        }
        with pytest.raises(ValidationError):
            MarginOrderbookSnapshotMessage.model_validate(frame)

    def test_delta_rejects_yes_side(self) -> None:
        frame = {
            "type": "orderbook_delta",
            "sid": 1,
            "seq": 2,
            "msg": {
                "market_ticker": "BTC-PERP",
                "price": "100.5000",
                "delta": "3.00",
                "side": "yes",
            },
        }
        with pytest.raises(ValidationError):
            MarginOrderbookDeltaMessage.model_validate(frame)

    def test_delta_last_update_reason_empty_string_ok(self) -> None:
        frame = {
            "type": "orderbook_delta",
            "sid": 1,
            "seq": 2,
            "msg": {
                "market_ticker": "BTC-PERP",
                "price": "100.5000",
                "delta": "3.00",
                "side": "ask",
                "last_update_reason": "",
            },
        }
        msg = MarginOrderbookDeltaMessage.model_validate(frame)
        assert msg.msg.last_update_reason == ""


class TestTicker:
    def _full_frame(self) -> dict[str, Any]:
        return {
            "type": "ticker",
            "sid": 2,
            "msg": {
                "market_ticker": "BTC-PERP",
                "price": "100.0000",
                "bid": "99.5000",
                "ask": "100.5000",
                "bid_size_fp": "10.00",
                "ask_size_fp": "12.00",
                "last_trade_size_fp": "1.00",
                "volume": "1000.00",
                "volume_24h": "5000.00",
                "open_interest": "200.00",
                "volume_notional_value_dollars": "100000.0000",
                "volume_24h_notional_value_dollars": "500000.0000",
                "open_interest_notional_value_dollars": "20000.0000",
                "reference_price": {"price": "100.1000", "ts_ms": 1700000000000},
                "settlement_mark_price": {"price": "100.2000", "ts_ms": 1700000000001},
                "liquidation_mark_price": {"price": "100.3000", "ts_ms": 1700000000002},
                "funding_rate": {
                    "rate": 0.0001,
                    "next_funding_time_ms": 1700003600000,
                    "ts_ms": 1700000000000,
                },
                "ts_ms": 1700000000000,
            },
        }

    def test_full_ticker_with_funding_and_marks(self) -> None:
        msg = MarginTickerMessage.model_validate(self._full_frame())
        assert msg.seq is None
        p = msg.msg
        assert p.price == Decimal("100.0000")
        assert p.bid == Decimal("99.5000") and p.ask == Decimal("100.5000")
        assert p.bid_size == Decimal("10.00")
        assert p.volume == Decimal("1000.00")
        assert p.volume_notional_value == Decimal("100000.0000")
        assert p.volume_24h_notional_value == Decimal("500000.0000")
        assert p.open_interest_notional_value == Decimal("20000.0000")
        assert isinstance(p.volume_notional_value, Decimal)
        assert isinstance(p.reference_price, TickerPrice)
        assert p.reference_price.price == Decimal("100.1000")
        assert isinstance(p.settlement_mark_price, TickerPrice)
        assert isinstance(p.liquidation_mark_price, TickerPrice)
        assert isinstance(p.funding_rate, FundingRate)
        # rate lands as Decimal, no binary-float drift.
        assert p.funding_rate.rate == Decimal("0.0001")
        assert isinstance(p.funding_rate.rate, Decimal)
        assert p.funding_rate.next_funding_time_ms == 1700003600000
        assert p.ts_ms == 1700000000000

    def test_ticker_marks_and_funding_absent_default_none(self) -> None:
        frame = self._full_frame()
        for key in (
            "reference_price",
            "settlement_mark_price",
            "liquidation_mark_price",
            "funding_rate",
        ):
            frame["msg"].pop(key)
        msg = MarginTickerMessage.model_validate(frame)
        assert msg.msg.reference_price is None
        assert msg.msg.settlement_mark_price is None
        assert msg.msg.liquidation_mark_price is None
        assert msg.msg.funding_rate is None
        assert msg.seq is None

    def test_ticker_missing_ts_ms_raises(self) -> None:
        frame = self._full_frame()
        frame["msg"].pop("ts_ms")
        with pytest.raises(ValidationError):
            MarginTickerMessage.model_validate(frame)

    def test_funding_rate_no_float_drift(self) -> None:
        # 0.65 as a JSON number must not commit to binary float at parse time.
        fr = FundingRate.model_validate(
            {"rate": 0.65, "next_funding_time_ms": 1, "ts_ms": 2}
        )
        assert fr.rate == Decimal("0.65")


class TestTrade:
    def test_happy(self) -> None:
        frame = {
            "type": "trade",
            "sid": 3,
            "msg": {
                "trade_id": "11111111-1111-1111-1111-111111111111",
                "market_ticker": "BTC-PERP",
                "price": "100.0000",
                "count": "5.00",
                "taker_side": "ask",
                "ts_ms": 1700000000000,
            },
        }
        msg = MarginTradeMessage.model_validate(frame)
        assert msg.msg.taker_side == "ask"
        assert msg.msg.count == Decimal("5.00")
        assert isinstance(msg.msg.count, Decimal)
        assert msg.msg.ts_ms == 1700000000000
        assert isinstance(msg.msg.ts_ms, int)
        assert msg.seq is None

    def test_rejects_equities_yes_taker_side(self) -> None:
        frame = {
            "type": "trade",
            "sid": 3,
            "msg": {
                "trade_id": "x",
                "market_ticker": "BTC-PERP",
                "price": "100.0000",
                "count": "5.00",
                "taker_side": "yes",
                "ts_ms": 1700000000000,
            },
        }
        with pytest.raises(ValidationError):
            MarginTradeMessage.model_validate(frame)


class TestFill:
    def _frame(self) -> dict[str, Any]:
        return {
            "type": "fill",
            "sid": 4,
            "msg": {
                "trade_id": "22222222-2222-2222-2222-222222222222",
                "order_id": "33333333-3333-3333-3333-333333333333",
                "market_ticker": "BTC-PERP",
                "is_taker": True,
                "side": "bid",
                "ts_ms": 1700000000000,
                "price": "100.0000",
                "count": "5.00",
                "fee_cost": "0.0500",
                "post_position": "15.00",
            },
        }

    def test_taker_fill_decimals(self) -> None:
        msg = MarginFillMessage.model_validate(self._frame())
        assert msg.msg.is_taker is True
        assert msg.msg.side == "bid"
        assert msg.msg.fee_cost == Decimal("0.0500")
        assert msg.msg.post_position == Decimal("15.00")
        assert isinstance(msg.msg.fee_cost, Decimal)
        assert msg.msg.client_order_id is None
        assert msg.msg.subaccount is None

    def test_optional_fields_present(self) -> None:
        frame = self._frame()
        frame["msg"]["client_order_id"] = "coid-1"
        frame["msg"]["subaccount"] = 7
        msg = MarginFillMessage.model_validate(frame)
        assert msg.msg.client_order_id == "coid-1"
        assert msg.msg.subaccount == 7

    def test_missing_post_position_raises(self) -> None:
        frame = self._frame()
        frame["msg"].pop("post_position")
        with pytest.raises(ValidationError):
            MarginFillMessage.model_validate(frame)


class TestUserOrders:
    def _frame(self) -> dict[str, Any]:
        return {
            "type": "user_order",
            "sid": 5,
            "msg": {
                "order_id": "44444444-4444-4444-4444-444444444444",
                "user_id": "55555555-5555-5555-5555-555555555555",
                "client_order_id": "coid-2",
                "ticker": "BTC-PERP",
                "side": "ask",
                "price": "100.0000",
                "fill_count": "2.00",
                "remaining_count": "8.00",
                "created_ts_ms": 1700000000000,
            },
        }

    def test_happy_with_group_and_stp(self) -> None:
        frame = self._frame()
        frame["msg"]["order_group_id"] = "og-1"
        frame["msg"]["self_trade_prevention_type"] = "maker"
        msg = MarginUserOrderMessage.model_validate(frame)
        assert msg.msg.order_group_id == "og-1"
        assert msg.msg.self_trade_prevention_type == "maker"

    def test_ticker_field_maps(self) -> None:
        # Field is ``ticker`` (NOT ``market_ticker``).
        msg = MarginUserOrderMessage.model_validate(self._frame())
        assert msg.msg.ticker == "BTC-PERP"
        assert msg.msg.expiration_ts_ms is None
        assert msg.msg.last_updated_ts_ms is None

    def test_missing_created_ts_ms_raises(self) -> None:
        frame = self._frame()
        frame["msg"].pop("created_ts_ms")
        with pytest.raises(ValidationError):
            MarginUserOrderMessage.model_validate(frame)

    def test_rejects_bad_stp(self) -> None:
        frame = self._frame()
        frame["msg"]["self_trade_prevention_type"] = "bogus"
        with pytest.raises(ValidationError):
            MarginUserOrderMessage.model_validate(frame)


class TestOrderGroup:
    def test_limit_updated_with_contracts_limit(self) -> None:
        frame = {
            "type": "order_group_updates",
            "sid": 6,
            "seq": 9,
            "msg": {
                "event_type": "limit_updated",
                "order_group_id": "og_123",
                "contracts_limit_fp": "150.00",
                "ts_ms": 1700000000000,
            },
        }
        msg = OrderGroupUpdatesMessage.model_validate(frame)
        assert msg.msg.event_type == "limit_updated"
        assert msg.msg.contracts_limit == Decimal("150.00")
        assert isinstance(msg.msg.contracts_limit, Decimal)

    def test_deleted_without_contracts_limit(self) -> None:
        frame = {
            "type": "order_group_updates",
            "sid": 6,
            "seq": 10,
            "msg": {
                "event_type": "deleted",
                "order_group_id": "og_123",
                "ts_ms": 1700000000000,
            },
        }
        msg = OrderGroupUpdatesMessage.model_validate(frame)
        assert msg.msg.contracts_limit is None

    def test_missing_seq_raises(self) -> None:
        frame = {
            "type": "order_group_updates",
            "sid": 6,
            "msg": {
                "event_type": "created",
                "order_group_id": "og_123",
                "ts_ms": 1700000000000,
            },
        }
        with pytest.raises(ValidationError):
            OrderGroupUpdatesMessage.model_validate(frame)

    def test_bad_event_type_raises(self) -> None:
        frame = {
            "type": "order_group_updates",
            "sid": 6,
            "seq": 9,
            "msg": {
                "event_type": "foo",
                "order_group_id": "og_123",
                "ts_ms": 1700000000000,
            },
        }
        with pytest.raises(ValidationError):
            OrderGroupUpdatesMessage.model_validate(frame)


class TestDispatcherRegistration:
    def test_message_models_registers_all_seven_types(self) -> None:
        from kalshi.perps.ws.dispatch import MESSAGE_MODELS

        assert {
            "orderbook_snapshot": MarginOrderbookSnapshotMessage,
            "orderbook_delta": MarginOrderbookDeltaMessage,
            "ticker": MarginTickerMessage,
            "trade": MarginTradeMessage,
            "fill": MarginFillMessage,
            "user_order": MarginUserOrderMessage,
            "order_group_updates": OrderGroupUpdatesMessage,
        } == MESSAGE_MODELS


class TestSubscribeHelpers:
    def test_six_typed_helpers_present(self) -> None:
        from kalshi.perps.ws.client import PerpsWebSocket

        for name in (
            "subscribe_orderbook_delta",
            "subscribe_ticker",
            "subscribe_trade",
            "subscribe_fill",
            "subscribe_user_orders",
            "subscribe_order_group",
        ):
            assert callable(getattr(PerpsWebSocket, name))

    def test_out_of_scope_channels_have_no_helpers(self) -> None:
        from kalshi.perps.ws.client import PerpsWebSocket

        for name in (
            "subscribe_market_positions",
            "subscribe_multivariate",
            "subscribe_multivariate_lifecycle",
            "subscribe_communications",
            "subscribe_market_lifecycle",
        ):
            assert not hasattr(PerpsWebSocket, name), (
                f"{name} has no perps counterpart and must not exist"
            )
