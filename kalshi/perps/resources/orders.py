"""Perps (margin) orders resource — create/get/list/cancel/decrease/amend + FCM (#391).

The trade-execution surface of the perps API. Mirrors the prediction-API V2
order family (``kalshi/resources/orders.py``) but talks to the perps base URL.

Every endpoint here carries a spec ``security`` block, so each method calls
``_require_auth()`` first — an unauthenticated caller gets ``AuthRequiredError``
before any HTTP request. ``create``, ``cancel``, ``decrease``, and ``amend`` are
POST/DELETE, which the transport never retries (duplicate-order / cancel-
idempotency risk); only the GET ``get``/``list``/``list_fcm`` retry.

``subaccount`` routing follows the spec split: ``create`` carries it in the
request *body* (``CreateMarginOrderRequest.subaccount``), while
cancel/decrease/amend route it as a *query* param. ``list_fcm`` has no
``subaccount`` at all — it filters by the required ``subtrader_id``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, overload

from kalshi.errors import KalshiError
from kalshi.perps.models.orders import (
    AmendMarginOrderRequest,
    AmendMarginOrderResponse,
    BookSideLiteral,
    CancelMarginOrderResponse,
    CreateMarginOrderRequest,
    CreateMarginOrderResponse,
    DecreaseMarginOrderRequest,
    DecreaseMarginOrderResponse,
    GetMarginOrderResponse,
    GetMarginOrdersResponse,
    MarginOrder,
    SelfTradePreventionTypeLiteral,
    TimeInForceLiteral,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _params,
    _seg,
    _validate_limit,
    _validate_max_pages,
)
from kalshi.types import to_decimal

# ---------------------------------------------------------------------------
# Shared request-body builders (pure: kwargs in, dict[str, Any] out). Both the
# sync and async resource methods call the same builder so model construction
# and serialization live in one place.
# ---------------------------------------------------------------------------


def _build_create_body(
    request: CreateMarginOrderRequest | None,
    *,
    ticker: str | None,
    client_order_id: str | None,
    side: BookSideLiteral | None,
    count: int | float | str | None,
    price: int | float | str | None,
    time_in_force: TimeInForceLiteral | None,
    self_trade_prevention_type: SelfTradePreventionTypeLiteral | None,
    expiration_time: int | None,
    post_only: bool | None,
    cancel_order_on_pause: bool | None,
    reduce_only: bool | None,
    subaccount: int | None,
    order_group_id: str | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        ticker=ticker,
        client_order_id=client_order_id,
        side=side,
        count=count,
        price=price,
        time_in_force=time_in_force,
        self_trade_prevention_type=self_trade_prevention_type,
        expiration_time=expiration_time,
        post_only=post_only,
        cancel_order_on_pause=cancel_order_on_pause,
        reduce_only=reduce_only,
        subaccount=subaccount,
        order_group_id=order_group_id,
    )
    if request is None:
        if (
            ticker is None
            or client_order_id is None
            or side is None
            or count is None
            or price is None
            or time_in_force is None
            or self_trade_prevention_type is None
        ):
            raise TypeError(
                "create() requires `ticker`, `client_order_id`, `side`, `count`, "
                "`price`, `time_in_force`, and `self_trade_prevention_type` "
                "(or pass `request=...`)."
            )
        request = CreateMarginOrderRequest(
            ticker=ticker,
            client_order_id=client_order_id,
            side=side,
            count=to_decimal(count),
            price=to_decimal(price),
            time_in_force=time_in_force,
            self_trade_prevention_type=self_trade_prevention_type,
            expiration_time=expiration_time,
            post_only=post_only,
            cancel_order_on_pause=cancel_order_on_pause,
            reduce_only=reduce_only,
            subaccount=subaccount,
            order_group_id=order_group_id,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_decrease_body(
    request: DecreaseMarginOrderRequest | None,
    *,
    reduce_by: int | float | str | None,
    reduce_to: int | float | str | None,
) -> dict[str, Any]:
    _check_request_exclusive(request, reduce_by=reduce_by, reduce_to=reduce_to)
    if request is None:
        # The model validator enforces the reduce_by/reduce_to XOR; build it
        # directly so both the kwarg and request= paths share one rule.
        request = DecreaseMarginOrderRequest(
            reduce_by=to_decimal(reduce_by) if reduce_by is not None else None,
            reduce_to=to_decimal(reduce_to) if reduce_to is not None else None,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_amend_body(
    request: AmendMarginOrderRequest | None,
    *,
    ticker: str | None,
    side: BookSideLiteral | None,
    price: int | float | str | None,
    count: int | float | str | None,
    client_order_id: str | None,
    updated_client_order_id: str | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        ticker=ticker,
        side=side,
        price=price,
        count=count,
        client_order_id=client_order_id,
        updated_client_order_id=updated_client_order_id,
    )
    if request is None:
        if ticker is None or side is None or price is None or count is None:
            raise TypeError(
                "amend() requires `ticker`, `side`, `price`, and `count` "
                "(or pass `request=...`)."
            )
        request = AmendMarginOrderRequest(
            ticker=ticker,
            side=side,
            price=to_decimal(price),
            count=to_decimal(count),
            client_order_id=client_order_id,
            updated_client_order_id=updated_client_order_id,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _list_orders_params(
    *,
    ticker: str | None,
    status: str | None,
    min_ts: int | None,
    max_ts: int | None,
    limit: int | None,
    cursor: str | None,
    subaccount: int | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000)
    return _params(
        ticker=ticker,
        status=status,
        min_ts=min_ts,
        max_ts=max_ts,
        limit=limit,
        cursor=cursor,
        subaccount=subaccount,
    )


def _list_fcm_params(
    *,
    subtrader_id: str,
    ticker: str | None,
    status: str | None,
    min_ts: int | None,
    max_ts: int | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000)
    return _params(
        subtrader_id=subtrader_id,
        ticker=ticker,
        status=status,
        min_ts=min_ts,
        max_ts=max_ts,
        limit=limit,
        cursor=cursor,
    )


class MarginOrdersResource(SyncResource):
    """Sync perps orders API (create/get/list/cancel/decrease/amend + FCM orders)."""

    @overload
    def create(
        self, *, request: CreateMarginOrderRequest, extra_headers: dict[str, str] | None = None
    ) -> CreateMarginOrderResponse: ...
    @overload
    def create(
        self,
        *,
        ticker: str,
        client_order_id: str,
        side: BookSideLiteral,
        count: int | float | str,
        price: int | float | str,
        time_in_force: TimeInForceLiteral,
        self_trade_prevention_type: SelfTradePreventionTypeLiteral,
        expiration_time: int | None = ...,
        post_only: bool | None = ...,
        cancel_order_on_pause: bool | None = ...,
        reduce_only: bool | None = ...,
        subaccount: int | None = ...,
        order_group_id: str | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginOrderResponse: ...
    def create(
        self,
        *,
        request: CreateMarginOrderRequest | None = None,
        ticker: str | None = None,
        client_order_id: str | None = None,
        side: BookSideLiteral | None = None,
        count: int | float | str | None = None,
        price: int | float | str | None = None,
        time_in_force: TimeInForceLiteral | None = None,
        self_trade_prevention_type: SelfTradePreventionTypeLiteral | None = None,
        expiration_time: int | None = None,
        post_only: bool | None = None,
        cancel_order_on_pause: bool | None = None,
        reduce_only: bool | None = None,
        subaccount: int | None = None,
        order_group_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginOrderResponse:
        """Place a new margin order (POST /margin/orders). Not retried.

        ``expiration_time`` is int64 Unix seconds per spec. ``subaccount``
        is carried in the request *body* (0 = primary).
        """
        self._require_auth()
        body = _build_create_body(
            request,
            ticker=ticker,
            client_order_id=client_order_id,
            side=side,
            count=count,
            price=price,
            time_in_force=time_in_force,
            self_trade_prevention_type=self_trade_prevention_type,
            expiration_time=expiration_time,
            post_only=post_only,
            cancel_order_on_pause=cancel_order_on_pause,
            reduce_only=reduce_only,
            subaccount=subaccount,
            order_group_id=order_group_id,
        )
        data = self._post("/margin/orders", json=body, extra_headers=extra_headers)
        return CreateMarginOrderResponse.model_validate(data)

    def get(self, order_id: str, *, extra_headers: dict[str, str] | None = None) -> MarginOrder:
        """Retrieve a single margin order (GET /margin/orders/{order_id})."""
        self._require_auth()
        data = self._get(
            f"/margin/orders/{_seg(order_id, name='order_id')}", extra_headers=extra_headers
        )
        return GetMarginOrderResponse.model_validate(data).order

    def list(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginOrdersResponse:
        """List margin orders, single page (GET /margin/orders).

        Returns the full envelope including ``cursor``. Use :meth:`list_all`
        to auto-paginate.
        """
        self._require_auth()
        params = _list_orders_params(
            ticker=ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
        )
        data = self._get("/margin/orders", params=params, extra_headers=extra_headers)
        return GetMarginOrdersResponse.model_validate(data)

    def list_all(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        subaccount: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[MarginOrder]:
        """Auto-paginate all margin orders (GET /margin/orders)."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_orders_params(
            ticker=ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
            subaccount=subaccount,
        )
        return self._list_all(
            "/margin/orders",
            MarginOrder,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def cancel(
        self,
        order_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CancelMarginOrderResponse:
        """Cancel a margin order (DELETE /margin/orders/{order_id}). Not retried."""
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._delete(
            f"/margin/orders/{_seg(order_id, name='order_id')}",
            params=params,
            extra_headers=extra_headers,
        )
        if data is None:
            raise KalshiError("Expected CancelMarginOrderResponse body, got 204 No Content.")
        return CancelMarginOrderResponse.model_validate(data)

    @overload
    def decrease(
        self,
        order_id: str,
        *,
        request: DecreaseMarginOrderRequest,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> DecreaseMarginOrderResponse: ...
    @overload
    def decrease(
        self,
        order_id: str,
        *,
        reduce_by: int | float | str | None = ...,
        reduce_to: int | float | str | None = ...,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> DecreaseMarginOrderResponse: ...
    def decrease(
        self,
        order_id: str,
        *,
        request: DecreaseMarginOrderRequest | None = None,
        reduce_by: int | float | str | None = None,
        reduce_to: int | float | str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> DecreaseMarginOrderResponse:
        """Decrease a margin order's size (POST /margin/orders/{order_id}/decrease).

        Exactly one of ``reduce_by`` / ``reduce_to`` is required (enforced by
        the request model). ``subaccount`` is a query param. Not retried.
        """
        self._require_auth()
        body = _build_decrease_body(request, reduce_by=reduce_by, reduce_to=reduce_to)
        params = _params(subaccount=subaccount)
        data = self._post(
            f"/margin/orders/{_seg(order_id, name='order_id')}/decrease",
            params=params,
            json=body,
            extra_headers=extra_headers,
        )
        return DecreaseMarginOrderResponse.model_validate(data)

    @overload
    def amend(
        self,
        order_id: str,
        *,
        request: AmendMarginOrderRequest,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendMarginOrderResponse: ...
    @overload
    def amend(
        self,
        order_id: str,
        *,
        ticker: str,
        side: BookSideLiteral,
        price: int | float | str,
        count: int | float | str,
        client_order_id: str | None = ...,
        updated_client_order_id: str | None = ...,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendMarginOrderResponse: ...
    def amend(
        self,
        order_id: str,
        *,
        request: AmendMarginOrderRequest | None = None,
        ticker: str | None = None,
        side: BookSideLiteral | None = None,
        price: int | float | str | None = None,
        count: int | float | str | None = None,
        client_order_id: str | None = None,
        updated_client_order_id: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendMarginOrderResponse:
        """Amend a margin order's price/size (POST /margin/orders/{order_id}/amend).

        ``subaccount`` is a query param. Increasing size or changing price
        forfeits queue position (server-side). Not retried.
        """
        self._require_auth()
        body = _build_amend_body(
            request,
            ticker=ticker,
            side=side,
            price=price,
            count=count,
            client_order_id=client_order_id,
            updated_client_order_id=updated_client_order_id,
        )
        params = _params(subaccount=subaccount)
        data = self._post(
            f"/margin/orders/{_seg(order_id, name='order_id')}/amend",
            params=params,
            json=body,
            extra_headers=extra_headers,
        )
        return AmendMarginOrderResponse.model_validate(data)

    def list_fcm(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginOrdersResponse:
        """List margin orders for an FCM subtrader, single page (GET /margin/fcm/orders).

        ``subtrader_id`` is required. No ``subaccount`` param.
        """
        self._require_auth()
        params = _list_fcm_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        data = self._get("/margin/fcm/orders", params=params, extra_headers=extra_headers)
        return GetMarginOrdersResponse.model_validate(data)

    def list_all_fcm(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[MarginOrder]:
        """Auto-paginate FCM subtrader orders (GET /margin/fcm/orders)."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_fcm_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/margin/fcm/orders",
            MarginOrder,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )


class AsyncMarginOrdersResource(AsyncResource):
    """Async perps orders API (create/get/list/cancel/decrease/amend + FCM orders)."""

    @overload
    async def create(
        self, *, request: CreateMarginOrderRequest, extra_headers: dict[str, str] | None = None
    ) -> CreateMarginOrderResponse: ...
    @overload
    async def create(
        self,
        *,
        ticker: str,
        client_order_id: str,
        side: BookSideLiteral,
        count: int | float | str,
        price: int | float | str,
        time_in_force: TimeInForceLiteral,
        self_trade_prevention_type: SelfTradePreventionTypeLiteral,
        expiration_time: int | None = ...,
        post_only: bool | None = ...,
        cancel_order_on_pause: bool | None = ...,
        reduce_only: bool | None = ...,
        subaccount: int | None = ...,
        order_group_id: str | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginOrderResponse: ...
    async def create(
        self,
        *,
        request: CreateMarginOrderRequest | None = None,
        ticker: str | None = None,
        client_order_id: str | None = None,
        side: BookSideLiteral | None = None,
        count: int | float | str | None = None,
        price: int | float | str | None = None,
        time_in_force: TimeInForceLiteral | None = None,
        self_trade_prevention_type: SelfTradePreventionTypeLiteral | None = None,
        expiration_time: int | None = None,
        post_only: bool | None = None,
        cancel_order_on_pause: bool | None = None,
        reduce_only: bool | None = None,
        subaccount: int | None = None,
        order_group_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginOrderResponse:
        """Place a new margin order. See :meth:`MarginOrdersResource.create`."""
        self._require_auth()
        body = _build_create_body(
            request,
            ticker=ticker,
            client_order_id=client_order_id,
            side=side,
            count=count,
            price=price,
            time_in_force=time_in_force,
            self_trade_prevention_type=self_trade_prevention_type,
            expiration_time=expiration_time,
            post_only=post_only,
            cancel_order_on_pause=cancel_order_on_pause,
            reduce_only=reduce_only,
            subaccount=subaccount,
            order_group_id=order_group_id,
        )
        data = await self._post("/margin/orders", json=body, extra_headers=extra_headers)
        return CreateMarginOrderResponse.model_validate(data)

    async def get(
        self, order_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> MarginOrder:
        """Retrieve a single margin order."""
        self._require_auth()
        data = await self._get(
            f"/margin/orders/{_seg(order_id, name='order_id')}", extra_headers=extra_headers
        )
        return GetMarginOrderResponse.model_validate(data).order

    async def list(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginOrdersResponse:
        """List margin orders, single page. See :meth:`MarginOrdersResource.list`."""
        self._require_auth()
        params = _list_orders_params(
            ticker=ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
        )
        data = await self._get("/margin/orders", params=params, extra_headers=extra_headers)
        return GetMarginOrdersResponse.model_validate(data)

    def list_all(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        subaccount: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[MarginOrder]:
        """Auto-paginate all margin orders. Returns an async iterator — use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_orders_params(
            ticker=ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
            subaccount=subaccount,
        )
        return self._list_all(
            "/margin/orders",
            MarginOrder,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def cancel(
        self,
        order_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CancelMarginOrderResponse:
        """Cancel a margin order. Not retried."""
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = await self._delete(
            f"/margin/orders/{_seg(order_id, name='order_id')}",
            params=params,
            extra_headers=extra_headers,
        )
        if data is None:
            raise KalshiError("Expected CancelMarginOrderResponse body, got 204 No Content.")
        return CancelMarginOrderResponse.model_validate(data)

    @overload
    async def decrease(
        self,
        order_id: str,
        *,
        request: DecreaseMarginOrderRequest,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> DecreaseMarginOrderResponse: ...
    @overload
    async def decrease(
        self,
        order_id: str,
        *,
        reduce_by: int | float | str | None = ...,
        reduce_to: int | float | str | None = ...,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> DecreaseMarginOrderResponse: ...
    async def decrease(
        self,
        order_id: str,
        *,
        request: DecreaseMarginOrderRequest | None = None,
        reduce_by: int | float | str | None = None,
        reduce_to: int | float | str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> DecreaseMarginOrderResponse:
        """Decrease a margin order's size. See :meth:`MarginOrdersResource.decrease`."""
        self._require_auth()
        body = _build_decrease_body(request, reduce_by=reduce_by, reduce_to=reduce_to)
        params = _params(subaccount=subaccount)
        data = await self._post(
            f"/margin/orders/{_seg(order_id, name='order_id')}/decrease",
            params=params,
            json=body,
            extra_headers=extra_headers,
        )
        return DecreaseMarginOrderResponse.model_validate(data)

    @overload
    async def amend(
        self,
        order_id: str,
        *,
        request: AmendMarginOrderRequest,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendMarginOrderResponse: ...
    @overload
    async def amend(
        self,
        order_id: str,
        *,
        ticker: str,
        side: BookSideLiteral,
        price: int | float | str,
        count: int | float | str,
        client_order_id: str | None = ...,
        updated_client_order_id: str | None = ...,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendMarginOrderResponse: ...
    async def amend(
        self,
        order_id: str,
        *,
        request: AmendMarginOrderRequest | None = None,
        ticker: str | None = None,
        side: BookSideLiteral | None = None,
        price: int | float | str | None = None,
        count: int | float | str | None = None,
        client_order_id: str | None = None,
        updated_client_order_id: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendMarginOrderResponse:
        """Amend a margin order's price/size. See :meth:`MarginOrdersResource.amend`."""
        self._require_auth()
        body = _build_amend_body(
            request,
            ticker=ticker,
            side=side,
            price=price,
            count=count,
            client_order_id=client_order_id,
            updated_client_order_id=updated_client_order_id,
        )
        params = _params(subaccount=subaccount)
        data = await self._post(
            f"/margin/orders/{_seg(order_id, name='order_id')}/amend",
            params=params,
            json=body,
            extra_headers=extra_headers,
        )
        return AmendMarginOrderResponse.model_validate(data)

    async def list_fcm(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginOrdersResponse:
        """List FCM subtrader orders, single page. See :meth:`MarginOrdersResource.list_fcm`."""
        self._require_auth()
        params = _list_fcm_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        data = await self._get("/margin/fcm/orders", params=params, extra_headers=extra_headers)
        return GetMarginOrdersResponse.model_validate(data)

    def list_all_fcm(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[MarginOrder]:
        """Auto-paginate FCM subtrader orders. Returns an async iterator — use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_fcm_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/margin/fcm/orders",
            MarginOrder,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )
