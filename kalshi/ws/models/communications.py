"""Communications channel message models (RFQ and quote notifications)."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal


class RfqCreatedPayload(BaseModel):
    """RFQ created notification payload.

    Wire format per AsyncAPI spec: ``created_ts`` is an RFC3339 date-time
    string; ``target_cost_dollars`` is a dollar string; ``contracts_fp`` is a
    2-decimal fixed-point count string.

    TODO(v0.15.1): ``created_ts`` is spec-aligned but lacks live capture.
    The v0.14.0 ``user_orders`` capture showed demo emitting
    ``created_ts_ms`` as integer milliseconds instead of the spec's ISO
    string. If Communications follows the same pattern, ``created_ts: str``
    will reject frames that previously parsed as ``int``. Capture a live
    frame on demo when the channel is active and confirm or adjust.
    ``extra="allow"`` provides a soft landing for unexpected extras.
    """

    id: str
    creator_id: str | None = None
    market_ticker: str | None = None
    created_ts: str | None = None
    event_ticker: str | None = None
    contracts: str | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_fp", "contracts"),
    )  # _fp format
    target_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("target_cost_dollars", "target_cost"),
    )
    model_config = {"extra": "allow"}


class RfqDeletedPayload(BaseModel):
    """RFQ deleted notification payload.

    ``deleted_ts`` is an RFC3339 date-time string per AsyncAPI spec.
    Same ``created_ts_ms``-precedent caveat as :class:`RfqCreatedPayload`.
    """

    id: str
    creator_id: str | None = None
    market_ticker: str | None = None
    deleted_ts: str | None = None
    model_config = {"extra": "allow"}


class QuoteCreatedPayload(BaseModel):
    """Quote created notification payload."""

    quote_id: str
    rfq_id: str | None = None
    quote_creator_id: str | None = None
    market_ticker: str | None = None
    yes_bid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_bid_dollars", "yes_bid"),
    )
    no_bid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_bid_dollars", "no_bid"),
    )
    created_ts: str | None = None
    model_config = {"extra": "allow"}


class QuoteAcceptedPayload(BaseModel):
    """Quote accepted notification payload."""

    quote_id: str
    rfq_id: str | None = None
    quote_creator_id: str | None = None
    market_ticker: str | None = None
    yes_bid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_bid_dollars", "yes_bid"),
    )
    no_bid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_bid_dollars", "no_bid"),
    )
    accepted_side: str | None = None
    contracts_accepted: str | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_accepted_fp", "contracts_accepted"),
    )  # _fp format
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
    executed_ts: str | None = None
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
