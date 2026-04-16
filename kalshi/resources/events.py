"""Events resource — list, get, metadata."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.models.events import Event, EventMetadata
from kalshi.resources._base import AsyncResource, SyncResource, _params


class EventsResource(SyncResource):
    """Sync events API."""

    def list(
        self,
        *,
        status: str | None = None,
        series_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        with_milestones: bool | None = None,
        min_close_ts: int | None = None,
        min_updated_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Event]:
        params = _params(
            status=status,
            series_ticker=series_ticker,
            with_nested_markets="true" if with_nested_markets else None,
            with_milestones="true" if with_milestones else None,
            min_close_ts=min_close_ts,
            min_updated_ts=min_updated_ts,
            limit=limit,
            cursor=cursor,
        )
        return self._list("/events", Event, "events", params=params)

    def list_all(
        self,
        *,
        status: str | None = None,
        series_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        with_milestones: bool | None = None,
        min_close_ts: int | None = None,
        min_updated_ts: int | None = None,
        limit: int | None = None,
    ) -> Iterator[Event]:
        params = _params(
            status=status,
            series_ticker=series_ticker,
            with_nested_markets="true" if with_nested_markets else None,
            with_milestones="true" if with_milestones else None,
            min_close_ts=min_close_ts,
            min_updated_ts=min_updated_ts,
            limit=limit,
        )
        return self._list_all("/events", Event, "events", params=params)

    def list_multivariate(
        self,
        *,
        series_ticker: str | None = None,
        collection_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Event]:
        params = _params(
            series_ticker=series_ticker,
            collection_ticker=collection_ticker,
            with_nested_markets="true" if with_nested_markets else None,
            limit=limit,
            cursor=cursor,
        )
        return self._list("/events/multivariate", Event, "events", params=params)

    def list_all_multivariate(
        self,
        *,
        series_ticker: str | None = None,
        collection_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        limit: int | None = None,
    ) -> Iterator[Event]:
        params = _params(
            series_ticker=series_ticker,
            collection_ticker=collection_ticker,
            with_nested_markets="true" if with_nested_markets else None,
            limit=limit,
        )
        return self._list_all("/events/multivariate", Event, "events", params=params)

    def get(
        self,
        event_ticker: str,
        *,
        with_nested_markets: bool = False,
    ) -> Event:
        params = _params(
            with_nested_markets="true" if with_nested_markets else None,
        )
        data = self._get(f"/events/{event_ticker}", params=params)
        return Event.model_validate(data.get("event", data))

    def metadata(self, event_ticker: str) -> EventMetadata:
        data = self._get(f"/events/{event_ticker}/metadata")
        return EventMetadata.model_validate(data)


class AsyncEventsResource(AsyncResource):
    """Async events API."""

    async def list(
        self,
        *,
        status: str | None = None,
        series_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        with_milestones: bool | None = None,
        min_close_ts: int | None = None,
        min_updated_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Event]:
        params = _params(
            status=status,
            series_ticker=series_ticker,
            with_nested_markets="true" if with_nested_markets else None,
            with_milestones="true" if with_milestones else None,
            min_close_ts=min_close_ts,
            min_updated_ts=min_updated_ts,
            limit=limit,
            cursor=cursor,
        )
        return await self._list("/events", Event, "events", params=params)

    def list_all(
        self,
        *,
        status: str | None = None,
        series_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        with_milestones: bool | None = None,
        min_close_ts: int | None = None,
        min_updated_ts: int | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Event]:
        params = _params(
            status=status,
            series_ticker=series_ticker,
            with_nested_markets="true" if with_nested_markets else None,
            with_milestones="true" if with_milestones else None,
            min_close_ts=min_close_ts,
            min_updated_ts=min_updated_ts,
            limit=limit,
        )
        return self._list_all("/events", Event, "events", params=params)

    async def list_multivariate(
        self,
        *,
        series_ticker: str | None = None,
        collection_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Event]:
        params = _params(
            series_ticker=series_ticker,
            collection_ticker=collection_ticker,
            with_nested_markets="true" if with_nested_markets else None,
            limit=limit,
            cursor=cursor,
        )
        return await self._list("/events/multivariate", Event, "events", params=params)

    def list_all_multivariate(
        self,
        *,
        series_ticker: str | None = None,
        collection_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Event]:
        params = _params(
            series_ticker=series_ticker,
            collection_ticker=collection_ticker,
            with_nested_markets="true" if with_nested_markets else None,
            limit=limit,
        )
        return self._list_all("/events/multivariate", Event, "events", params=params)

    async def get(
        self,
        event_ticker: str,
        *,
        with_nested_markets: bool = False,
    ) -> Event:
        params = _params(
            with_nested_markets="true" if with_nested_markets else None,
        )
        data = await self._get(f"/events/{event_ticker}", params=params)
        return Event.model_validate(data.get("event", data))

    async def metadata(self, event_ticker: str) -> EventMetadata:
        data = await self._get(f"/events/{event_ticker}/metadata")
        return EventMetadata.model_validate(data)
