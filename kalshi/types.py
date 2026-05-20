"""Custom types and Pydantic field helpers for the Kalshi SDK."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, TypeVar

from pydantic import BeforeValidator, PlainSerializer

T = TypeVar("T")


def _coerce_decimal(value: Any) -> Decimal:
    """Coerce a wire value (str/int/float/Decimal) to ``Decimal`` without going through float.

    Used by both :data:`DollarDecimal` (price/cost fields with ``_dollars`` aliases) and
    :data:`FixedPointCount` (volume/count fields with ``_fp`` aliases). The two aliases
    differ only in their canonical wire name and intent; the decimal coercion is the same.
    Going through ``str(value)`` for ``int`` / ``float`` avoids the binary-float
    representation drift (``Decimal(0.65) == Decimal('0.65000000000000002...')``).
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
    BeforeValidator(_coerce_decimal),
    PlainSerializer(_decimal_to_str, return_type=str),
]
"""A Decimal field that handles bidirectional conversion for Kalshi dollar values.

- Parse: Accepts str/int/float/Decimal, converts via Decimal(str(value))
- Serialize: Outputs string representation for API requests
"""


# FixedPointCount: count/volume fields (e.g., ``count_fp``, ``volume_fp``).
# Uses the same decimal coercion as :data:`DollarDecimal`; see _coerce_decimal.


FixedPointCount = Annotated[
    Decimal,
    BeforeValidator(_coerce_decimal),
    PlainSerializer(_decimal_to_str, return_type=str),
]
"""A Decimal field that handles bidirectional conversion for Kalshi count/volume values.

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


def _none_to_empty_list(value: Any) -> Any:
    """Coerce None to [] for optional list response fields.

    Kalshi's demo API returns JSON null for some optional list fields that the
    spec declares as non-nullable arrays. Pydantic's default list[T] annotation
    rejects None and raises ValidationError, breaking response parsing.
    Use NullableList[T] on response-model fields where the server may return null.
    """
    return [] if value is None else value


NullableList = Annotated[list[T], BeforeValidator(_none_to_empty_list)]
"""A list[T] that tolerates server-returned null by coercing to [].

Use on response-model fields (extra='allow') whose spec says 'array' but where
the live API has been observed to return null. Do NOT use on request bodies —
those should enforce strict validation.
"""
