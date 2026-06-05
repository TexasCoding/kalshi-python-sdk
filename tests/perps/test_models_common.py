"""Tests for the shared perps common models (enums + value-objects)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel, TypeAdapter

from kalshi.perps.models.common import (
    BookSide,
    EmptyResponse,
    ErrorResponse,
    ExchangeIndex,
    ExchangeInstance,
    LastUpdateReason,
    MarginMarketStatus,
    OrderSource,
    PriceLevelDollarsCountFp,
    SelfTradePreventionType,
)
from kalshi.types import DollarDecimal, FixedPointCount


class TestEnums:
    def test_book_side_values(self) -> None:
        assert BookSide("bid") is BookSide.BID
        assert BookSide("ask") is BookSide.ASK
        assert BookSide.BID.value == "bid"

    def test_self_trade_prevention_values(self) -> None:
        assert SelfTradePreventionType("taker_at_cross") is SelfTradePreventionType.TAKER_AT_CROSS
        assert SelfTradePreventionType("maker") is SelfTradePreventionType.MAKER

    def test_last_update_reason_includes_empty_string_member(self) -> None:
        # The empty-string member is a real wire value.
        assert LastUpdateReason("") is LastUpdateReason.NONE
        assert LastUpdateReason.NONE.value == ""
        # PascalCase wire members (no snake_case rename).
        assert LastUpdateReason("MarginCancel") is LastUpdateReason.MARGIN_CANCEL
        assert LastUpdateReason("PostOnlyCrossCancel") is LastUpdateReason.POST_ONLY_CROSS_CANCEL

    def test_order_source_values(self) -> None:
        assert OrderSource("user") is OrderSource.USER
        assert OrderSource("system") is OrderSource.SYSTEM

    def test_margin_market_status_values(self) -> None:
        assert {s.value for s in MarginMarketStatus} == {"inactive", "active", "closed"}

    def test_exchange_instance_values(self) -> None:
        assert ExchangeInstance("event_contract") is ExchangeInstance.EVENT_CONTRACT
        assert ExchangeInstance("margined") is ExchangeInstance.MARGINED

    def test_unknown_enum_value_raises(self) -> None:
        with pytest.raises(ValueError):
            BookSide("yes")  # prediction-API value — not valid for perps
        with pytest.raises(ValueError):
            ExchangeInstance("nope")


class TestValueObjects:
    def test_exchange_index_is_int_alias(self) -> None:
        assert ExchangeIndex is int

    def test_price_level_tuple_parses(self) -> None:
        adapter = TypeAdapter(PriceLevelDollarsCountFp)
        price, qty = adapter.validate_python(["0.1500", "100.00"])
        assert price == Decimal("0.1500")
        assert qty == Decimal("100.00")
        assert isinstance(price, Decimal)
        assert isinstance(qty, Decimal)

    def test_empty_response_parses_empty_object(self) -> None:
        assert EmptyResponse.model_validate({}) is not None
        # extra="allow": an additive field doesn't break parsing.
        EmptyResponse.model_validate({"unexpected": 1})

    def test_error_response_parses_full_body(self) -> None:
        err = ErrorResponse.model_validate(
            {
                "code": "margin_disabled",
                "message": "Margin not enabled",
                "details": "contact support",
                "service": "trade-api",
            }
        )
        assert err.code == "margin_disabled"
        assert err.message == "Margin not enabled"
        assert err.details == "contact support"
        assert err.service == "trade-api"

    def test_error_response_all_optional(self) -> None:
        err = ErrorResponse.model_validate({})
        assert err.code is None and err.message is None


class _RoundTrip(BaseModel):
    price: DollarDecimal
    count: FixedPointCount


class TestDecimalReuse:
    def test_dollar_and_count_roundtrip(self) -> None:
        m = _RoundTrip.model_validate({"price": "0.560000", "count": "10.00"})
        assert m.price == Decimal("0.560000")
        assert m.count == Decimal("10.00")
        dumped = m.model_dump(mode="json")
        assert dumped == {"price": "0.560000", "count": "10.00"}
