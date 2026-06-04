"""Shared enums and value-objects for the Kalshi Perps (margin) API.

These primitives are **defined once here** and imported by every per-area perps
model module — they must not be redefined. Field/value semantics are verified
against ``specs/perps_openapi.yaml``.

Note: perps order side is ``bid``/``ask`` (:class:`BookSide`), **not** the
prediction API's ``yes``/``no``.

``DollarDecimal`` and ``FixedPointCount`` are reused from :mod:`kalshi.types`
as-is — the perps spec's ``FixedPointDollars`` (string, up to 6 decimals) and
``FixedPointCount`` (string, 2 decimals, ``_fp`` suffix in field names) have
identical decimal semantics to the prediction API, so no new custom type is
needed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from kalshi.types import DollarDecimal, FixedPointCount

# ExchangeIndex: spec ``ExchangeIndex`` is ``type: integer``, default 0,
# "only 0 currently supported". A documented bare-int alias (mirrors the
# lightweight ``UnixSecondsTimestamp`` alias in kalshi.types); a full model
# would be overkill for a single shard identifier.
ExchangeIndex = int
"""Spec ``ExchangeIndex`` — an exchange-shard identifier (``type: integer``).

Defaults to ``0``; only ``0`` is currently supported. Modeled as a bare ``int``.
"""

# PriceLevelDollarsCountFp: spec positional 2-tuple ``[dollars_string, fp]``
# where element 0 is a FixedPointDollars price string and element 1 is a
# FixedPointCount contract-count string. The second element is the contract
# quantity (NOT a price). Pydantic validates a 2-element JSON array into this.
PriceLevelDollarsCountFp = tuple[DollarDecimal, FixedPointCount]
"""Spec ``PriceLevelDollarsCountFp`` — ``(price_in_dollars, contract_count_fp)``.

A positional 2-tuple parsed from a JSON array like ``["0.1500", "100.00"]``:
element 0 is the price (:data:`~kalshi.types.DollarDecimal`), element 1 is the
contract quantity (:data:`~kalshi.types.FixedPointCount`).
"""


class BookSide(StrEnum):
    """Spec ``BookSide`` — the side of an order or trade.

    Perps uses ``bid``/``ask`` (NOT the prediction API's ``yes``/``no``).
    """

    BID = "bid"
    ASK = "ask"


class SelfTradePreventionType(StrEnum):
    """Spec ``SelfTradePreventionType`` — how self-crossing orders are handled."""

    TAKER_AT_CROSS = "taker_at_cross"
    MAKER = "maker"


class LastUpdateReason(StrEnum):
    """Spec ``LastUpdateReason`` — why an order was last updated.

    The empty-string member (``NONE = ""``) is a real wire value. Members are the
    literal PascalCase wire strings (no snake_case rename).
    """

    NONE = ""
    DECREASE = "Decrease"
    AMEND = "Amend"
    MARGIN_CANCEL = "MarginCancel"
    SELF_TRADE_CANCEL = "SelfTradeCancel"
    EXPIRY_CANCEL = "ExpiryCancel"
    TRADE = "Trade"
    POST_ONLY_CROSS_CANCEL = "PostOnlyCrossCancel"


class OrderSource(StrEnum):
    """Spec ``OrderSource`` — ``user`` (user-placed) or ``system`` (liquidation)."""

    USER = "user"
    SYSTEM = "system"


class MarginMarketStatus(StrEnum):
    """Spec ``MarginMarketStatus`` — the status of a margin market."""

    INACTIVE = "inactive"
    ACTIVE = "active"
    CLOSED = "closed"


class ExchangeInstance(StrEnum):
    """Spec ``ExchangeInstance`` — ``event_contract`` or ``margined``."""

    EVENT_CONTRACT = "event_contract"
    MARGINED = "margined"


class EmptyResponse(BaseModel):
    """Spec ``EmptyResponse`` — an empty object body.

    The success response for delete/reset/trigger/update-limit order-group
    operations. ``extra="allow"`` so a future additive server field doesn't break
    parsing.
    """

    model_config = ConfigDict(extra="allow")


class ErrorResponse(BaseModel):
    """Spec ``ErrorResponse`` — a structured API error body.

    Parsed by the transport's ``_map_error`` path already; provided here for
    typed access. All fields are optional per spec.
    """

    model_config = ConfigDict(extra="allow")

    code: str | None = None
    message: str | None = None
    details: str | None = None
    service: str | None = None
