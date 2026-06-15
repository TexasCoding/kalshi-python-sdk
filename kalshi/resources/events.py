"""Events resource — list, get, metadata."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator
from typing import Any

from kalshi.models.common import Page
from kalshi.models.events import Event, EventFeeChange, EventMetadata, EventStatusLiteral
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _bool_param,
    _join_tickers,
    _params,
    _seg,
    _validate_limit,
    _validate_max_pages,
)

# Shared param builders (issue #46).


def _list_events_params(
    *,
    status: EventStatusLiteral | None,
    series_ticker: str | None,
    tickers: builtins.list[str] | str | None,
    with_nested_markets: bool | None,
    with_milestones: bool | None,
    min_close_ts: int | None,
    min_updated_ts: int | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=200)
    return _params(
        status=status,
        series_ticker=series_ticker,
        tickers=_join_tickers(tickers),
        with_nested_markets=_bool_param(with_nested_markets),
        with_milestones=_bool_param(with_milestones),
        min_close_ts=min_close_ts,
        min_updated_ts=min_updated_ts,
        limit=limit,
        cursor=cursor,
    )


def _list_multivariate_events_params(
    *,
    series_ticker: str | None,
    collection_ticker: str | None,
    with_nested_markets: bool | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=200)
    return _params(
        series_ticker=series_ticker,
        collection_ticker=collection_ticker,
        with_nested_markets=_bool_param(with_nested_markets),
        limit=limit,
        cursor=cursor,
    )


def _event_fee_changes_params(
    *,
    event_ticker: str | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000)
    return _params(
        event_ticker=event_ticker,
        limit=limit,
        cursor=cursor,
    )


class EventsResource(SyncResource):
    """Sync events API."""

    def list(
        self,
        *,
        status: EventStatusLiteral | None = None,
        series_ticker: str | None = None,
        tickers: builtins.list[str] | str | None = None,
        with_nested_markets: bool | None = None,
        with_milestones: bool | None = None,
        min_close_ts: int | None = None,
        min_updated_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Event]:
        params = _list_events_params(
            status=status,
            series_ticker=series_ticker,
            tickers=tickers,
            with_nested_markets=with_nested_markets,
            with_milestones=with_milestones,
            min_close_ts=min_close_ts,
            min_updated_ts=min_updated_ts,
            limit=limit,
            cursor=cursor,
        )
        return self._list("/events", Event, "events", params=params, extra_headers=extra_headers)

    def list_all(
        self,
        *,
        status: EventStatusLiteral | None = None,
        series_ticker: str | None = None,
        tickers: builtins.list[str] | str | None = None,
        with_nested_markets: bool | None = None,
        with_milestones: bool | None = None,
        min_close_ts: int | None = None,
        min_updated_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Event]:
        _validate_max_pages(max_pages)
        params = _list_events_params(
            status=status,
            series_ticker=series_ticker,
            tickers=tickers,
            with_nested_markets=with_nested_markets,
            with_milestones=with_milestones,
            min_close_ts=min_close_ts,
            min_updated_ts=min_updated_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/events",
            Event,
            "events",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def list_multivariate(
        self,
        *,
        series_ticker: str | None = None,
        collection_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Event]:
        params = _list_multivariate_events_params(
            series_ticker=series_ticker,
            collection_ticker=collection_ticker,
            with_nested_markets=with_nested_markets,
            limit=limit,
            cursor=cursor,
        )
        return self._list(
            "/events/multivariate", Event, "events", params=params, extra_headers=extra_headers
        )

    def list_all_multivariate(
        self,
        *,
        series_ticker: str | None = None,
        collection_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Event]:
        _validate_max_pages(max_pages)
        params = _list_multivariate_events_params(
            series_ticker=series_ticker,
            collection_ticker=collection_ticker,
            with_nested_markets=with_nested_markets,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/events/multivariate",
            Event,
            "events",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def get(
        self,
        event_ticker: str,
        *,
        with_nested_markets: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Event:
        params = _params(
            with_nested_markets=_bool_param(with_nested_markets),
        )
        data = self._get(
            f"/events/{_seg(event_ticker, name='event_ticker')}",
            params=params,
            extra_headers=extra_headers,
        )
        return Event.model_validate(data.get("event", data))

    def metadata(
        self, event_ticker: str, *, extra_headers: dict[str, str] | None = None
    ) -> EventMetadata:
        data = self._get(
            f"/events/{_seg(event_ticker, name='event_ticker')}/metadata",
            extra_headers=extra_headers,
        )
        return EventMetadata.model_validate(data)

    def fee_changes(
        self,
        *,
        event_ticker: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[EventFeeChange]:
        params = _event_fee_changes_params(
            event_ticker=event_ticker,
            limit=limit,
            cursor=cursor,
        )
        return self._list(
            "/events/fee_changes",
            EventFeeChange,
            "event_fee_changes",
            params=params,
            extra_headers=extra_headers,
        )

    def fee_changes_all(
        self,
        *,
        event_ticker: str | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[EventFeeChange]:
        _validate_max_pages(max_pages)
        params = _event_fee_changes_params(
            event_ticker=event_ticker,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/events/fee_changes",
            EventFeeChange,
            "event_fee_changes",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )


class AsyncEventsResource(AsyncResource):
    """Async events API."""

    async def list(
        self,
        *,
        status: EventStatusLiteral | None = None,
        series_ticker: str | None = None,
        tickers: builtins.list[str] | str | None = None,
        with_nested_markets: bool | None = None,
        with_milestones: bool | None = None,
        min_close_ts: int | None = None,
        min_updated_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Event]:
        params = _list_events_params(
            status=status,
            series_ticker=series_ticker,
            tickers=tickers,
            with_nested_markets=with_nested_markets,
            with_milestones=with_milestones,
            min_close_ts=min_close_ts,
            min_updated_ts=min_updated_ts,
            limit=limit,
            cursor=cursor,
        )
        return await self._list(
            "/events", Event, "events", params=params, extra_headers=extra_headers
        )

    def list_all(
        self,
        *,
        status: EventStatusLiteral | None = None,
        series_ticker: str | None = None,
        tickers: builtins.list[str] | str | None = None,
        with_nested_markets: bool | None = None,
        with_milestones: bool | None = None,
        min_close_ts: int | None = None,
        min_updated_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Event]:
        _validate_max_pages(max_pages)
        params = _list_events_params(
            status=status,
            series_ticker=series_ticker,
            tickers=tickers,
            with_nested_markets=with_nested_markets,
            with_milestones=with_milestones,
            min_close_ts=min_close_ts,
            min_updated_ts=min_updated_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/events",
            Event,
            "events",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def list_multivariate(
        self,
        *,
        series_ticker: str | None = None,
        collection_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Event]:
        params = _list_multivariate_events_params(
            series_ticker=series_ticker,
            collection_ticker=collection_ticker,
            with_nested_markets=with_nested_markets,
            limit=limit,
            cursor=cursor,
        )
        return await self._list(
            "/events/multivariate", Event, "events", params=params, extra_headers=extra_headers
        )

    def list_all_multivariate(
        self,
        *,
        series_ticker: str | None = None,
        collection_ticker: str | None = None,
        with_nested_markets: bool | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Event]:
        _validate_max_pages(max_pages)
        params = _list_multivariate_events_params(
            series_ticker=series_ticker,
            collection_ticker=collection_ticker,
            with_nested_markets=with_nested_markets,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/events/multivariate",
            Event,
            "events",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def get(
        self,
        event_ticker: str,
        *,
        with_nested_markets: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Event:
        params = _params(
            with_nested_markets=_bool_param(with_nested_markets),
        )
        data = await self._get(
            f"/events/{_seg(event_ticker, name='event_ticker')}",
            params=params,
            extra_headers=extra_headers,
        )
        return Event.model_validate(data.get("event", data))

    async def metadata(
        self, event_ticker: str, *, extra_headers: dict[str, str] | None = None
    ) -> EventMetadata:
        data = await self._get(
            f"/events/{_seg(event_ticker, name='event_ticker')}/metadata",
            extra_headers=extra_headers,
        )
        return EventMetadata.model_validate(data)

    async def fee_changes(
        self,
        *,
        event_ticker: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[EventFeeChange]:
        params = _event_fee_changes_params(
            event_ticker=event_ticker,
            limit=limit,
            cursor=cursor,
        )
        return await self._list(
            "/events/fee_changes",
            EventFeeChange,
            "event_fee_changes",
            params=params,
            extra_headers=extra_headers,
        )

    def fee_changes_all(
        self,
        *,
        event_ticker: str | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[EventFeeChange]:
        """Returns an async iterator — use ``async for``."""
        _validate_max_pages(max_pages)
        params = _event_fee_changes_params(
            event_ticker=event_ticker,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/events/fee_changes",
            EventFeeChange,
            "event_fee_changes",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )
