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
    # Communications
    "CommunicationsMessage",
    "ErrorMessage",
    "ErrorPayload",
    # Fill
    "FillMessage",
    "FillPayload",
    # Market lifecycle
    "MarketLifecycleMessage",
    "MarketLifecyclePayload",
    # Market positions
    "MarketPositionsMessage",
    "MarketPositionsPayload",
    # Multivariate
    "MultivariateLifecycleMessage",
    "MultivariateMessage",
    "MultivariatePayload",
    "OkMessage",
    # Order group
    "OrderGroupMessage",
    "OrderGroupPayload",
    # Orderbook
    "OrderbookDeltaMessage",
    "OrderbookDeltaPayload",
    "OrderbookSnapshotMessage",
    "OrderbookSnapshotPayload",
    "QuoteAcceptedPayload",
    "QuoteCreatedPayload",
    "QuoteExecutedPayload",
    "RfqCreatedPayload",
    "RfqDeletedPayload",
    "SelectedMarket",
    "SubscribedMessage",
    "SubscriptionInfo",
    # Ticker
    "TickerMessage",
    "TickerPayload",
    # Trade
    "TradeMessage",
    "TradePayload",
    "UnsubscribedMessage",
    # User orders
    "UserOrdersMessage",
    "UserOrdersPayload",
]
