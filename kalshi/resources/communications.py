"""Communications / RFQ resource — request-for-quote + quote API.

v3.0.0 reorganized the surface into sub-namespaces matching the OpenAPI tag
structure: ``client.communications.rfqs`` and ``client.communications.quotes``.
The flat ``list_rfqs`` / ``get_rfq`` / ``create_rfq`` / ``delete_rfq`` /
``list_all_rfqs`` / ``list_quotes`` / ``get_quote`` / ``create_quote`` /
``delete_quote`` / ``list_all_quotes`` / ``accept_quote`` / ``confirm_quote``
methods remain as ``@deprecated`` forwarders for one release; they emit
``DeprecationWarning`` on call and will be removed in a future release.
``get_id`` is a misc top-level endpoint and stays on the parent class.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, overload

from typing_extensions import deprecated

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.models.common import Page
from kalshi.models.communications import (
    RFQ,
    AcceptBlockTradeProposalRequest,
    AcceptQuoteRequest,
    BlockTradeProposal,
    CreateQuoteRequest,
    CreateQuoteResponse,
    CreateRFQRequest,
    CreateRFQResponse,
    GetCommunicationsIDResponse,
    GetQuoteResponse,
    GetRFQResponse,
    ProposeBlockTradeRequest,
    ProposeBlockTradeResponse,
    Quote,
    QuoteStatusLiteral,
    RfqStatusLiteral,
    UserFilterLiteral,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _params,
    _seg,
    _validate_limit,
    _validate_max_pages,
)


def _require_quote_filter(
    quote_creator_user_id: str | None,
    rfq_creator_user_id: str | None,
    user_filter: UserFilterLiteral | None,
    rfq_user_filter: UserFilterLiteral | None,
) -> None:
    """Spec + demo require one of these filters on GET /communications/quotes.

    rfq_id alone is NOT sufficient (verified against demo during v0.11.0).
    Fail fast locally instead of paying a network round trip for a 400.
    The ``user_filter`` / ``rfq_user_filter`` params added in spec v3.18.0
    accept ``"self"`` as a server-side shorthand for the caller's user-id,
    so either of them also satisfies the filter requirement.
    """
    if (
        quote_creator_user_id is None
        and rfq_creator_user_id is None
        and user_filter is None
        and rfq_user_filter is None
    ):
        raise ValueError(
            "list_quotes requires one of quote_creator_user_id, "
            "rfq_creator_user_id, user_filter, or rfq_user_filter "
            "(server-side requirement; rfq_id alone is not sufficient)."
        )


# Shared param + body builders (issue #46).


def _list_rfqs_params(
    *,
    cursor: str | None,
    limit: int | None,
    event_ticker: str | None,
    market_ticker: str | None,
    subaccount: int | None,
    status: RfqStatusLiteral | None,
    creator_user_id: str | None,
    user_filter: UserFilterLiteral | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=100)
    return _params(
        cursor=cursor,
        limit=limit,
        event_ticker=event_ticker,
        market_ticker=market_ticker,
        subaccount=subaccount,
        status=status,
        creator_user_id=creator_user_id,
        user_filter=user_filter,
    )


def _list_quotes_params(
    *,
    cursor: str | None,
    limit: int | None,
    min_ts: int | None,
    max_ts: int | None,
    status: QuoteStatusLiteral | None,
    quote_creator_user_id: str | None,
    rfq_creator_user_id: str | None,
    rfq_creator_subtrader_id: str | None,
    rfq_id: str | None,
    user_filter: UserFilterLiteral | None,
    rfq_user_filter: UserFilterLiteral | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=500)
    return _params(
        cursor=cursor,
        limit=limit,
        min_ts=min_ts,
        max_ts=max_ts,
        status=status,
        quote_creator_user_id=quote_creator_user_id,
        rfq_creator_user_id=rfq_creator_user_id,
        rfq_creator_subtrader_id=rfq_creator_subtrader_id,
        rfq_id=rfq_id,
        user_filter=user_filter,
        rfq_user_filter=rfq_user_filter,
    )


def _build_create_rfq_body(
    request: CreateRFQRequest | None,
    *,
    market_ticker: str | None,
    rest_remainder: bool | None,
    contracts: int | None,
    target_cost: Decimal | str | float | int | None,
    replace_existing: bool | None,
    subtrader_id: str | None,
    subaccount: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        market_ticker=market_ticker,
        rest_remainder=rest_remainder,
        contracts=contracts,
        target_cost=target_cost,
        replace_existing=replace_existing,
        subtrader_id=subtrader_id,
        subaccount=subaccount,
    )
    if request is None:
        if market_ticker is None or rest_remainder is None:
            raise TypeError(
                "create_rfq() requires `market_ticker` and `rest_remainder` (or pass `request=...`)"
            )
        request = CreateRFQRequest(
            market_ticker=market_ticker,
            rest_remainder=rest_remainder,
            contracts=contracts,
            target_cost=target_cost,  # type: ignore[arg-type]
            replace_existing=replace_existing,
            subtrader_id=subtrader_id,
            subaccount=subaccount,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_create_quote_body(
    request: CreateQuoteRequest | None,
    *,
    rfq_id: str | None,
    yes_bid: Decimal | str | float | int | None,
    no_bid: Decimal | str | float | int | None,
    rest_remainder: bool | None,
    subaccount: int | None,
    post_only: bool | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        rfq_id=rfq_id,
        yes_bid=yes_bid,
        no_bid=no_bid,
        rest_remainder=rest_remainder,
        subaccount=subaccount,
        post_only=post_only,
    )
    if request is None:
        if rfq_id is None or yes_bid is None or no_bid is None or rest_remainder is None:
            raise TypeError(
                "create_quote() requires `rfq_id`, `yes_bid`, `no_bid`, and "
                "`rest_remainder` (or pass `request=...`)"
            )
        request = CreateQuoteRequest(
            rfq_id=rfq_id,
            yes_bid=yes_bid,  # type: ignore[arg-type]
            no_bid=no_bid,  # type: ignore[arg-type]
            rest_remainder=rest_remainder,
            subaccount=subaccount,
            post_only=post_only,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_accept_quote_body(
    request: AcceptQuoteRequest | None,
    *,
    accepted_side: Literal["yes", "no"] | None,
) -> dict[str, Any]:
    _check_request_exclusive(request, accepted_side=accepted_side)
    if request is None:
        if accepted_side is None:
            raise TypeError("accept_quote() requires `accepted_side` (or pass `request=...`)")
        request = AcceptQuoteRequest(accepted_side=accepted_side)
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _list_block_trade_proposals_params(
    *,
    cursor: str | None,
    limit: int | None,
    market_ticker: str | None,
    status: str | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=100)
    return _params(
        cursor=cursor,
        limit=limit,
        market_ticker=market_ticker,
        status=status,
    )


def _build_propose_block_trade_body(
    request: ProposeBlockTradeRequest | None,
    *,
    buyer_user_id: str | None,
    seller_user_id: str | None,
    market_ticker: str | None,
    price_centi_cents: int | None,
    centicount: int | None,
    maker_side: Literal["yes", "no"] | None,
    expiration_ts: Any,
    buyer_subtrader_id: str | None,
    buyer_subaccount: int | None,
    seller_subtrader_id: str | None,
    seller_subaccount: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        buyer_user_id=buyer_user_id,
        seller_user_id=seller_user_id,
        market_ticker=market_ticker,
        price_centi_cents=price_centi_cents,
        centicount=centicount,
        maker_side=maker_side,
        expiration_ts=expiration_ts,
        buyer_subtrader_id=buyer_subtrader_id,
        buyer_subaccount=buyer_subaccount,
        seller_subtrader_id=seller_subtrader_id,
        seller_subaccount=seller_subaccount,
    )
    if request is None:
        if (
            buyer_user_id is None
            or seller_user_id is None
            or market_ticker is None
            or price_centi_cents is None
            or centicount is None
            or maker_side is None
            or expiration_ts is None
        ):
            raise TypeError(
                "create() requires `buyer_user_id`, `seller_user_id`, "
                "`market_ticker`, `price_centi_cents`, `centicount`, "
                "`maker_side`, and `expiration_ts` (or pass `request=...`)"
            )
        request = ProposeBlockTradeRequest(
            buyer_user_id=buyer_user_id,
            seller_user_id=seller_user_id,
            market_ticker=market_ticker,
            price_centi_cents=price_centi_cents,
            centicount=centicount,
            maker_side=maker_side,
            expiration_ts=expiration_ts,
            buyer_subtrader_id=buyer_subtrader_id,
            buyer_subaccount=buyer_subaccount,
            seller_subtrader_id=seller_subtrader_id,
            seller_subaccount=seller_subaccount,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_accept_block_trade_proposal_body(
    request: AcceptBlockTradeProposalRequest | None,
    *,
    subtrader_id: str | None,
    subaccount: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(request, subtrader_id=subtrader_id, subaccount=subaccount)
    if request is None:
        request = AcceptBlockTradeProposalRequest(
            subtrader_id=subtrader_id,
            subaccount=subaccount,
        )
    # Empty body is valid (spec requestBody required: false). model_dump yields
    # {} when nothing is set, which still forces Content-Type: application/json.
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


# v3.0.0 deprecation messages shown by ``typing_extensions.deprecated`` at the
# call site. Templated so each forwarder names its replacement explicitly.
def _rfq_dep(new: str, old: str) -> str:
    return (
        f"`CommunicationsResource.{old}` is deprecated since v3.0.0 and will "
        f"be removed in a future release; use `client.communications.rfqs.{new}` instead."
    )


def _quote_dep(new: str, old: str) -> str:
    return (
        f"`CommunicationsResource.{old}` is deprecated since v3.0.0 and will "
        f"be removed in a future release; use `client.communications.quotes.{new}` instead."
    )


class RFQsResource(SyncResource):
    """Sync RFQ sub-resource — ``client.communications.rfqs``.

    Reached via :attr:`CommunicationsResource.rfqs`. Backs
    ``/communications/rfqs`` endpoints.
    """

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: RfqStatusLiteral | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[RFQ]:
        self._require_auth()
        params = _list_rfqs_params(
            cursor=cursor,
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
            user_filter=user_filter,
        )
        return self._list(
            "/communications/rfqs", RFQ, "rfqs", params=params, extra_headers=extra_headers
        )

    def list_all(
        self,
        *,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: RfqStatusLiteral | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[RFQ]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_rfqs_params(
            cursor=None,
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
            user_filter=user_filter,
        )
        return self._list_all(
            "/communications/rfqs",
            RFQ,
            "rfqs",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def get(
        self, rfq_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetRFQResponse:
        self._require_auth()
        data = self._get(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}", extra_headers=extra_headers
        )
        return GetRFQResponse.model_validate(data)

    @overload
    def create(
        self, *, request: CreateRFQRequest, extra_headers: dict[str, str] | None = None
    ) -> CreateRFQResponse: ...
    @overload
    def create(
        self,
        *,
        market_ticker: str,
        rest_remainder: bool,
        contracts: int | None = ...,
        target_cost: Decimal | str | float | int | None = ...,
        replace_existing: bool | None = ...,
        subtrader_id: str | None = ...,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateRFQResponse: ...
    def create(
        self,
        *,
        request: CreateRFQRequest | None = None,
        market_ticker: str | None = None,
        rest_remainder: bool | None = None,
        contracts: int | None = None,
        target_cost: Decimal | str | float | int | None = None,
        replace_existing: bool | None = None,
        subtrader_id: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateRFQResponse:
        self._require_auth()
        body = _build_create_rfq_body(
            request,
            market_ticker=market_ticker,
            rest_remainder=rest_remainder,
            contracts=contracts,
            target_cost=target_cost,
            replace_existing=replace_existing,
            subtrader_id=subtrader_id,
            subaccount=subaccount,
        )
        data = self._post("/communications/rfqs", json=body, extra_headers=extra_headers)
        return CreateRFQResponse.model_validate(data)

    def delete(self, rfq_id: str, *, extra_headers: dict[str, str] | None = None) -> None:
        self._require_auth()
        self._delete(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}", extra_headers=extra_headers
        )


class QuotesResource(SyncResource):
    """Sync Quote sub-resource — ``client.communications.quotes``.

    Reached via :attr:`CommunicationsResource.quotes`. Backs
    ``/communications/quotes`` endpoints.
    """

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        status: QuoteStatusLiteral | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Quote]:
        self._require_auth()
        _require_quote_filter(
            quote_creator_user_id,
            rfq_creator_user_id,
            user_filter,
            rfq_user_filter,
        )
        params = _list_quotes_params(
            cursor=cursor,
            limit=limit,
            min_ts=min_ts,
            max_ts=max_ts,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
        )
        return self._list(
            "/communications/quotes", Quote, "quotes", params=params, extra_headers=extra_headers
        )

    def list_all(
        self,
        *,
        limit: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        status: QuoteStatusLiteral | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Quote]:
        self._require_auth()
        _require_quote_filter(
            quote_creator_user_id,
            rfq_creator_user_id,
            user_filter,
            rfq_user_filter,
        )
        _validate_max_pages(max_pages)
        params = _list_quotes_params(
            cursor=None,
            limit=limit,
            min_ts=min_ts,
            max_ts=max_ts,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
        )
        return self._list_all(
            "/communications/quotes",
            Quote,
            "quotes",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def get(
        self, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetQuoteResponse:
        self._require_auth()
        data = self._get(
            f"/communications/quotes/{_seg(quote_id, name='quote_id')}", extra_headers=extra_headers
        )
        return GetQuoteResponse.model_validate(data)

    @overload
    def create(
        self, *, request: CreateQuoteRequest, extra_headers: dict[str, str] | None = None
    ) -> CreateQuoteResponse: ...
    @overload
    def create(
        self,
        *,
        rfq_id: str,
        yes_bid: Decimal | str | float | int,
        no_bid: Decimal | str | float | int,
        rest_remainder: bool,
        subaccount: int | None = ...,
        post_only: bool | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateQuoteResponse: ...
    def create(
        self,
        *,
        request: CreateQuoteRequest | None = None,
        rfq_id: str | None = None,
        yes_bid: Decimal | str | float | int | None = None,
        no_bid: Decimal | str | float | int | None = None,
        rest_remainder: bool | None = None,
        subaccount: int | None = None,
        post_only: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateQuoteResponse:
        self._require_auth()
        body = _build_create_quote_body(
            request,
            rfq_id=rfq_id,
            yes_bid=yes_bid,
            no_bid=no_bid,
            rest_remainder=rest_remainder,
            subaccount=subaccount,
            post_only=post_only,
        )
        data = self._post("/communications/quotes", json=body, extra_headers=extra_headers)
        return CreateQuoteResponse.model_validate(data)

    def delete(self, quote_id: str, *, extra_headers: dict[str, str] | None = None) -> None:
        self._require_auth()
        self._delete(
            f"/communications/quotes/{_seg(quote_id, name='quote_id')}", extra_headers=extra_headers
        )

    @overload
    def accept(
        self,
        quote_id: str,
        *,
        request: AcceptQuoteRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def accept(
        self,
        quote_id: str,
        *,
        accepted_side: Literal["yes", "no"],
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def accept(
        self,
        quote_id: str,
        *,
        request: AcceptQuoteRequest | None = None,
        accepted_side: Literal["yes", "no"] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_accept_quote_body(request, accepted_side=accepted_side)
        self._put(
            f"/communications/quotes/{_seg(quote_id, name='quote_id')}/accept",
            json=body,
            extra_headers=extra_headers,
        )

    def confirm(self, quote_id: str, *, extra_headers: dict[str, str] | None = None) -> None:
        self._require_auth()
        # json={} forces Content-Type: application/json — demo rejects empty PUTs.
        self._put(
            f"/communications/quotes/{_seg(quote_id, name='quote_id')}/confirm",
            json={},
            extra_headers=extra_headers,
        )

    # -- RFQ-scoped quote actions (spec v3.22.0) -------------------------------
    # /communications/rfqs/{rfq_id}/quotes/{quote_id}[/accept|/confirm].
    # Same semantics as the flat quote actions above, but scoped to the RFQ.

    def get_for_rfq(
        self, rfq_id: str, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetQuoteResponse:
        """Get a quote scoped to its RFQ (spec v3.24.0).

        ``GET /communications/rfqs/{rfq_id}/quotes/{quote_id}`` — same payload as
        the flat :meth:`get`, addressed through the parent RFQ.
        """
        self._require_auth()
        data = self._get(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}"
            f"/quotes/{_seg(quote_id, name='quote_id')}",
            extra_headers=extra_headers,
        )
        return GetQuoteResponse.model_validate(data)

    def delete_for_rfq(
        self, rfq_id: str, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        """Delete a quote scoped to its RFQ (spec v3.22.0).

        ``DELETE /communications/rfqs/{rfq_id}/quotes/{quote_id}`` — once
        deleted the quote can no longer be accepted.
        """
        self._require_auth()
        self._delete(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}"
            f"/quotes/{_seg(quote_id, name='quote_id')}",
            extra_headers=extra_headers,
        )

    @overload
    def accept_for_rfq(
        self,
        rfq_id: str,
        quote_id: str,
        *,
        request: AcceptQuoteRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def accept_for_rfq(
        self,
        rfq_id: str,
        quote_id: str,
        *,
        accepted_side: Literal["yes", "no"],
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def accept_for_rfq(
        self,
        rfq_id: str,
        quote_id: str,
        *,
        request: AcceptQuoteRequest | None = None,
        accepted_side: Literal["yes", "no"] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Accept a quote scoped to its RFQ (spec v3.22.0).

        ``PUT /communications/rfqs/{rfq_id}/quotes/{quote_id}/accept`` —
        acceptance still requires the quoter to confirm.
        """
        self._require_auth()
        body = _build_accept_quote_body(request, accepted_side=accepted_side)
        self._put(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}"
            f"/quotes/{_seg(quote_id, name='quote_id')}/accept",
            json=body,
            extra_headers=extra_headers,
        )

    def confirm_for_rfq(
        self, rfq_id: str, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        """Confirm a quote scoped to its RFQ (spec v3.22.0).

        ``PUT /communications/rfqs/{rfq_id}/quotes/{quote_id}/confirm`` —
        starts the order-execution timer.
        """
        self._require_auth()
        # json={} forces Content-Type: application/json — demo rejects empty PUTs.
        self._put(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}"
            f"/quotes/{_seg(quote_id, name='quote_id')}/confirm",
            json={},
            extra_headers=extra_headers,
        )


class BlockTradeProposalsResource(SyncResource):
    """Sync block-trade-proposals sub-resource.

    ``client.communications.block_trade_proposals`` — backs the
    ``/communications/block-trade-proposals`` endpoints (openapi 3.21.0).
    """

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        market_ticker: str | None = None,
        status: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[BlockTradeProposal]:
        self._require_auth()
        params = _list_block_trade_proposals_params(
            cursor=cursor,
            limit=limit,
            market_ticker=market_ticker,
            status=status,
        )
        return self._list(
            "/communications/block-trade-proposals",
            BlockTradeProposal,
            "block_trade_proposals",
            params=params,
            extra_headers=extra_headers,
        )

    def list_all(
        self,
        *,
        limit: int | None = None,
        market_ticker: str | None = None,
        status: str | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[BlockTradeProposal]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_block_trade_proposals_params(
            cursor=None,
            limit=limit,
            market_ticker=market_ticker,
            status=status,
        )
        return self._list_all(
            "/communications/block-trade-proposals",
            BlockTradeProposal,
            "block_trade_proposals",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @overload
    def create(
        self,
        *,
        request: ProposeBlockTradeRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> ProposeBlockTradeResponse: ...
    @overload
    def create(
        self,
        *,
        buyer_user_id: str,
        seller_user_id: str,
        market_ticker: str,
        price_centi_cents: int,
        centicount: int,
        maker_side: Literal["yes", "no"],
        expiration_ts: datetime | str,
        buyer_subtrader_id: str | None = ...,
        buyer_subaccount: int | None = ...,
        seller_subtrader_id: str | None = ...,
        seller_subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> ProposeBlockTradeResponse: ...
    def create(
        self,
        *,
        request: ProposeBlockTradeRequest | None = None,
        buyer_user_id: str | None = None,
        seller_user_id: str | None = None,
        market_ticker: str | None = None,
        price_centi_cents: int | None = None,
        centicount: int | None = None,
        maker_side: Literal["yes", "no"] | None = None,
        expiration_ts: Any = None,
        buyer_subtrader_id: str | None = None,
        buyer_subaccount: int | None = None,
        seller_subtrader_id: str | None = None,
        seller_subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> ProposeBlockTradeResponse:
        self._require_auth()
        body = _build_propose_block_trade_body(
            request,
            buyer_user_id=buyer_user_id,
            seller_user_id=seller_user_id,
            market_ticker=market_ticker,
            price_centi_cents=price_centi_cents,
            centicount=centicount,
            maker_side=maker_side,
            expiration_ts=expiration_ts,
            buyer_subtrader_id=buyer_subtrader_id,
            buyer_subaccount=buyer_subaccount,
            seller_subtrader_id=seller_subtrader_id,
            seller_subaccount=seller_subaccount,
        )
        data = self._post(
            "/communications/block-trade-proposals", json=body, extra_headers=extra_headers
        )
        return ProposeBlockTradeResponse.model_validate(data)

    @overload
    def accept(
        self,
        block_trade_proposal_id: str,
        *,
        request: AcceptBlockTradeProposalRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def accept(
        self,
        block_trade_proposal_id: str,
        *,
        subtrader_id: str | None = ...,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def accept(
        self,
        block_trade_proposal_id: str,
        *,
        request: AcceptBlockTradeProposalRequest | None = None,
        subtrader_id: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_accept_block_trade_proposal_body(
            request, subtrader_id=subtrader_id, subaccount=subaccount
        )
        self._post_void(
            f"/communications/block-trade-proposals/"
            f"{_seg(block_trade_proposal_id, name='block_trade_proposal_id')}/accept",
            json=body,
            extra_headers=extra_headers,
        )


class CommunicationsResource(SyncResource):
    """Sync communications / RFQ API.

    Sub-namespaces:

    - :attr:`rfqs` — :class:`RFQsResource` — ``/communications/rfqs`` surface.
    - :attr:`quotes` — :class:`QuotesResource` — ``/communications/quotes`` surface.

    The misc :meth:`get_id` endpoint stays at the top level because it has no
    sub-noun. The flat ``list_rfqs`` / ``get_rfq`` / ``create_rfq`` /
    ``delete_rfq`` / ``list_all_rfqs`` / ``list_quotes`` / ``get_quote`` /
    ``create_quote`` / ``delete_quote`` / ``list_all_quotes`` / ``accept_quote``
    / ``confirm_quote`` methods are :class:`typing_extensions.deprecated`
    forwarders kept for one release.
    """

    rfqs: RFQsResource
    quotes: QuotesResource
    block_trade_proposals: BlockTradeProposalsResource

    def __init__(self, transport: SyncTransport) -> None:
        super().__init__(transport)
        self.rfqs = RFQsResource(transport)
        self.quotes = QuotesResource(transport)
        self.block_trade_proposals = BlockTradeProposalsResource(transport)

    def get_id(self, *, extra_headers: dict[str, str] | None = None) -> GetCommunicationsIDResponse:
        self._require_auth()
        data = self._get("/communications/id", extra_headers=extra_headers)
        return GetCommunicationsIDResponse.model_validate(data)

    # ── Deprecated flat forwarders (v3.0.0) ────────────────────────────────

    @deprecated(_rfq_dep("list", "list_rfqs"))
    def list_rfqs(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: RfqStatusLiteral | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[RFQ]:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.rfqs.list` instead."""
        return self.rfqs.list(
            cursor=cursor,
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
            user_filter=user_filter,
            extra_headers=extra_headers,
        )

    @deprecated(_rfq_dep("list_all", "list_all_rfqs"))
    def list_all_rfqs(
        self,
        *,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: RfqStatusLiteral | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[RFQ]:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.rfqs.list_all` instead."""
        return self.rfqs.list_all(
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
            user_filter=user_filter,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @deprecated(_rfq_dep("get", "get_rfq"))
    def get_rfq(
        self, rfq_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetRFQResponse:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.rfqs.get` instead."""
        return self.rfqs.get(rfq_id, extra_headers=extra_headers)

    @deprecated(_rfq_dep("create", "create_rfq"))
    def create_rfq(
        self,
        *,
        request: CreateRFQRequest | None = None,
        market_ticker: str | None = None,
        rest_remainder: bool | None = None,
        contracts: int | None = None,
        target_cost: Decimal | str | float | int | None = None,
        replace_existing: bool | None = None,
        subtrader_id: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateRFQResponse:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.rfqs.create` instead."""
        return self.rfqs.create(  # type: ignore[call-overload, no-any-return, misc]  # `misc`: mypy's "too many union combinations" overload limit
            request=request,
            market_ticker=market_ticker,
            rest_remainder=rest_remainder,
            contracts=contracts,
            target_cost=target_cost,
            replace_existing=replace_existing,
            subtrader_id=subtrader_id,
            subaccount=subaccount,
            extra_headers=extra_headers,
        )

    @deprecated(_rfq_dep("delete", "delete_rfq"))
    def delete_rfq(self, rfq_id: str, *, extra_headers: dict[str, str] | None = None) -> None:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.rfqs.delete` instead."""
        self.rfqs.delete(rfq_id, extra_headers=extra_headers)

    @deprecated(_quote_dep("list", "list_quotes"))
    def list_quotes(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        status: QuoteStatusLiteral | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Quote]:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.list` instead."""
        return self.quotes.list(
            cursor=cursor,
            limit=limit,
            min_ts=min_ts,
            max_ts=max_ts,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
            extra_headers=extra_headers,
        )

    @deprecated(_quote_dep("list_all", "list_all_quotes"))
    def list_all_quotes(
        self,
        *,
        limit: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        status: QuoteStatusLiteral | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Quote]:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.list_all` instead."""
        return self.quotes.list_all(
            limit=limit,
            min_ts=min_ts,
            max_ts=max_ts,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @deprecated(_quote_dep("get", "get_quote"))
    def get_quote(
        self, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetQuoteResponse:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.get` instead."""
        return self.quotes.get(quote_id, extra_headers=extra_headers)

    @deprecated(_quote_dep("create", "create_quote"))
    def create_quote(
        self,
        *,
        request: CreateQuoteRequest | None = None,
        rfq_id: str | None = None,
        yes_bid: Decimal | str | float | int | None = None,
        no_bid: Decimal | str | float | int | None = None,
        rest_remainder: bool | None = None,
        subaccount: int | None = None,
        post_only: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateQuoteResponse:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.create` instead."""
        return self.quotes.create(  # type: ignore[call-overload, no-any-return, misc]  # `misc`: mypy's "too many union combinations" overload limit
            request=request,
            rfq_id=rfq_id,
            yes_bid=yes_bid,
            no_bid=no_bid,
            rest_remainder=rest_remainder,
            subaccount=subaccount,
            post_only=post_only,
            extra_headers=extra_headers,
        )

    @deprecated(_quote_dep("delete", "delete_quote"))
    def delete_quote(self, quote_id: str, *, extra_headers: dict[str, str] | None = None) -> None:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.delete` instead."""
        self.quotes.delete(quote_id, extra_headers=extra_headers)

    @deprecated(_quote_dep("accept", "accept_quote"))
    def accept_quote(
        self,
        quote_id: str,
        *,
        request: AcceptQuoteRequest | None = None,
        accepted_side: Literal["yes", "no"] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.accept` instead."""
        self.quotes.accept(  # type: ignore[call-overload]
            quote_id,
            request=request,
            accepted_side=accepted_side,
            extra_headers=extra_headers,
        )

    @deprecated(_quote_dep("confirm", "confirm_quote"))
    def confirm_quote(self, quote_id: str, *, extra_headers: dict[str, str] | None = None) -> None:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.confirm` instead."""
        self.quotes.confirm(quote_id, extra_headers=extra_headers)


class AsyncRFQsResource(AsyncResource):
    """Async RFQ sub-resource — ``client.communications.rfqs``."""

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: RfqStatusLiteral | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[RFQ]:
        self._require_auth()
        params = _list_rfqs_params(
            cursor=cursor,
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
            user_filter=user_filter,
        )
        return await self._list(
            "/communications/rfqs", RFQ, "rfqs", params=params, extra_headers=extra_headers
        )

    def list_all(
        self,
        *,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: RfqStatusLiteral | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[RFQ]:
        """Returns an async iterator — use ``async for``."""
        # Plain ``def`` so _require_auth + _validate_max_pages run at call time.
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_rfqs_params(
            cursor=None,
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
            user_filter=user_filter,
        )
        return self._list_all(
            "/communications/rfqs",
            RFQ,
            "rfqs",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def get(
        self, rfq_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetRFQResponse:
        self._require_auth()
        data = await self._get(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}", extra_headers=extra_headers
        )
        return GetRFQResponse.model_validate(data)

    @overload
    async def create(
        self, *, request: CreateRFQRequest, extra_headers: dict[str, str] | None = None
    ) -> CreateRFQResponse: ...
    @overload
    async def create(
        self,
        *,
        market_ticker: str,
        rest_remainder: bool,
        contracts: int | None = ...,
        target_cost: Decimal | str | float | int | None = ...,
        replace_existing: bool | None = ...,
        subtrader_id: str | None = ...,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateRFQResponse: ...
    async def create(
        self,
        *,
        request: CreateRFQRequest | None = None,
        market_ticker: str | None = None,
        rest_remainder: bool | None = None,
        contracts: int | None = None,
        target_cost: Decimal | str | float | int | None = None,
        replace_existing: bool | None = None,
        subtrader_id: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateRFQResponse:
        self._require_auth()
        body = _build_create_rfq_body(
            request,
            market_ticker=market_ticker,
            rest_remainder=rest_remainder,
            contracts=contracts,
            target_cost=target_cost,
            replace_existing=replace_existing,
            subtrader_id=subtrader_id,
            subaccount=subaccount,
        )
        data = await self._post("/communications/rfqs", json=body, extra_headers=extra_headers)
        return CreateRFQResponse.model_validate(data)

    async def delete(self, rfq_id: str, *, extra_headers: dict[str, str] | None = None) -> None:
        self._require_auth()
        await self._delete(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}", extra_headers=extra_headers
        )


class AsyncQuotesResource(AsyncResource):
    """Async Quote sub-resource — ``client.communications.quotes``."""

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        status: QuoteStatusLiteral | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Quote]:
        self._require_auth()
        _require_quote_filter(
            quote_creator_user_id,
            rfq_creator_user_id,
            user_filter,
            rfq_user_filter,
        )
        params = _list_quotes_params(
            cursor=cursor,
            limit=limit,
            min_ts=min_ts,
            max_ts=max_ts,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
        )
        return await self._list(
            "/communications/quotes", Quote, "quotes", params=params, extra_headers=extra_headers
        )

    def list_all(
        self,
        *,
        limit: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        status: QuoteStatusLiteral | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Quote]:
        """Returns an async iterator — use ``async for``."""
        self._require_auth()
        _require_quote_filter(
            quote_creator_user_id,
            rfq_creator_user_id,
            user_filter,
            rfq_user_filter,
        )
        _validate_max_pages(max_pages)
        params = _list_quotes_params(
            cursor=None,
            limit=limit,
            min_ts=min_ts,
            max_ts=max_ts,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
        )
        return self._list_all(
            "/communications/quotes",
            Quote,
            "quotes",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def get(
        self, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetQuoteResponse:
        self._require_auth()
        data = await self._get(
            f"/communications/quotes/{_seg(quote_id, name='quote_id')}", extra_headers=extra_headers
        )
        return GetQuoteResponse.model_validate(data)

    @overload
    async def create(
        self, *, request: CreateQuoteRequest, extra_headers: dict[str, str] | None = None
    ) -> CreateQuoteResponse: ...
    @overload
    async def create(
        self,
        *,
        rfq_id: str,
        yes_bid: Decimal | str | float | int,
        no_bid: Decimal | str | float | int,
        rest_remainder: bool,
        subaccount: int | None = ...,
        post_only: bool | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateQuoteResponse: ...
    async def create(
        self,
        *,
        request: CreateQuoteRequest | None = None,
        rfq_id: str | None = None,
        yes_bid: Decimal | str | float | int | None = None,
        no_bid: Decimal | str | float | int | None = None,
        rest_remainder: bool | None = None,
        subaccount: int | None = None,
        post_only: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateQuoteResponse:
        self._require_auth()
        body = _build_create_quote_body(
            request,
            rfq_id=rfq_id,
            yes_bid=yes_bid,
            no_bid=no_bid,
            rest_remainder=rest_remainder,
            subaccount=subaccount,
            post_only=post_only,
        )
        data = await self._post("/communications/quotes", json=body, extra_headers=extra_headers)
        return CreateQuoteResponse.model_validate(data)

    async def delete(
        self, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        self._require_auth()
        await self._delete(
            f"/communications/quotes/{_seg(quote_id, name='quote_id')}", extra_headers=extra_headers
        )

    @overload
    async def accept(
        self,
        quote_id: str,
        *,
        request: AcceptQuoteRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def accept(
        self,
        quote_id: str,
        *,
        accepted_side: Literal["yes", "no"],
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def accept(
        self,
        quote_id: str,
        *,
        request: AcceptQuoteRequest | None = None,
        accepted_side: Literal["yes", "no"] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_accept_quote_body(request, accepted_side=accepted_side)
        await self._put(
            f"/communications/quotes/{_seg(quote_id, name='quote_id')}/accept",
            json=body,
            extra_headers=extra_headers,
        )

    async def confirm(
        self, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        self._require_auth()
        # json={} forces Content-Type: application/json — demo rejects empty PUTs.
        await self._put(
            f"/communications/quotes/{_seg(quote_id, name='quote_id')}/confirm",
            json={},
            extra_headers=extra_headers,
        )

    # -- RFQ-scoped quote actions (spec v3.22.0) -------------------------------

    async def get_for_rfq(
        self, rfq_id: str, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetQuoteResponse:
        """Async :meth:`QuotesResource.get_for_rfq` (spec v3.24.0)."""
        self._require_auth()
        data = await self._get(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}"
            f"/quotes/{_seg(quote_id, name='quote_id')}",
            extra_headers=extra_headers,
        )
        return GetQuoteResponse.model_validate(data)

    async def delete_for_rfq(
        self, rfq_id: str, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        """Delete a quote scoped to its RFQ (spec v3.22.0).

        ``DELETE /communications/rfqs/{rfq_id}/quotes/{quote_id}``.
        """
        self._require_auth()
        await self._delete(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}"
            f"/quotes/{_seg(quote_id, name='quote_id')}",
            extra_headers=extra_headers,
        )

    @overload
    async def accept_for_rfq(
        self,
        rfq_id: str,
        quote_id: str,
        *,
        request: AcceptQuoteRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def accept_for_rfq(
        self,
        rfq_id: str,
        quote_id: str,
        *,
        accepted_side: Literal["yes", "no"],
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def accept_for_rfq(
        self,
        rfq_id: str,
        quote_id: str,
        *,
        request: AcceptQuoteRequest | None = None,
        accepted_side: Literal["yes", "no"] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Accept a quote scoped to its RFQ (spec v3.22.0).

        ``PUT /communications/rfqs/{rfq_id}/quotes/{quote_id}/accept``.
        """
        self._require_auth()
        body = _build_accept_quote_body(request, accepted_side=accepted_side)
        await self._put(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}"
            f"/quotes/{_seg(quote_id, name='quote_id')}/accept",
            json=body,
            extra_headers=extra_headers,
        )

    async def confirm_for_rfq(
        self, rfq_id: str, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        """Confirm a quote scoped to its RFQ (spec v3.22.0).

        ``PUT /communications/rfqs/{rfq_id}/quotes/{quote_id}/confirm``.
        """
        self._require_auth()
        # json={} forces Content-Type: application/json — demo rejects empty PUTs.
        await self._put(
            f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}"
            f"/quotes/{_seg(quote_id, name='quote_id')}/confirm",
            json={},
            extra_headers=extra_headers,
        )


class AsyncBlockTradeProposalsResource(AsyncResource):
    """Async block-trade-proposals sub-resource.

    ``client.communications.block_trade_proposals`` — backs the
    ``/communications/block-trade-proposals`` endpoints (openapi 3.21.0).
    """

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        market_ticker: str | None = None,
        status: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[BlockTradeProposal]:
        self._require_auth()
        params = _list_block_trade_proposals_params(
            cursor=cursor,
            limit=limit,
            market_ticker=market_ticker,
            status=status,
        )
        return await self._list(
            "/communications/block-trade-proposals",
            BlockTradeProposal,
            "block_trade_proposals",
            params=params,
            extra_headers=extra_headers,
        )

    def list_all(
        self,
        *,
        limit: int | None = None,
        market_ticker: str | None = None,
        status: str | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[BlockTradeProposal]:
        """Returns an async iterator — use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_block_trade_proposals_params(
            cursor=None,
            limit=limit,
            market_ticker=market_ticker,
            status=status,
        )
        return self._list_all(
            "/communications/block-trade-proposals",
            BlockTradeProposal,
            "block_trade_proposals",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @overload
    async def create(
        self,
        *,
        request: ProposeBlockTradeRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> ProposeBlockTradeResponse: ...
    @overload
    async def create(
        self,
        *,
        buyer_user_id: str,
        seller_user_id: str,
        market_ticker: str,
        price_centi_cents: int,
        centicount: int,
        maker_side: Literal["yes", "no"],
        expiration_ts: datetime | str,
        buyer_subtrader_id: str | None = ...,
        buyer_subaccount: int | None = ...,
        seller_subtrader_id: str | None = ...,
        seller_subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> ProposeBlockTradeResponse: ...
    async def create(
        self,
        *,
        request: ProposeBlockTradeRequest | None = None,
        buyer_user_id: str | None = None,
        seller_user_id: str | None = None,
        market_ticker: str | None = None,
        price_centi_cents: int | None = None,
        centicount: int | None = None,
        maker_side: Literal["yes", "no"] | None = None,
        expiration_ts: Any = None,
        buyer_subtrader_id: str | None = None,
        buyer_subaccount: int | None = None,
        seller_subtrader_id: str | None = None,
        seller_subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> ProposeBlockTradeResponse:
        self._require_auth()
        body = _build_propose_block_trade_body(
            request,
            buyer_user_id=buyer_user_id,
            seller_user_id=seller_user_id,
            market_ticker=market_ticker,
            price_centi_cents=price_centi_cents,
            centicount=centicount,
            maker_side=maker_side,
            expiration_ts=expiration_ts,
            buyer_subtrader_id=buyer_subtrader_id,
            buyer_subaccount=buyer_subaccount,
            seller_subtrader_id=seller_subtrader_id,
            seller_subaccount=seller_subaccount,
        )
        data = await self._post(
            "/communications/block-trade-proposals", json=body, extra_headers=extra_headers
        )
        return ProposeBlockTradeResponse.model_validate(data)

    @overload
    async def accept(
        self,
        block_trade_proposal_id: str,
        *,
        request: AcceptBlockTradeProposalRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def accept(
        self,
        block_trade_proposal_id: str,
        *,
        subtrader_id: str | None = ...,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def accept(
        self,
        block_trade_proposal_id: str,
        *,
        request: AcceptBlockTradeProposalRequest | None = None,
        subtrader_id: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_accept_block_trade_proposal_body(
            request, subtrader_id=subtrader_id, subaccount=subaccount
        )
        await self._post_void(
            f"/communications/block-trade-proposals/"
            f"{_seg(block_trade_proposal_id, name='block_trade_proposal_id')}/accept",
            json=body,
            extra_headers=extra_headers,
        )


class AsyncCommunicationsResource(AsyncResource):
    """Async communications / RFQ API.

    Sub-namespaces:

    - :attr:`rfqs` — :class:`AsyncRFQsResource` — ``/communications/rfqs``.
    - :attr:`quotes` — :class:`AsyncQuotesResource` — ``/communications/quotes``.

    The flat ``list_rfqs`` / ``get_rfq`` / ``create_rfq`` / ``delete_rfq`` /
    ``list_all_rfqs`` / ``list_quotes`` / ``get_quote`` / ``create_quote`` /
    ``delete_quote`` / ``list_all_quotes`` / ``accept_quote`` / ``confirm_quote``
    coroutines are :class:`typing_extensions.deprecated` forwarders kept for
    one release.
    """

    rfqs: AsyncRFQsResource
    quotes: AsyncQuotesResource
    block_trade_proposals: AsyncBlockTradeProposalsResource

    def __init__(self, transport: AsyncTransport) -> None:
        super().__init__(transport)
        self.rfqs = AsyncRFQsResource(transport)
        self.quotes = AsyncQuotesResource(transport)
        self.block_trade_proposals = AsyncBlockTradeProposalsResource(transport)

    async def get_id(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetCommunicationsIDResponse:
        self._require_auth()
        data = await self._get("/communications/id", extra_headers=extra_headers)
        return GetCommunicationsIDResponse.model_validate(data)

    # ── Deprecated flat forwarders (v3.0.0) ────────────────────────────────

    @deprecated(_rfq_dep("list", "list_rfqs"))
    async def list_rfqs(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: RfqStatusLiteral | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[RFQ]:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.rfqs.list` instead."""
        return await self.rfqs.list(
            cursor=cursor,
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
            user_filter=user_filter,
            extra_headers=extra_headers,
        )

    @deprecated(_rfq_dep("list_all", "list_all_rfqs"))
    def list_all_rfqs(
        self,
        *,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: RfqStatusLiteral | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[RFQ]:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.rfqs.list_all` instead."""
        # Plain ``def`` so deprecation + validation fire at call time, before
        # the user awaits/iterates. Mirrors the sub-resource shape.
        return self.rfqs.list_all(
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
            user_filter=user_filter,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @deprecated(_rfq_dep("get", "get_rfq"))
    async def get_rfq(
        self, rfq_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetRFQResponse:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.rfqs.get` instead."""
        return await self.rfqs.get(rfq_id, extra_headers=extra_headers)

    @deprecated(_rfq_dep("create", "create_rfq"))
    async def create_rfq(
        self,
        *,
        request: CreateRFQRequest | None = None,
        market_ticker: str | None = None,
        rest_remainder: bool | None = None,
        contracts: int | None = None,
        target_cost: Decimal | str | float | int | None = None,
        replace_existing: bool | None = None,
        subtrader_id: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateRFQResponse:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.rfqs.create` instead."""
        return await self.rfqs.create(  # type: ignore[call-overload, no-any-return, misc]  # `misc`: mypy's "too many union combinations" overload limit
            request=request,
            market_ticker=market_ticker,
            rest_remainder=rest_remainder,
            contracts=contracts,
            target_cost=target_cost,
            replace_existing=replace_existing,
            subtrader_id=subtrader_id,
            subaccount=subaccount,
            extra_headers=extra_headers,
        )

    @deprecated(_rfq_dep("delete", "delete_rfq"))
    async def delete_rfq(self, rfq_id: str, *, extra_headers: dict[str, str] | None = None) -> None:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.rfqs.delete` instead."""
        await self.rfqs.delete(rfq_id, extra_headers=extra_headers)

    @deprecated(_quote_dep("list", "list_quotes"))
    async def list_quotes(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        status: QuoteStatusLiteral | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Quote]:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.list` instead."""
        return await self.quotes.list(
            cursor=cursor,
            limit=limit,
            min_ts=min_ts,
            max_ts=max_ts,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
            extra_headers=extra_headers,
        )

    @deprecated(_quote_dep("list_all", "list_all_quotes"))
    def list_all_quotes(
        self,
        *,
        limit: int | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        status: QuoteStatusLiteral | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Quote]:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.list_all` instead."""
        return self.quotes.list_all(
            limit=limit,
            min_ts=min_ts,
            max_ts=max_ts,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @deprecated(_quote_dep("get", "get_quote"))
    async def get_quote(
        self, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> GetQuoteResponse:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.get` instead."""
        return await self.quotes.get(quote_id, extra_headers=extra_headers)

    @deprecated(_quote_dep("create", "create_quote"))
    async def create_quote(
        self,
        *,
        request: CreateQuoteRequest | None = None,
        rfq_id: str | None = None,
        yes_bid: Decimal | str | float | int | None = None,
        no_bid: Decimal | str | float | int | None = None,
        rest_remainder: bool | None = None,
        subaccount: int | None = None,
        post_only: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateQuoteResponse:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.create` instead."""
        return await self.quotes.create(  # type: ignore[call-overload, no-any-return, misc]  # `misc`: mypy's "too many union combinations" overload limit
            request=request,
            rfq_id=rfq_id,
            yes_bid=yes_bid,
            no_bid=no_bid,
            rest_remainder=rest_remainder,
            subaccount=subaccount,
            post_only=post_only,
            extra_headers=extra_headers,
        )

    @deprecated(_quote_dep("delete", "delete_quote"))
    async def delete_quote(
        self, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.delete` instead."""
        await self.quotes.delete(quote_id, extra_headers=extra_headers)

    @deprecated(_quote_dep("accept", "accept_quote"))
    async def accept_quote(
        self,
        quote_id: str,
        *,
        request: AcceptQuoteRequest | None = None,
        accepted_side: Literal["yes", "no"] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.accept` instead."""
        await self.quotes.accept(  # type: ignore[call-overload]
            quote_id,
            request=request,
            accepted_side=accepted_side,
            extra_headers=extra_headers,
        )

    @deprecated(_quote_dep("confirm", "confirm_quote"))
    async def confirm_quote(
        self, quote_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        """.. deprecated:: 3.0.0  Use :meth:`client.communications.quotes.confirm` instead."""
        await self.quotes.confirm(quote_id, extra_headers=extra_headers)
