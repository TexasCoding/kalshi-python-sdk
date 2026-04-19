"""Structured targets resource — external entities markets anchor to."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.models.structured_targets import (
    GetStructuredTargetResponse,
    StructuredTarget,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


class StructuredTargetsResource(SyncResource):
    """Sync structured targets API.

    The ``type`` spec query param is exposed as ``target_type`` to avoid
    shadowing the Python built-in. ``page_size`` keeps the spec name (no
    standard ``limit`` param on this endpoint — per spec page_size is 1-2000,
    default 100).
    """

    def list(
        self,
        *,
        ids: builtins.list[str] | None = None,
        target_type: str | None = None,
        competition: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> Page[StructuredTarget]:
        params = _params(
            ids=ids,
            type=target_type,
            competition=competition,
            page_size=page_size,
            cursor=cursor,
        )
        return self._list(
            "/structured_targets",
            StructuredTarget,
            "structured_targets",
            params=params,
        )

    def list_all(
        self,
        *,
        ids: builtins.list[str] | None = None,
        target_type: str | None = None,
        competition: str | None = None,
        page_size: int | None = None,
    ) -> Iterator[StructuredTarget]:
        params = _params(
            ids=ids,
            type=target_type,
            competition=competition,
            page_size=page_size,
        )
        yield from self._list_all(
            "/structured_targets",
            StructuredTarget,
            "structured_targets",
            params=params,
        )

    def get(self, structured_target_id: str) -> StructuredTarget | None:
        data = self._get(f"/structured_targets/{structured_target_id}")
        return GetStructuredTargetResponse.model_validate(data).structured_target


class AsyncStructuredTargetsResource(AsyncResource):
    """Async structured targets API."""

    async def list(
        self,
        *,
        ids: builtins.list[str] | None = None,
        target_type: str | None = None,
        competition: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> Page[StructuredTarget]:
        params = _params(
            ids=ids,
            type=target_type,
            competition=competition,
            page_size=page_size,
            cursor=cursor,
        )
        return await self._list(
            "/structured_targets",
            StructuredTarget,
            "structured_targets",
            params=params,
        )

    def list_all(
        self,
        *,
        ids: builtins.list[str] | None = None,
        target_type: str | None = None,
        competition: str | None = None,
        page_size: int | None = None,
    ) -> AsyncIterator[StructuredTarget]:
        """Returns an async iterator — use ``async for``."""
        params = _params(
            ids=ids,
            type=target_type,
            competition=competition,
            page_size=page_size,
        )
        return self._list_all(
            "/structured_targets",
            StructuredTarget,
            "structured_targets",
            params=params,
        )

    async def get(self, structured_target_id: str) -> StructuredTarget | None:
        data = await self._get(f"/structured_targets/{structured_target_id}")
        return GetStructuredTargetResponse.model_validate(data).structured_target
