"""Communications / RFQ models — request-for-quote and quote subsystem."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import DollarDecimal, FixedPointCount


class MveSelectedLeg(BaseModel):
    """A selected leg within a multivariate event collection RFQ."""

    event_ticker: str | None = None
    market_ticker: str | None = None
    side: str | None = None
    yes_settlement_value: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "yes_settlement_value_dollars", "yes_settlement_value",
        ),
    )

    model_config = {"extra": "allow", "populate_by_name": True}


class RFQ(BaseModel):
    """An RFQ — request for quote on a market."""

    id: str
    creator_id: str
    market_ticker: str
    contracts: FixedPointCount = Field(
        validation_alias=AliasChoices("contracts_fp", "contracts"),
    )
    status: str
    created_ts: datetime
    target_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("target_cost_dollars", "target_cost"),
    )
    mve_collection_ticker: str | None = None
    mve_selected_legs: list[MveSelectedLeg] | None = None
    rest_remainder: bool | None = None
    cancellation_reason: str | None = None
    creator_user_id: str | None = None
    cancelled_ts: datetime | None = None
    updated_ts: datetime | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class Quote(BaseModel):
    """A quote responding to an RFQ."""

    id: str
    rfq_id: str
    creator_id: str
    market_ticker: str
    contracts: FixedPointCount = Field(
        validation_alias=AliasChoices("contracts_fp", "contracts"),
    )
    yes_bid: DollarDecimal = Field(
        validation_alias=AliasChoices("yes_bid_dollars", "yes_bid"),
    )
    no_bid: DollarDecimal = Field(
        validation_alias=AliasChoices("no_bid_dollars", "no_bid"),
    )
    rfq_creator_id: str
    created_ts: datetime
    updated_ts: datetime
    status: str
    accepted_side: Literal["yes", "no"] | None = None
    accepted_ts: datetime | None = None
    confirmed_ts: datetime | None = None
    executed_ts: datetime | None = None
    cancelled_ts: datetime | None = None
    rest_remainder: bool | None = None
    cancellation_reason: str | None = None
    creator_user_id: str | None = None
    rfq_creator_user_id: str | None = None
    rfq_target_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("rfq_target_cost_dollars", "rfq_target_cost"),
    )
    rfq_creator_order_id: str | None = None
    creator_order_id: str | None = None
    yes_contracts: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_contracts_fp", "yes_contracts"),
    )
    no_contracts: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("no_contracts_fp", "no_contracts"),
    )

    model_config = {"extra": "allow", "populate_by_name": True}


class GetCommunicationsIDResponse(BaseModel):
    """Wraps the caller's public communications ID."""

    communications_id: str

    model_config = {"extra": "allow"}


class GetRFQsResponse(BaseModel):
    """Paginated list of RFQs."""

    rfqs: list[RFQ]
    cursor: str | None = None

    model_config = {"extra": "allow"}


class GetRFQResponse(BaseModel):
    """Single-RFQ envelope."""

    rfq: RFQ

    model_config = {"extra": "allow"}


class CreateRFQRequest(BaseModel):
    """Body for POST /communications/rfqs.

    Spec allows ``contracts`` (integer) or ``contracts_fp`` (fixed-point string);
    SDK commits to the integer form. Target cost uses ``_dollars`` wire suffix.
    ``target_cost_centi_cents`` is deprecated upstream — omitted here.
    """

    market_ticker: str
    rest_remainder: bool
    contracts: int | None = Field(default=None, ge=1)
    target_cost: DollarDecimal | None = Field(
        default=None,
        serialization_alias="target_cost_dollars",
    )
    replace_existing: bool | None = None
    subtrader_id: str | None = None
    subaccount: int | None = Field(default=None, ge=0, le=32)

    model_config = {"extra": "forbid"}


class CreateRFQResponse(BaseModel):
    """Wraps the newly-created RFQ's id."""

    id: str

    model_config = {"extra": "allow"}


class GetQuotesResponse(BaseModel):
    """Paginated list of quotes."""

    quotes: list[Quote]
    cursor: str | None = None

    model_config = {"extra": "allow"}


class GetQuoteResponse(BaseModel):
    """Single-quote envelope."""

    quote: Quote

    model_config = {"extra": "allow"}


class CreateQuoteRequest(BaseModel):
    """Body for POST /communications/quotes.

    Unlike order/amend requests, the spec names the wire fields ``yes_bid`` /
    ``no_bid`` (no ``_dollars`` suffix) for this request. The Quote response
    fields, however, use the ``_dollars`` suffix — handled on the response model.
    """

    rfq_id: str
    yes_bid: DollarDecimal
    no_bid: DollarDecimal
    rest_remainder: bool
    subaccount: int | None = Field(default=None, ge=0, le=32)

    model_config = {"extra": "forbid"}


class CreateQuoteResponse(BaseModel):
    """Wraps the newly-created quote's id."""

    id: str

    model_config = {"extra": "allow"}


class AcceptQuoteRequest(BaseModel):
    """Body for PUT /communications/quotes/{quote_id}/accept."""

    accepted_side: Literal["yes", "no"]

    model_config = {"extra": "forbid"}
