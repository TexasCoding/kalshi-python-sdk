"""Kalshi Perps (margin) API — standalone client surface.

The Perps (perpetual futures / margin) API lives on a **separate host** from the
prediction (event-contract) API and Kalshi recommends a **separate API key** for
it. It is therefore exposed through standalone :class:`PerpsClient` /
:class:`AsyncPerpsClient` classes with their own :class:`PerpsConfig`.

Perps model and resource classes are exported from this package namespace
(``kalshi.perps``) rather than the top-level ``kalshi`` namespace, because many
perps schema names are intentional twins of the prediction-API models and would
collide in ``kalshi.__all__``. Only the headline entry points (``PerpsClient`` /
``AsyncPerpsClient`` / ``PerpsConfig``) are re-exported from ``kalshi``.
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
from kalshi.perps.models.funding import (
    MarginFundingHistoryEntry,
    MarginFundingRate,
    MarginFundingRateEstimate,
)
from kalshi.perps.models.margin_account import (
    GetMarginBalanceResponse,
    GetMarginFeeTiersResponse,
    GetMarginRiskResponse,
    MarginRiskPosition,
    MarginSubaccountBalance,
    NotionalRiskLimitResponse,
)
from kalshi.perps.models.markets import (
    BidAskDistributionHistorical,
    MarginMarket,
    MarginMarketCandlestick,
    MarginMarketStatusLiteral,
    MarginOrderbook,
    MarginOrderbookLevel,
    PriceDistributionHistorical,
)
from kalshi.perps.models.order_groups import (
    CreateOrderGroupRequest,
    CreateOrderGroupResponse,
    GetOrderGroupResponse,
    OrderGroup,
    UpdateOrderGroupLimitRequest,
)
from kalshi.perps.models.orders import (
    AmendMarginOrderRequest,
    AmendMarginOrderResponse,
    BookSideLiteral,
    CancelMarginOrderResponse,
    CreateMarginOrderRequest,
    CreateMarginOrderResponse,
    DecreaseMarginOrderRequest,
    DecreaseMarginOrderResponse,
    GetMarginOrderResponse,
    GetMarginOrdersResponse,
    LastUpdateReasonLiteral,
    MarginOrder,
    OrderSourceLiteral,
    SelfTradePreventionTypeLiteral,
    TimeInForceLiteral,
)
from kalshi.perps.models.portfolio import (
    GetMarginFillsResponse,
    GetMarginPositionsResponse,
    GetMarginTradesResponse,
    MarginFill,
    MarginPosition,
    MarginTrade,
)
from kalshi.perps.models.transfers import (
    ApplySubaccountTransferRequest,
    CreateSubaccountResponse,
    ExchangeInstanceLiteral,
    IntraExchangeInstanceTransferRequest,
    IntraExchangeInstanceTransferResponse,
)
from kalshi.perps.resources.exchange import (
    AsyncPerpsExchangeResource,
    PerpsExchangeResource,
)
from kalshi.perps.resources.funding import (
    AsyncFundingResource,
    FundingResource,
)
from kalshi.perps.resources.margin_account import (
    AsyncMarginAccountResource,
    MarginAccountResource,
)
from kalshi.perps.resources.markets import (
    AsyncPerpsMarketsResource,
    PerpsMarketsResource,
)
from kalshi.perps.resources.order_groups import (
    AsyncOrderGroupsResource,
    OrderGroupsResource,
)
from kalshi.perps.resources.orders import (
    AsyncMarginOrdersResource,
    MarginOrdersResource,
)
from kalshi.perps.resources.portfolio import (
    AsyncPerpsPortfolioResource,
    PerpsPortfolioResource,
)
from kalshi.perps.resources.transfers import (
    AsyncTransfersResource,
    TransfersResource,
)

__all__ = [
    "PERPS_DEMO_BASE_URL",
    "PERPS_DEMO_WS_URL",
    "PERPS_PRODUCTION_BASE_URL",
    "PERPS_PRODUCTION_WS_URL",
    "AmendMarginOrderRequest",
    "AmendMarginOrderResponse",
    "ApplySubaccountTransferRequest",
    "AsyncFundingResource",
    "AsyncMarginAccountResource",
    "AsyncMarginOrdersResource",
    "AsyncOrderGroupsResource",
    "AsyncPerpsClient",
    "AsyncPerpsExchangeResource",
    "AsyncPerpsMarketsResource",
    "AsyncPerpsPortfolioResource",
    "AsyncTransfersResource",
    "BidAskDistributionHistorical",
    "BookSide",
    "BookSideLiteral",
    "CancelMarginOrderResponse",
    "CreateMarginOrderRequest",
    "CreateMarginOrderResponse",
    "CreateOrderGroupRequest",
    "CreateOrderGroupResponse",
    "CreateSubaccountResponse",
    "DecreaseMarginOrderRequest",
    "DecreaseMarginOrderResponse",
    "EmptyResponse",
    "ErrorResponse",
    "ExchangeIndex",
    "ExchangeInstance",
    "ExchangeInstanceLiteral",
    "ExchangeStatus",
    "FundingResource",
    "GetMarginBalanceResponse",
    "GetMarginFeeTiersResponse",
    "GetMarginFillsResponse",
    "GetMarginOrderResponse",
    "GetMarginOrdersResponse",
    "GetMarginPositionsResponse",
    "GetMarginRiskParametersResponse",
    "GetMarginRiskResponse",
    "GetMarginTradesResponse",
    "GetOrderGroupResponse",
    "IntraExchangeInstanceTransferRequest",
    "IntraExchangeInstanceTransferResponse",
    "LastUpdateReason",
    "LastUpdateReasonLiteral",
    "MarginAccountResource",
    "MarginEnabledResponse",
    "MarginFill",
    "MarginFundingHistoryEntry",
    "MarginFundingRate",
    "MarginFundingRateEstimate",
    "MarginMarket",
    "MarginMarketCandlestick",
    "MarginMarketStatus",
    "MarginMarketStatusLiteral",
    "MarginOrder",
    "MarginOrderbook",
    "MarginOrderbookLevel",
    "MarginOrdersResource",
    "MarginPosition",
    "MarginRiskPosition",
    "MarginSubaccountBalance",
    "MarginTrade",
    "NotionalRiskLimitResponse",
    "OrderGroup",
    "OrderGroupsResource",
    "OrderSource",
    "OrderSourceLiteral",
    "PerpsClient",
    "PerpsConfig",
    "PerpsExchangeResource",
    "PerpsMarketsResource",
    "PerpsPortfolioResource",
    "PriceDistributionHistorical",
    "PriceLevelDollarsCountFp",
    "SelfTradePreventionType",
    "SelfTradePreventionTypeLiteral",
    "TimeInForceLiteral",
    "TransfersResource",
    "UpdateOrderGroupLimitRequest",
]
