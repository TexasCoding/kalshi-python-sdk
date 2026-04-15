"""Unit tests for the semantic oracle (assert_model_fields).

These don't hit the network — they verify the oracle catches field violations
on synthetic model instances.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import BaseModel

from tests.integration.assertions import assert_model_fields


class FakePrice(BaseModel):
    """Minimal model with a price-range field."""
    price: Decimal


class FakeMarket(BaseModel):
    """Minimal model mimicking Market fields."""
    ticker: str
    yes_bid: Decimal | None = None
    created_time: datetime | None = None
    volume: Decimal | None = None
    nested: FakePrice | None = None
    levels: list[FakePrice] = []


class TestDecimalEnforcement:
    def test_passes_with_decimal(self) -> None:
        m = FakeMarket(ticker="T", yes_bid=Decimal("0.50"))
        assert_model_fields(m)  # should not raise

    def test_fails_with_float(self) -> None:
        m = FakeMarket.__pydantic_validator__.validate_python(
            {"ticker": "T"}
        )
        # Manually set a float to simulate a parse failure
        object.__setattr__(m, "volume", 0.5)
        with pytest.raises(AssertionError, match=r"float.*expected Decimal"):
            assert_model_fields(m)


class TestPriceRange:
    def test_passes_in_range(self) -> None:
        m = FakeMarket(ticker="T", yes_bid=Decimal("0.65"))
        assert_model_fields(m)

    def test_fails_above_one(self) -> None:
        m = FakeMarket(ticker="T", yes_bid=Decimal("1.50"))
        with pytest.raises(AssertionError, match=r"outside.*range"):
            assert_model_fields(m)

    def test_volume_not_range_checked(self) -> None:
        """volume is in the exclusion set — values > 1 are fine."""
        m = FakeMarket(ticker="T", volume=Decimal("9999"))
        assert_model_fields(m)  # should not raise


class TestTimestampEnforcement:
    def test_passes_with_datetime(self) -> None:
        m = FakeMarket(ticker="T", created_time=datetime(2026, 1, 1))
        assert_model_fields(m)

    def test_fails_with_raw_string(self) -> None:
        m = FakeMarket.__pydantic_validator__.validate_python(
            {"ticker": "T"}
        )
        object.__setattr__(m, "created_time", "2026-01-01T00:00:00Z")
        with pytest.raises(AssertionError, match=r"raw string.*expected datetime"):
            assert_model_fields(m)


class TestRequiredFields:
    def test_fails_when_required_is_none(self) -> None:
        m = FakeMarket.__pydantic_validator__.validate_python(
            {"ticker": "T"}
        )
        object.__setattr__(m, "ticker", None)
        with pytest.raises(AssertionError, match="None but field is required"):
            assert_model_fields(m)


class TestNestedRecursion:
    def test_recurses_into_nested_model(self) -> None:
        m = FakeMarket(ticker="T", nested=FakePrice(price=Decimal("1.50")))
        with pytest.raises(AssertionError, match=r"price.*outside.*range"):
            assert_model_fields(m)

    def test_recurses_into_list_of_models(self) -> None:
        m = FakeMarket(
            ticker="T",
            levels=[
                FakePrice(price=Decimal("0.50")),
                FakePrice(price=Decimal("2.00")),
            ],
        )
        with pytest.raises(AssertionError, match=r"price.*outside.*range"):
            assert_model_fields(m)

    def test_passes_valid_nested(self) -> None:
        m = FakeMarket(
            ticker="T",
            nested=FakePrice(price=Decimal("0.75")),
            levels=[FakePrice(price=Decimal("0.25"))],
        )
        assert_model_fields(m)
