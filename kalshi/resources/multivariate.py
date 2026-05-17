"""Multivariate event collections resource — list, get, create, lookup."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator
from typing import overload

from kalshi.models.common import Page
from kalshi.models.multivariate import (
    CreateMarketInMultivariateEventCollectionRequest,
    CreateMarketResponse,
    LookupPoint,
    LookupTickersForMarketInMultivariateEventCollectionRequest,
    LookupTickersResponse,
    MultivariateCollectionStatusLiteral,
    MultivariateEventCollection,
    TickerPair,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _params,
)


class MultivariateCollectionsResource(SyncResource):
    """Sync multivariate event collections API."""

    def list(
        self,
        *,
        status: MultivariateCollectionStatusLiteral | None = None,
        associated_event_ticker: str | None = None,
        series_ticker: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[MultivariateEventCollection]:
        params = _params(
            status=status,
            associated_event_ticker=associated_event_ticker,
            series_ticker=series_ticker,
            limit=limit,
            cursor=cursor,
        )
        return self._list(
            "/multivariate_event_collections",
            MultivariateEventCollection,
            "multivariate_contracts",
            params=params,
        )

    def list_all(
        self,
        *,
        status: MultivariateCollectionStatusLiteral | None = None,
        associated_event_ticker: str | None = None,
        series_ticker: str | None = None,
        limit: int | None = None,
    ) -> Iterator[MultivariateEventCollection]:
        params = _params(
            status=status,
            associated_event_ticker=associated_event_ticker,
            series_ticker=series_ticker,
            limit=limit,
        )
        return self._list_all(
            "/multivariate_event_collections",
            MultivariateEventCollection,
            "multivariate_contracts",
            params=params,
        )

    def get(self, collection_ticker: str) -> MultivariateEventCollection:
        data = self._get(f"/multivariate_event_collections/{collection_ticker}")
        return MultivariateEventCollection.model_validate(
            data.get("multivariate_contract", data)
        )

    @overload
    def create_market(
        self,
        collection_ticker: str,
        *,
        request: CreateMarketInMultivariateEventCollectionRequest,
    ) -> CreateMarketResponse: ...
    @overload
    def create_market(
        self,
        collection_ticker: str,
        *,
        selected_markets: builtins.list[TickerPair],
        with_market_payload: bool | None = ...,
    ) -> CreateMarketResponse: ...
    def create_market(
        self,
        collection_ticker: str,
        *,
        request: CreateMarketInMultivariateEventCollectionRequest | None = None,
        selected_markets: builtins.list[TickerPair] | None = None,
        with_market_payload: bool | None = None,
    ) -> CreateMarketResponse:
        self._require_auth()
        _check_request_exclusive(
            request,
            selected_markets=selected_markets,
            with_market_payload=with_market_payload,
        )
        if request is None:
            if selected_markets is None:
                raise TypeError(
                    "create_market() requires `selected_markets` "
                    "(or pass `request=...`)"
                )
            request = CreateMarketInMultivariateEventCollectionRequest(
                selected_markets=list(selected_markets),
                with_market_payload=with_market_payload,
            )
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post(
            f"/multivariate_event_collections/{collection_ticker}",
            json=body,
        )
        return CreateMarketResponse.model_validate(data)

    @overload
    def lookup_tickers(
        self,
        collection_ticker: str,
        *,
        request: LookupTickersForMarketInMultivariateEventCollectionRequest,
    ) -> LookupTickersResponse: ...
    @overload
    def lookup_tickers(
        self,
        collection_ticker: str,
        *,
        selected_markets: builtins.list[TickerPair],
    ) -> LookupTickersResponse: ...
    def lookup_tickers(
        self,
        collection_ticker: str,
        *,
        request: (
            LookupTickersForMarketInMultivariateEventCollectionRequest | None
        ) = None,
        selected_markets: builtins.list[TickerPair] | None = None,
    ) -> LookupTickersResponse:
        self._require_auth()
        _check_request_exclusive(request, selected_markets=selected_markets)
        if request is None:
            if selected_markets is None:
                raise TypeError(
                    "lookup_tickers() requires `selected_markets` "
                    "(or pass `request=...`)"
                )
            request = LookupTickersForMarketInMultivariateEventCollectionRequest(
                selected_markets=list(selected_markets),
            )
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._put(
            f"/multivariate_event_collections/{collection_ticker}/lookup",
            json=body,
        )
        # Spec: this endpoint always returns 200 with body; guard against a
        # future server regression to 204 giving opaque Pydantic errors.
        # (use an explicit check, not assert — asserts are stripped under -O)
        if data is None:
            raise RuntimeError(
                "lookup: expected 200 with body, got 204 (spec drift)",
            )
        return LookupTickersResponse.model_validate(data)

    def lookup_history(
        self,
        collection_ticker: str,
        *,
        lookback_seconds: int,
    ) -> builtins.list[LookupPoint]:
        params = _params(lookback_seconds=lookback_seconds)
        data = self._get(
            f"/multivariate_event_collections/{collection_ticker}/lookup",
            params=params,
        )
        raw = data.get("lookup_points", [])
        return [LookupPoint.model_validate(item) for item in raw]


class AsyncMultivariateCollectionsResource(AsyncResource):
    """Async multivariate event collections API."""

    async def list(
        self,
        *,
        status: MultivariateCollectionStatusLiteral | None = None,
        associated_event_ticker: str | None = None,
        series_ticker: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[MultivariateEventCollection]:
        params = _params(
            status=status,
            associated_event_ticker=associated_event_ticker,
            series_ticker=series_ticker,
            limit=limit,
            cursor=cursor,
        )
        return await self._list(
            "/multivariate_event_collections",
            MultivariateEventCollection,
            "multivariate_contracts",
            params=params,
        )

    def list_all(
        self,
        *,
        status: MultivariateCollectionStatusLiteral | None = None,
        associated_event_ticker: str | None = None,
        series_ticker: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[MultivariateEventCollection]:
        params = _params(
            status=status,
            associated_event_ticker=associated_event_ticker,
            series_ticker=series_ticker,
            limit=limit,
        )
        return self._list_all(
            "/multivariate_event_collections",
            MultivariateEventCollection,
            "multivariate_contracts",
            params=params,
        )

    async def get(self, collection_ticker: str) -> MultivariateEventCollection:
        data = await self._get(f"/multivariate_event_collections/{collection_ticker}")
        return MultivariateEventCollection.model_validate(
            data.get("multivariate_contract", data)
        )

    @overload
    async def create_market(
        self,
        collection_ticker: str,
        *,
        request: CreateMarketInMultivariateEventCollectionRequest,
    ) -> CreateMarketResponse: ...
    @overload
    async def create_market(
        self,
        collection_ticker: str,
        *,
        selected_markets: builtins.list[TickerPair],
        with_market_payload: bool | None = ...,
    ) -> CreateMarketResponse: ...
    async def create_market(
        self,
        collection_ticker: str,
        *,
        request: CreateMarketInMultivariateEventCollectionRequest | None = None,
        selected_markets: builtins.list[TickerPair] | None = None,
        with_market_payload: bool | None = None,
    ) -> CreateMarketResponse:
        self._require_auth()
        _check_request_exclusive(
            request,
            selected_markets=selected_markets,
            with_market_payload=with_market_payload,
        )
        if request is None:
            if selected_markets is None:
                raise TypeError(
                    "create_market() requires `selected_markets` "
                    "(or pass `request=...`)"
                )
            request = CreateMarketInMultivariateEventCollectionRequest(
                selected_markets=list(selected_markets),
                with_market_payload=with_market_payload,
            )
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post(
            f"/multivariate_event_collections/{collection_ticker}",
            json=body,
        )
        return CreateMarketResponse.model_validate(data)

    @overload
    async def lookup_tickers(
        self,
        collection_ticker: str,
        *,
        request: LookupTickersForMarketInMultivariateEventCollectionRequest,
    ) -> LookupTickersResponse: ...
    @overload
    async def lookup_tickers(
        self,
        collection_ticker: str,
        *,
        selected_markets: builtins.list[TickerPair],
    ) -> LookupTickersResponse: ...
    async def lookup_tickers(
        self,
        collection_ticker: str,
        *,
        request: (
            LookupTickersForMarketInMultivariateEventCollectionRequest | None
        ) = None,
        selected_markets: builtins.list[TickerPair] | None = None,
    ) -> LookupTickersResponse:
        self._require_auth()
        _check_request_exclusive(request, selected_markets=selected_markets)
        if request is None:
            if selected_markets is None:
                raise TypeError(
                    "lookup_tickers() requires `selected_markets` "
                    "(or pass `request=...`)"
                )
            request = LookupTickersForMarketInMultivariateEventCollectionRequest(
                selected_markets=list(selected_markets),
            )
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._put(
            f"/multivariate_event_collections/{collection_ticker}/lookup",
            json=body,
        )
        return LookupTickersResponse.model_validate(data)

    async def lookup_history(
        self,
        collection_ticker: str,
        *,
        lookback_seconds: int,
    ) -> builtins.list[LookupPoint]:
        params = _params(lookback_seconds=lookback_seconds)
        data = await self._get(
            f"/multivariate_event_collections/{collection_ticker}/lookup",
            params=params,
        )
        raw = data.get("lookup_points", [])
        return [LookupPoint.model_validate(item) for item in raw]
