"""Incentive programs resource — market-level reward programs.

Unique wire shape: this endpoint paginates on ``next_cursor`` (not
``cursor`` like every other Kalshi endpoint), so we bypass the base
``_list`` helper and hand-roll the Page wrapping.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from kalshi.models.common import Page
from kalshi.models.incentive_programs import (
    GetIncentiveProgramsResponse,
    IncentiveProgram,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params

# Safety cap on auto-pagination — same default as the base _list_all helper.
_MAX_PAGES = 1000


def _parse_page(data: dict[str, Any]) -> Page[IncentiveProgram]:
    """Parse the envelope into a Page[IncentiveProgram]."""
    parsed = GetIncentiveProgramsResponse.model_validate(data)
    return Page(
        items=list(parsed.incentive_programs),
        cursor=parsed.next_cursor if parsed.next_cursor else None,
    )


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
        data = self._get("/incentive_programs", params=params)
        return _parse_page(data)

    def list_all(
        self,
        *,
        status: str | None = None,
        incentive_type: str | None = None,
        limit: int | None = None,
    ) -> Iterator[IncentiveProgram]:
        params = _params(status=status, type=incentive_type, limit=limit)
        current_params = dict(params)
        for _ in range(_MAX_PAGES):
            data = self._get("/incentive_programs", params=current_params)
            page = _parse_page(data)
            yield from page.items
            if not page.has_next:
                break
            current_params["cursor"] = page.cursor


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
        data = await self._get("/incentive_programs", params=params)
        return _parse_page(data)

    async def list_all(
        self,
        *,
        status: str | None = None,
        incentive_type: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[IncentiveProgram]:
        """Returns an async iterator — use ``async for``."""
        params = _params(status=status, type=incentive_type, limit=limit)
        current_params = dict(params)
        for _ in range(_MAX_PAGES):
            data = await self._get("/incentive_programs", params=current_params)
            page = _parse_page(data)
            for item in page.items:
                yield item
            if not page.has_next:
                break
            current_params["cursor"] = page.cursor
