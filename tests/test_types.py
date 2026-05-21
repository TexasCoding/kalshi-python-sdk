"""Tests for DollarDecimal / FixedPointCount type-fallback branches in kalshi.types."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel

from kalshi.types import DollarDecimal, FixedPointCount, _decimal_to_str, to_decimal


class _DollarModel(BaseModel):
    x: DollarDecimal


class _CountModel(BaseModel):
    x: FixedPointCount


class TestDollarDecimalTypeFallback:
    def test_list_input_raises_type_error_with_named_type(self) -> None:
        with pytest.raises(TypeError, match="Cannot convert list to Decimal"):
            _DollarModel.model_validate({"x": [1, 2]})

    def test_dict_input_raises_type_error_with_named_type(self) -> None:
        with pytest.raises(TypeError, match="Cannot convert dict to Decimal"):
            _DollarModel.model_validate({"x": {"nested": "value"}})


class TestFixedPointCountTypeFallback:
    def test_list_input_raises_type_error_with_named_type(self) -> None:
        with pytest.raises(TypeError, match="Cannot convert list to Decimal"):
            _CountModel.model_validate({"x": [1, 2]})

    def test_dict_input_raises_type_error_with_named_type(self) -> None:
        with pytest.raises(TypeError, match="Cannot convert dict to Decimal"):
            _CountModel.model_validate({"x": {"nested": "value"}})

class TestDecimalToStrPositional:
    def test_decimal_to_str_positional_for_large_exp(self) -> None:
        assert _decimal_to_str(Decimal("1E+10")) == "10000000000"

    def test_decimal_to_str_positional_for_small_exp(self) -> None:
        assert _decimal_to_str(Decimal("1E-7")) == "0.0000001"

    def test_decimal_to_str_preserves_trailing_zero(self) -> None:
        assert _decimal_to_str(Decimal("0.5600")) == "0.5600"


class TestCoerceDecimalRejectsBool:
    def test_coerce_decimal_rejects_bool_true(self) -> None:
        with pytest.raises(TypeError, match="bool"):
            _DollarModel.model_validate({"x": True})

    def test_coerce_decimal_rejects_bool_false(self) -> None:
        with pytest.raises(TypeError, match="bool"):
            _DollarModel.model_validate({"x": False})

    def test_to_decimal_rejects_bool(self) -> None:
        with pytest.raises(TypeError, match="bool"):
            to_decimal(True)  # type: ignore[arg-type]


class TestDollarDecimalDumpMode:
    def test_dollar_decimal_model_dump_python_returns_decimal_not_str(self) -> None:
        class M(BaseModel):
            price: DollarDecimal

        m = M(price=Decimal("0.5600"))  # type: ignore[arg-type]
        result = m.model_dump(mode="python")
        assert isinstance(result["price"], Decimal)
        assert result["price"] == Decimal("0.5600")

    def test_dollar_decimal_model_dump_json_returns_str(self) -> None:
        class M(BaseModel):
            price: DollarDecimal

        m = M(price=Decimal("1E+10"))  # type: ignore[arg-type]
        result = m.model_dump(mode="json")
        assert isinstance(result["price"], str)
        assert result["price"] == "10000000000"


class TestFixedPointCountDumpMode:
    def test_fixed_point_count_model_dump_python_returns_decimal_not_str(self) -> None:
        class M(BaseModel):
            count: FixedPointCount

        m = M(count=Decimal("42"))  # type: ignore[arg-type]
        result = m.model_dump(mode="python")
        assert isinstance(result["count"], Decimal)
        assert result["count"] == Decimal("42")


class TestCoerceDecimalRejectsNonFinite:
    """#270 Item 5: NaN/Infinity rejected so they never reach the wire.

    ``f"{Decimal('NaN'):f}"`` returns the literal string ``"NaN"``, and before this
    guard ``_coerce_decimal`` short-circuited on the ``isinstance(value, Decimal)``
    branch — a caller doing arithmetic that produced NaN would silently ship
    ``"NaN"`` to a real-money order placement endpoint. Same for Infinity.
    """

    def test_rejects_nan_decimal_on_dollar_field(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _DollarModel.model_validate({"x": Decimal("NaN")})

    def test_rejects_infinity_decimal_on_dollar_field(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _DollarModel.model_validate({"x": Decimal("Infinity")})

    def test_rejects_negative_infinity_decimal_on_count_field(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _CountModel.model_validate({"x": Decimal("-Infinity")})

    def test_rejects_nan_string_on_dollar_field(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _DollarModel.model_validate({"x": "NaN"})

    def test_accepts_finite_decimal(self) -> None:
        m = _DollarModel.model_validate({"x": Decimal("0.5")})
        assert m.x == Decimal("0.5")

    def test_create_order_request_rejects_nan_yes_price(self) -> None:
        from kalshi.models.orders import CreateOrderRequest
        with pytest.raises(ValueError, match="finite"):
            CreateOrderRequest(
                ticker="T", side="yes", action="buy",
                count=Decimal("1"), yes_price=Decimal("NaN"),
            )

