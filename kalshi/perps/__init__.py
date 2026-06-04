"""Kalshi Perps (margin) API — standalone client surface.

The Perps (perpetual futures / margin) API lives on a **separate host** from the
prediction (event-contract) API and Kalshi recommends a **separate API key** for
it. It is therefore exposed through standalone :class:`PerpsClient` /
:class:`AsyncPerpsClient` classes with their own :class:`PerpsConfig` rather than
as a namespace on ``KalshiClient``.

The RSA-PSS signer (:class:`kalshi.auth.KalshiAuth`) and the HTTP transport
(:class:`kalshi._base_client.SyncTransport` / ``AsyncTransport``) are reused
unchanged — they sign ``str(ts_ms) + METHOD + path`` and the ``/trade-api/v2``
path component is identical for perps.

Perps model and resource classes are exported from this package namespace
(``kalshi.perps``) rather than the top-level ``kalshi`` namespace, because many
perps schema names (``ExchangeStatus``, ``OrderGroup``, ``CreateOrderGroupRequest``,
``ApplySubaccountTransferRequest``, …) are intentional twins of the prediction-API
models and would collide in ``kalshi.__all__``. Only the headline entry points
(``PerpsClient`` / ``AsyncPerpsClient`` / ``PerpsConfig``) are re-exported from
``kalshi``.
"""

from __future__ import annotations

from kalshi.perps.async_client import AsyncPerpsClient
from kalshi.perps.client import PerpsClient
from kalshi.perps.config import (
    PERPS_DEMO_BASE_URL,
    PERPS_DEMO_WS_URL,
    PERPS_PRODUCTION_BASE_URL,
    PERPS_PRODUCTION_WS_URL,
    PerpsConfig,
)
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
from kalshi.perps.models.exchange import (
    ExchangeStatus,
    GetMarginRiskParametersResponse,
    MarginEnabledResponse,
)
from kalshi.perps.resources.exchange import (
    AsyncPerpsExchangeResource,
    PerpsExchangeResource,
)

__all__ = [
    "PERPS_DEMO_BASE_URL",
    "PERPS_DEMO_WS_URL",
    "PERPS_PRODUCTION_BASE_URL",
    "PERPS_PRODUCTION_WS_URL",
    "AsyncPerpsClient",
    "AsyncPerpsExchangeResource",
    "BookSide",
    "EmptyResponse",
    "ErrorResponse",
    "ExchangeIndex",
    "ExchangeInstance",
    "ExchangeStatus",
    "GetMarginRiskParametersResponse",
    "LastUpdateReason",
    "MarginEnabledResponse",
    "MarginMarketStatus",
    "OrderSource",
    "PerpsClient",
    "PerpsConfig",
    "PerpsExchangeResource",
    "PriceLevelDollarsCountFp",
    "SelfTradePreventionType",
]
