"""Pydantic models for the Kalshi Perps (margin) API.

Shared enums and value-objects live in :mod:`kalshi.perps.models.common` and are
imported (never redefined) by the per-area model modules. Per-resource model
modules (``markets``, ``orders``, ``order_groups``, ``portfolio``,
``margin_account``, ``funding``, ``transfers``, ``exchange``, ``margin``) are
added by the dependent perps issues.
"""

from __future__ import annotations

from kalshi.perps.models.common import (
    BookSide,
    EmptyResponse,
    ErrorResponse,
    ExchangeIndex,
    ExchangeInstance,
    LastUpdateReason,
    MarginMarketStatus,
    OrderSource,
    PriceLevelDollarsCountFp,
    SelfTradePreventionType,
)

__all__ = [
    "BookSide",
    "EmptyResponse",
    "ErrorResponse",
    "ExchangeIndex",
    "ExchangeInstance",
    "LastUpdateReason",
    "MarginMarketStatus",
    "OrderSource",
    "PriceLevelDollarsCountFp",
    "SelfTradePreventionType",
]
