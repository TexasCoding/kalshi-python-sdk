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


class TestDollarsAliasFields:
    """Verify models accept _dollars-suffixed field names from the API.

    The Kalshi API returns price fields with a '_dollars' suffix
    (e.g. 'yes_bid_dollars') as FixedPointDollars strings. The SDK
    uses shorter Python field names (e.g. 'yes_bid') with validation
    aliases to accept both formats.
    """

    def test_market_accepts_dollars_suffix(self) -> None:
        m = Market.model_validate({
            "ticker": "T",
            "yes_bid_dollars": "0.4500",
            "yes_ask_dollars": "0.5500",
            "no_bid_dollars": "0.3000",
            "no_ask_dollars": "0.7000",
            "last_price_dollars": "0.5000",
        })
        assert m.yes_bid == Decimal("0.4500")
        assert m.yes_ask == Decimal("0.5500")
        assert m.no_bid == Decimal("0.3000")
        assert m.no_ask == Decimal("0.7000")
        assert m.last_price == Decimal("0.5000")

    def test_market_accepts_bare_names(self) -> None:
        m = Market(ticker="T", yes_bid="0.45")
        assert m.yes_bid == Decimal("0.45")

    def test_order_accepts_dollars_suffix(self) -> None:
        o = Order.model_validate({
            "order_id": "x",
            "yes_price_dollars": "0.6500",
            "no_price_dollars": "0.3500",
            "taker_fill_cost_dollars": "6.5000",
            "maker_fill_cost_dollars": "0.0000",
            "taker_fees_dollars": "0.0650",
            "maker_fees_dollars": "0.0000",
        })
        assert o.yes_price == Decimal("0.6500")
        assert o.no_price == Decimal("0.3500")
        assert o.taker_fill_cost == Decimal("6.5000")
        assert o.taker_fees == Decimal("0.0650")

    def test_fill_accepts_dollars_suffix(self) -> None:
        from kalshi.models.orders import Fill

        f = Fill.model_validate({
            "trade_id": "t1",
            "yes_price_dollars": "0.5000",
            "no_price_dollars": "0.5000",
        })
        assert f.yes_price == Decimal("0.5000")
        assert f.no_price == Decimal("0.5000")

    def test_candlestick_accepts_dollars_suffix(self) -> None:
        from kalshi.models.markets import Candlestick

        c = Candlestick.model_validate({
            "open_dollars": "0.5000",
            "high_dollars": "0.6000",
            "low_dollars": "0.4000",
            "close_dollars": "0.5500",
            "volume": 100,
        })
        assert c.open == Decimal("0.5000")
        assert c.high == Decimal("0.6000")
        assert c.low == Decimal("0.4000")
        assert c.close == Decimal("0.5500")

    def test_create_order_serializes_with_dollars_alias(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="T",
            side="yes",
            yes_price=Decimal("0.65"),
        )
        data = req.model_dump(exclude_none=True, by_alias=True)
        assert "yes_price_dollars" in data
        assert data["yes_price_dollars"] == "0.65"
        assert "yes_price" not in data


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
