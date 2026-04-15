"""Semantic oracle — validates runtime field values on any Pydantic model.

Checks:
1. No float values where Decimal is expected (catches DollarDecimal parse failures)
2. Price fields in [0, 1] range for binary market fields
3. Timestamp fields are datetime instances (not raw strings/ints)
4. Required fields are non-None
5. Recurses into nested BaseModel fields and list[BaseModel] fields
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

# Exhaustive set of field names that must be in [0, 1] when non-None.
# Covers Market, OrderbookLevel, BidAskDistribution, PriceDistribution,
# Order, Fill, and Trade models.
PRICE_RANGE_FIELDS: frozenset[str] = frozenset({
    # Market model
    "yes_bid",
    "yes_ask",
    "no_bid",
    "no_ask",
    "last_price",
    "previous_yes_bid",
    "previous_yes_ask",
    "previous_price",
    # OrderbookLevel
    "price",
    # BidAskDistribution / PriceDistribution (candlestick OHLC)
    "open",
    "high",
    "low",
    "close",
    # Order / Fill / Trade
    "yes_price",
    "no_price",
})


def assert_model_fields(model: BaseModel, *, _path: str = "") -> None:
    """Validate runtime field values on a Pydantic model instance.

    Args:
        model: Any Pydantic BaseModel instance from the SDK.
        _path: Internal, for nested error messages. Do not pass externally.

    Raises:
        AssertionError with a descriptive message on the first violation found.
    """
    prefix = f"{_path}." if _path else ""
    model_name = type(model).__name__

    for field_name, field_info in type(model).model_fields.items():
        full_name = f"{prefix}{model_name}.{field_name}"
        val = getattr(model, field_name, None)

        if val is None:
            # Check required-field presence
            if field_info.is_required():
                raise AssertionError(
                    f"{full_name} is None but field is required"
                )
            continue

        # 1. No floats where Decimal is expected
        if isinstance(val, float):
            raise AssertionError(
                f"{full_name} is float ({val!r}), expected Decimal. "
                f"DollarDecimal parsing may have failed."
            )

        # 2. Price range validation for inclusion-set fields
        if (
            field_name in PRICE_RANGE_FIELDS
            and isinstance(val, Decimal)
            and not (Decimal("0") <= val <= Decimal("1"))
        ):
            raise AssertionError(
                f"{full_name} = {val} is outside [0, 1] range for a price field"
            )

        # 3. Timestamp type enforcement
        #    If the field annotation resolves to datetime (or datetime | None),
        #    verify the runtime value is actually a datetime instance.
        if isinstance(val, str):
            # Check if this field is supposed to be a datetime
            annotation = field_info.annotation
            if annotation is datetime or (
                hasattr(annotation, "__args__")
                and datetime in getattr(annotation, "__args__", ())
            ):
                raise AssertionError(
                    f"{full_name} is a raw string ({val!r}), expected datetime. "
                    f"Timestamp parsing may have failed."
                )

        # 4. Recurse into nested BaseModel fields
        if isinstance(val, BaseModel):
            assert_model_fields(val, _path=f"{prefix}{model_name}")

        # 5. Recurse into list[BaseModel] fields
        if isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, BaseModel):
                    assert_model_fields(
                        item, _path=f"{prefix}{model_name}.{field_name}[{i}]"
                    )
