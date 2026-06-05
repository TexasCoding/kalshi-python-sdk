"""Shared literal/enum types for perps (margin) WS channel payloads.

These mirror the AsyncAPI ``components.schemas`` enums in
``specs/perps_asyncapi.yaml``. Defined once here so the per-channel payload
modules import a single source of truth.

CRITICAL — perps differs from the prediction-API WS:

* Book sides are ``bid``/``ask`` (:data:`PerpsBookSide`), NOT the prediction
  API's ``yes``/``no``. Do NOT reuse :data:`kalshi.models.orders.BookSideLiteral`.
* All channel timestamps are Unix epoch **milliseconds** carried on ``int``
  ``*_ms``-suffixed fields — never coerced to RFC3339 ``datetime``.
"""

from __future__ import annotations

from typing import Literal

# Spec schema ``bookSide`` — the side of an order or book level.
PerpsBookSide = Literal["bid", "ask"]

# Spec schema ``selfTradePreventionType``.
PerpsSelfTradePreventionType = Literal["taker_at_cross", "maker"]

# Spec schema ``lastUpdateReason`` — margin order update reason on a delta
# corresponding to the authenticated user's order. The empty string is a valid
# enum member per spec.
PerpsLastUpdateReason = Literal[
    "",
    "Decrease",
    "Amend",
    "MarginCancel",
    "SelfTradeCancel",
    "ExpiryCancel",
    "Trade",
    "PostOnlyCrossCancel",
]

# Spec ``orderGroupUpdatesPayload.msg.event_type`` enum.
OrderGroupEventType = Literal[
    "created",
    "triggered",
    "reset",
    "deleted",
    "limit_updated",
]

__all__ = [
    "OrderGroupEventType",
    "PerpsBookSide",
    "PerpsLastUpdateReason",
    "PerpsSelfTradePreventionType",
]
