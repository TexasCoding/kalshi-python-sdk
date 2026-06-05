"""Perps (margin) WebSocket message models.

The command + response/control envelopes live in
:mod:`kalshi.perps.ws.models.control` (#397). The six per-channel data payload
+ envelope models (orderbook snapshot/delta, ticker, trade, fill, user_order,
order_group_updates) and the shared channel literals live in the per-channel
modules added by #398 and are re-exported here.
"""

from kalshi.perps.ws.models._common import (
    OrderGroupEventType,
    PerpsLastUpdateReason,
    PerpsSelfTradePreventionType,
)
from kalshi.perps.ws.models.control import (
    ListSubscriptionsCommand,
    ListSubscriptionsResponse,
    OkMsg,
    OkResponse,
    PerpsBookSide,
    PerpsChannel,
    PerpsErrorMsg,
    PerpsErrorResponse,
    SubscribeCommand,
    SubscribedMsg,
    SubscribedResponse,
    SubscribeParams,
    SubscriptionEntry,
    UnsubscribeCommand,
    UnsubscribedResponse,
    UnsubscribeParams,
    UpdateSubscriptionAction,
    UpdateSubscriptionCommand,
    UpdateSubscriptionParams,
)
from kalshi.perps.ws.models.fill import MarginFillMessage, MarginFillPayload
from kalshi.perps.ws.models.order_group import (
    OrderGroupUpdatesMessage,
    OrderGroupUpdatesPayload,
)
from kalshi.perps.ws.models.orderbook import (
    MarginOrderbookDeltaMessage,
    MarginOrderbookDeltaPayload,
    MarginOrderbookSnapshotMessage,
    MarginOrderbookSnapshotPayload,
)
from kalshi.perps.ws.models.ticker import (
    FundingRate,
    MarginTickerMessage,
    MarginTickerPayload,
    TickerPrice,
)
from kalshi.perps.ws.models.trade import MarginTradeMessage, MarginTradePayload
from kalshi.perps.ws.models.user_orders import (
    MarginUserOrderMessage,
    MarginUserOrderPayload,
)

__all__ = [
    "FundingRate",
    "ListSubscriptionsCommand",
    "ListSubscriptionsResponse",
    "MarginFillMessage",
    "MarginFillPayload",
    "MarginOrderbookDeltaMessage",
    "MarginOrderbookDeltaPayload",
    "MarginOrderbookSnapshotMessage",
    "MarginOrderbookSnapshotPayload",
    "MarginTickerMessage",
    "MarginTickerPayload",
    "MarginTradeMessage",
    "MarginTradePayload",
    "MarginUserOrderMessage",
    "MarginUserOrderPayload",
    "OkMsg",
    "OkResponse",
    "OrderGroupEventType",
    "OrderGroupUpdatesMessage",
    "OrderGroupUpdatesPayload",
    "PerpsBookSide",
    "PerpsChannel",
    "PerpsErrorMsg",
    "PerpsErrorResponse",
    "PerpsLastUpdateReason",
    "PerpsSelfTradePreventionType",
    "SubscribeCommand",
    "SubscribeParams",
    "SubscribedMsg",
    "SubscribedResponse",
    "SubscriptionEntry",
    "TickerPrice",
    "UnsubscribeCommand",
    "UnsubscribeParams",
    "UnsubscribedResponse",
    "UpdateSubscriptionAction",
    "UpdateSubscriptionCommand",
    "UpdateSubscriptionParams",
]
