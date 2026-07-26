"""Tests for kalshi.types and model Decimal handling."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar

import pytest
from pydantic import BaseModel, ValidationError

from kalshi.models.communications import RFQ, Quote
from kalshi.models.events import Event, EventMetadata, SettlementSource
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


class TestEventSettlementSources:
    """#451 spec drift: ``EventData.settlement_sources`` (required, nullable).

    Typed ``NullableList[SettlementSource]`` so a JSON ``null`` coerces to ``[]``
    while the key-present contract still holds (same shape as
    ``Series.settlement_sources``).
    """

    def test_null_coerces_to_empty_list(self) -> None:
        e = Event.model_validate(event_dict(settlement_sources=None))
        assert e.settlement_sources == []

    def test_parses_list_of_sources(self) -> None:
        e = Event.model_validate(
            event_dict(
                settlement_sources=[
                    {"url": "https://example.com", "name": "NWS"},
                    {"url": None, "name": None},
                ]
            )
        )
        assert len(e.settlement_sources) == 2
        assert all(isinstance(s, SettlementSource) for s in e.settlement_sources)
        assert e.settlement_sources[0].url == "https://example.com"
        assert e.settlement_sources[0].name == "NWS"

    def test_field_is_required(self) -> None:
        """Spec marks the field required — the key must be present."""
        data = event_dict()
        data.pop("settlement_sources")
        with pytest.raises(ValidationError):
            Event.model_validate(data)


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

    def test_parses_is_block_trade(self) -> None:
        """v3.20.0 (#385): required ``is_block_trade`` bool on ``Trade``."""
        assert Trade.model_validate(trade_dict(is_block_trade=True)).is_block_trade is True
        assert Trade.model_validate(trade_dict()).is_block_trade is False

    def test_is_block_trade_missing_raises(self) -> None:
        """Spec marks ``is_block_trade`` required + non-nullable; a missing key
        must raise so a schema regression surfaces, not silently default."""
        from pydantic import ValidationError

        data = trade_dict()
        data.pop("is_block_trade")
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
            # V2 order requests (#295 follow-up)
            (
                "kalshi.models.orders:CreateOrderV2Request",
                "expiration_time",
                {
                    "ticker": "MKT",
                    "client_order_id": "c1",
                    "side": "bid",
                    "count": 1,
                    "price": "0.50",
                    "time_in_force": "good_till_canceled",
                    "self_trade_prevention_type": "maker",
                },
            ),
            (
                "kalshi.models.orders:CreateOrderV2Request",
                "subaccount",
                {
                    "ticker": "MKT",
                    "client_order_id": "c1",
                    "side": "bid",
                    "count": 1,
                    "price": "0.50",
                    "time_in_force": "good_till_canceled",
                    "self_trade_prevention_type": "maker",
                },
            ),
            (
                "kalshi.models.orders:CreateOrderV2Request",
                "exchange_index",
                {
                    "ticker": "MKT",
                    "client_order_id": "c1",
                    "side": "bid",
                    "count": 1,
                    "price": "0.50",
                    "time_in_force": "good_till_canceled",
                    "self_trade_prevention_type": "maker",
                },
            ),
            (
                "kalshi.models.orders:DecreaseOrderV2Request",
                "exchange_index",
                {"reduce_by": 1},
            ),
            (
                "kalshi.models.orders:AmendOrderV2Request",
                "exchange_index",
                {"ticker": "MKT", "side": "bid", "price": "0.50", "count": 1},
            ),
            (
                "kalshi.models.orders:BatchCancelOrdersV2RequestOrder",
                "subaccount",
                {"order_id": "abc"},
            ),
            (
                "kalshi.models.orders:BatchCancelOrdersV2RequestOrder",
                "exchange_index",
                {"order_id": "abc"},
            ),
            (
                "kalshi.models.subaccounts:UpdateSubaccountNettingRequest",
                "subaccount_number",
                {"enabled": True},
            ),
            (
                "kalshi.models.subaccounts:LockSubaccountForSettlementAdvanceRequest",
                "subaccount_number",
                {},
            ),
            (
                "kalshi.models.subaccounts:LockSubaccountForSettlementAdvanceRequest",
                "exchange_index",
                {"subaccount_number": 0},
            ),
            (
                "kalshi.models.subaccounts:UnlockSubaccountForSettlementAdvanceRequest",
                "subaccount_number",
                {},
            ),
            (
                "kalshi.models.subaccounts:UnlockSubaccountForSettlementAdvanceRequest",
                "exchange_index",
                {"subaccount_number": 0},
            ),
            (
                "kalshi.models.communications:CreateQuoteRequest",
                "subaccount",
                {
                    "rfq_id": "rfq1",
                    "yes_bid": "0.50",
                    "no_bid": "0.50",
                    "rest_remainder": True,
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


class TestIssue326V1SubaccountGeZero:
    """#326: V1 order request models gain ``ge=0`` on subaccount-shaped ints.

    Achieves parity with V2 + communications + order_groups + subaccount-
    transfer. Negative ``subaccount``/``exchange_index`` previously survived
    construction, was signed by the SDK, and was 400'd by the server.

    Also sweeps the V2 ``exchange_index`` slots missed by the original
    V2 hardening.
    """

    @pytest.mark.parametrize(
        ("model_path", "field_name", "other_kwargs"),
        [
            # V2 exchange_index slots that were missed in #295
            (
                "kalshi.models.orders:CreateOrderV2Request",
                "exchange_index",
                {
                    "ticker": "MKT",
                    "client_order_id": "c1",
                    "side": "bid",
                    "count": 1,
                    "price": "0.50",
                    "time_in_force": "good_till_canceled",
                    "self_trade_prevention_type": "maker",
                },
            ),
            # BatchCancelOrdersV2RequestOrder.exchange_index intentionally has NO
            # ge=0 floor (spec v3.22.0 allows -1 to auto-route by market_ticker),
            # so the ge=0 assertion targets its ``subaccount`` field instead.
            (
                "kalshi.models.orders:BatchCancelOrdersV2RequestOrder",
                "subaccount",
                {"order_id": "abc"},
            ),
        ],
    )
    def test_issue_326_v1_subaccount_ge_zero(
        self,
        model_path: str,
        field_name: str,
        other_kwargs: dict[str, object],
    ) -> None:
        import importlib

        module_name, class_name = model_path.split(":")
        model_cls = getattr(importlib.import_module(module_name), class_name)

        with pytest.raises(ValidationError, match=r"greater than or equal to 0"):
            model_cls(**{**other_kwargs, field_name: -1})

        # Zero (primary subaccount / first shard) remains valid.
        instance = model_cls(**{**other_kwargs, field_name: 0})
        assert getattr(instance, field_name) == 0


class TestIssue328PageColumnsNoneFirstNested:
    """#328: ``Page._columns`` peeked only ``col[0]`` to decide the dump branch.

    An ``Optional[NestedModel]`` field whose first row is ``None`` (common
    across nullable struct columns on Market / Event / Series / Settlement)
    skipped the per-cell ``model_dump`` pass — the second row's populated
    nested model leaked out as a raw ``BaseModel`` instance, breaking the
    polars ``Struct`` dtype the docstring promises (#264).
    """

    def test_issue_328_page_columns_handles_none_first_nested(self) -> None:
        from kalshi.models.common import Page

        class _Inner(BaseModel):
            label: str

        class _Row(BaseModel):
            ticker: str
            inner: _Inner | None = None

        page: Page[_Row] = Page(
            items=[
                _Row(ticker="A", inner=None),
                _Row(ticker="B", inner=_Inner(label="x")),
            ],
            cursor=None,
        )

        cols = page._columns()
        assert cols["ticker"] == ["A", "B"]
        # Pre-fix: cols["inner"] == [None, _Inner(label="x")] (raw BaseModel leaks)
        # Post-fix: the populated row dumps to a dict; the None row stays None.
        assert cols["inner"][0] is None
        assert cols["inner"][1] == {"label": "x"}

    def test_issue_328_page_to_polars_yields_struct_for_none_first_nested(self) -> None:
        pl = pytest.importorskip("polars")

        from kalshi.models.common import Page

        class _Inner(BaseModel):
            label: str

        class _Row(BaseModel):
            ticker: str
            inner: _Inner | None = None

        page: Page[_Row] = Page(
            items=[
                _Row(ticker="A", inner=None),
                _Row(ticker="B", inner=_Inner(label="x")),
            ],
            cursor=None,
        )

        df = page.to_polars()
        assert isinstance(df["inner"].dtype, pl.Struct)


class TestIssue343DollarDecimalRequestBounds:
    """#343: request-side ``DollarDecimal`` fields lacked sign and tick bounds.

    The shared :data:`DollarDecimal` alias is intentionally permissive for
    response-side PnL/fee/settlement fields where negatives and arbitrary
    precision are legitimate. Request-side price fields, however, are bounded
    by Kalshi's order contract: non-negative and aligned to the $0.0001 tick.
    The :data:`OrderPrice` alias applied on CreateOrderV2Request /
    AmendOrderV2Request enforces both at construction.
    """

    def test_issue_343_dollar_decimal_request_rejects_negative_and_invalid_tick(self) -> None:
        from kalshi.models.orders import (
            AmendOrderV2Request,
            CreateOrderV2Request,
        )

        # V2 CreateOrderV2Request.
        with pytest.raises(ValidationError, match="non-negative"):
            CreateOrderV2Request(
                ticker="T", client_order_id="c1", side="bid",
                count=Decimal("1"), price=Decimal("-0.5"),
                time_in_force="good_till_canceled",
                self_trade_prevention_type="taker_at_cross",
            )
        with pytest.raises(ValidationError, match=r"\$0\.0001 tick"):
            CreateOrderV2Request(
                ticker="T", client_order_id="c1", side="bid",
                count=Decimal("1"), price=Decimal("0.55555"),
                time_in_force="good_till_canceled",
                self_trade_prevention_type="taker_at_cross",
            )

        # V2 AmendOrderV2Request.
        with pytest.raises(ValidationError, match="non-negative"):
            AmendOrderV2Request(
                ticker="T", side="ask",
                price=Decimal("-0.01"), count=Decimal("1"),
            )
        with pytest.raises(ValidationError, match=r"\$0\.0001 tick"):
            AmendOrderV2Request(
                ticker="T", side="ask",
                price=Decimal("0.12345"), count=Decimal("1"),
            )

    def test_issue_343_response_dollar_decimal_unchanged(self) -> None:
        # Response-side averages (V2) keep bare DollarDecimal — negatives must
        # remain legal for PnL/fee/settlement parity. Pin the contract.
        from kalshi.models.orders import CreateOrderV2Response

        resp = CreateOrderV2Response.model_validate({
            "order_id": "o", "fill_count": "1", "remaining_count": "0",
            "ts_ms": 0, "average_fill_price": "-0.0001",
        })
        assert resp.average_fill_price == Decimal("-0.0001")
