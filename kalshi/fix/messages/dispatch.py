"""Inbound application-message dispatch: ``MsgType`` -> typed model.

Central registry spanning the application message flows (order entry, drop copy,
and later market data / RFQ / settlement). A consumer turns an inbound
:class:`~kalshi.fix.codec.RawMessage` (delivered to ``FixSession.on_message``)
into its typed model via :func:`decode_app_message`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import MappingProxyType

from pydantic import ValidationError

from kalshi.fix.codec import RawMessage
from kalshi.fix.enums import MsgType
from kalshi.fix.messages.base import FixMessage
from kalshi.fix.messages.drop_copy import EventResendComplete, EventResendReject
from kalshi.fix.messages.market_data import (
    MarketDataIncrementalRefresh,
    MarketDataRequestReject,
    MarketDataSnapshotFullRefresh,
    SecurityStatus,
)
from kalshi.fix.messages.order_entry import (
    BusinessMessageReject,
    ExecutionReport,
    OrderCancelReject,
    OrderMassCancelReport,
)

logger = logging.getLogger("kalshi.fix")

# Read-only (MappingProxyType) so application code cannot corrupt dispatch.
APP_MESSAGE_MODELS: Mapping[str, type[FixMessage]] = MappingProxyType(
    {
        MsgType.EXECUTION_REPORT.value: ExecutionReport,
        MsgType.ORDER_CANCEL_REJECT.value: OrderCancelReject,
        MsgType.ORDER_MASS_CANCEL_REPORT.value: OrderMassCancelReport,
        MsgType.BUSINESS_MESSAGE_REJECT.value: BusinessMessageReject,
        MsgType.EVENT_RESEND_COMPLETE.value: EventResendComplete,
        MsgType.EVENT_RESEND_REJECT.value: EventResendReject,
        MsgType.MARKET_DATA_SNAPSHOT_FULL_REFRESH.value: MarketDataSnapshotFullRefresh,
        MsgType.MARKET_DATA_INCREMENTAL_REFRESH.value: MarketDataIncrementalRefresh,
        MsgType.MARKET_DATA_REQUEST_REJECT.value: MarketDataRequestReject,
        MsgType.SECURITY_STATUS.value: SecurityStatus,
    }
)


def decode_app_message(raw: RawMessage) -> FixMessage | None:
    """Decode an inbound application :class:`RawMessage` to its typed model.

    Returns ``None`` for message types without a registered model (an admin
    message or a not-yet-implemented application flow), and also ``None`` if the
    payload fails schema validation — a malformed inbound message is logged and
    swallowed rather than raised into the consumer's ``on_message`` handler.
    See GH #432 for surfacing decode failures to consumers.
    """
    model = APP_MESSAGE_MODELS.get(raw.msg_type or "")
    if model is None:
        return None
    try:
        return model.from_raw(raw)
    except (ValidationError, ValueError, ArithmeticError):
        # ValueError: bad bool / int; ArithmeticError: bad Decimal (InvalidOperation).
        logger.warning("failed to decode inbound %s; returning None", raw.msg_type, exc_info=True)
        return None
