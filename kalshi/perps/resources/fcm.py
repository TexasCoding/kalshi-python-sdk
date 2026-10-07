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
    UpdateFCMNotionalRiskLimitRequest,
    UpdateFCMSubtraderRiskControlsRequest,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _params,
)

_RISK_CONTROLS_PATH = "/margin/fcm/subtraders/risk_controls"
_NOTIONAL_RISK_LIMIT_PATH = "/margin/fcm/notional_risk_limit"


def _build_create_subtrader_body(
    request: CreateMarginFCMSubtraderRequest | None,
    *,
    subtrader_suffix: str | None,
    require_category_cap: bool | None,
) -> dict[str, object]:
    _check_request_exclusive(
        request,
        subtrader_suffix=subtrader_suffix,
        require_category_cap=require_category_cap,
    )
    if request is None:
        if subtrader_suffix is None or require_category_cap is None:
            raise TypeError(
                "create_subtrader() requires `subtrader_suffix` and "
                "`require_category_cap` (or pass `request=...`)"
            )
        request = CreateMarginFCMSubtraderRequest(
            subtrader_suffix=subtrader_suffix,
            require_category_cap=require_category_cap,
        )
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


def _build_update_notional_risk_limit_body(
    request: UpdateFCMNotionalRiskLimitRequest | None,
    *,
    notional_value_risk_limit: Decimal | None,
) -> dict[str, object]:
    _check_request_exclusive(request, notional_value_risk_limit=notional_value_risk_limit)
    if request is None:
        if notional_value_risk_limit is None:
            raise TypeError(
                "update_notional_risk_limit() requires `notional_value_risk_limit` "
                "(or pass `request=...`)"
            )
        request = UpdateFCMNotionalRiskLimitRequest(
            notional_value_risk_limit=notional_value_risk_limit,
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
        require_category_cap: bool,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMSubtraderResponse: ...
    def create_subtrader(
        self,
        *,
        request: CreateMarginFCMSubtraderRequest | None = None,
        subtrader_suffix: str | None = None,
        require_category_cap: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMSubtraderResponse:
        """``POST /margin/fcm/subtraders`` — create a margin FCM subtrader.

        The full ``subtrader_id`` is composed server-side as
        ``{user_id}_{subtrader_suffix}``. ``require_category_cap`` is required:
        when true, ordinary orders need an explicit asset-class IM cap.
        """
        self._require_auth()
        body = _build_create_subtrader_body(
            request,
            subtrader_suffix=subtrader_suffix,
            require_category_cap=require_category_cap,
        )
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

    @overload
    def update_notional_risk_limit(
        self,
        *,
        request: UpdateFCMNotionalRiskLimitRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def update_notional_risk_limit(
        self,
        *,
        notional_value_risk_limit: Decimal,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def update_notional_risk_limit(
        self,
        *,
        request: UpdateFCMNotionalRiskLimitRequest | None = None,
        notional_value_risk_limit: Decimal | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """``PUT /margin/fcm/notional_risk_limit`` — set the member's account limit.

        Not retried. Returns no body (``EmptyResponse``).
        """
        self._require_auth()
        body = _build_update_notional_risk_limit_body(
            request, notional_value_risk_limit=notional_value_risk_limit
        )
        self._put(_NOTIONAL_RISK_LIMIT_PATH, json=body, extra_headers=extra_headers)

    def delete_notional_risk_limit(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        """``DELETE /margin/fcm/notional_risk_limit`` — clear the member-set limit.

        Not retried. A Kalshi-set limit on the account stays in force.
        """
        self._require_auth()
        self._delete(_NOTIONAL_RISK_LIMIT_PATH, extra_headers=extra_headers)


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
        require_category_cap: bool,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMSubtraderResponse: ...
    async def create_subtrader(
        self,
        *,
        request: CreateMarginFCMSubtraderRequest | None = None,
        subtrader_suffix: str | None = None,
        require_category_cap: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMSubtraderResponse:
        """Async :meth:`FcmResource.create_subtrader`."""
        self._require_auth()
        body = _build_create_subtrader_body(
            request,
            subtrader_suffix=subtrader_suffix,
            require_category_cap=require_category_cap,
        )
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

    @overload
    async def update_notional_risk_limit(
        self,
        *,
        request: UpdateFCMNotionalRiskLimitRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def update_notional_risk_limit(
        self,
        *,
        notional_value_risk_limit: Decimal,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def update_notional_risk_limit(
        self,
        *,
        request: UpdateFCMNotionalRiskLimitRequest | None = None,
        notional_value_risk_limit: Decimal | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Async :meth:`FcmResource.update_notional_risk_limit`."""
        self._require_auth()
        body = _build_update_notional_risk_limit_body(
            request, notional_value_risk_limit=notional_value_risk_limit
        )
        await self._put(_NOTIONAL_RISK_LIMIT_PATH, json=body, extra_headers=extra_headers)

    async def delete_notional_risk_limit(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        """Async :meth:`FcmResource.delete_notional_risk_limit`."""
        self._require_auth()
        await self._delete(_NOTIONAL_RISK_LIMIT_PATH, extra_headers=extra_headers)
