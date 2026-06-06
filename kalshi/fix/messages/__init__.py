"""Typed FIX message models (FIX Dictionary v1.03).

Exposes the base framework (scalar + repeating-group fields), the session-layer
(admin) messages, the shared repeating-group entry components, and the
order-entry message flow. Market-data, drop-copy, and RFQ/settlement flows are
added in later phases — see GH #402.
"""

from __future__ import annotations

from kalshi.fix.messages.base import (
    FixGroup,
    FixGroupMeta,
    FixMessage,
    FixType,
    fixfield,
    groupfield,
)
from kalshi.fix.messages.components import (
    CollateralAmountChange,
    MarketSettlementParty,
    MiscFee,
    MultivariateSelectedLeg,
    Party,
)
from kalshi.fix.messages.dispatch import APP_MESSAGE_MODELS, decode_app_message
from kalshi.fix.messages.drop_copy import (
    EventResendComplete,
    EventResendReject,
    EventResendRequest,
)
from kalshi.fix.messages.order_entry import (
    BusinessMessageReject,
    ExecutionReport,
    NewOrderSingle,
    OrderCancelReject,
    OrderCancelReplaceRequest,
    OrderCancelRequest,
    OrderMassCancelReport,
    OrderMassCancelRequest,
)
from kalshi.fix.messages.session import (
    Heartbeat,
    Logon,
    Logout,
    Reject,
    ResendRequest,
    SequenceReset,
    TestRequest,
)

__all__ = [
    "APP_MESSAGE_MODELS",
    "BusinessMessageReject",
    "CollateralAmountChange",
    "EventResendComplete",
    "EventResendReject",
    "EventResendRequest",
    "ExecutionReport",
    "FixGroup",
    "FixGroupMeta",
    "FixMessage",
    "FixType",
    "Heartbeat",
    "Logon",
    "Logout",
    "MarketSettlementParty",
    "MiscFee",
    "MultivariateSelectedLeg",
    "NewOrderSingle",
    "OrderCancelReject",
    "OrderCancelReplaceRequest",
    "OrderCancelRequest",
    "OrderMassCancelReport",
    "OrderMassCancelRequest",
    "Party",
    "Reject",
    "ResendRequest",
    "SequenceReset",
    "TestRequest",
    "decode_app_message",
    "fixfield",
    "groupfield",
]
