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
    ExecInst,
    ExecType,
    MsgType,
    OrdStatus,
    OrdType,
    SelfTradePreventionType,
    SessionRejectReason,
    Side,
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
    FixMessage,
    Heartbeat,
    Logon,
    Logout,
    Reject,
    ResendRequest,
    SequenceReset,
    TestRequest,
)
from kalshi.fix.session import FixSession, FixSessionState
from kalshi.fix.tags import Tag

__all__ = [
    "BEGIN_STRING_FIXT11",
    "SOH",
    "ApplVerID",
    "EncryptMethod",
    "ExecInst",
    "ExecType",
    # Clients / sessions
    "FixClient",
    "FixCodecError",
    # Config
    "FixConfig",
    "FixConnection",
    "FixConnectionError",
    "FixEnvironment",
    "FixLogonError",
    # Messages
    "FixMessage",
    "FixParser",
    "FixProduct",
    "FixRejectError",
    "FixSequenceError",
    "FixSession",
    "FixSessionError",
    "FixSessionState",
    "FixSessionType",
    # Auth
    "FixSigner",
    "Heartbeat",
    # Errors
    "KalshiFixError",
    "Logon",
    "Logout",
    # Enums
    "MsgType",
    "OrdStatus",
    "OrdType",
    "RawMessage",
    "Reject",
    "ResendRequest",
    "SelfTradePreventionType",
    "SequenceReset",
    "SessionRejectReason",
    "Side",
    "Tag",
    "TestRequest",
    "TimeInForce",
    "decode",
    # Codec
    "encode",
]
