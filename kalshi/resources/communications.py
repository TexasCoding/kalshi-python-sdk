"""Communications / RFQ resource — request-for-quote + quote API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from typing import Any, Literal, overload

from kalshi.models.common import Page
from kalshi.models.communications import (
    RFQ,
    AcceptQuoteRequest,
    CreateQuoteRequest,
    CreateQuoteResponse,
    CreateRFQRequest,
    CreateRFQResponse,
    GetCommunicationsIDResponse,
    GetQuoteResponse,
    GetRFQResponse,
    Quote,
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
    status: str | None,
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
    event_ticker: str | None,
    market_ticker: str | None,
    status: str | None,
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
        event_ticker=event_ticker,
        market_ticker=market_ticker,
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
        market_ticker=market_ticker, rest_remainder=rest_remainder,
        contracts=contracts, target_cost=target_cost,
        replace_existing=replace_existing, subtrader_id=subtrader_id,
        subaccount=subaccount,
    )
    if request is None:
        if market_ticker is None or rest_remainder is None:
            raise TypeError(
                "create_rfq() requires `market_ticker` and `rest_remainder` "
                "(or pass `request=...`)"
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
        request, rfq_id=rfq_id, yes_bid=yes_bid, no_bid=no_bid,
        rest_remainder=rest_remainder, subaccount=subaccount,
        post_only=post_only,
    )
    if request is None:
        if (
            rfq_id is None or yes_bid is None or no_bid is None
            or rest_remainder is None
        ):
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
            raise TypeError(
                "accept_quote() requires `accepted_side` "
                "(or pass `request=...`)"
            )
        request = AcceptQuoteRequest(accepted_side=accepted_side)
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


class CommunicationsResource(SyncResource):
    """Sync communications / RFQ API."""

    def get_id(self) -> GetCommunicationsIDResponse:
        self._require_auth()
        data = self._get("/communications/id")
        return GetCommunicationsIDResponse.model_validate(data)

    def list_rfqs(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: str | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
    ) -> Page[RFQ]:
        self._require_auth()
        params = _list_rfqs_params(
            cursor=cursor, limit=limit, event_ticker=event_ticker,
            market_ticker=market_ticker, subaccount=subaccount,
            status=status, creator_user_id=creator_user_id,
            user_filter=user_filter,
        )
        return self._list("/communications/rfqs", RFQ, "rfqs", params=params)

    def list_all_rfqs(
        self,
        *,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: str | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
    ) -> Iterator[RFQ]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_rfqs_params(
            cursor=None, limit=limit, event_ticker=event_ticker,
            market_ticker=market_ticker, subaccount=subaccount,
            status=status, creator_user_id=creator_user_id,
            user_filter=user_filter,
        )
        return self._list_all(
            "/communications/rfqs", RFQ, "rfqs",
            params=params, max_pages=max_pages,
        )

    def get_rfq(self, rfq_id: str) -> GetRFQResponse:
        self._require_auth()
        data = self._get(f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}")
        return GetRFQResponse.model_validate(data)

    @overload
    def create_rfq(self, *, request: CreateRFQRequest) -> CreateRFQResponse: ...
    @overload
    def create_rfq(
        self,
        *,
        market_ticker: str,
        rest_remainder: bool,
        contracts: int | None = ...,
        target_cost: Decimal | str | float | int | None = ...,
        replace_existing: bool | None = ...,
        subtrader_id: str | None = ...,
        subaccount: int | None = ...,
    ) -> CreateRFQResponse: ...
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
    ) -> CreateRFQResponse:
        self._require_auth()
        body = _build_create_rfq_body(
            request,
            market_ticker=market_ticker, rest_remainder=rest_remainder,
            contracts=contracts, target_cost=target_cost,
            replace_existing=replace_existing, subtrader_id=subtrader_id,
            subaccount=subaccount,
        )
        data = self._post("/communications/rfqs", json=body)
        return CreateRFQResponse.model_validate(data)

    def delete_rfq(self, rfq_id: str) -> None:
        self._require_auth()
        self._delete(f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}")

    def list_quotes(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        status: str | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
    ) -> Page[Quote]:
        self._require_auth()
        _require_quote_filter(
            quote_creator_user_id, rfq_creator_user_id,
            user_filter, rfq_user_filter,
        )
        params = _list_quotes_params(
            cursor=cursor, limit=limit, event_ticker=event_ticker,
            market_ticker=market_ticker, status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
        )
        return self._list("/communications/quotes", Quote, "quotes", params=params)

    def list_all_quotes(
        self,
        *,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        status: str | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
    ) -> Iterator[Quote]:
        self._require_auth()
        _require_quote_filter(
            quote_creator_user_id, rfq_creator_user_id,
            user_filter, rfq_user_filter,
        )
        _validate_max_pages(max_pages)
        params = _list_quotes_params(
            cursor=None, limit=limit, event_ticker=event_ticker,
            market_ticker=market_ticker, status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
        )
        return self._list_all(
            "/communications/quotes", Quote, "quotes",
            params=params, max_pages=max_pages,
        )

    def get_quote(self, quote_id: str) -> GetQuoteResponse:
        self._require_auth()
        data = self._get(f"/communications/quotes/{_seg(quote_id, name='quote_id')}")
        return GetQuoteResponse.model_validate(data)

    @overload
    def create_quote(self, *, request: CreateQuoteRequest) -> CreateQuoteResponse: ...
    @overload
    def create_quote(
        self,
        *,
        rfq_id: str,
        yes_bid: Decimal | str | float | int,
        no_bid: Decimal | str | float | int,
        rest_remainder: bool,
        subaccount: int | None = ...,
        post_only: bool | None = ...,
    ) -> CreateQuoteResponse: ...
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
    ) -> CreateQuoteResponse:
        self._require_auth()
        body = _build_create_quote_body(
            request, rfq_id=rfq_id, yes_bid=yes_bid, no_bid=no_bid,
            rest_remainder=rest_remainder, subaccount=subaccount,
            post_only=post_only,
        )
        data = self._post("/communications/quotes", json=body)
        return CreateQuoteResponse.model_validate(data)

    def delete_quote(self, quote_id: str) -> None:
        self._require_auth()
        self._delete(f"/communications/quotes/{_seg(quote_id, name='quote_id')}")

    @overload
    def accept_quote(
        self, quote_id: str, *, request: AcceptQuoteRequest,
    ) -> None: ...
    @overload
    def accept_quote(
        self, quote_id: str, *, accepted_side: Literal["yes", "no"],
    ) -> None: ...
    def accept_quote(
        self,
        quote_id: str,
        *,
        request: AcceptQuoteRequest | None = None,
        accepted_side: Literal["yes", "no"] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_accept_quote_body(request, accepted_side=accepted_side)
        self._put(f"/communications/quotes/{_seg(quote_id, name='quote_id')}/accept", json=body)

    def confirm_quote(self, quote_id: str) -> None:
        self._require_auth()
        # json={} forces Content-Type: application/json — demo rejects empty PUTs.
        self._put(f"/communications/quotes/{_seg(quote_id, name='quote_id')}/confirm", json={})


class AsyncCommunicationsResource(AsyncResource):
    """Async communications / RFQ API."""

    async def get_id(self) -> GetCommunicationsIDResponse:
        self._require_auth()
        data = await self._get("/communications/id")
        return GetCommunicationsIDResponse.model_validate(data)

    async def list_rfqs(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: str | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
    ) -> Page[RFQ]:
        self._require_auth()
        params = _list_rfqs_params(
            cursor=cursor, limit=limit, event_ticker=event_ticker,
            market_ticker=market_ticker, subaccount=subaccount,
            status=status, creator_user_id=creator_user_id,
            user_filter=user_filter,
        )
        return await self._list("/communications/rfqs", RFQ, "rfqs", params=params)

    def list_all_rfqs(
        self,
        *,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: str | None = None,
        creator_user_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[RFQ]:
        # Plain `def` so _require_auth + _validate_max_pages run at call time.
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_rfqs_params(
            cursor=None, limit=limit, event_ticker=event_ticker,
            market_ticker=market_ticker, subaccount=subaccount,
            status=status, creator_user_id=creator_user_id,
            user_filter=user_filter,
        )
        return self._list_all(
            "/communications/rfqs", RFQ, "rfqs",
            params=params, max_pages=max_pages,
        )

    async def get_rfq(self, rfq_id: str) -> GetRFQResponse:
        self._require_auth()
        data = await self._get(f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}")
        return GetRFQResponse.model_validate(data)

    @overload
    async def create_rfq(self, *, request: CreateRFQRequest) -> CreateRFQResponse: ...
    @overload
    async def create_rfq(
        self,
        *,
        market_ticker: str,
        rest_remainder: bool,
        contracts: int | None = ...,
        target_cost: Decimal | str | float | int | None = ...,
        replace_existing: bool | None = ...,
        subtrader_id: str | None = ...,
        subaccount: int | None = ...,
    ) -> CreateRFQResponse: ...
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
    ) -> CreateRFQResponse:
        self._require_auth()
        body = _build_create_rfq_body(
            request,
            market_ticker=market_ticker, rest_remainder=rest_remainder,
            contracts=contracts, target_cost=target_cost,
            replace_existing=replace_existing, subtrader_id=subtrader_id,
            subaccount=subaccount,
        )
        data = await self._post("/communications/rfqs", json=body)
        return CreateRFQResponse.model_validate(data)

    async def delete_rfq(self, rfq_id: str) -> None:
        self._require_auth()
        await self._delete(f"/communications/rfqs/{_seg(rfq_id, name='rfq_id')}")

    async def list_quotes(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        status: str | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
    ) -> Page[Quote]:
        self._require_auth()
        _require_quote_filter(
            quote_creator_user_id, rfq_creator_user_id,
            user_filter, rfq_user_filter,
        )
        params = _list_quotes_params(
            cursor=cursor, limit=limit, event_ticker=event_ticker,
            market_ticker=market_ticker, status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
        )
        return await self._list(
            "/communications/quotes", Quote, "quotes", params=params,
        )

    def list_all_quotes(
        self,
        *,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        status: str | None = None,
        quote_creator_user_id: str | None = None,
        rfq_creator_user_id: str | None = None,
        rfq_creator_subtrader_id: str | None = None,
        rfq_id: str | None = None,
        user_filter: UserFilterLiteral | None = None,
        rfq_user_filter: UserFilterLiteral | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[Quote]:
        self._require_auth()
        _require_quote_filter(
            quote_creator_user_id, rfq_creator_user_id,
            user_filter, rfq_user_filter,
        )
        _validate_max_pages(max_pages)
        params = _list_quotes_params(
            cursor=None, limit=limit, event_ticker=event_ticker,
            market_ticker=market_ticker, status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
            user_filter=user_filter,
            rfq_user_filter=rfq_user_filter,
        )
        return self._list_all(
            "/communications/quotes", Quote, "quotes",
            params=params, max_pages=max_pages,
        )

    async def get_quote(self, quote_id: str) -> GetQuoteResponse:
        self._require_auth()
        data = await self._get(f"/communications/quotes/{_seg(quote_id, name='quote_id')}")
        return GetQuoteResponse.model_validate(data)

    @overload
    async def create_quote(
        self, *, request: CreateQuoteRequest,
    ) -> CreateQuoteResponse: ...
    @overload
    async def create_quote(
        self,
        *,
        rfq_id: str,
        yes_bid: Decimal | str | float | int,
        no_bid: Decimal | str | float | int,
        rest_remainder: bool,
        subaccount: int | None = ...,
        post_only: bool | None = ...,
    ) -> CreateQuoteResponse: ...
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
    ) -> CreateQuoteResponse:
        self._require_auth()
        body = _build_create_quote_body(
            request, rfq_id=rfq_id, yes_bid=yes_bid, no_bid=no_bid,
            rest_remainder=rest_remainder, subaccount=subaccount,
            post_only=post_only,
        )
        data = await self._post("/communications/quotes", json=body)
        return CreateQuoteResponse.model_validate(data)

    async def delete_quote(self, quote_id: str) -> None:
        self._require_auth()
        await self._delete(f"/communications/quotes/{_seg(quote_id, name='quote_id')}")

    @overload
    async def accept_quote(
        self, quote_id: str, *, request: AcceptQuoteRequest,
    ) -> None: ...
    @overload
    async def accept_quote(
        self, quote_id: str, *, accepted_side: Literal["yes", "no"],
    ) -> None: ...
    async def accept_quote(
        self,
        quote_id: str,
        *,
        request: AcceptQuoteRequest | None = None,
        accepted_side: Literal["yes", "no"] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_accept_quote_body(request, accepted_side=accepted_side)
        await self._put(f"/communications/quotes/{_seg(quote_id, name='quote_id')}/accept", json=body)  # noqa: E501

    async def confirm_quote(self, quote_id: str) -> None:
        self._require_auth()
        # json={} forces Content-Type: application/json — demo rejects empty PUTs.
        await self._put(f"/communications/quotes/{_seg(quote_id, name='quote_id')}/confirm", json={})  # noqa: E501
