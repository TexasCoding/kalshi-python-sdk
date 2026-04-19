"""Milestones resource — structured event markers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import datetime

from kalshi.models.common import Page
from kalshi.models.milestones import Milestone
from kalshi.resources._base import AsyncResource, SyncResource, _params


def _iso(dt: datetime | str | None) -> str | None:
    """Coerce a ``datetime`` to an RFC3339 string; pass strings through."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return dt


class MilestonesResource(SyncResource):
    """Sync milestones API — list + single get.

    Unlike most resources ``limit`` is REQUIRED on list (spec) — range
    1-500. Dates use RFC3339.
    """

    def list(
        self,
        *,
        limit: int,
        minimum_start_date: datetime | str | None = None,
        category: str | None = None,
        competition: str | None = None,
        source_id: str | None = None,
        type: str | None = None,
        related_event_ticker: str | None = None,
        cursor: str | None = None,
        min_updated_ts: int | None = None,
    ) -> Page[Milestone]:
        params = _params(
            limit=limit,
            minimum_start_date=_iso(minimum_start_date),
            category=category,
            competition=competition,
            source_id=source_id,
            type=type,
            related_event_ticker=related_event_ticker,
            cursor=cursor,
            min_updated_ts=min_updated_ts,
        )
        return self._list("/milestones", Milestone, "milestones", params=params)

    def list_all(
        self,
        *,
        limit: int,
        minimum_start_date: datetime | str | None = None,
        category: str | None = None,
        competition: str | None = None,
        source_id: str | None = None,
        type: str | None = None,
        related_event_ticker: str | None = None,
        min_updated_ts: int | None = None,
    ) -> Iterator[Milestone]:
        params = _params(
            limit=limit,
            minimum_start_date=_iso(minimum_start_date),
            category=category,
            competition=competition,
            source_id=source_id,
            type=type,
            related_event_ticker=related_event_ticker,
            min_updated_ts=min_updated_ts,
        )
        yield from self._list_all(
            "/milestones", Milestone, "milestones", params=params,
        )

    def get(self, milestone_id: str) -> Milestone:
        data = self._get(f"/milestones/{milestone_id}")
        ms = data.get("milestone", data)
        return Milestone.model_validate(ms)


class AsyncMilestonesResource(AsyncResource):
    """Async milestones API."""

    async def list(
        self,
        *,
        limit: int,
        minimum_start_date: datetime | str | None = None,
        category: str | None = None,
        competition: str | None = None,
        source_id: str | None = None,
        type: str | None = None,
        related_event_ticker: str | None = None,
        cursor: str | None = None,
        min_updated_ts: int | None = None,
    ) -> Page[Milestone]:
        params = _params(
            limit=limit,
            minimum_start_date=_iso(minimum_start_date),
            category=category,
            competition=competition,
            source_id=source_id,
            type=type,
            related_event_ticker=related_event_ticker,
            cursor=cursor,
            min_updated_ts=min_updated_ts,
        )
        return await self._list(
            "/milestones", Milestone, "milestones", params=params,
        )

    def list_all(
        self,
        *,
        limit: int,
        minimum_start_date: datetime | str | None = None,
        category: str | None = None,
        competition: str | None = None,
        source_id: str | None = None,
        type: str | None = None,
        related_event_ticker: str | None = None,
        min_updated_ts: int | None = None,
    ) -> AsyncIterator[Milestone]:
        """Returns an async iterator — use ``async for``."""
        params = _params(
            limit=limit,
            minimum_start_date=_iso(minimum_start_date),
            category=category,
            competition=competition,
            source_id=source_id,
            type=type,
            related_event_ticker=related_event_ticker,
            min_updated_ts=min_updated_ts,
        )
        return self._list_all(
            "/milestones", Milestone, "milestones", params=params,
        )

    async def get(self, milestone_id: str) -> Milestone:
        data = await self._get(f"/milestones/{milestone_id}")
        ms = data.get("milestone", data)
        return Milestone.model_validate(ms)
