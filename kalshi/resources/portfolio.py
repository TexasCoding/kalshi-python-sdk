"""Portfolio resource — balance, positions, settlements."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.models.portfolio import Balance, PositionsResponse, Settlement
from kalshi.resources._base import AsyncResource, SyncResource, _params


class PortfolioResource(SyncResource):
    """Sync portfolio API."""

    def balance(self, *, subaccount: int | None = None) -> Balance:
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._get("/portfolio/balance", params=params)
        return Balance.model_validate(data)

    def positions(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        count_filter: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
    ) -> PositionsResponse:
        self._require_auth()
        params = _params(
            limit=limit,
            cursor=cursor,
            count_filter=count_filter,
            ticker=ticker,
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        data = self._get("/portfolio/positions", params=params)
        return PositionsResponse.model_validate(data)

    def settlements(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        subaccount: int | None = None,
    ) -> Page[Settlement]:
        self._require_auth()
        params = _params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            event_ticker=event_ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            subaccount=subaccount,
        )
        return self._list("/portfolio/settlements", Settlement, "settlements", params=params)

    def settlements_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        subaccount: int | None = None,
    ) -> Iterator[Settlement]:
        self._require_auth()
        params = _params(
            limit=limit,
            ticker=ticker,
            event_ticker=event_ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            subaccount=subaccount,
        )
        return self._list_all("/portfolio/settlements", Settlement, "settlements", params=params)


class AsyncPortfolioResource(AsyncResource):
    """Async portfolio API."""

    async def balance(self, *, subaccount: int | None = None) -> Balance:
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = await self._get("/portfolio/balance", params=params)
        return Balance.model_validate(data)

    async def positions(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        count_filter: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
    ) -> PositionsResponse:
        self._require_auth()
        params = _params(
            limit=limit,
            cursor=cursor,
            count_filter=count_filter,
            ticker=ticker,
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        data = await self._get("/portfolio/positions", params=params)
        return PositionsResponse.model_validate(data)

    async def settlements(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        subaccount: int | None = None,
    ) -> Page[Settlement]:
        self._require_auth()
        params = _params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            event_ticker=event_ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            subaccount=subaccount,
        )
        return await self._list(
            "/portfolio/settlements", Settlement, "settlements", params=params
        )

    def settlements_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        subaccount: int | None = None,
    ) -> AsyncIterator[Settlement]:
        self._require_auth()
        params = _params(
            limit=limit,
            ticker=ticker,
            event_ticker=event_ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            subaccount=subaccount,
        )
        return self._list_all(
            "/portfolio/settlements", Settlement, "settlements", params=params
        )
