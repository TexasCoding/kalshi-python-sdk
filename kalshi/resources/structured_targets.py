"""Structured targets resource — external entities markets anchor to."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.models.structured_targets import (
    GetStructuredTargetResponse,
    StructuredTarget,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _params,
    _seg,
    _validate_limit,
    _validate_max_pages,
)


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
        extra_headers: dict[str, str] | None = None,
    ) -> Page[StructuredTarget]:
        _validate_limit(page_size, hi=2000, name="page_size")
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
            extra_headers=extra_headers,
        )

    def list_all(
        self,
        *,
        ids: builtins.list[str] | None = None,
        target_type: str | None = None,
        competition: str | None = None,
        page_size: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[StructuredTarget]:
        _validate_max_pages(max_pages)
        _validate_limit(page_size, hi=2000, name="page_size")
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
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def get(
        self, structured_target_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> StructuredTarget | None:
        data = self._get(
            f"/structured_targets/{_seg(structured_target_id, name='structured_target_id')}",
            extra_headers=extra_headers,
        )
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
        extra_headers: dict[str, str] | None = None,
    ) -> Page[StructuredTarget]:
        _validate_limit(page_size, hi=2000, name="page_size")
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
            extra_headers=extra_headers,
        )

    def list_all(
        self,
        *,
        ids: builtins.list[str] | None = None,
        target_type: str | None = None,
        competition: str | None = None,
        page_size: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[StructuredTarget]:
        """Returns an async iterator — use ``async for``."""
        _validate_max_pages(max_pages)
        _validate_limit(page_size, hi=2000, name="page_size")
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
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def get(
        self, structured_target_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> StructuredTarget | None:
        data = await self._get(
            f"/structured_targets/{_seg(structured_target_id, name='structured_target_id')}",
            extra_headers=extra_headers,
        )
        return GetStructuredTargetResponse.model_validate(data).structured_target
