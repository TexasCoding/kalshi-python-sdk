"""Tests for kalshi.types and model Decimal handling."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar

import pytest

from kalshi.models.communications import RFQ, Quote
from kalshi.models.events import Event, EventMetadata
from kalshi.models.historical import Trade
from kalshi.models.incentive_programs import IncentiveProgram
from kalshi.models.markets import Market
from kalshi.models.order_groups import (
    CreateOrderGroupResponse,
    GetOrderGroupResponse,
    OrderGroup,
)
from kalshi.models.orders import Fill, Order
from kalshi.models.portfolio import Settlement
from kalshi.types import to_decimal
from tests._model_fixtures import (
    candlestick_dict,
    create_order_group_response_dict,
    event_dict,
    event_metadata_dict,
    fill_dict,
    get_order_group_response_dict,
    incentive_program_dict,
    market_dict,
    order_dict,
    settlement_dict,
    trade_dict,
)


class TestToDecimal:
    def test_float_to_decimal(self) -> None:
        result = to_decimal(0.65)
        assert result == Decimal("0.65")
        assert isinstance(result, Decimal)

    def test_float_precision(self) -> None:
        """0.65 as float has representation issues. to_decimal avoids them."""
        result = to_decimal(0.65)
        # Decimal(0.65) would give 0.6499999999...
        # Decimal(str(0.65)) gives exactly 0.65
        assert str(result) == "0.65"

    def test_string_to_decimal(self) -> None:
        result = to_decimal("0.72")
        assert result == Decimal("0.72")

    def test_int_to_decimal(self) -> None:
        result = to_decimal(1)
        assert result == Decimal("1")

    def test_decimal_passthrough(self) -> None:
        d = Decimal("0.50")
        result = to_decimal(d)
        assert result is d


class TestDollarDecimalField:
    def test_market_parses_string_price(self) -> None:
        m = Market.model_validate(market_dict(ticker="T", yes_ask_dollars="0.65"))
        assert m.yes_ask == Decimal("0.65")
        assert isinstance(m.yes_ask, Decimal)

    def test_market_parses_float_price(self) -> None:
        m = Market.model_validate(market_dict(ticker="T", yes_bid_dollars=0.45))
        assert m.yes_bid == Decimal("0.45")

    def test_market_parses_int_price(self) -> None:
        m = Market.model_validate(market_dict(ticker="T", last_price_dollars=1))
        assert m.last_price == Decimal("1")

    def test_market_model_dump_serializes(self) -> None:
        m = Market.model_validate(market_dict(ticker="T", yes_ask_dollars="0.72"))
        # mode='python' preserves Decimal; mode='json' produces wire string.
        assert m.model_dump()["yes_ask"] == Decimal("0.72")
        assert m.model_dump(mode="json")["yes_ask"] == "0.72"

    def test_order_decimal_fields(self) -> None:
        o = Order.model_validate(
            order_dict(order_id="x", yes_price_dollars="0.65", no_price_dollars="0.35")
        )
        assert o.yes_price == Decimal("0.65")
        assert o.no_price == Decimal("0.35")


class TestMarketOccurrenceDatetime:
    """Round-trip the `occurrence_datetime` field added in spec v3.13.x.

    Nullable `date-time` field; must parse ISO-8601 strings to `datetime`
    and default to `None` when the server omits it.
    """

    def test_parses_iso_string(self) -> None:
        m = Market.model_validate(market_dict(occurrence_datetime="2026-01-15T10:30:00Z"))
        assert isinstance(m.occurrence_datetime, datetime)
        assert m.occurrence_datetime.year == 2026

    def test_absent_defaults_to_none(self) -> None:
        m = Market.model_validate(market_dict())
        assert m.occurrence_datetime is None


class TestDollarsAliasFields:
    """Verify models accept _dollars-suffixed field names from the API.

    The Kalshi API returns price fields with a '_dollars' suffix
    (e.g. 'yes_bid_dollars') as FixedPointDollars strings. The SDK
    uses shorter Python field names (e.g. 'yes_bid') with validation
    aliases to accept both formats.
    """

    def test_market_accepts_dollars_suffix(self) -> None:
        m = Market.model_validate(
            market_dict(
                yes_bid_dollars="0.4500",
                yes_ask_dollars="0.5500",
                no_bid_dollars="0.3000",
                no_ask_dollars="0.7000",
                last_price_dollars="0.5000",
            )
        )
        assert m.yes_bid == Decimal("0.4500")
        assert m.yes_ask == Decimal("0.5500")
        assert m.no_bid == Decimal("0.3000")
        assert m.no_ask == Decimal("0.7000")
        assert m.last_price == Decimal("0.5000")

    def test_market_accepts_bare_names(self) -> None:
        data = market_dict(yes_bid="0.45")
        data.pop("yes_bid_dollars")  # bare-name path requires absence of _dollars alias
        m = Market.model_validate(data)
        assert m.yes_bid == Decimal("0.45")

    def test_order_accepts_dollars_suffix(self) -> None:
        o = Order.model_validate(
            order_dict(
                yes_price_dollars="0.6500",
                no_price_dollars="0.3500",
                taker_fill_cost_dollars="6.5000",
                maker_fill_cost_dollars="0.0000",
                taker_fees_dollars="0.0650",
                maker_fees_dollars="0.0000",
            )
        )
        assert o.yes_price == Decimal("0.6500")
        assert o.no_price == Decimal("0.3500")
        assert o.taker_fill_cost == Decimal("6.5000")
        assert o.taker_fees == Decimal("0.0650")

    def test_order_type_populated_from_wire_field(self) -> None:
        """Regression: issue #91.

        Spec ``Order.type`` is renamed to ``order_type`` on the SDK side to
        avoid shadowing the Python builtin. The wire still sends ``type``;
        validation must keep populating ``order_type`` from it so callers
        actually see the value (previous dead-field state always returned
        ``None``).
        """
        o = Order.model_validate(order_dict(type="limit"))
        assert o.order_type == "limit"

    def test_order_type_accepts_python_name(self) -> None:
        """Pydantic ``populate_by_name`` keeps the SDK kwarg name working."""
        data = order_dict(order_type="market")
        data.pop("type")  # exercises the populate_by_name branch
        o = Order.model_validate(data)
        assert o.order_type == "market"

    def test_order_has_no_type_field(self) -> None:
        """The old ``type`` attribute is gone — callers must use ``order_type``."""
        assert "type" not in Order.model_fields
        assert "order_type" in Order.model_fields

    def test_fill_accepts_dollars_suffix(self) -> None:
        f = Fill.model_validate(
            fill_dict(
                yes_price_dollars="0.5000",
                no_price_dollars="0.5000",
            )
        )
        assert f.yes_price == Decimal("0.5000")
        assert f.no_price == Decimal("0.5000")

    def test_candlestick_nested_structure(self) -> None:
        from kalshi.models.markets import Candlestick

        c = Candlestick.model_validate(
            candlestick_dict(
                end_period_ts=1700000000,
                yes_bid={
                    "open_dollars": "0.4000",
                    "high_dollars": "0.5000",
                    "low_dollars": "0.3500",
                    "close_dollars": "0.4500",
                },
                price={
                    "open_dollars": "0.5000",
                    "close_dollars": "0.5500",
                },
                volume_fp="100.00",
            )
        )
        assert c.yes_bid.open == Decimal("0.4000")
        assert c.yes_bid.high == Decimal("0.5000")
        assert c.price.open == Decimal("0.5000")
        assert c.price.close == Decimal("0.5500")
        assert c.volume == Decimal("100.00")

    def test_create_order_serializes_with_dollars_alias(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="T",
            side="yes",
            action="buy",
            count=1,
            yes_price=Decimal("0.65"),
        )
        data = req.model_dump(mode="json", exclude_none=True, by_alias=True)
        assert "yes_price_dollars" in data
        assert data["yes_price_dollars"] == "0.65"
        assert "yes_price" not in data


class TestMarketV3180Fields:
    """v3.18.0 backfill (issue #159): 11 new optional fields on ``Market``.

    Spec adds direction-of-evolution fields (``price_level_structure`` /
    ``price_ranges`` superseding the deprecated ``response_price_units``)
    plus multivariate-event linkage and exchange-shard metadata.
    """

    def test_parses_all_new_scalar_fields(self) -> None:
        m = Market.model_validate(
            market_dict(
                ticker="T",
                early_close_condition="if_settled_early",
                exchange_index=7,
                fee_waiver_expiration_time="2026-06-01T00:00:00Z",
                functional_strike="x**2",
                is_provisional=True,
                mve_collection_ticker="COLL-001",
                price_level_structure="tick_5_cent",
                primary_participant_key="team-a",
            )
        )
        assert m.early_close_condition == "if_settled_early"
        assert m.exchange_index == 7
        assert m.fee_waiver_expiration_time is not None
        assert m.fee_waiver_expiration_time.year == 2026
        assert isinstance(m.fee_waiver_expiration_time, datetime)
        assert m.functional_strike == "x**2"
        assert m.is_provisional is True
        assert m.mve_collection_ticker == "COLL-001"
        assert m.price_level_structure == "tick_5_cent"
        assert m.primary_participant_key == "team-a"

    def test_parses_object_and_array_fields(self) -> None:
        m = Market.model_validate(
            market_dict(
                ticker="T",
                custom_strike={"yes_threshold": 50, "no_threshold": 100},
                mve_selected_legs=[
                    {"event_ticker": "EVT-001", "market_ticker": "MKT-001", "side": "yes"},
                ],
                price_ranges=[
                    {"start": "0.01", "end": "0.99", "step": "0.01"},
                ],
            )
        )
        assert m.custom_strike == {"yes_threshold": 50, "no_threshold": 100}
        assert m.mve_selected_legs is not None
        assert m.mve_selected_legs[0]["event_ticker"] == "EVT-001"
        assert m.price_ranges is not None
        assert m.price_ranges[0]["step"] == "0.01"

    def test_all_new_fields_default_to_none(self) -> None:
        m = Market.model_validate(market_dict(ticker="T"))
        for name in (
            "custom_strike",
            "early_close_condition",
            "exchange_index",
            "fee_waiver_expiration_time",
            "functional_strike",
            "is_provisional",
            "mve_collection_ticker",
            "mve_selected_legs",
            # NOTE: price_level_structure / price_ranges were optional in v3.18.0
            # but #172 promoted them to required-on-the-wire. They no longer
            # default to None; removed from this list.
            "primary_participant_key",
        ):
            assert getattr(m, name) is None, f"{name} should default to None"


class TestOrderV3180Fields:
    """v3.18.0 backfill (issue #159): 8 new optional fields on ``Order``.

    ``outcome_side`` / ``book_side`` are the canonical direction encoding
    going forward; the deprecated ``action`` field (allowlisted in #158)
    stays for back-compat. ``subaccount_number`` is distinct from the
    existing ``subaccount`` field.
    """

    def test_parses_outcome_and_book_side(self) -> None:
        o = Order.model_validate(
            order_dict(
                order_id="x",
                outcome_side="yes",
                book_side="bid",
            )
        )
        assert o.outcome_side == "yes"
        assert o.book_side == "bid"

    def test_parses_remaining_new_fields(self) -> None:
        o = Order.model_validate(
            order_dict(
                order_id="x",
                cancel_order_on_pause=True,
                exchange_index=3,
                last_update_time="2026-05-01T12:00:00Z",
                order_group_id="group-42",
                self_trade_prevention_type="taker_at_cross",
                subaccount_number=5,
            )
        )
        assert o.cancel_order_on_pause is True
        assert o.exchange_index == 3
        assert o.last_update_time is not None
        assert isinstance(o.last_update_time, datetime)
        assert o.order_group_id == "group-42"
        assert o.self_trade_prevention_type == "taker_at_cross"
        assert o.subaccount_number == 5

    def test_subaccount_number_is_distinct_from_subaccount(self) -> None:
        """``subaccount_number`` was added in v3.18.0 separately from the
        existing ``subaccount`` field. Both must coexist."""
        o = Order.model_validate(
            order_dict(
                order_id="x",
                subaccount=1,
                subaccount_number=5,
            )
        )
        assert o.subaccount == 1
        assert o.subaccount_number == 5

    def test_all_new_fields_default_to_none(self) -> None:
        o = Order.model_validate(order_dict(order_id="x"))
        for name in (
            # NOTE: outcome_side / book_side were optional in v3.18.0 but
            # #172 promoted them to required; they no longer default to None.
            "last_update_time",
            "self_trade_prevention_type",
            "order_group_id",
            "cancel_order_on_pause",
            "subaccount_number",
            "exchange_index",
        ):
            assert getattr(o, name) is None, f"{name} should default to None"


class TestFillV3180Fields:
    """v3.18.0 backfill (issue #159): 4 new optional fields on ``Fill``."""

    def test_parses_new_fields(self) -> None:
        f = Fill.model_validate(
            fill_dict(
                trade_id="t1",
                outcome_side="no",
                book_side="ask",
                subaccount_number=2,
                ts=1733047200000,
            )
        )
        assert f.outcome_side == "no"
        assert f.book_side == "ask"
        assert f.subaccount_number == 2
        assert f.ts == 1733047200000

    def test_ts_is_int_not_datetime(self) -> None:
        """Spec declares ``ts: integer`` (Unix-ms timestamp). The SDK must NOT
        coerce it to ``datetime`` — it's the legacy companion to the typed
        ``created_time: datetime`` field, and callers depend on the raw int."""
        f = Fill.model_validate(fill_dict(trade_id="t1", ts=1733047200000))
        assert f.ts == 1733047200000
        assert isinstance(f.ts, int)
        assert not isinstance(f.ts, bool)  # bools are ints; guard against ambiguity

    def test_all_new_fields_default_to_none(self) -> None:
        f = Fill.model_validate(fill_dict(trade_id="t1"))
        # NOTE: outcome_side / book_side were optional in v3.18.0 but
        # #172 promoted them to required; they no longer default to None.
        for name in ("subaccount_number", "ts"):
            assert getattr(f, name) is None, f"{name} should default to None"


class TestEventV3180Fields:
    """v3.18.0 backfill (issue #160): 3 new optional fields on ``Event``."""

    def test_parses_new_fields(self) -> None:
        e = Event.model_validate(
            event_dict(
                event_ticker="EVT-001",
                fee_type_override="quadratic",
                fee_multiplier_override="1.25",
                exchange_index=7,
            )
        )
        assert e.fee_type_override == "quadratic"
        assert e.fee_multiplier_override == Decimal("1.25")
        assert isinstance(e.fee_multiplier_override, Decimal)
        assert e.exchange_index == 7

    def test_all_new_fields_default_to_none(self) -> None:
        e = Event.model_validate(event_dict(event_ticker="EVT-001"))
        for name in ("fee_type_override", "fee_multiplier_override", "exchange_index"):
            assert getattr(e, name) is None, f"{name} should default to None"

    def test_parses_when_server_omits_product_metadata(self) -> None:
        """#183 regression: the live demo server omits `product_metadata` on most
        events even though spec marks it required. SDK must tolerate the omission
        instead of raising. Tracked via EXCLUSIONS server_omits_despite_required."""
        data = event_dict()
        data.pop("product_metadata")
        e = Event.model_validate(data)
        assert e.product_metadata is None


class TestEventMetadataV3180Fields:
    """v3.18.0 backfill (issue #160): 2 new optional fields on ``EventMetadata``."""

    def test_parses_new_fields(self) -> None:
        m = EventMetadata.model_validate(
            event_metadata_dict(
                competition="NBA Eastern Conference",
                competition_scope="playoffs",
            )
        )
        assert m.competition == "NBA Eastern Conference"
        assert m.competition_scope == "playoffs"

    def test_all_new_fields_default_to_none(self) -> None:
        m = EventMetadata.model_validate(event_metadata_dict())
        assert m.competition is None
        assert m.competition_scope is None

    def test_parses_when_server_sends_null_market_details(self) -> None:
        """#183 regression: the live demo server sends JSON null for
        `market_details` instead of a list. `NullableList` coerces null -> []
        so callers always see a list."""
        data = event_metadata_dict()
        data["market_details"] = None
        m = EventMetadata.model_validate(data)
        assert m.market_details == []


class TestSettlementV3180Fields:
    """v3.18.0 backfill (issue #160): 1 new optional field on ``Settlement``.

    ``value`` is integer cents per spec ("Payout of a single yes contract in
    cents") — NOT ``DollarDecimal``. Distinct from the existing
    ``yes_total_cost_dollars`` / ``no_total_cost_dollars`` fields.
    """

    def test_value_is_int_not_decimal(self) -> None:
        s = Settlement.model_validate(settlement_dict(ticker="T", value=100))
        assert s.value == 100
        assert isinstance(s.value, int)
        assert not isinstance(s.value, bool)  # bools are ints; guard

    def test_value_defaults_to_none(self) -> None:
        s = Settlement.model_validate(settlement_dict(ticker="T"))
        assert s.value is None


class TestTradeV3180Fields:
    """v3.18.0 backfill (issue #160): 2 new optional fields on ``Trade``.

    Mirrors ``Order.outcome_side`` / ``book_side`` from PR1 — canonical
    direction encoding superseding the deprecated ``taker_side``.
    """

    def test_parses_new_fields(self) -> None:
        t = Trade.model_validate(
            trade_dict(
                trade_id="tr-001",
                taker_outcome_side="yes",
                taker_book_side="bid",
            )
        )
        assert t.taker_outcome_side == "yes"
        assert t.taker_book_side == "bid"

    def test_taker_outcome_side_missing_raises(self) -> None:
        """Post-#172: ``taker_outcome_side`` / ``taker_book_side`` are required.
        Omitting them on parse must raise instead of defaulting to None."""
        from pydantic import ValidationError

        data = trade_dict()
        data.pop("taker_outcome_side")
        data.pop("taker_book_side")
        with pytest.raises(ValidationError):
            Trade.model_validate(data)


class TestIncentiveProgramV3180Fields:
    """v3.18.0 backfill (issue #160): 1 new optional field on ``IncentiveProgram``."""

    def test_parses_new_field(self) -> None:
        p = IncentiveProgram.model_validate(
            incentive_program_dict(
                id="ip-001",
                market_id="mkt-001",
                market_ticker="MKT-001",
                incentive_type="volume",
                start_date="2026-01-01T00:00:00Z",
                end_date="2026-02-01T00:00:00Z",
                period_reward=10000,
                paid_out=False,
                incentive_description="Liquidity provision rewards",
            )
        )
        assert p.incentive_description == "Liquidity provision rewards"

    def test_incentive_description_missing_raises(self) -> None:
        """Post-#172: ``incentive_description`` is required.
        Omitting it on parse must raise instead of defaulting to None."""
        from pydantic import ValidationError

        data = incentive_program_dict()
        data.pop("incentive_description")
        with pytest.raises(ValidationError):
            IncentiveProgram.model_validate(data)


class TestRFQV3180Fields:
    """v3.18.0 backfill (issue #161): 1 new optional field on ``RFQ``."""

    def test_parses_creator_subaccount(self) -> None:
        r = RFQ.model_validate(
            {
                "id": "rfq-1",
                "creator_id": "user-1",
                "market_ticker": "MKT",
                "contracts_fp": "10.00",
                "status": "open",
                "created_ts": "2026-05-01T00:00:00Z",
                "creator_subaccount": 3,
            }
        )
        assert r.creator_subaccount == 3

    def test_creator_subaccount_defaults_to_none(self) -> None:
        r = RFQ.model_validate(
            {
                "id": "rfq-1",
                "creator_id": "user-1",
                "market_ticker": "MKT",
                "contracts_fp": "10.00",
                "status": "open",
                "created_ts": "2026-05-01T00:00:00Z",
            }
        )
        assert r.creator_subaccount is None


class TestQuoteV3180Fields:
    """v3.18.0 backfill (issue #161): 3 new optional fields on ``Quote``."""

    _MINIMAL: ClassVar[dict[str, str]] = {
        "id": "q-1",
        "rfq_id": "rfq-1",
        "creator_id": "user-1",
        "rfq_creator_id": "user-2",
        "market_ticker": "MKT",
        "contracts_fp": "10.00",
        "yes_bid_dollars": "0.5500",
        "no_bid_dollars": "0.4500",
        "created_ts": "2026-05-01T00:00:00Z",
        "updated_ts": "2026-05-01T00:00:00Z",
        "status": "open",
    }

    def test_parses_all_new_fields(self) -> None:
        q = Quote.model_validate(
            self._MINIMAL
            | {
                "creator_subaccount": 3,
                "rfq_creator_subaccount": 5,
                "post_only": True,
            }
        )
        assert q.creator_subaccount == 3
        assert q.rfq_creator_subaccount == 5
        assert q.post_only is True

    def test_all_new_fields_default_to_none(self) -> None:
        q = Quote.model_validate(self._MINIMAL)
        assert q.creator_subaccount is None
        assert q.rfq_creator_subaccount is None
        assert q.post_only is None


class TestOrderGroupV3180Fields:
    """v3.18.0 backfill (issue #161): exchange_index on OrderGroup + responses."""

    def test_order_group_parses_exchange_index(self) -> None:
        g = OrderGroup.model_validate(
            {
                "id": "g-1",
                "is_auto_cancel_enabled": True,
                "exchange_index": 7,
            }
        )
        assert g.exchange_index == 7

    def test_order_group_exchange_index_defaults_to_none(self) -> None:
        g = OrderGroup.model_validate(
            {
                "id": "g-1",
                "is_auto_cancel_enabled": True,
            }
        )
        assert g.exchange_index is None

    def test_get_order_group_response_parses_exchange_index(self) -> None:
        r = GetOrderGroupResponse.model_validate(
            get_order_group_response_dict(
                is_auto_cancel_enabled=True,
                orders=["ord-1"],
                exchange_index=7,
            )
        )
        assert r.exchange_index == 7

    def test_create_order_group_response_parses_subaccount_and_exchange_index(self) -> None:
        """Server echoes the routing context (subaccount + shard) on create."""
        r = CreateOrderGroupResponse.model_validate(
            create_order_group_response_dict(
                order_group_id="g-1",
                subaccount=4,
                exchange_index=7,
            )
        )
        assert r.subaccount == 4
        assert r.exchange_index == 7

    def test_create_order_group_response_defaults_to_none(self) -> None:
        r = CreateOrderGroupResponse.model_validate(
            create_order_group_response_dict(order_group_id="g-1")
        )
        # NOTE: subaccount was optional in v3.18.0 but #172 promoted it to
        # required. exchange_index stays optional.
        assert r.exchange_index is None


class TestErrorHierarchy:
    def test_all_errors_inherit_base(self) -> None:
        from kalshi.errors import (
            KalshiAuthError,
            KalshiError,
            KalshiNotFoundError,
            KalshiRateLimitError,
            KalshiServerError,
            KalshiValidationError,
        )

        assert issubclass(KalshiAuthError, KalshiError)
        assert issubclass(KalshiNotFoundError, KalshiError)
        assert issubclass(KalshiRateLimitError, KalshiError)
        assert issubclass(KalshiValidationError, KalshiError)
        assert issubclass(KalshiServerError, KalshiError)

    def test_rate_limit_has_retry_after(self) -> None:
        from kalshi.errors import KalshiRateLimitError

        err = KalshiRateLimitError("too fast", retry_after=2.5)
        assert err.retry_after == 2.5

    def test_validation_has_details(self) -> None:
        from kalshi.errors import KalshiValidationError

        err = KalshiValidationError("bad input", details={"field": "required"})
        assert err.details == {"field": "required"}


class TestAmendOrderResponse:
    def test_parses_old_and_new_order(self) -> None:
        from kalshi.models.orders import AmendOrderResponse

        data = {
            "old_order": order_dict(
                order_id="ord-old",
                ticker="MKT-A",
                yes_price_dollars="0.5000",
                initial_count_fp=5,
            ),
            "order": order_dict(
                order_id="ord-new",
                ticker="MKT-A",
                yes_price_dollars="0.6500",
                initial_count_fp=5,
            ),
        }
        result = AmendOrderResponse.model_validate(data)
        assert result.old_order.order_id == "ord-old"
        assert result.order.order_id == "ord-new"
        assert result.old_order.yes_price == Decimal("0.5000")
        assert result.order.yes_price == Decimal("0.6500")


class TestOrderQueuePosition:
    def test_parses_queue_position(self) -> None:
        from kalshi.models.orders import OrderQueuePosition

        data = {
            "order_id": "ord-123",
            "market_ticker": "MKT-A",
            "queue_position_fp": "42.00",
        }
        result = OrderQueuePosition.model_validate(data)
        assert result.order_id == "ord-123"
        assert result.market_ticker == "MKT-A"
        assert result.queue_position == Decimal("42.00")


class TestCreateOrderRequestExtended:
    def test_accepts_time_in_force(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            count=1,
            time_in_force="fill_or_kill",
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["time_in_force"] == "fill_or_kill"

    def test_accepts_post_only_and_reduce_only(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            count=1,
            post_only=True,
            reduce_only=False,
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["post_only"] is True
        assert body["reduce_only"] is False

    def test_accepts_self_trade_prevention_and_order_group(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            count=1,
            self_trade_prevention_type="maker",
            order_group_id="grp-123",
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["self_trade_prevention_type"] == "maker"
        assert body["order_group_id"] == "grp-123"

    def test_accepts_cancel_on_pause_and_subaccount(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            count=1,
            cancel_order_on_pause=True,
            subaccount=5,
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["cancel_order_on_pause"] is True
        assert body["subaccount"] == 5

    def test_buy_max_cost_is_int_cents(self) -> None:
        """Spec says integer cents; SDK must send int on the wire."""
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            count=1,
            buy_max_cost=500,
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["buy_max_cost"] == 500
        assert isinstance(body["buy_max_cost"], int)

    def test_buy_max_cost_rejects_fractional_value(self) -> None:
        """A caller passing a fractional string like '5.5' must raise.

        Pydantic v2 int coercion rejects strings that are not whole numbers
        (e.g. '5.5'), but accepts whole-number strings like '500' and even
        '5.00' (coerced to 5). The field is int cents, so fractional values
        are always invalid.
        """
        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT",
                side="yes",
                action="buy",
                count=1,
                buy_max_cost="5.5",  # type: ignore[arg-type]
            )

    def test_buy_max_cost_rejects_decimal(self) -> None:
        """Migration-hazard guard: Decimal inputs raise clearly, not silently coerce."""
        from decimal import Decimal

        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        # Both whole and fractional Decimal values must raise — the hazard is
        # silent coercion to cents regardless of the numeric value.
        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT",
                side="yes",
                action="buy",
                count=1,
                buy_max_cost=Decimal("500"),  # type: ignore[arg-type]
            )
        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT",
                side="yes",
                action="buy",
                count=1,
                buy_max_cost=Decimal("5.00"),  # type: ignore[arg-type]
            )

    def test_buy_max_cost_rejects_float(self) -> None:
        """Float inputs (even whole-valued) must raise to prevent unit confusion."""
        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT",
                side="yes",
                action="buy",
                count=1,
                buy_max_cost=5.0,  # type: ignore[arg-type]
            )

    def test_buy_max_cost_rejects_bool(self) -> None:
        """#243: bool inputs must raise — bool is an ``int`` subclass, so
        ``True`` would otherwise slip through as ``1`` (= 1 cent cap), a
        silent money-risk failure matching the #225 class of bug for
        ``DollarDecimal`` / ``FixedPointCount``. A caller who passes a flag
        (``risk_check_passed``, ``dry_run``) where cents were expected must
        get a clear error, not a $0.01-capped order."""
        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        with pytest.raises(ValidationError, match=r"bool"):
            CreateOrderRequest(
                ticker="MKT",
                side="yes",
                action="buy",
                count=1,
                buy_max_cost=True,  # type: ignore[arg-type]
            )
        with pytest.raises(ValidationError, match=r"bool"):
            CreateOrderRequest(
                ticker="MKT",
                side="yes",
                action="buy",
                count=1,
                buy_max_cost=False,  # type: ignore[arg-type]
            )

    def test_buy_max_cost_accepts_plain_int(self) -> None:
        """#243: regression — plain int (cents) still works."""
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            count=1,
            buy_max_cost=500,
        )
        assert req.buy_max_cost == 500
        assert isinstance(req.buy_max_cost, int)
        assert not isinstance(req.buy_max_cost, bool)

    def test_buy_max_cost_accepts_int_string(self) -> None:
        """Int-shaped strings are coerced normally (e.g., loading from env/config)."""
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            count=1,
            buy_max_cost="500",  # type: ignore[arg-type]
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["buy_max_cost"] == 500

    def test_omits_none_fields_from_wire(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(ticker="MKT", side="yes", action="buy", count=1)
        body = req.model_dump(exclude_none=True, by_alias=True)
        # Core fields present
        assert body["ticker"] == "MKT"
        # Optional fields absent (defaults to None, stripped by exclude_none)
        assert "time_in_force" not in body
        assert "post_only" not in body
        assert "buy_max_cost" not in body
        assert "subaccount" not in body

    def test_phantom_type_field_removed(self) -> None:
        """v0.8.0 removed the phantom `type` field (spec has no such field)."""
        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT",
                side="yes",
                action="buy",
                count=1,
                type="limit",  # type: ignore[call-arg]
            )

    def test_forbid_extra_rejects_unknown_kwarg(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT",
                side="yes",
                action="buy",
                count=1,
                bogus_field="x",  # type: ignore[call-arg]
            )

    def test_serializes_count_fp_not_count(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            count=Decimal("7"),
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert "count_fp" in body
        assert "count" not in body


class TestAmendOrderRequest:
    def test_required_fields(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import AmendOrderRequest

        with pytest.raises(ValidationError):
            AmendOrderRequest()  # type: ignore[call-arg]

        # ticker/side/action required per spec
        req = AmendOrderRequest(ticker="MKT", side="yes", action="buy")
        assert req.ticker == "MKT"

    def test_serializes_yes_price_dollars(self) -> None:
        from decimal import Decimal

        from kalshi.models.orders import AmendOrderRequest

        req = AmendOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            yes_price=Decimal("0.55"),
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["yes_price_dollars"] == "0.55"
        assert "yes_price" not in body  # int cent form excluded

    def test_serializes_no_price_dollars(self) -> None:
        from decimal import Decimal

        from kalshi.models.orders import AmendOrderRequest

        req = AmendOrderRequest(
            ticker="MKT",
            side="no",
            action="sell",
            no_price=Decimal("0.75"),
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["no_price_dollars"] == "0.75"
        assert "no_price" not in body

    def test_serializes_count_fp(self) -> None:
        from decimal import Decimal

        from kalshi.models.orders import AmendOrderRequest

        req = AmendOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            count=Decimal("3"),
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert "count_fp" in body
        assert body["count_fp"] == "3"
        assert "count" not in body

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import AmendOrderRequest

        with pytest.raises(ValidationError):
            AmendOrderRequest(
                ticker="MKT",
                side="yes",
                action="buy",
                bogus_field="x",  # type: ignore[call-arg]
            )

    def test_accepts_client_order_ids(self) -> None:
        from kalshi.models.orders import AmendOrderRequest

        req = AmendOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            client_order_id="old-id",
            updated_client_order_id="new-id",
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["client_order_id"] == "old-id"
        assert body["updated_client_order_id"] == "new-id"

    def test_accepts_subaccount(self) -> None:
        from kalshi.models.orders import AmendOrderRequest

        req = AmendOrderRequest(
            ticker="MKT",
            side="yes",
            action="buy",
            subaccount=3,
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["subaccount"] == 3


class TestDecreaseOrderRequest:
    def test_accepts_reduce_by(self) -> None:
        from kalshi.models.orders import DecreaseOrderRequest

        req = DecreaseOrderRequest(reduce_by=3)
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body == {"reduce_by": 3}

    def test_accepts_reduce_to(self) -> None:
        from kalshi.models.orders import DecreaseOrderRequest

        req = DecreaseOrderRequest(reduce_to=2)
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body == {"reduce_to": 2}

    def test_accepts_subaccount(self) -> None:
        from kalshi.models.orders import DecreaseOrderRequest

        req = DecreaseOrderRequest(reduce_by=1, subaccount=4)
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["subaccount"] == 4

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import DecreaseOrderRequest

        with pytest.raises(ValidationError):
            DecreaseOrderRequest(
                reduce_by=1,
                bogus_field=5,  # type: ignore[call-arg]
            )

    def test_rejects_both_reduce_by_and_reduce_to(self) -> None:
        """Model rejects setting both fields — direct construction must match
        the method-level guard in ``orders.decrease()``.
        """
        from pydantic import ValidationError

        from kalshi.models.orders import DecreaseOrderRequest

        with pytest.raises(ValidationError, match="not both"):
            DecreaseOrderRequest(reduce_by=3, reduce_to=2)

    def test_rejects_neither_reduce_by_nor_reduce_to(self) -> None:
        """Model rejects the all-None case too: sending an empty decrease body
        is meaningless, so fail-fast at construction matches the method-level
        guard and keeps the v0.9 model-first API honest.
        """
        from pydantic import ValidationError

        from kalshi.models.orders import DecreaseOrderRequest

        with pytest.raises(ValidationError, match="reduce_by or reduce_to"):
            DecreaseOrderRequest()


class TestBatchCreateOrdersRequest:
    def test_wraps_order_list(self) -> None:
        from kalshi.models.orders import (
            BatchCreateOrdersRequest,
            CreateOrderRequest,
        )

        orders = [
            CreateOrderRequest(ticker="MKT-A", side="yes", action="buy", count=1),
            CreateOrderRequest(ticker="MKT-B", side="no", action="sell", count=1),
        ]
        req = BatchCreateOrdersRequest(orders=orders)
        body = req.model_dump(exclude_none=True, by_alias=True)

        assert "orders" in body
        assert len(body["orders"]) == 2
        assert body["orders"][0]["ticker"] == "MKT-A"
        assert body["orders"][1]["ticker"] == "MKT-B"

    def test_empty_list_allowed(self) -> None:
        from kalshi.models.orders import BatchCreateOrdersRequest

        req = BatchCreateOrdersRequest(orders=[])
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body == {"orders": []}

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import BatchCreateOrdersRequest

        with pytest.raises(ValidationError):
            BatchCreateOrdersRequest(
                orders=[],
                bogus=1,  # type: ignore[call-arg]
            )

    def test_nested_create_order_phantom_rejected(self) -> None:
        """Phantom key in a raw-dict nested order rejected via BatchCreateOrdersRequest.

        Constructs BatchCreateOrdersRequest with a raw dict item — Pydantic
        coerces into CreateOrderRequest and its extra='forbid' fires on the
        phantom. This exercises the BatchCreateOrdersRequest -> nested item
        path, not CreateOrderRequest's forbid in isolation (already covered
        by TestCreateOrderRequestExtended.test_forbid_extra).
        """
        from pydantic import ValidationError

        from kalshi.models.orders import BatchCreateOrdersRequest

        with pytest.raises(ValidationError):
            BatchCreateOrdersRequest(
                orders=[
                    {
                        "ticker": "MKT",
                        "side": "yes",
                        "action": "buy",
                        "type": "limit",  # phantom
                    },  # type: ignore[list-item]
                ],
            )


class TestCreateMarketInMultivariateRequest:
    def test_requires_selected_markets(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.multivariate import (
            CreateMarketInMultivariateEventCollectionRequest,
        )

        with pytest.raises(ValidationError):
            CreateMarketInMultivariateEventCollectionRequest()  # type: ignore[call-arg]

    def test_accepts_ticker_pair_items(self) -> None:
        from kalshi.models.multivariate import (
            CreateMarketInMultivariateEventCollectionRequest,
            TickerPair,
        )

        pair = TickerPair(event_ticker="E1", market_ticker="M1", side="yes")
        req = CreateMarketInMultivariateEventCollectionRequest(
            selected_markets=[pair],
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["selected_markets"][0]["event_ticker"] == "E1"

    def test_with_market_payload_optional(self) -> None:
        from kalshi.models.multivariate import (
            CreateMarketInMultivariateEventCollectionRequest,
            TickerPair,
        )

        pair = TickerPair(event_ticker="E1", market_ticker="M1", side="yes")
        req = CreateMarketInMultivariateEventCollectionRequest(
            selected_markets=[pair],
            with_market_payload=True,
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["with_market_payload"] is True

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.multivariate import (
            CreateMarketInMultivariateEventCollectionRequest,
            TickerPair,
        )

        pair = TickerPair(event_ticker="E1", market_ticker="M1", side="yes")
        with pytest.raises(ValidationError):
            CreateMarketInMultivariateEventCollectionRequest(
                selected_markets=[pair],
                bogus=1,  # type: ignore[call-arg]
            )


class TestLookupTickersRequest:
    def test_requires_selected_markets(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.multivariate import (
            LookupTickersForMarketInMultivariateEventCollectionRequest,
        )

        with pytest.raises(ValidationError):
            LookupTickersForMarketInMultivariateEventCollectionRequest()  # type: ignore[call-arg]

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.multivariate import (
            LookupTickersForMarketInMultivariateEventCollectionRequest,
            TickerPair,
        )

        pair = TickerPair(event_ticker="E1", market_ticker="M1", side="yes")
        with pytest.raises(ValidationError):
            LookupTickersForMarketInMultivariateEventCollectionRequest(
                selected_markets=[pair],
                bogus=1,  # type: ignore[call-arg]
            )


class TestBatchCancelOrdersRequest:
    def test_orders_field_required(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import BatchCancelOrdersRequest

        with pytest.raises(ValidationError):
            BatchCancelOrdersRequest()  # type: ignore[call-arg]

    def test_empty_orders_list_allowed(self) -> None:
        from kalshi.models.orders import BatchCancelOrdersRequest

        req = BatchCancelOrdersRequest(orders=[])
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body == {"orders": []}

    def test_wraps_order_entries(self) -> None:
        from kalshi.models.orders import (
            BatchCancelOrdersRequest,
            BatchCancelOrdersRequestOrder,
        )

        req = BatchCancelOrdersRequest(
            orders=[
                BatchCancelOrdersRequestOrder(order_id="ord-1"),
                BatchCancelOrdersRequestOrder(order_id="ord-2", subaccount=3),
            ],
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert len(body["orders"]) == 2
        assert body["orders"][0] == {"order_id": "ord-1"}
        assert body["orders"][1] == {"order_id": "ord-2", "subaccount": 3}

    def test_forbid_extra_on_wrapper(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import BatchCancelOrdersRequest

        with pytest.raises(ValidationError):
            BatchCancelOrdersRequest(
                orders=[],
                bogus=1,  # type: ignore[call-arg]
            )


class TestBatchCancelOrdersRequestOrder:
    def test_order_id_required(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import BatchCancelOrdersRequestOrder

        with pytest.raises(ValidationError):
            BatchCancelOrdersRequestOrder()  # type: ignore[call-arg]

    def test_subaccount_optional(self) -> None:
        from kalshi.models.orders import BatchCancelOrdersRequestOrder

        req = BatchCancelOrdersRequestOrder(order_id="ord-x")
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body == {"order_id": "ord-x"}

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import BatchCancelOrdersRequestOrder

        with pytest.raises(ValidationError):
            BatchCancelOrdersRequestOrder(
                order_id="x",
                bogus=5,  # type: ignore[call-arg]
            )


# ---------- P2#4: AwareDatetime on REST response models ----------


class TestAwareDatetimeRejectsNaive:
    """REST models reject naive datetimes at construction (#221 P2.4)."""

    @pytest.mark.parametrize(
        ("model_cls", "ts_field", "fixture_builder"),
        [
            (Order, "created_time", order_dict),
            (Market, "created_time", market_dict),
            (Settlement, "settled_time", settlement_dict),
        ],
        ids=["Order", "Market", "Settlement"],
    )
    def test_aware_datetime_rejects_naive_datetime(
        self, model_cls: type, ts_field: str, fixture_builder
    ) -> None:
        from pydantic import ValidationError

        # Override the timestamp field with a naive datetime.
        naive = datetime(2026, 1, 1, 12, 0, 0)  # intentional naive for the negative test
        wire = fixture_builder(**{ts_field: naive})
        with pytest.raises(ValidationError):
            model_cls.model_validate(wire)

    @pytest.mark.parametrize(
        ("model_cls", "ts_field", "fixture_builder"),
        [
            (Order, "created_time", order_dict),
            (Market, "created_time", market_dict),
            (Settlement, "settled_time", settlement_dict),
        ],
        ids=["Order", "Market", "Settlement"],
    )
    def test_aware_datetime_accepts_rfc3339_with_z(
        self, model_cls: type, ts_field: str, fixture_builder
    ) -> None:
        """Wire format (RFC3339 with Z suffix) still parses cleanly."""
        wire = fixture_builder(**{ts_field: "2026-01-01T12:00:00Z"})
        obj = model_cls.model_validate(wire)
        ts = getattr(obj, ts_field)
        assert ts is not None
        assert ts.tzinfo is not None
        # UTC conversion round-trips cleanly.
        assert ts.astimezone(UTC).isoformat().startswith("2026-01-01T12:00:00")


class TestMarketStrikeDecimal:
    """#259: floor_strike / cap_strike use DollarDecimal (not bare Decimal)."""

    def test_floor_strike_float_routed_through_str(self) -> None:
        from tests._model_fixtures import market_dict

        m = Market.model_validate(market_dict(ticker="T", floor_strike=4487.65))
        assert isinstance(m.floor_strike, Decimal)
        # Bare-Decimal path commits via float — DollarDecimal goes through str.
        assert m.floor_strike == Decimal("4487.65")
        assert str(m.floor_strike) == "4487.65"

    def test_cap_strike_string_parses(self) -> None:
        from tests._model_fixtures import market_dict

        m = Market.model_validate(market_dict(ticker="T", cap_strike="100.50"))
        assert isinstance(m.cap_strike, Decimal)
        assert m.cap_strike == Decimal("100.50")

    def test_strikes_reject_bool(self) -> None:
        import pytest

        from tests._model_fixtures import market_dict

        with pytest.raises(TypeError, match="bool"):
            Market.model_validate(market_dict(ticker="T", floor_strike=True))
        with pytest.raises(TypeError, match="bool"):
            Market.model_validate(market_dict(ticker="T", cap_strike=True))

    def test_strikes_default_to_none(self) -> None:
        from tests._model_fixtures import market_dict

        m = Market.model_validate(market_dict(ticker="T"))
        assert m.floor_strike is None
        assert m.cap_strike is None


class TestEventFeeMultiplierOverrideDecimal:
    """#259: Event.fee_multiplier_override uses MultiplierDecimal."""

    def test_float_routed_through_str(self) -> None:
        from tests._model_fixtures import event_dict

        e = Event.model_validate(event_dict(fee_multiplier_override=0.65))
        assert isinstance(e.fee_multiplier_override, Decimal)
        assert e.fee_multiplier_override == Decimal("0.65")
        assert str(e.fee_multiplier_override) == "0.65"

    def test_rejects_bool(self) -> None:
        import pytest

        from tests._model_fixtures import event_dict

        with pytest.raises(TypeError, match="bool"):
            Event.model_validate(event_dict(fee_multiplier_override=True))


class TestStrictIntRejectsBoolOnRequestModels:
    """#295: every ``StrictInt`` field on a Request model must reject ``bool``.

    ``bool`` is an ``int`` subclass, so a plain ``int`` annotation would
    silently coerce ``True``->1 / ``False``->0 — silently routing money to
    subaccount 1, capping order groups at 1 contract, transferring 1 cent
    between the wrong subaccounts, etc. #243 hardened ``buy_max_cost``
    against this; this test pins the same guard on every other int request
    field.
    """

    @pytest.mark.parametrize(
        ("model_path", "field_name", "other_kwargs"),
        [
            # CreateOrderRequest
            (
                "kalshi.models.orders:CreateOrderRequest",
                "subaccount",
                {"ticker": "MKT", "side": "yes", "action": "buy", "count": 1},
            ),
            (
                "kalshi.models.orders:CreateOrderRequest",
                "exchange_index",
                {"ticker": "MKT", "side": "yes", "action": "buy", "count": 1},
            ),
            (
                "kalshi.models.orders:CreateOrderRequest",
                "expiration_ts",
                {"ticker": "MKT", "side": "yes", "action": "buy", "count": 1},
            ),
            # AmendOrderRequest
            (
                "kalshi.models.orders:AmendOrderRequest",
                "subaccount",
                {"ticker": "MKT", "side": "yes", "action": "buy"},
            ),
            (
                "kalshi.models.orders:AmendOrderRequest",
                "exchange_index",
                {"ticker": "MKT", "side": "yes", "action": "buy"},
            ),
            # DecreaseOrderRequest — reduce_by/reduce_to are XOR with each other,
            # so each row pairs the StrictInt-under-test against a valid sibling
            # where required. subaccount/exchange_index need a real reduce_* set.
            ("kalshi.models.orders:DecreaseOrderRequest", "reduce_by", {}),
            ("kalshi.models.orders:DecreaseOrderRequest", "reduce_to", {}),
            (
                "kalshi.models.orders:DecreaseOrderRequest",
                "subaccount",
                {"reduce_by": 1},
            ),
            (
                "kalshi.models.orders:DecreaseOrderRequest",
                "exchange_index",
                {"reduce_by": 1},
            ),
            # BatchCancelOrdersRequestOrder
            (
                "kalshi.models.orders:BatchCancelOrdersRequestOrder",
                "subaccount",
                {"order_id": "abc"},
            ),
            (
                "kalshi.models.orders:BatchCancelOrdersRequestOrder",
                "exchange_index",
                {"order_id": "abc"},
            ),
            # Order groups
            (
                "kalshi.models.order_groups:CreateOrderGroupRequest",
                "contracts_limit",
                {},
            ),
            (
                "kalshi.models.order_groups:CreateOrderGroupRequest",
                "subaccount",
                {"contracts_limit": 10},
            ),
            (
                "kalshi.models.order_groups:CreateOrderGroupRequest",
                "exchange_index",
                {"contracts_limit": 10},
            ),
            (
                "kalshi.models.order_groups:UpdateOrderGroupLimitRequest",
                "contracts_limit",
                {},
            ),
            # Communications / RFQ
            (
                "kalshi.models.communications:CreateRFQRequest",
                "contracts",
                {"market_ticker": "MKT", "rest_remainder": True},
            ),
            (
                "kalshi.models.communications:CreateRFQRequest",
                "subaccount",
                {"market_ticker": "MKT", "rest_remainder": True},
            ),
            # Subaccount transfers — the highest-risk surface in #295: a bool
            # slipping through silently moves cents between subaccount 1 and 1.
            (
                "kalshi.models.subaccounts:ApplySubaccountTransferRequest",
                "from_subaccount",
                {
                    "client_transfer_id": "00000000-0000-4000-8000-000000000000",
                    "to_subaccount": 2,
                    "amount_cents": 1,
                },
            ),
            (
                "kalshi.models.subaccounts:ApplySubaccountTransferRequest",
                "to_subaccount",
                {
                    "client_transfer_id": "00000000-0000-4000-8000-000000000000",
                    "from_subaccount": 1,
                    "amount_cents": 1,
                },
            ),
            (
                "kalshi.models.subaccounts:ApplySubaccountTransferRequest",
                "amount_cents",
                {
                    "client_transfer_id": "00000000-0000-4000-8000-000000000000",
                    "from_subaccount": 1,
                    "to_subaccount": 2,
                },
            ),
        ],
    )
    def test_strict_int_rejects_bool_on_request_models(
        self,
        model_path: str,
        field_name: str,
        other_kwargs: dict,
    ) -> None:
        import importlib

        from pydantic import ValidationError

        module_name, class_name = model_path.split(":")
        model_cls = getattr(importlib.import_module(module_name), class_name)

        for bool_value in (True, False):
            with pytest.raises(ValidationError, match=r"bool"):
                model_cls(**{**other_kwargs, field_name: bool_value})
