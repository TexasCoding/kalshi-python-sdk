"""Communications channel message models (RFQ and quote notifications)."""
from __future__ import annotations

from pydantic import BaseModel


class RfqCreatedPayload(BaseModel):
    """RFQ created notification payload."""

    id: str
    creator_id: str | None = None
    market_ticker: str | None = None
    created_ts: int | None = None
    event_ticker: str | None = None
    contracts: str | None = None  # _fp format
    target_cost: str | None = None  # dollar string
    model_config = {"extra": "allow"}


class RfqDeletedPayload(BaseModel):
    """RFQ deleted notification payload."""

    id: str
    creator_id: str | None = None
    market_ticker: str | None = None
    deleted_ts: int | None = None
    model_config = {"extra": "allow"}


class QuoteCreatedPayload(BaseModel):
    """Quote created notification payload."""

    quote_id: str
    rfq_id: str | None = None
    quote_creator_id: str | None = None
    market_ticker: str | None = None
    yes_bid: str | None = None  # dollar string
    no_bid: str | None = None  # dollar string
    created_ts: int | None = None
    model_config = {"extra": "allow"}


class QuoteAcceptedPayload(BaseModel):
    """Quote accepted notification payload."""

    quote_id: str
    rfq_id: str | None = None
    quote_creator_id: str | None = None
    market_ticker: str | None = None
    yes_bid: str | None = None
    no_bid: str | None = None
    accepted_side: str | None = None
    contracts_accepted: str | None = None  # _fp format
    model_config = {"extra": "allow"}


class QuoteExecutedPayload(BaseModel):
    """Quote executed notification payload."""

    quote_id: str
    rfq_id: str | None = None
    quote_creator_id: str | None = None
    rfq_creator_id: str | None = None
    order_id: str | None = None
    client_order_id: str | None = None
    market_ticker: str | None = None
    executed_ts: int | None = None
    model_config = {"extra": "allow"}


class CommunicationsMessage(BaseModel):
    """RFQ and quote notifications. Payload varies by sub-type, so msg is a dict.

    Users who want typed parsing can use the individual payload models
    (RfqCreatedPayload, QuoteCreatedPayload, etc.) to validate msg contents.
    """

    type: str = "communications"
    sid: int
    seq: int | None = None
    msg: dict[str, object]
    model_config = {"extra": "allow"}
