"""Tests for DollarDecimal and FixedPointCount type-fallback branches.

Pins the ``raise TypeError(f"Cannot convert {type(value).__name__} to Decimal")``
branches in ``kalshi.types`` (lines 27, 60). Unexpected input types (e.g. a list)
must surface as a ``TypeError`` with the type name in the message — not a
confusing ``InvalidOperation`` or silent coercion.

Note: Pydantic ``BeforeValidator`` lets non-ValueError exceptions propagate
unwrapped, so the raised ``TypeError`` is visible directly to callers.
"""
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
