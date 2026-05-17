"""Tests for DollarDecimal / FixedPointCount type-fallback branches in kalshi.types."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from kalshi.types import DollarDecimal, FixedPointCount


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
