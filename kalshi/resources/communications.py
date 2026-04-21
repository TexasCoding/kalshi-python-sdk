"""Communications / RFQ resource — request-for-quote + quote API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from typing import Literal

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
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


def _require_quote_filter(
    quote_creator_user_id: str | None, rfq_creator_user_id: str | None,
) -> None:
    """Spec + demo require one of these filters on GET /communications/quotes.

    rfq_id alone is NOT sufficient (verified against demo during v0.11.0).
    Fail fast locally instead of paying a network round trip for a 400.
    """
    if quote_creator_user_id is None and rfq_creator_user_id is None:
        raise ValueError(
            "list_quotes requires one of quote_creator_user_id or "
            "rfq_creator_user_id (server-side requirement; rfq_id alone "
            "is not sufficient)."
        )


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
    ) -> Page[RFQ]:
        self._require_auth()
        params = _params(
            cursor=cursor,
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
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
    ) -> Iterator[RFQ]:
        self._require_auth()
        params = _params(
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
        )
        yield from self._list_all("/communications/rfqs", RFQ, "rfqs", params=params)

    def get_rfq(self, rfq_id: str) -> GetRFQResponse:
        self._require_auth()
        data = self._get(f"/communications/rfqs/{rfq_id}")
        return GetRFQResponse.model_validate(data)

    def create_rfq(
        self,
        *,
        market_ticker: str,
        rest_remainder: bool,
        contracts: int | None = None,
        target_cost: Decimal | str | float | int | None = None,
        replace_existing: bool | None = None,
        subtrader_id: str | None = None,
        subaccount: int | None = None,
    ) -> CreateRFQResponse:
        self._require_auth()
        req = CreateRFQRequest(
            market_ticker=market_ticker,
            rest_remainder=rest_remainder,
            contracts=contracts,
            target_cost=target_cost,  # type: ignore[arg-type]
            replace_existing=replace_existing,
            subtrader_id=subtrader_id,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post("/communications/rfqs", json=body)
        return CreateRFQResponse.model_validate(data)

    def delete_rfq(self, rfq_id: str) -> None:
        self._require_auth()
        self._delete(f"/communications/rfqs/{rfq_id}")

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
    ) -> Page[Quote]:
        self._require_auth()
        _require_quote_filter(quote_creator_user_id, rfq_creator_user_id)
        params = _params(
            cursor=cursor,
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
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
    ) -> Iterator[Quote]:
        self._require_auth()
        _require_quote_filter(quote_creator_user_id, rfq_creator_user_id)
        params = _params(
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
        )
        return self._list_all(
            "/communications/quotes", Quote, "quotes", params=params,
        )

    def get_quote(self, quote_id: str) -> GetQuoteResponse:
        self._require_auth()
        data = self._get(f"/communications/quotes/{quote_id}")
        return GetQuoteResponse.model_validate(data)

    def create_quote(
        self,
        *,
        rfq_id: str,
        yes_bid: Decimal | str | float | int,
        no_bid: Decimal | str | float | int,
        rest_remainder: bool,
        subaccount: int | None = None,
    ) -> CreateQuoteResponse:
        self._require_auth()
        req = CreateQuoteRequest(
            rfq_id=rfq_id,
            yes_bid=yes_bid,  # type: ignore[arg-type]
            no_bid=no_bid,  # type: ignore[arg-type]
            rest_remainder=rest_remainder,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post("/communications/quotes", json=body)
        return CreateQuoteResponse.model_validate(data)

    def delete_quote(self, quote_id: str) -> None:
        self._require_auth()
        self._delete(f"/communications/quotes/{quote_id}")

    def accept_quote(
        self, quote_id: str, *, accepted_side: Literal["yes", "no"],
    ) -> None:
        self._require_auth()
        req = AcceptQuoteRequest(accepted_side=accepted_side)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        self._put(f"/communications/quotes/{quote_id}/accept", json=body)

    def confirm_quote(self, quote_id: str) -> None:
        self._require_auth()
        # json={} forces Content-Type: application/json — demo rejects empty PUTs.
        self._put(f"/communications/quotes/{quote_id}/confirm", json={})


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
    ) -> Page[RFQ]:
        self._require_auth()
        params = _params(
            cursor=cursor,
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
        )
        return await self._list("/communications/rfqs", RFQ, "rfqs", params=params)

    async def list_all_rfqs(
        self,
        *,
        limit: int | None = None,
        event_ticker: str | None = None,
        market_ticker: str | None = None,
        subaccount: int | None = None,
        status: str | None = None,
        creator_user_id: str | None = None,
    ) -> AsyncIterator[RFQ]:
        self._require_auth()
        params = _params(
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            subaccount=subaccount,
            status=status,
            creator_user_id=creator_user_id,
        )
        async for item in self._list_all(
            "/communications/rfqs", RFQ, "rfqs", params=params,
        ):
            yield item

    async def get_rfq(self, rfq_id: str) -> GetRFQResponse:
        self._require_auth()
        data = await self._get(f"/communications/rfqs/{rfq_id}")
        return GetRFQResponse.model_validate(data)

    async def create_rfq(
        self,
        *,
        market_ticker: str,
        rest_remainder: bool,
        contracts: int | None = None,
        target_cost: Decimal | str | float | int | None = None,
        replace_existing: bool | None = None,
        subtrader_id: str | None = None,
        subaccount: int | None = None,
    ) -> CreateRFQResponse:
        self._require_auth()
        req = CreateRFQRequest(
            market_ticker=market_ticker,
            rest_remainder=rest_remainder,
            contracts=contracts,
            target_cost=target_cost,  # type: ignore[arg-type]
            replace_existing=replace_existing,
            subtrader_id=subtrader_id,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post("/communications/rfqs", json=body)
        return CreateRFQResponse.model_validate(data)

    async def delete_rfq(self, rfq_id: str) -> None:
        self._require_auth()
        await self._delete(f"/communications/rfqs/{rfq_id}")

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
    ) -> Page[Quote]:
        self._require_auth()
        _require_quote_filter(quote_creator_user_id, rfq_creator_user_id)
        params = _params(
            cursor=cursor,
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
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
    ) -> AsyncIterator[Quote]:
        self._require_auth()
        _require_quote_filter(quote_creator_user_id, rfq_creator_user_id)
        params = _params(
            limit=limit,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
            status=status,
            quote_creator_user_id=quote_creator_user_id,
            rfq_creator_user_id=rfq_creator_user_id,
            rfq_creator_subtrader_id=rfq_creator_subtrader_id,
            rfq_id=rfq_id,
        )
        return self._list_all(
            "/communications/quotes", Quote, "quotes", params=params,
        )

    async def get_quote(self, quote_id: str) -> GetQuoteResponse:
        self._require_auth()
        data = await self._get(f"/communications/quotes/{quote_id}")
        return GetQuoteResponse.model_validate(data)

    async def create_quote(
        self,
        *,
        rfq_id: str,
        yes_bid: Decimal | str | float | int,
        no_bid: Decimal | str | float | int,
        rest_remainder: bool,
        subaccount: int | None = None,
    ) -> CreateQuoteResponse:
        self._require_auth()
        req = CreateQuoteRequest(
            rfq_id=rfq_id,
            yes_bid=yes_bid,  # type: ignore[arg-type]
            no_bid=no_bid,  # type: ignore[arg-type]
            rest_remainder=rest_remainder,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post("/communications/quotes", json=body)
        return CreateQuoteResponse.model_validate(data)

    async def delete_quote(self, quote_id: str) -> None:
        self._require_auth()
        await self._delete(f"/communications/quotes/{quote_id}")

    async def accept_quote(
        self, quote_id: str, *, accepted_side: Literal["yes", "no"],
    ) -> None:
        self._require_auth()
        req = AcceptQuoteRequest(accepted_side=accepted_side)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        await self._put(f"/communications/quotes/{quote_id}/accept", json=body)

    async def confirm_quote(self, quote_id: str) -> None:
        self._require_auth()
        # json={} forces Content-Type: application/json — demo rejects empty PUTs.
        await self._put(f"/communications/quotes/{quote_id}/confirm", json={})
