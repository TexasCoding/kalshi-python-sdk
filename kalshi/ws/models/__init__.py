"""WebSocket message models for all 11 Kalshi channels."""
from kalshi.ws.models.base import (
    BaseMessage,
    ErrorMessage,
    ErrorPayload,
    OkMessage,
    SubscribedMessage,
    SubscriptionInfo,
    UnsubscribedMessage,
)
from kalshi.ws.models.communications import (
    CommunicationsMessage,
    QuoteAcceptedPayload,
    QuoteCreatedPayload,
    QuoteExecutedPayload,
    RfqCreatedPayload,
    RfqDeletedPayload,
)
from kalshi.ws.models.fill import FillMessage, FillPayload
from kalshi.ws.models.market_lifecycle import (
    MarketLifecycleMessage,
    MarketLifecyclePayload,
)
from kalshi.ws.models.market_positions import (
    MarketPositionsMessage,
    MarketPositionsPayload,
)
from kalshi.ws.models.multivariate import (
    MultivariateLifecycleMessage,
    MultivariateMessage,
    MultivariatePayload,
    SelectedMarket,
)
from kalshi.ws.models.order_group import (
    OrderGroupMessage,
    OrderGroupPayload,
)
from kalshi.ws.models.orderbook_delta import (
    OrderbookDeltaMessage,
    OrderbookDeltaPayload,
    OrderbookSnapshotMessage,
    OrderbookSnapshotPayload,
)
from kalshi.ws.models.ticker import TickerMessage, TickerPayload
from kalshi.ws.models.trade import TradeMessage, TradePayload
from kalshi.ws.models.user_orders import UserOrdersMessage, UserOrdersPayload

__all__ = [
    # Base envelope
    "BaseMessage",
    "ErrorMessage",
    "ErrorPayload",
    "OkMessage",
    "SubscribedMessage",
    "SubscriptionInfo",
    "UnsubscribedMessage",
    # Orderbook
    "OrderbookDeltaMessage",
    "OrderbookDeltaPayload",
    "OrderbookSnapshotMessage",
    "OrderbookSnapshotPayload",
    # Ticker
    "TickerMessage",
    "TickerPayload",
    # Trade
    "TradeMessage",
    "TradePayload",
    # Fill
    "FillMessage",
    "FillPayload",
    # Market positions
    "MarketPositionsMessage",
    "MarketPositionsPayload",
    # User orders
    "UserOrdersMessage",
    "UserOrdersPayload",
    # Order group
    "OrderGroupMessage",
    "OrderGroupPayload",
    # Market lifecycle
    "MarketLifecycleMessage",
    "MarketLifecyclePayload",
    # Multivariate
    "MultivariateLifecycleMessage",
    "MultivariateMessage",
    "MultivariatePayload",
    "SelectedMarket",
    # Communications
    "CommunicationsMessage",
    "QuoteAcceptedPayload",
    "QuoteCreatedPayload",
    "QuoteExecutedPayload",
    "RfqCreatedPayload",
    "RfqDeletedPayload",
]
