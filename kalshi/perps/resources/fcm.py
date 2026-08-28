"""Perps FCM resource — create margin FCM subtraders and manage IM caps.

``POST /margin/fcm/subtraders`` creates a new FCM subtrader under the
authenticated member. Auth required; POST/PUT/DELETE are never retried.
"""

from __future__ import annotations

from decimal import Decimal
from typing import overload

from kalshi.perps.models.fcm import (
    CreateMarginFCMSubtraderRequest,
    CreateMarginFCMSubtraderResponse,
    FCMAssetClassLiteral,
    GetFCMSubtraderRiskControlsResponse,
    UpdateFCMSubtraderRiskControlsRequest,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _params,
)

_RISK_CONTROLS_PATH = "/margin/fcm/subtraders/risk_controls"


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


def _build_update_risk_controls_body(
    request: UpdateFCMSubtraderRiskControlsRequest | None,
    *,
    subtrader_id: str | None,
    im_cap: Decimal | None,
    market_ticker: str | None,
    asset_class: FCMAssetClassLiteral | None,
) -> dict[str, object]:
    _check_request_exclusive(
        request,
        subtrader_id=subtrader_id,
        im_cap=im_cap,
        market_ticker=market_ticker,
        asset_class=asset_class,
    )
    if request is None:
        if subtrader_id is None or im_cap is None:
            raise TypeError(
                "update_risk_controls() requires `subtrader_id` and `im_cap` "
                "(or pass `request=...`)"
            )
        request = UpdateFCMSubtraderRiskControlsRequest(
            subtrader_id=subtrader_id,
            im_cap=im_cap,
            market_ticker=market_ticker,
            asset_class=asset_class,
        )
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

    def risk_controls(
        self,
        *,
        subtrader_id: str,
        market_ticker: str | None = None,
        asset_class: FCMAssetClassLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetFCMSubtraderRiskControlsResponse:
        """``GET /margin/fcm/subtraders/risk_controls`` — list IM caps."""
        self._require_auth()
        params = _params(
            subtrader_id=subtrader_id,
            market_ticker=market_ticker,
            asset_class=asset_class,
        )
        data = self._get(_RISK_CONTROLS_PATH, params=params, extra_headers=extra_headers)
        return GetFCMSubtraderRiskControlsResponse.model_validate(data)

    @overload
    def update_risk_controls(
        self,
        *,
        request: UpdateFCMSubtraderRiskControlsRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def update_risk_controls(
        self,
        *,
        subtrader_id: str,
        im_cap: Decimal,
        market_ticker: str | None = None,
        asset_class: FCMAssetClassLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def update_risk_controls(
        self,
        *,
        request: UpdateFCMSubtraderRiskControlsRequest | None = None,
        subtrader_id: str | None = None,
        im_cap: Decimal | None = None,
        market_ticker: str | None = None,
        asset_class: FCMAssetClassLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """``PUT /margin/fcm/subtraders/risk_controls`` — set an IM cap."""
        self._require_auth()
        body = _build_update_risk_controls_body(
            request,
            subtrader_id=subtrader_id,
            im_cap=im_cap,
            market_ticker=market_ticker,
            asset_class=asset_class,
        )
        self._put(_RISK_CONTROLS_PATH, json=body, extra_headers=extra_headers)

    def delete_risk_controls(
        self,
        *,
        subtrader_id: str,
        market_ticker: str | None = None,
        asset_class: FCMAssetClassLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """``DELETE /margin/fcm/subtraders/risk_controls`` — remove an IM cap."""
        self._require_auth()
        params = _params(
            subtrader_id=subtrader_id,
            market_ticker=market_ticker,
            asset_class=asset_class,
        )
        self._delete(_RISK_CONTROLS_PATH, params=params, extra_headers=extra_headers)


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

    async def risk_controls(
        self,
        *,
        subtrader_id: str,
        market_ticker: str | None = None,
        asset_class: FCMAssetClassLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetFCMSubtraderRiskControlsResponse:
        """Async :meth:`FcmResource.risk_controls`."""
        self._require_auth()
        params = _params(
            subtrader_id=subtrader_id,
            market_ticker=market_ticker,
            asset_class=asset_class,
        )
        data = await self._get(_RISK_CONTROLS_PATH, params=params, extra_headers=extra_headers)
        return GetFCMSubtraderRiskControlsResponse.model_validate(data)

    @overload
    async def update_risk_controls(
        self,
        *,
        request: UpdateFCMSubtraderRiskControlsRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def update_risk_controls(
        self,
        *,
        subtrader_id: str,
        im_cap: Decimal,
        market_ticker: str | None = None,
        asset_class: FCMAssetClassLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def update_risk_controls(
        self,
        *,
        request: UpdateFCMSubtraderRiskControlsRequest | None = None,
        subtrader_id: str | None = None,
        im_cap: Decimal | None = None,
        market_ticker: str | None = None,
        asset_class: FCMAssetClassLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Async :meth:`FcmResource.update_risk_controls`."""
        self._require_auth()
        body = _build_update_risk_controls_body(
            request,
            subtrader_id=subtrader_id,
            im_cap=im_cap,
            market_ticker=market_ticker,
            asset_class=asset_class,
        )
        await self._put(_RISK_CONTROLS_PATH, json=body, extra_headers=extra_headers)

    async def delete_risk_controls(
        self,
        *,
        subtrader_id: str,
        market_ticker: str | None = None,
        asset_class: FCMAssetClassLiteral | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Async :meth:`FcmResource.delete_risk_controls`."""
        self._require_auth()
        params = _params(
            subtrader_id=subtrader_id,
            market_ticker=market_ticker,
            asset_class=asset_class,
        )
        await self._delete(_RISK_CONTROLS_PATH, params=params, extra_headers=extra_headers)
