"""Custom types and Pydantic field helpers for the Kalshi SDK."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, TypeVar

from pydantic import AfterValidator, BeforeValidator, PlainSerializer

T = TypeVar("T")


def _coerce_decimal(value: Any) -> Decimal:
    """Coerce a wire value (str/int/float/Decimal) to ``Decimal`` without going through float.

    Used by both :data:`DollarDecimal` (price/cost fields with ``_dollars`` aliases) and
    :data:`FixedPointCount` (volume/count fields with ``_fp`` aliases). The two aliases
    differ only in their canonical wire name and intent; the decimal coercion is the same.
    Going through ``str(value)`` for ``int`` / ``float`` avoids the binary-float
    representation drift (``Decimal(0.65) == Decimal('0.65000000000000002...')``).

    Non-finite values (``NaN``, ``Infinity``, ``-Infinity``) are rejected after coercion.
    ``f"{Decimal('NaN'):f}"`` returns the literal string ``"NaN"``; without this guard
    a caller doing arithmetic that produces NaN and then constructing a Dollar/FP-typed
    request would ship the string ``"NaN"`` straight to a real-money endpoint.
    """
    if isinstance(value, bool):
        raise TypeError(
            "Cannot convert bool to Decimal — bool is an int subclass, "
            "so this is almost always a typo (did you mean count=1?)."
        )
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, float)):
        result = Decimal(str(value))
    elif isinstance(value, str):
        result = Decimal(value)
    else:
        raise TypeError(f"Cannot convert {type(value).__name__} to Decimal")
    if not result.is_finite():
        raise ValueError("Decimal must be finite (got NaN/Infinity)")
    return result


def _decimal_to_str(value: Decimal) -> str:
    """Serialize Decimal back to string for API requests."""
    return f"{value:f}"


DollarDecimal = Annotated[
    Decimal,
    BeforeValidator(_coerce_decimal),
    PlainSerializer(_decimal_to_str, return_type=str, when_used="json"),
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
    PlainSerializer(_decimal_to_str, return_type=str, when_used="json"),
]
"""A Decimal field that handles bidirectional conversion for Kalshi count/volume values.

- Parse: Accepts str/int/float/Decimal, converts via Decimal(str(value))
- Serialize: Outputs string representation for API requests
"""


MultiplierDecimal = Annotated[
    Decimal,
    BeforeValidator(_coerce_decimal),
    PlainSerializer(_decimal_to_str, return_type=str, when_used="json"),
]
"""A Decimal field for fee/rate multipliers (e.g. ``Series.fee_multiplier``).

Wire shape is ``type: number, format: double`` per spec. Using the bare
``float`` annotation commits the value to binary float at parse time
(``0.65 -> 0.65000000000000002...``); using bare ``Decimal`` skips
_coerce_decimal entirely and routes JSON numbers through float. This
alias applies the same coercion as :data:`DollarDecimal` /
:data:`FixedPointCount` so multipliers honor the #225 invariant.
"""


def to_decimal(value: int | float | str | Decimal) -> Decimal:
    """Convert a user-supplied price/count value to Decimal safely.

    Always goes through str() to avoid float representation errors.
    e.g., to_decimal(0.65) returns Decimal("0.65"), not Decimal(0.65).

    Rejects ``bool`` inputs (#225 pattern) and non-finite values
    (``NaN``/``Infinity``); delegates to :func:`_coerce_decimal` so the
    public helper and the :data:`DollarDecimal` / :data:`FixedPointCount`
    validators share a single guard (#325).
    """
    return _coerce_decimal(value)


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

# Internal type aid — not re-exported via kalshi.__init__. The bare int
# wire shape is preserved; this alias only documents intent and gives mypy/IDE
# a greppable name when balance/deposit/withdrawal timestamps are read
# alongside the AwareDatetime peers on MarketPosition/Settlement.
UnixSecondsTimestamp = Annotated[int, "Unix epoch seconds (int64) per OpenAPI spec"]
"""Server-side ``format: int64`` Unix-seconds timestamp.

Same wire shape as plain ``int``; the alias exists to make it obvious at the
field site that the value is *seconds* (not milliseconds, not a datetime).
Callers wanting a :class:`datetime.datetime` can use
``datetime.fromtimestamp(value, tz=timezone.utc)``.
"""


def _reject_bool_int(value: object) -> object:
    """Reject ``bool`` so True->1 / False->0 cannot silently route money (#243 pattern, #295)."""
    if isinstance(value, bool):
        raise ValueError(
            "bool is not a valid int here — pass an explicit integer "
            "(e.g. 1 instead of True). bool is an int subclass so True "
            "would otherwise silently become 1."
        )
    return value


StrictInt = Annotated[int, BeforeValidator(_reject_bool_int)]
"""``int`` that rejects ``bool`` — use on every Request-model integer field. See #295."""


_REQUEST_PRICE_TICK = Decimal("0.0001")


def _ensure_request_price(value: Decimal) -> Decimal:
    """Validate a request-side dollar price (#343).

    ``DollarDecimal`` is shared with response-side fields (PnL, fees,
    settlements) where negatives and arbitrary precision are legitimate.
    Request-side price fields, however, are bounded by Kalshi's order
    contract: prices must be non-negative and aligned to the $0.0001
    tick. Catching both at construction (rather than as a server-side
    400) matches the boundary-validation pattern that ``StrictInt`` /
    ``Literal`` / ``_reject_bool_int`` apply elsewhere.
    """
    if value < 0:
        raise ValueError(
            f"Order price must be non-negative (got {value}); request-side "
            "DollarDecimal fields reject negatives. Negative prices are "
            "legitimate only on response-side PnL/fee/settlement fields."
        )
    if value != value.quantize(_REQUEST_PRICE_TICK):
        raise ValueError(
            f"Order price {value} is finer than the $0.0001 tick; round "
            "to four decimal places (e.g. Decimal('0.5600')) before "
            "constructing the request."
        )
    return value


OrderPrice = Annotated[
    Decimal,
    BeforeValidator(_coerce_decimal),
    AfterValidator(_ensure_request_price),
    PlainSerializer(_decimal_to_str, return_type=str, when_used="json"),
]
"""Request-side dollar price with sign and $0.0001 tick guards (#343).

Same wire shape as :data:`DollarDecimal` (BeforeValidator coerces to
``Decimal`` without float drift, PlainSerializer emits a fixed-point
string on ``mode="json"``), but adds an :class:`AfterValidator` that
rejects negatives and sub-tick precision. Use on
``CreateOrderRequest`` / ``AmendOrderRequest`` / V2 equivalents so a
caller passing ``Decimal('-0.65')`` or ``Decimal('0.12345')`` fails at
construction instead of round-tripping to a server 400.
"""
