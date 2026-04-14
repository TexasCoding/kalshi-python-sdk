"""Tests for FixedPointCount type."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel

from kalshi.types import FixedPointCount


class SampleModel(BaseModel):
    count: FixedPointCount


class TestFixedPointCount:
    def test_parse_string(self) -> None:
        m = SampleModel.model_validate({"count": "100.00"})
        assert m.count == Decimal("100.00")

    def test_parse_int(self) -> None:
        m = SampleModel.model_validate({"count": 42})
        assert m.count == Decimal("42")

    def test_parse_float(self) -> None:
        m = SampleModel.model_validate({"count": 3.14})
        assert m.count == Decimal("3.14")

    def test_parse_decimal_passthrough(self) -> None:
        m = SampleModel.model_validate({"count": Decimal("99.99")})
        assert m.count == Decimal("99.99")

    def test_parse_negative(self) -> None:
        m = SampleModel.model_validate({"count": "-5.00"})
        assert m.count == Decimal("-5.00")

    def test_serialize_to_string(self) -> None:
        m = SampleModel(count=Decimal("100.00"))
        data = m.model_dump(mode="json")
        assert data["count"] == "100.00"

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(TypeError):
            SampleModel.model_validate({"count": [1, 2, 3]})
