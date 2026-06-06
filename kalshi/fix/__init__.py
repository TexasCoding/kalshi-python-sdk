"""Kalshi FIX protocol support (FIXT.1.1 transport / FIX50SP2 application layer).

A hand-rolled, async-first, dependency-free FIX engine shared by the prediction
and perps (margin) products. One Kalshi FIX dictionary (v1.03) covers both; the
margin product is a subset (no RFQ / settlement / post-trade) that always quotes
fixed-point dollars. See GH issue #402 for the epic and the locked design
decisions (hand-rolled codec + typed Pydantic message models + async session
engine; shared core in ``kalshi.fix`` with a thin margin facade in
``kalshi.perps.fix``).

This package is the *foundation* layer — codec, typed message models, the
session/recovery state machine, the RSA-PSS logon signer, and connectivity
config. Order-entry, drop-copy, market-data, and RFQ/settlement message flows
land in later phases.

Usage::

    from kalshi.fix import FixClient, FixEnvironment, FixSessionType

    client = FixClient.from_env(environment=FixEnvironment.DEMO)
    async with client.order_entry(on_message=handle) as session:
        ...  # send order-entry messages, receive execution reports
"""

from __future__ import annotations

from kalshi.fix.auth import FixSigner
from kalshi.fix.client import FixClient
from kalshi.fix.codec import (
    BEGIN_STRING_FIXT11,
    SOH,
    FixParser,
    RawMessage,
    decode,
    encode,
)
from kalshi.fix.config import (
    FixConfig,
    FixEnvironment,
    FixProduct,
    FixSessionType,
)
from kalshi.fix.connection import FixConnection
from kalshi.fix.enums import (
    ApplVerID,
    EncryptMethod,
    EventResendRejectReason,
    ExecInst,
    ExecType,
    MDEntryType,
    MDReqRejReason,
    MDUpdateAction,
    MsgType,
    OrdStatus,
    OrdType,
    SecurityTradingStatus,
    SelfTradePreventionType,
    SessionRejectReason,
    Side,
    SubscriptionRequestType,
    TimeInForce,
)
from kalshi.fix.errors import (
    FixCodecError,
    FixConnectionError,
    FixLogonError,
    FixRejectError,
    FixSequenceError,
    FixSessionError,
    KalshiFixError,
)
from kalshi.fix.messages import (
    APP_MESSAGE_MODELS,
    BusinessMessageReject,
    CollateralAmountChange,
    EventResendComplete,
    EventResendReject,
    EventResendRequest,
    ExecutionReport,
    FixGroup,
    FixGroupMeta,
    FixMessage,
    Heartbeat,
    Logon,
    Logout,
    MarketDataIncrementalRefresh,
    MarketDataRequest,
    MarketDataRequestReject,
    MarketDataSnapshotFullRefresh,
    MarketSettlementParty,
    MDIncrementalEntry,
    MDSnapshotEntry,
    MiscFee,
    MultivariateSelectedLeg,
    NewOrderSingle,
    OrderCancelReject,
    OrderCancelReplaceRequest,
    OrderCancelRequest,
    OrderMassCancelReport,
    OrderMassCancelRequest,
    Party,
    Reject,
    RelatedSymbol,
    ResendRequest,
    SecurityStatus,
    SecurityStatusRequest,
    SequenceReset,
    TestRequest,
    decode_app_message,
    groupfield,
)
from kalshi.fix.orderbook import BookLevel, FixOrderBook, MarketDataBook
from kalshi.fix.session import FixSession, FixSessionState
from kalshi.fix.tags import Tag

# Sorted (ruff RUF022); grouping is by the imports above, not by ``__all__`` order.
__all__ = [
    "APP_MESSAGE_MODELS",
    "BEGIN_STRING_FIXT11",
    "SOH",
    "ApplVerID",
    "BookLevel",
    "BusinessMessageReject",
    "CollateralAmountChange",
    "EncryptMethod",
    "EventResendComplete",
    "EventResendReject",
    "EventResendRejectReason",
    "EventResendRequest",
    "ExecInst",
    "ExecType",
    "ExecutionReport",
    "FixClient",
    "FixCodecError",
    "FixConfig",
    "FixConnection",
    "FixConnectionError",
    "FixEnvironment",
    "FixGroup",
    "FixGroupMeta",
    "FixLogonError",
    "FixMessage",
    "FixOrderBook",
    "FixParser",
    "FixProduct",
    "FixRejectError",
    "FixSequenceError",
    "FixSession",
    "FixSessionError",
    "FixSessionState",
    "FixSessionType",
    "FixSigner",
    "Heartbeat",
    "KalshiFixError",
    "Logon",
    "Logout",
    "MDEntryType",
    "MDIncrementalEntry",
    "MDReqRejReason",
    "MDSnapshotEntry",
    "MDUpdateAction",
    "MarketDataBook",
    "MarketDataIncrementalRefresh",
    "MarketDataRequest",
    "MarketDataRequestReject",
    "MarketDataSnapshotFullRefresh",
    "MarketSettlementParty",
    "MiscFee",
    "MsgType",
    "MultivariateSelectedLeg",
    "NewOrderSingle",
    "OrdStatus",
    "OrdType",
    "OrderCancelReject",
    "OrderCancelReplaceRequest",
    "OrderCancelRequest",
    "OrderMassCancelReport",
    "OrderMassCancelRequest",
    "Party",
    "RawMessage",
    "Reject",
    "RelatedSymbol",
    "ResendRequest",
    "SecurityStatus",
    "SecurityStatusRequest",
    "SecurityTradingStatus",
    "SelfTradePreventionType",
    "SequenceReset",
    "SessionRejectReason",
    "Side",
    "SubscriptionRequestType",
    "Tag",
    "TestRequest",
    "TimeInForce",
    "decode",
    "decode_app_message",
    "encode",
    "groupfield",
]
