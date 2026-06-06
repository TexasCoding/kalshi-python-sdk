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
from kalshi.fix.errors import FixDecodeError
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
from kalshi.fix.messages.order_groups import OrderGroupResponse
from kalshi.fix.messages.rfq import (
    AcceptQuoteStatus,
    Quote,
    QuoteCancelStatus,
    QuoteConfirmStatus,
    QuoteRequest,
    QuoteRequestAck,
    QuoteRequestReject,
    QuoteStatusReport,
    RFQCancelStatus,
)
from kalshi.fix.messages.settlement import MarketSettlementReport

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
        MsgType.ORDER_GROUP_RESPONSE.value: OrderGroupResponse,
        # RFQ / quoting. R and S are bidirectional — a client acting as market
        # maker (or creator) receives them as notifications, so they decode too.
        MsgType.QUOTE_REQUEST.value: QuoteRequest,
        MsgType.QUOTE.value: Quote,
        MsgType.QUOTE_REQUEST_ACK.value: QuoteRequestAck,
        MsgType.QUOTE_STATUS_REPORT.value: QuoteStatusReport,
        MsgType.QUOTE_REQUEST_REJECT.value: QuoteRequestReject,
        MsgType.QUOTE_CONFIRM_STATUS.value: QuoteConfirmStatus,
        MsgType.QUOTE_CANCEL_STATUS.value: QuoteCancelStatus,
        MsgType.RFQ_CANCEL_STATUS.value: RFQCancelStatus,
        MsgType.ACCEPT_QUOTE_STATUS.value: AcceptQuoteStatus,
        # Market settlement (post trade)
        MsgType.MARKET_SETTLEMENT_REPORT.value: MarketSettlementReport,
    }
)


def decode_app_message_strict(raw: RawMessage) -> FixMessage | None:
    """Decode an inbound application :class:`RawMessage`, raising on a malformed one.

    Returns ``None`` only for an *unregistered* message type (an admin message or
    a not-yet-implemented flow). A registered model whose payload fails schema
    validation raises :class:`~kalshi.fix.errors.FixDecodeError` (chaining the
    underlying error) rather than returning ``None``, so a genuine message lost to
    a single off-spec field is observable. Used by ``FixSession``'s
    ``on_decode_error`` hook; direct callers wanting the distinction can call this.
    """
    mt = raw.msg_type or ""
    model = APP_MESSAGE_MODELS.get(mt)
    if model is None:
        return None
    try:
        return model.from_raw(raw)
    except (ValidationError, ValueError, ArithmeticError) as exc:
        # ValueError: bad bool / int; ArithmeticError: bad Decimal (InvalidOperation).
        # mt is the registered key here, so it is a real (non-empty) MsgType.
        raise FixDecodeError(f"failed to decode inbound {mt}", raw=raw, msg_type=mt) from exc


def decode_app_message(raw: RawMessage) -> FixMessage | None:
    """Decode an inbound application :class:`RawMessage` to its typed model.

    Returns ``None`` for message types without a registered model (an admin
    message or a not-yet-implemented application flow), and also ``None`` if the
    payload fails schema validation — a malformed inbound message is logged and
    swallowed rather than raised into the consumer's ``on_message`` handler. To
    distinguish those two cases (e.g. to route a malformed known message to a
    dead-letter), use :func:`decode_app_message_strict` or ``FixSession``'s
    ``on_decode_error`` hook.
    """
    try:
        return decode_app_message_strict(raw)
    except FixDecodeError:
        logger.warning("failed to decode inbound %s; returning None", raw.msg_type, exc_info=True)
        return None
