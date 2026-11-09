"""Perps FCM resource — create margin FCM subtraders and manage IM caps.

``POST /margin/fcm/subtraders`` creates a new FCM subtrader under the
authenticated member. ``POST /margin/fcm/positions/transfers`` moves a
perps position into the FCM error account. Auth required; POST/PUT/DELETE
are never retried.
"""

from __future__ import annotations

from decimal import Decimal
from typing import overload
from uuid import UUID

from kalshi.perps.models.fcm import (
    CreateMarginFCMPositionTransferRequest,
    CreateMarginFCMPositionTransferResponse,
    CreateMarginFCMSubtraderRequest,
    CreateMarginFCMSubtraderResponse,
    FCMAssetClassLiteral,
    FCMPositionTransferSideLiteral,
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
from kalshi.types import to_decimal

_RISK_CONTROLS_PATH = "/margin/fcm/subtraders/risk_controls"
_NOTIONAL_RISK_LIMIT_PATH = "/margin/fcm/notional_risk_limit"
_POSITION_TRANSFER_PATH = "/margin/fcm/positions/transfers"


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


def _build_transfer_position_body(
    request: CreateMarginFCMPositionTransferRequest | None,
    *,
    source_subtrader_id: str | None,
    target_subtrader_id: str | None,
    side: FCMPositionTransferSideLiteral | None,
    count: Decimal | int | float | str | None,
    price: Decimal | int | float | str | None,
    client_transfer_id: UUID | str | None,
    ticker: str | None,
    market_id: str | None,
) -> dict[str, object]:
    _check_request_exclusive(
        request,
        source_subtrader_id=source_subtrader_id,
        target_subtrader_id=target_subtrader_id,
        side=side,
        count=count,
        price=price,
        client_transfer_id=client_transfer_id,
        ticker=ticker,
        market_id=market_id,
    )
    if request is None:
        if (
            source_subtrader_id is None
            or target_subtrader_id is None
            or side is None
            or count is None
            or price is None
            or client_transfer_id is None
        ):
            raise TypeError(
                "transfer_position() requires `source_subtrader_id`, "
                "`target_subtrader_id`, `side`, `count`, `price`, and "
                "`client_transfer_id` (or pass `request=...`)"
            )
        uid = (
            client_transfer_id
            if isinstance(client_transfer_id, UUID)
            else UUID(client_transfer_id)
        )
        request = CreateMarginFCMPositionTransferRequest(
            source_subtrader_id=source_subtrader_id,
            target_subtrader_id=target_subtrader_id,
            side=side,
            count=to_decimal(count),
            price=to_decimal(price),
            client_transfer_id=uid,
            ticker=ticker,
            market_id=market_id,
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

    @overload
    def transfer_position(
        self,
        *,
        request: CreateMarginFCMPositionTransferRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMPositionTransferResponse: ...
    @overload
    def transfer_position(
        self,
        *,
        source_subtrader_id: str,
        target_subtrader_id: str,
        side: FCMPositionTransferSideLiteral,
        count: Decimal | int | float | str,
        price: Decimal | int | float | str,
        client_transfer_id: UUID | str,
        ticker: str | None = None,
        market_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMPositionTransferResponse: ...
    def transfer_position(
        self,
        *,
        request: CreateMarginFCMPositionTransferRequest | None = None,
        source_subtrader_id: str | None = None,
        target_subtrader_id: str | None = None,
        side: FCMPositionTransferSideLiteral | None = None,
        count: Decimal | int | float | str | None = None,
        price: Decimal | int | float | str | None = None,
        client_transfer_id: UUID | str | None = None,
        ticker: str | None = None,
        market_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMPositionTransferResponse:
        """``POST /margin/fcm/positions/transfers`` — move a perps position.

        FCM members only. Kalshi must enable the endpoint for the member
        (400 until then; 409 while transfers are off for the exchange).
        Supply ``ticker`` or ``market_id`` (ticker wins if both).
        ``client_transfer_id`` is a required UUID idempotency key.
        POST is never retried.
        """
        self._require_auth()
        body = _build_transfer_position_body(
            request,
            source_subtrader_id=source_subtrader_id,
            target_subtrader_id=target_subtrader_id,
            side=side,
            count=count,
            price=price,
            client_transfer_id=client_transfer_id,
            ticker=ticker,
            market_id=market_id,
        )
        data = self._post(_POSITION_TRANSFER_PATH, json=body, extra_headers=extra_headers)
        return CreateMarginFCMPositionTransferResponse.model_validate(data)


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

    @overload
    async def transfer_position(
        self,
        *,
        request: CreateMarginFCMPositionTransferRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMPositionTransferResponse: ...
    @overload
    async def transfer_position(
        self,
        *,
        source_subtrader_id: str,
        target_subtrader_id: str,
        side: FCMPositionTransferSideLiteral,
        count: Decimal | int | float | str,
        price: Decimal | int | float | str,
        client_transfer_id: UUID | str,
        ticker: str | None = None,
        market_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMPositionTransferResponse: ...
    async def transfer_position(
        self,
        *,
        request: CreateMarginFCMPositionTransferRequest | None = None,
        source_subtrader_id: str | None = None,
        target_subtrader_id: str | None = None,
        side: FCMPositionTransferSideLiteral | None = None,
        count: Decimal | int | float | str | None = None,
        price: Decimal | int | float | str | None = None,
        client_transfer_id: UUID | str | None = None,
        ticker: str | None = None,
        market_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginFCMPositionTransferResponse:
        """Async :meth:`FcmResource.transfer_position`."""
        self._require_auth()
        body = _build_transfer_position_body(
            request,
            source_subtrader_id=source_subtrader_id,
            target_subtrader_id=target_subtrader_id,
            side=side,
            count=count,
            price=price,
            client_transfer_id=client_transfer_id,
            ticker=ticker,
            market_id=market_id,
        )
        data = await self._post(
            _POSITION_TRANSFER_PATH, json=body, extra_headers=extra_headers
        )
        return CreateMarginFCMPositionTransferResponse.model_validate(data)
