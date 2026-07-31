"""Perps FCM resource — create margin FCM subtraders.

``POST /margin/fcm/subtraders`` creates a new FCM subtrader under the
authenticated member. Auth required; POST is never retried.
"""

from __future__ import annotations

from typing import overload

from kalshi.perps.models.fcm import (
    CreateMarginFCMSubtraderRequest,
    CreateMarginFCMSubtraderResponse,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
)


def _build_create_subtrader_body(
    request: CreateMarginFCMSubtraderRequest | None,
    *,
    subtrader_suffix: str | None,
) -> dict[str, object]:
    _check_request_exclusive(request, subtrader_suffix=subtrader_suffix)
    if request is None:
        if subtrader_suffix is None:
            raise TypeError(
                "create_subtrader() requires `subtrader_suffix` (or pass `request=...`)"
            )
        request = CreateMarginFCMSubtraderRequest(subtrader_suffix=subtrader_suffix)
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


class FcmResource(SyncResource):
    """Sync perps FCM API."""

    @overload
    def create_subtrader(
        self,
        *,
        request: CreateMarginFCMSubtraderRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMSubtraderResponse: ...
    @overload
    def create_subtrader(
        self,
        *,
        subtrader_suffix: str,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMSubtraderResponse: ...
    def create_subtrader(
        self,
        *,
        request: CreateMarginFCMSubtraderRequest | None = None,
        subtrader_suffix: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMSubtraderResponse:
        """``POST /margin/fcm/subtraders`` — create a margin FCM subtrader.

        The full ``subtrader_id`` is composed server-side as
        ``{user_id}_{subtrader_suffix}``.
        """
        self._require_auth()
        body = _build_create_subtrader_body(request, subtrader_suffix=subtrader_suffix)
        data = self._post("/margin/fcm/subtraders", json=body, extra_headers=extra_headers)
        return CreateMarginFCMSubtraderResponse.model_validate(data)


class AsyncFcmResource(AsyncResource):
    """Async perps FCM API."""

    @overload
    async def create_subtrader(
        self,
        *,
        request: CreateMarginFCMSubtraderRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMSubtraderResponse: ...
    @overload
    async def create_subtrader(
        self,
        *,
        subtrader_suffix: str,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMSubtraderResponse: ...
    async def create_subtrader(
        self,
        *,
        request: CreateMarginFCMSubtraderRequest | None = None,
        subtrader_suffix: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMSubtraderResponse:
        """Async :meth:`FcmResource.create_subtrader`."""
        self._require_auth()
        body = _build_create_subtrader_body(request, subtrader_suffix=subtrader_suffix)
        data = await self._post("/margin/fcm/subtraders", json=body, extra_headers=extra_headers)
        return CreateMarginFCMSubtraderResponse.model_validate(data)
