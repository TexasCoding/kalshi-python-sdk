"""Tests for kalshi.types and model Decimal handling."""

from __future__ import annotations

from decimal import Decimal

from kalshi.models.markets import Market
from kalshi.models.orders import Order
from kalshi.types import to_decimal


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
        m = Market(ticker="T", yes_ask="0.65")
        assert m.yes_ask == Decimal("0.65")
        assert isinstance(m.yes_ask, Decimal)

    def test_market_parses_float_price(self) -> None:
        m = Market(ticker="T", yes_bid=0.45)
        assert m.yes_bid == Decimal("0.45")

    def test_market_parses_int_price(self) -> None:
        m = Market(ticker="T", last_price=1)
        assert m.last_price == Decimal("1")

    def test_market_model_dump_serializes(self) -> None:
        m = Market(ticker="T", yes_ask="0.72")
        data = m.model_dump()
        assert data["yes_ask"] == "0.72"

    def test_order_decimal_fields(self) -> None:
        o = Order(order_id="x", yes_price="0.65", no_price="0.35")
        assert o.yes_price == Decimal("0.65")
        assert o.no_price == Decimal("0.35")


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
