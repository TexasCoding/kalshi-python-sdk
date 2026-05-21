"""Communications channel message models (RFQ and quote notifications)."""
from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal, FixedPointCount


class RfqCreatedPayload(BaseModel):
    """RFQ created notification payload.

    Wire format per AsyncAPI spec: ``created_ts`` is an RFC3339 date-time
    string; ``target_cost_dollars`` is a dollar string; ``contracts_fp`` is a
    2-decimal fixed-point count string.
    """

    id: str
    creator_id: str
    market_ticker: str
    created_ts: datetime
    event_ticker: str | None = None
    contracts: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_fp", "contracts"),
    )
    target_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("target_cost_dollars", "target_cost"),
    )

    # v0.14+ backfill (#162). MVE linkage fields when the RFQ targets a
    # multivariate event collection. Element shape: object with
    # event_ticker/market_ticker/side/yes_settlement_value_dollars.
    mve_collection_ticker: str | None = None
    mve_selected_legs: list[dict[str, object]] | None = None
    model_config = {"extra": "allow"}


class RfqDeletedPayload(BaseModel):
    """RFQ deleted notification payload.

    ``deleted_ts`` is an RFC3339 date-time string per AsyncAPI spec.
    """

    id: str
    creator_id: str
    market_ticker: str
    deleted_ts: datetime

    # v0.14+ backfill (#162). Same RFQ context as RfqCreatedPayload —
    # surfaced again on delete for clients that subscribed mid-RFQ.
    event_ticker: str | None = None
    contracts: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_fp", "contracts"),
    )
    target_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("target_cost_dollars", "target_cost"),
    )
    model_config = {"extra": "allow"}


class QuoteCreatedPayload(BaseModel):
    """Quote created notification payload."""

    quote_id: str
    rfq_id: str
    quote_creator_id: str
    market_ticker: str
    yes_bid: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_bid_dollars", "yes_bid"),
    )
    no_bid: DollarDecimal = Field(
        validation_alias=AliasChoices("no_bid_dollars", "no_bid"),
    )
    created_ts: datetime

    # v0.14+ backfill (#162). Event linkage + RFQ offer/cost context echoed
    # on the quote so subscribers don't need to look up the parent RFQ.
    event_ticker: str | None = None
    yes_contracts_offered: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_contracts_offered_fp", "yes_contracts_offered"),
    )
    no_contracts_offered: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("no_contracts_offered_fp", "no_contracts_offered"),
    )
    rfq_target_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("rfq_target_cost_dollars", "rfq_target_cost"),
    )
    model_config = {"extra": "allow"}


class QuoteAcceptedPayload(BaseModel):
    """Quote accepted notification payload."""

    quote_id: str
    rfq_id: str
    quote_creator_id: str
    market_ticker: str
    yes_bid: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_bid_dollars", "yes_bid"),
    )
    no_bid: DollarDecimal = Field(
        validation_alias=AliasChoices("no_bid_dollars", "no_bid"),
    )
    accepted_side: str | None = None
    contracts_accepted: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_accepted_fp", "contracts_accepted"),
    )

    # v0.14+ backfill (#162). Mirrors QuoteCreatedPayload — same RFQ context
    # echoed on accept.
    event_ticker: str | None = None
    yes_contracts_offered: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_contracts_offered_fp", "yes_contracts_offered"),
    )
    no_contracts_offered: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("no_contracts_offered_fp", "no_contracts_offered"),
    )
    rfq_target_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("rfq_target_cost_dollars", "rfq_target_cost"),
    )
    model_config = {"extra": "allow"}


class QuoteExecutedPayload(BaseModel):
    """Quote executed notification payload."""

    quote_id: str
    rfq_id: str
    quote_creator_id: str
    rfq_creator_id: str
    order_id: str
    client_order_id: str
    market_ticker: str
    executed_ts: datetime
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
