"""Order-entry FIX messages (GH #424).

Outbound requests (NewOrderSingle / OrderCancelRequest / OrderCancelReplaceRequest
/ OrderMassCancelRequest) use the typed enum vocabulary and keep required fields
required, so a caller error fails at construction. Inbound reports
(ExecutionReport / OrderCancelReject / OrderMassCancelReport /
BusinessMessageReject) keep their fields optional and carry char/int code fields
as raw ``str``/``int`` (compare against :mod:`kalshi.fix.enums`) so a slightly
off-spec report from the server parses cleanly rather than rejecting.

Pricing: ``Price`` (44) rides the FIX ``PRICE`` field; its units follow the
session's ``UseDollars``: integer cents (1-99) on the prediction product by
default, fixed-point dollars on margin (and on prediction with UseDollars=Y).
Quantities are fractional decimals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from kalshi.fix.enums import (
    ExecInst,
    MassCancelRequestType,
    MsgType,
    OrdType,
    SelfTradePreventionType,
    Side,
    TimeInForce,
)
from kalshi.fix.messages.base import (
    FixGroupMeta,
    FixMessage,
    FixType,
    fixfield,
    groupfield,
)
from kalshi.fix.messages.components import CollateralAmountChange, MiscFee, Party
from kalshi.fix.tags import Tag
from kalshi.types import DollarDecimal, FixedPointCount

# ---------------------------------------------------------------------------
# Outbound requests
# ---------------------------------------------------------------------------


class NewOrderSingle(FixMessage):
    """NewOrderSingle (35=D) — submit a new order.

    ``TransactTime`` (60) is intentionally not sent: the Kalshi dictionary v1.03
    does not include it on 35=D (the gateway stamps its own time), unlike the
    generic FIX 5.0SP2 message.
    """

    MSG_TYPE = MsgType.NEW_ORDER_SINGLE

    cl_ord_id: str = fixfield(Tag.CL_ORD_ID, FixType.STRING)
    exec_inst: ExecInst | None = fixfield(Tag.EXEC_INST, FixType.MULTIPLEVALUESTRING, default=None)
    order_qty: FixedPointCount = fixfield(Tag.ORDER_QTY, FixType.QTY)
    ord_type: OrdType = fixfield(Tag.ORD_TYPE, FixType.CHAR, default=OrdType.LIMIT)
    price: DollarDecimal = fixfield(Tag.PRICE, FixType.PRICE)
    side: Side = fixfield(Tag.SIDE, FixType.CHAR)
    symbol: str = fixfield(Tag.SYMBOL, FixType.STRING)
    time_in_force: TimeInForce | None = fixfield(Tag.TIME_IN_FORCE, FixType.CHAR, default=None)
    expire_time: datetime | None = fixfield(Tag.EXPIRE_TIME, FixType.UTCTIMESTAMP, default=None)
    self_trade_prevention_type: SelfTradePreventionType | None = fixfield(
        Tag.SELF_TRADE_PREVENTION_TYPE, FixType.INT, default=None
    )
    parties: Annotated[list[Party], FixGroupMeta(Tag.NO_PARTY_IDS, Party)] = groupfield()
    secondary_cl_ord_id: str | None = fixfield(
        Tag.SECONDARY_CL_ORD_ID, FixType.STRING, default=None
    )
    order_group_id: str | None = fixfield(Tag.ORDER_GROUP_ID, FixType.STRING, default=None)
    cancel_order_on_pause: bool | None = fixfield(
        Tag.CANCEL_ORDER_ON_PAUSE, FixType.BOOLEAN, default=None
    )
    max_execution_cost: DollarDecimal | None = fixfield(
        Tag.MAX_EXECUTION_COST, FixType.DECIMAL, default=None
    )
    # Kalshi dictionary v1.03 types AllocAccount (79) as INT — the subaccount
    # number (0 primary, 1-32) — not the FIX-standard STRING.
    alloc_account: int | None = fixfield(Tag.ALLOC_ACCOUNT, FixType.INT, default=None)


class OrderCancelReplaceRequest(FixMessage):
    """OrderCancelReplaceRequest (35=G) — amend an order's price/quantity."""

    MSG_TYPE = MsgType.ORDER_CANCEL_REPLACE_REQUEST

    cl_ord_id: str = fixfield(Tag.CL_ORD_ID, FixType.STRING)
    order_id: str | None = fixfield(Tag.ORDER_ID, FixType.STRING, default=None)
    orig_cl_ord_id: str = fixfield(Tag.ORIG_CL_ORD_ID, FixType.STRING)
    order_qty: FixedPointCount = fixfield(Tag.ORDER_QTY, FixType.QTY)
    ord_type: OrdType = fixfield(Tag.ORD_TYPE, FixType.CHAR, default=OrdType.LIMIT)
    price: DollarDecimal | None = fixfield(Tag.PRICE, FixType.PRICE, default=None)
    side: Side = fixfield(Tag.SIDE, FixType.CHAR)
    symbol: str = fixfield(Tag.SYMBOL, FixType.STRING)
    parties: Annotated[list[Party], FixGroupMeta(Tag.NO_PARTY_IDS, Party)] = groupfield()
    order_group_id: str | None = fixfield(Tag.ORDER_GROUP_ID, FixType.STRING, default=None)
    alloc_account: int | None = fixfield(Tag.ALLOC_ACCOUNT, FixType.INT, default=None)


class OrderCancelRequest(FixMessage):
    """OrderCancelRequest (35=F) — cancel an order's remaining quantity."""

    MSG_TYPE = MsgType.ORDER_CANCEL_REQUEST

    cl_ord_id: str = fixfield(Tag.CL_ORD_ID, FixType.STRING)
    order_id: str | None = fixfield(Tag.ORDER_ID, FixType.STRING, default=None)
    orig_cl_ord_id: str = fixfield(Tag.ORIG_CL_ORD_ID, FixType.STRING)
    side: Side = fixfield(Tag.SIDE, FixType.CHAR)
    symbol: str = fixfield(Tag.SYMBOL, FixType.STRING)
    parties: Annotated[list[Party], FixGroupMeta(Tag.NO_PARTY_IDS, Party)] = groupfield()
    alloc_account: int | None = fixfield(Tag.ALLOC_ACCOUNT, FixType.INT, default=None)


class OrderMassCancelRequest(FixMessage):
    """OrderMassCancelRequest (35=q) — cancel all orders for the session (NR only)."""

    MSG_TYPE = MsgType.ORDER_MASS_CANCEL_REQUEST

    cl_ord_id: str = fixfield(Tag.CL_ORD_ID, FixType.STRING)
    mass_cancel_request_type: MassCancelRequestType = fixfield(
        Tag.MASS_CANCEL_REQUEST_TYPE, FixType.CHAR, default=MassCancelRequestType.CANCEL_FOR_SESSION
    )


# ---------------------------------------------------------------------------
# Inbound reports (fields optional; codes raw for robustness)
# ---------------------------------------------------------------------------


class ExecutionReport(FixMessage):
    """ExecutionReport (35=8) — order state change from the exchange.

    ``exec_type`` / ``ord_status`` / ``side`` are raw chars (compare against
    :class:`~kalshi.fix.enums.ExecType` / ``OrdStatus`` / ``Side``); rejection and
    STP codes are raw ints. Position/fee/collateral detail is present on
    ``ExecType=Trade`` via the misc-fees and collateral groups.
    """

    MSG_TYPE = MsgType.EXECUTION_REPORT

    order_id: str | None = fixfield(Tag.ORDER_ID, FixType.STRING, default=None)
    cl_ord_id: str | None = fixfield(Tag.CL_ORD_ID, FixType.STRING, default=None)
    # Kalshi compound "int;int" exec id (e.g. "4;7"; "-1;-1" for PENDING reports);
    # kept as the raw string, not normalized.
    exec_id: str | None = fixfield(Tag.EXEC_ID, FixType.STRING, default=None)
    exec_type: str | None = fixfield(Tag.EXEC_TYPE, FixType.CHAR, default=None)
    ord_status: str | None = fixfield(Tag.ORD_STATUS, FixType.CHAR, default=None)
    side: str | None = fixfield(Tag.SIDE, FixType.CHAR, default=None)
    symbol: str | None = fixfield(Tag.SYMBOL, FixType.STRING, default=None)
    leaves_qty: FixedPointCount | None = fixfield(Tag.LEAVES_QTY, FixType.QTY, default=None)
    cum_qty: FixedPointCount | None = fixfield(Tag.CUM_QTY, FixType.QTY, default=None)
    avg_px: DollarDecimal | None = fixfield(Tag.AVG_PX, FixType.PRICE, default=None)
    order_qty: FixedPointCount | None = fixfield(Tag.ORDER_QTY, FixType.QTY, default=None)
    last_px: DollarDecimal | None = fixfield(Tag.LAST_PX, FixType.PRICE, default=None)
    last_qty: FixedPointCount | None = fixfield(Tag.LAST_QTY, FixType.QTY, default=None)
    ord_rej_reason: int | None = fixfield(Tag.ORD_REJ_REASON, FixType.INT, default=None)
    orig_cl_ord_id: str | None = fixfield(Tag.ORIG_CL_ORD_ID, FixType.STRING, default=None)
    price: DollarDecimal | None = fixfield(Tag.PRICE, FixType.PRICE, default=None)
    transact_time: datetime | None = fixfield(Tag.TRANSACT_TIME, FixType.UTCTIMESTAMP, default=None)
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)
    expire_time: datetime | None = fixfield(Tag.EXPIRE_TIME, FixType.UTCTIMESTAMP, default=None)
    exec_restatement_reason: int | None = fixfield(
        Tag.EXEC_RESTATEMENT_REASON, FixType.INT, default=None
    )
    misc_fees: Annotated[list[MiscFee], FixGroupMeta(Tag.NO_MISC_FEES, MiscFee)] = groupfield()
    parties: Annotated[list[Party], FixGroupMeta(Tag.NO_PARTY_IDS, Party)] = groupfield()
    alloc_account: int | None = fixfield(Tag.ALLOC_ACCOUNT, FixType.INT, default=None)
    long_qty: FixedPointCount | None = fixfield(Tag.LONG_QTY, FixType.QTY, default=None)
    short_qty: FixedPointCount | None = fixfield(Tag.SHORT_QTY, FixType.QTY, default=None)
    collateral_amount_changes: Annotated[
        list[CollateralAmountChange],
        FixGroupMeta(Tag.NO_COLLATERAL_AMOUNT_CHANGES, CollateralAmountChange),
    ] = groupfield()
    trd_match_id: str | None = fixfield(Tag.TRD_MATCH_ID, FixType.STRING, default=None)
    aggressor_indicator: bool | None = fixfield(
        Tag.AGGRESSOR_INDICATOR, FixType.BOOLEAN, default=None
    )
    self_trade_prevention_type: int | None = fixfield(
        Tag.SELF_TRADE_PREVENTION_TYPE, FixType.INT, default=None
    )


class OrderCancelReject(FixMessage):
    """OrderCancelReject (35=9) — an amend/cancel was rejected by the exchange."""

    MSG_TYPE = MsgType.ORDER_CANCEL_REJECT

    order_id: str | None = fixfield(Tag.ORDER_ID, FixType.STRING, default=None)
    cl_ord_id: str | None = fixfield(Tag.CL_ORD_ID, FixType.STRING, default=None)
    orig_cl_ord_id: str | None = fixfield(Tag.ORIG_CL_ORD_ID, FixType.STRING, default=None)
    ord_status: str | None = fixfield(Tag.ORD_STATUS, FixType.CHAR, default=None)
    cxl_rej_response_to: str | None = fixfield(Tag.CXL_REJ_RESPONSE_TO, FixType.CHAR, default=None)
    cxl_rej_reason: int | None = fixfield(Tag.CXL_REJ_REASON, FixType.INT, default=None)
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)


class OrderMassCancelReport(FixMessage):
    """OrderMassCancelReport (35=r) — response to a mass-cancel request."""

    MSG_TYPE = MsgType.ORDER_MASS_CANCEL_REPORT

    cl_ord_id: str | None = fixfield(Tag.CL_ORD_ID, FixType.STRING, default=None)
    order_id: str | None = fixfield(Tag.ORDER_ID, FixType.STRING, default=None)
    mass_cancel_response: str | None = fixfield(
        Tag.MASS_CANCEL_RESPONSE, FixType.CHAR, default=None
    )
    mass_cancel_reject_reason: int | None = fixfield(
        Tag.MASS_CANCEL_REJECT_REASON, FixType.INT, default=None
    )


class BusinessMessageReject(FixMessage):
    """BusinessMessageReject (35=j) — application-level rejection of a message."""

    MSG_TYPE = MsgType.BUSINESS_MESSAGE_REJECT

    ref_seq_num: int | None = fixfield(Tag.REF_SEQ_NUM, FixType.SEQNUM, default=None)
    ref_msg_type: str | None = fixfield(Tag.REF_MSG_TYPE, FixType.STRING, default=None)
    business_reject_ref_id: str | None = fixfield(
        Tag.BUSINESS_REJECT_REF_ID, FixType.STRING, default=None
    )
    business_reject_reason: int | None = fixfield(
        Tag.BUSINESS_REJECT_REASON, FixType.INT, default=None
    )
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)
