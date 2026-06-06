"""FIX enumerations for the Kalshi dialect (FIXT.1.1 / FIX50SP2).

Values are the exact on-the-wire tokens from the Kalshi FIX Dictionary v1.03.
String/char enums subclass :class:`enum.StrEnum` so ``member.value`` *is* the
wire string; integer enums subclass :class:`enum.IntEnum` and serialize via
``str(int(member))``. The codec / message layer converts in both directions.

Defining the full enum surface up front (including order-entry and RFQ values
not exercised by the foundation layer) keeps a single spec-aligned source of
truth for the later message-flow phases.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class MsgType(StrEnum):
    """Tag 35 — message type. Admin (session) + application message identifiers."""

    # Session / admin
    HEARTBEAT = "0"
    TEST_REQUEST = "1"
    RESEND_REQUEST = "2"
    REJECT = "3"
    SEQUENCE_RESET = "4"
    LOGOUT = "5"
    LOGON = "A"
    # Order entry
    NEW_ORDER_SINGLE = "D"
    ORDER_CANCEL_REQUEST = "F"
    ORDER_CANCEL_REPLACE_REQUEST = "G"
    EXECUTION_REPORT = "8"
    ORDER_CANCEL_REJECT = "9"
    ORDER_MASS_CANCEL_REQUEST = "q"
    ORDER_MASS_CANCEL_REPORT = "r"
    BUSINESS_MESSAGE_REJECT = "j"
    # Order groups
    ORDER_GROUP_REQUEST = "UOG"
    ORDER_GROUP_RESPONSE = "UOH"
    # Drop copy (event resend)
    EVENT_RESEND_REQUEST = "U1"
    EVENT_RESEND_COMPLETE = "U2"
    EVENT_RESEND_REJECT = "U3"
    # Market data
    MARKET_DATA_REQUEST = "V"
    MARKET_DATA_SNAPSHOT_FULL_REFRESH = "W"
    MARKET_DATA_INCREMENTAL_REFRESH = "X"
    MARKET_DATA_REQUEST_REJECT = "Y"
    SECURITY_STATUS_REQUEST = "e"
    SECURITY_STATUS = "f"
    # Post trade
    MARKET_SETTLEMENT_REPORT = "UMS"
    # RFQ / quoting
    QUOTE_REQUEST = "R"
    QUOTE_REQUEST_ACK = "b"
    QUOTE = "S"
    QUOTE_CANCEL = "Z"
    QUOTE_STATUS_REPORT = "AI"
    QUOTE_REQUEST_REJECT = "AG"
    QUOTE_CONFIRM = "U7"
    QUOTE_CONFIRM_STATUS = "U8"
    QUOTE_CANCEL_STATUS = "U9"
    ACCEPT_QUOTE = "UA"
    RFQ_CANCEL_STATUS = "UB"
    ACCEPT_QUOTE_STATUS = "UC"
    RFQ_CANCEL = "UE"


# Admin message types are handled by the session state machine itself; everything
# else is an application message routed to consumers.
ADMIN_MSG_TYPES: frozenset[MsgType] = frozenset(
    {
        MsgType.HEARTBEAT,
        MsgType.TEST_REQUEST,
        MsgType.RESEND_REQUEST,
        MsgType.REJECT,
        MsgType.SEQUENCE_RESET,
        MsgType.LOGOUT,
        MsgType.LOGON,
    }
)


class EncryptMethod(IntEnum):
    """Tag 98 — Kalshi FIX uses transport TLS, so message-level encryption is None."""

    NONE = 0


class ApplVerID(StrEnum):
    """Tags 1128 / 1137 — application version. Kalshi is FIX50SP2."""

    FIX50SP2 = "9"


class Side(StrEnum):
    """Tag 54 — order side in Kalshi's yes/no contract vocabulary."""

    BUY_YES = "1"
    SELL_NO = "2"


class OrdType(StrEnum):
    """Tag 40 — Kalshi supports limit orders only."""

    LIMIT = "2"


class TimeInForce(StrEnum):
    """Tag 59 — order time in force."""

    DAY = "0"
    GTC = "1"
    IOC = "3"
    FOK = "4"
    GTD = "6"


class OrdStatus(StrEnum):
    """Tag 39 — order status."""

    NEW = "0"
    PARTIALLY_FILLED = "1"
    FILLED = "2"
    CANCELED = "4"
    PENDING_CANCEL = "6"
    REJECTED = "8"
    PENDING_NEW = "A"
    EXPIRED = "C"
    PENDING_REPLACE = "E"


class ExecType(StrEnum):
    """Tag 150 — execution report type."""

    NEW = "0"
    CANCELED = "4"
    REPLACED = "5"
    PENDING_CANCEL = "6"
    REJECTED = "8"
    PENDING_NEW = "A"
    EXPIRED = "C"
    PENDING_REPLACE = "E"
    TRADE = "F"


class ExecInst(StrEnum):
    """Tag 18 — execution instructions (multi-value string; Kalshi uses POST_ONLY)."""

    POST_ONLY = "6"


class SelfTradePreventionType(IntEnum):
    """Tag 2964 — self-trade prevention behaviour."""

    UNKNOWN = 0
    TAKER_AT_CROSS = 1
    MAKER = 2


class SessionRejectReason(IntEnum):
    """Tag 373 — reason a session-level Reject (35=3) was issued."""

    INVALID_TAG_NUMBER = 0
    REQUIRED_TAG_MISSING = 1
    TAG_NOT_DEFINED_FOR_MESSAGE = 2
    UNDEFINED_TAG = 3
    TAG_SPECIFIED_WITHOUT_VALUE = 4
    VALUE_INCORRECT = 5
    INCORRECT_DATA_FORMAT = 6
    DECRYPTION_PROBLEM = 7
    SIGNATURE_PROBLEM = 8
    COMPID_PROBLEM = 9
    SENDINGTIME_ACCURACY_PROBLEM = 10
    INVALID_MSGTYPE = 11
    XML_VALIDATION_ERROR = 12
    TAG_APPEARS_MORE_THAN_ONCE = 13
    TAG_SPECIFIED_OUT_OF_REQUIRED_ORDER = 14
    REPEATING_GROUP_FIELDS_OUT_OF_ORDER = 15
    INCORRECT_NUMINGROUP_COUNT_FOR_REPEATING_GROUP = 16
    NON_DATA_VALUE_INCLUDES_FIELD_DELIMITER = 17
    INVALID_UNSUPPORTED_APPLICATION_VERSION = 18
    OTHER = 99


class BusinessRejectReason(IntEnum):
    """Tag 380 — reason a BusinessMessageReject (35=j) was issued."""

    OTHER = 0
    UNKNOWN_ID = 1
    UNKNOWN_SECURITY = 2
    UNSUPPORTED_MESSAGE_TYPE = 3
    APPLICATION_NOT_AVAILABLE = 4
    CONDITIONALLY_REQUIRED_FIELD_MISSING = 5
    NOT_AUTHORIZED = 6
    RATE_LIMIT_EXCEEDED = 8


class CxlRejReason(IntEnum):
    """Tag 102 — order cancel/replace rejection reason."""

    TOO_LATE_TO_CANCEL = 0
    UNKNOWN_ORDER = 1
    BROKER = 2
    INVALID_PRICE_INCREMENT = 18
    OTHER = 99


class CxlRejResponseTo(StrEnum):
    """Tag 434 — which request an OrderCancelReject (35=9) responds to."""

    ORDER_CANCEL_REQUEST = "1"
    ORDER_CANCEL_REPLACE_REQUEST = "2"


class OrdRejReason(IntEnum):
    """Tag 103 — order rejection reason."""

    UNKNOWN_SYMBOL = 1
    EXCHANGE_CLOSED = 2
    ORDER_EXCEEDS_LIMIT = 3
    TOO_LATE_TO_ENTER = 4
    DUPLICATE_ORDER = 6
    STALE_ORDER = 8
    UNSUPPORTED_ORDER_CHARACTERISTIC = 11
    INCORRECT_QUANTITY = 13
    UNKNOWN_ACCOUNT = 15
    OTHER = 99


class MassCancelRequestType(StrEnum):
    """Tag 530 — scope of an OrderMassCancelRequest (35=q)."""

    CANCEL_FOR_SESSION = "6"


class MassCancelResponse(StrEnum):
    """Tag 531 — result of an OrderMassCancelRequest."""

    REJECTED = "0"
    ALL_ORDERS_CANCELLED = "6"


class PartyRole(IntEnum):
    """Tag 452 — role of a party in the NoPartyIDs group."""

    CUSTOMER_ACCOUNT = 24


class OrderGroupAction(IntEnum):
    """Tag 20131 — order-group lifecycle operation (35=UOG)."""

    CREATE = 1
    RESET = 2
    DELETE = 3
    TRIGGER_CANCEL = 4
    UPDATE = 5


class EventResendRejectReason(IntEnum):
    """Tag 21004 — why a drop-copy EventResendRequest (35=U3) was rejected."""

    RATE_LIMITED = 1
    SERVER_ERROR = 2
    BEGIN_EXECID_TOO_SMALL = 3
    END_EXECID_TOO_LARGE = 4


class SubscriptionRequestType(StrEnum):
    """Tag 263 — market-data / security-status subscription action.

    For ``MarketDataRequest`` (35=V): ``0``=snapshot, ``1``=snapshot plus updates,
    ``2``=disable a previous subscription. For ``SecurityStatusRequest`` (35=e)
    only ``1`` (subscribe) and ``2`` (unsubscribe) are valid.
    """

    SNAPSHOT = "0"
    SNAPSHOT_PLUS_UPDATES = "1"
    DISABLE = "2"


class MDEntryType(StrEnum):
    """Tag 269 — side of a market-data book level."""

    BID = "0"
    OFFER = "1"


class MDUpdateAction(StrEnum):
    """Tag 279 — action for an incremental market-data entry (35=X).

    FIX 5.0SP2 also defines New=0; Kalshi MD does not emit it, so it is
    intentionally absent (an action='0' is dropped as unknown).
    """

    CHANGE = "1"
    DELETE = "2"


class MDReqRejReason(StrEnum):
    """Tag 281 — why a MarketDataRequest (35=V) was rejected (35=Y)."""

    INSUFFICIENT_BANDWIDTH = "2"
    UNSUPPORTED_SUBSCRIPTION_REQUEST_TYPE = "4"


class SecurityTradingStatus(IntEnum):
    """Tag 326 — per-market trading-status change streamed via SecurityStatus (35=f)."""

    TRADING_HALT = 2
    RESUME = 3
    KALSHI_DETERMINED = 100
    KALSHI_SETTLED = 101
