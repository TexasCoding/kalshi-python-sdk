"""Typed FIX message models (FIX Dictionary v1.03).

Exposes the base framework (scalar + repeating-group fields), the session-layer
(admin) messages, and the shared repeating-group entry components. Application
messages (order entry, drop copy, market data, RFQ/settlement) are added in later
phases — see GH #402.
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
    "CollateralAmountChange",
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
    "Party",
    "Reject",
    "ResendRequest",
    "SequenceReset",
    "TestRequest",
    "fixfield",
    "groupfield",
]
