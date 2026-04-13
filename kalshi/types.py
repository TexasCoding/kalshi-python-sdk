"""Custom types and Pydantic field helpers for the Kalshi SDK."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer


def _to_decimal_dollars(value: Any) -> Decimal:
    """Convert a raw API dollar-string value to Decimal.

    Kalshi API returns price fields with a '_dollars' suffix as string
    representations of dollar amounts (e.g., "0.65"). This converts them
    to Decimal without float intermediaries.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise TypeError(f"Cannot convert {type(value).__name__} to Decimal")


def _decimal_to_str(value: Decimal) -> str:
    """Serialize Decimal back to string for API requests."""
    return str(value)


DollarDecimal = Annotated[
    Decimal,
    BeforeValidator(_to_decimal_dollars),
    PlainSerializer(_decimal_to_str, return_type=str),
]
"""A Decimal field that handles bidirectional conversion for Kalshi dollar values.

- Parse: Accepts str/int/float/Decimal, converts via Decimal(str(value))
- Serialize: Outputs string representation for API requests
"""


def to_decimal(value: int | float | str | Decimal) -> Decimal:
    """Convert a user-supplied price/count value to Decimal safely.

    Always goes through str() to avoid float representation errors.
    e.g., to_decimal(0.65) returns Decimal("0.65"), not Decimal(0.65).
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
