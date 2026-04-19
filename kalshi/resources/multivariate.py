"""Multivariate event collections resource — list, get, create, lookup."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.models.multivariate import (
    CreateMarketInMultivariateEventCollectionRequest,
    CreateMarketResponse,
    LookupPoint,
    LookupTickersForMarketInMultivariateEventCollectionRequest,
    LookupTickersResponse,
    MultivariateEventCollection,
    TickerPair,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


class MultivariateCollectionsResource(SyncResource):
    """Sync multivariate event collections API."""

    def list(
        self,
        *,
        status: str | None = None,
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
        status: str | None = None,
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

    def create_market(
        self,
        collection_ticker: str,
        *,
        selected_markets: builtins.list[TickerPair],
        with_market_payload: bool | None = None,
    ) -> CreateMarketResponse:
        self._require_auth()
        req = CreateMarketInMultivariateEventCollectionRequest(
            selected_markets=list(selected_markets),
            with_market_payload=with_market_payload,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post(
            f"/multivariate_event_collections/{collection_ticker}",
            json=body,
        )
        return CreateMarketResponse.model_validate(data)

    def lookup_tickers(
        self,
        collection_ticker: str,
        *,
        selected_markets: builtins.list[TickerPair],
    ) -> LookupTickersResponse:
        self._require_auth()
        req = LookupTickersForMarketInMultivariateEventCollectionRequest(
            selected_markets=list(selected_markets),
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._put(
            f"/multivariate_event_collections/{collection_ticker}/lookup",
            json=body,
        )
        # Spec: this endpoint always returns 200 with body; guard against a
        # future server regression to 204 giving opaque Pydantic errors.
        assert data is not None, "lookup: expected 200 with body, got 204"
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
        status: str | None = None,
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
        status: str | None = None,
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

    async def create_market(
        self,
        collection_ticker: str,
        *,
        selected_markets: builtins.list[TickerPair],
        with_market_payload: bool | None = None,
    ) -> CreateMarketResponse:
        self._require_auth()
        req = CreateMarketInMultivariateEventCollectionRequest(
            selected_markets=list(selected_markets),
            with_market_payload=with_market_payload,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post(
            f"/multivariate_event_collections/{collection_ticker}",
            json=body,
        )
        return CreateMarketResponse.model_validate(data)

    async def lookup_tickers(
        self,
        collection_ticker: str,
        *,
        selected_markets: builtins.list[TickerPair],
    ) -> LookupTickersResponse:
        self._require_auth()
        req = LookupTickersForMarketInMultivariateEventCollectionRequest(
            selected_markets=list(selected_markets),
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
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
