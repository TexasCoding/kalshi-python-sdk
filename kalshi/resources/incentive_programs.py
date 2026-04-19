"""Incentive programs resource — market-level reward programs.

Wire quirk: this endpoint paginates on ``next_cursor`` (every other
Kalshi endpoint uses ``cursor``). The base ``_list`` / ``_list_all``
helpers accept a ``cursor_key`` kwarg to handle the difference.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.models.incentive_programs import IncentiveProgram
from kalshi.resources._base import AsyncResource, SyncResource, _params


class IncentiveProgramsResource(SyncResource):
    """Sync incentive programs API.

    ``incentive_type`` renames the spec's ``type`` query param to avoid
    shadowing the Python built-in. Wire still sends ``?type=...``.
    """

    def list(
        self,
        *,
        status: str | None = None,
        incentive_type: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[IncentiveProgram]:
        params = _params(
            status=status,
            type=incentive_type,
            limit=limit,
            cursor=cursor,
        )
        return self._list(
            "/incentive_programs",
            IncentiveProgram,
            "incentive_programs",
            params=params,
            cursor_key="next_cursor",
        )

    def list_all(
        self,
        *,
        status: str | None = None,
        incentive_type: str | None = None,
        limit: int | None = None,
    ) -> Iterator[IncentiveProgram]:
        params = _params(status=status, type=incentive_type, limit=limit)
        yield from self._list_all(
            "/incentive_programs",
            IncentiveProgram,
            "incentive_programs",
            params=params,
            cursor_key="next_cursor",
        )


class AsyncIncentiveProgramsResource(AsyncResource):
    """Async incentive programs API."""

    async def list(
        self,
        *,
        status: str | None = None,
        incentive_type: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[IncentiveProgram]:
        params = _params(
            status=status,
            type=incentive_type,
            limit=limit,
            cursor=cursor,
        )
        return await self._list(
            "/incentive_programs",
            IncentiveProgram,
            "incentive_programs",
            params=params,
            cursor_key="next_cursor",
        )

    def list_all(
        self,
        *,
        status: str | None = None,
        incentive_type: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[IncentiveProgram]:
        """Returns an async iterator — use ``async for``."""
        params = _params(status=status, type=incentive_type, limit=limit)
        return self._list_all(
            "/incentive_programs",
            IncentiveProgram,
            "incentive_programs",
            params=params,
            cursor_key="next_cursor",
        )
