"""Communications / RFQ models — request-for-quote and quote subsystem."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, AwareDatetime, BaseModel, Field

from kalshi.types import DollarDecimal, FixedPointCount, StrictInt

UserFilterLiteral = Literal["self"]
"""Filter for items created by the authenticated user. Spec: UserFilter enum."""

RfqStatusLiteral = Literal["open", "closed"]
"""RFQ status filter for GET /communications/rfqs. Spec: RFQ.status enum."""

QuoteStatusLiteral = Literal["open", "accepted", "confirmed", "executed", "cancelled"]
"""Quote status filter for GET /communications/quotes. Spec: Quote.status enum."""


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
    created_ts: AwareDatetime
    target_cost: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("target_cost_dollars", "target_cost"),
    )
    mve_collection_ticker: str | None = None
    mve_selected_legs: list[MveSelectedLeg] | None = None
    rest_remainder: bool | None = None
    cancellation_reason: str | None = None
    creator_user_id: str | None = None
    cancelled_ts: AwareDatetime | None = None
    updated_ts: AwareDatetime | None = None

    # v3.18.0 backfill (#161).
    creator_subaccount: int | None = None

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
    created_ts: AwareDatetime
    updated_ts: AwareDatetime
    status: str
    accepted_side: Literal["yes", "no"] | None = None
    accepted_ts: AwareDatetime | None = None
    confirmed_ts: AwareDatetime | None = None
    executed_ts: AwareDatetime | None = None
    cancelled_ts: AwareDatetime | None = None
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

    # v3.18.0 backfill (#161). post_only mirrors CreateQuoteRequest.post_only —
    # server echoes the value on Quote when the caller is the creator.
    creator_subaccount: int | None = None
    rfq_creator_subaccount: int | None = None
    post_only: bool | None = None

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

    Spec only requires ``market_ticker`` and ``rest_remainder``; ``contracts``
    and ``target_cost`` are both optional and may both be omitted (a "shopping
    around" RFQ with no committed size or cost). The SDK does not enforce a
    contracts-or-cost invariant because the spec doesn't.
    """

    market_ticker: str
    rest_remainder: bool
    contracts: StrictInt | None = Field(default=None, ge=1)
    target_cost: DollarDecimal | None = Field(
        default=None,
        serialization_alias="target_cost_dollars",
    )
    replace_existing: bool | None = None
    subtrader_id: str | None = None
    subaccount: StrictInt | None = Field(default=None, ge=0)

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
    subaccount: StrictInt | None = Field(default=None, ge=0)
    post_only: bool | None = None

    model_config = {"extra": "forbid"}


class CreateQuoteResponse(BaseModel):
    """Wraps the newly-created quote's id."""

    id: str

    model_config = {"extra": "allow"}


class AcceptQuoteRequest(BaseModel):
    """Body for PUT /communications/quotes/{quote_id}/accept."""

    accepted_side: Literal["yes", "no"]

    model_config = {"extra": "forbid"}


# ── Block trade proposals (openapi 3.21.0) ─────────────────────────────────


class BlockTradeProposal(BaseModel):
    """A block trade proposal — bilateral negotiated trade awaiting both sides.

    ``price_centi_cents`` and ``centicount`` are plain integers in the spec
    (centi-cents and centicounts respectively), NOT FixedPointDollars/_fp
    fixed-point wire fields, so they are not ``DollarDecimal``/``FixedPointCount``.
    """

    id: str
    proposer_user_id: str
    buyer_user_id: str
    seller_user_id: str
    market_ticker: str
    price_centi_cents: int
    centicount: int
    maker_side: Literal["yes", "no"]
    expiration_ts: AwareDatetime
    status: str
    created_ts: AwareDatetime
    updated_ts: AwareDatetime
    buyer_accepted: bool
    seller_accepted: bool
    # Optional fields.
    buyer_subtrader_id: str | None = None
    seller_subtrader_id: str | None = None
    buyer_accepted_ts: AwareDatetime | None = None
    seller_accepted_ts: AwareDatetime | None = None
    executed_ts: AwareDatetime | None = None
    buyer_order_id: str | None = None
    seller_order_id: str | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class GetBlockTradeProposalsResponse(BaseModel):
    """Paginated list of block trade proposals."""

    block_trade_proposals: list[BlockTradeProposal]
    cursor: str | None = None

    model_config = {"extra": "allow"}


class ProposeBlockTradeRequest(BaseModel):
    """Body for POST /communications/block-trade-proposals.

    ``price_centi_cents`` (centi-cents) and ``centicount`` (centicounts) are
    plain integers per spec, both ``minimum: 1``. ``buyer_subtrader_id`` /
    ``buyer_subaccount`` are mutually exclusive (same for the seller pair), but
    the spec does not encode the exclusivity, so the SDK does not enforce it.
    """

    buyer_user_id: str
    seller_user_id: str
    market_ticker: str
    price_centi_cents: StrictInt = Field(ge=1)
    centicount: StrictInt = Field(ge=1)
    maker_side: Literal["yes", "no"]
    expiration_ts: AwareDatetime
    buyer_subtrader_id: str | None = None
    buyer_subaccount: StrictInt | None = Field(default=None, ge=0, le=63)
    seller_subtrader_id: str | None = None
    seller_subaccount: StrictInt | None = Field(default=None, ge=0, le=63)

    model_config = {"extra": "forbid"}


class ProposeBlockTradeResponse(BaseModel):
    """Wraps the newly-created block trade proposal's id."""

    block_trade_proposal_id: str

    model_config = {"extra": "allow"}


class AcceptBlockTradeProposalRequest(BaseModel):
    """Body for POST /communications/block-trade-proposals/{id}/accept.

    Both fields are optional (spec requestBody ``required: false``); accept as
    primary by sending an empty body. ``subtrader_id`` / ``subaccount`` are
    mutually exclusive but the spec does not encode it, so it is not enforced.
    """

    subtrader_id: str | None = None
    subaccount: StrictInt | None = Field(default=None, ge=0, le=63)

    model_config = {"extra": "forbid"}
