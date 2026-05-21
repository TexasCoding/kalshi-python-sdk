"""Order Groups resource — rolling 15-second contracts-limit groups for linked orders."""

from __future__ import annotations

import builtins
from typing import Any, overload

from kalshi.models.order_groups import (
    CreateOrderGroupRequest,
    CreateOrderGroupResponse,
    GetOrderGroupResponse,
    OrderGroup,
    UpdateOrderGroupLimitRequest,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _params,
    _seg,
)

# Shared body builders (issue #46).


def _build_create_order_group_body(
    request: CreateOrderGroupRequest | None,
    *,
    contracts_limit: int | None,
    subaccount: int | None,
    exchange_index: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        contracts_limit=contracts_limit,
        subaccount=subaccount,
        exchange_index=exchange_index,
    )
    if request is None:
        if contracts_limit is None:
            raise TypeError("create() requires `contracts_limit` (or pass `request=...`)")
        request = CreateOrderGroupRequest(
            contracts_limit=contracts_limit,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_update_limit_body(
    request: UpdateOrderGroupLimitRequest | None,
    *,
    contracts_limit: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(request, contracts_limit=contracts_limit)
    if request is None:
        if contracts_limit is None:
            raise TypeError("update_limit() requires `contracts_limit` (or pass `request=...`)")
        request = UpdateOrderGroupLimitRequest(contracts_limit=contracts_limit)
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


class OrderGroupsResource(SyncResource):
    """Sync order groups API."""

    def list(
        self, *, subaccount: int | None = None, extra_headers: dict[str, str] | None = None
    ) -> builtins.list[OrderGroup]:
        # Returns plain list (not Page) — spec response has no cursor.
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._get("/portfolio/order_groups", params=params, extra_headers=extra_headers)
        raw = data.get("order_groups", [])
        return [OrderGroup.model_validate(item) for item in raw]

    def get(
        self,
        order_group_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetOrderGroupResponse:
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._get(
            f"/portfolio/order_groups/{_seg(order_group_id, name='order_group_id')}",
            params=params,
            extra_headers=extra_headers,
        )
        return GetOrderGroupResponse.model_validate(data)

    @overload
    def create(
        self, *, request: CreateOrderGroupRequest, extra_headers: dict[str, str] | None = None
    ) -> CreateOrderGroupResponse: ...
    @overload
    def create(
        self,
        *,
        contracts_limit: int,
        subaccount: int | None = ...,
        exchange_index: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateOrderGroupResponse: ...
    def create(
        self,
        *,
        request: CreateOrderGroupRequest | None = None,
        contracts_limit: int | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateOrderGroupResponse:
        # POST path is /order_groups/create, not /order_groups.
        self._require_auth()
        body = _build_create_order_group_body(
            request,
            contracts_limit=contracts_limit,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        data = self._post("/portfolio/order_groups/create", json=body, extra_headers=extra_headers)
        return CreateOrderGroupResponse.model_validate(data)

    def delete(
        self,
        order_group_id: str,
        *,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount, exchange_index=exchange_index)
        self._delete(
            f"/portfolio/order_groups/{_seg(order_group_id, name='order_group_id')}",
            params=params,
            extra_headers=extra_headers,
        )

    def reset(
        self,
        order_group_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        # json={} forces Content-Type: application/json — demo rejects the PUT without it.
        self._put(
            f"/portfolio/order_groups/{_seg(order_group_id, name='order_group_id')}/reset",
            params=params,
            json={},
            extra_headers=extra_headers,
        )

    def trigger(
        self,
        order_group_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        # json={} forces Content-Type: application/json — demo rejects the PUT without it.
        self._put(
            f"/portfolio/order_groups/{_seg(order_group_id, name='order_group_id')}/trigger",
            params=params,
            json={},
            extra_headers=extra_headers,
        )

    @overload
    def update_limit(
        self,
        order_group_id: str,
        *,
        request: UpdateOrderGroupLimitRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def update_limit(
        self,
        order_group_id: str,
        *,
        contracts_limit: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def update_limit(
        self,
        order_group_id: str,
        *,
        request: UpdateOrderGroupLimitRequest | None = None,
        contracts_limit: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        # No subaccount kwarg — spec omits SubaccountQuery on /limit.
        self._require_auth()
        body = _build_update_limit_body(
            request,
            contracts_limit=contracts_limit,
        )
        self._put(
            f"/portfolio/order_groups/{_seg(order_group_id, name='order_group_id')}/limit",
            json=body,
            extra_headers=extra_headers,
        )


class AsyncOrderGroupsResource(AsyncResource):
    """Async order groups API."""

    async def list(
        self, *, subaccount: int | None = None, extra_headers: dict[str, str] | None = None
    ) -> builtins.list[OrderGroup]:
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = await self._get(
            "/portfolio/order_groups", params=params, extra_headers=extra_headers
        )
        raw = data.get("order_groups", [])
        return [OrderGroup.model_validate(item) for item in raw]

    async def get(
        self,
        order_group_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetOrderGroupResponse:
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = await self._get(
            f"/portfolio/order_groups/{_seg(order_group_id, name='order_group_id')}",
            params=params,
            extra_headers=extra_headers,
        )
        return GetOrderGroupResponse.model_validate(data)

    @overload
    async def create(
        self, *, request: CreateOrderGroupRequest, extra_headers: dict[str, str] | None = None
    ) -> CreateOrderGroupResponse: ...
    @overload
    async def create(
        self,
        *,
        contracts_limit: int,
        subaccount: int | None = ...,
        exchange_index: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateOrderGroupResponse: ...
    async def create(
        self,
        *,
        request: CreateOrderGroupRequest | None = None,
        contracts_limit: int | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateOrderGroupResponse:
        self._require_auth()
        body = _build_create_order_group_body(
            request,
            contracts_limit=contracts_limit,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        data = await self._post(
            "/portfolio/order_groups/create", json=body, extra_headers=extra_headers
        )
        return CreateOrderGroupResponse.model_validate(data)

    async def delete(
        self,
        order_group_id: str,
        *,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount, exchange_index=exchange_index)
        await self._delete(
            f"/portfolio/order_groups/{_seg(order_group_id, name='order_group_id')}",
            params=params,
            extra_headers=extra_headers,
        )

    async def reset(
        self,
        order_group_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        # json={} forces Content-Type: application/json — demo rejects the PUT without it.
        await self._put(
            f"/portfolio/order_groups/{_seg(order_group_id, name='order_group_id')}/reset",
            params=params,
            json={},
            extra_headers=extra_headers,
        )

    async def trigger(
        self,
        order_group_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        # json={} forces Content-Type: application/json — demo rejects the PUT without it.
        await self._put(
            f"/portfolio/order_groups/{_seg(order_group_id, name='order_group_id')}/trigger",
            params=params,
            json={},
            extra_headers=extra_headers,
        )

    @overload
    async def update_limit(
        self,
        order_group_id: str,
        *,
        request: UpdateOrderGroupLimitRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def update_limit(
        self,
        order_group_id: str,
        *,
        contracts_limit: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def update_limit(
        self,
        order_group_id: str,
        *,
        request: UpdateOrderGroupLimitRequest | None = None,
        contracts_limit: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_update_limit_body(
            request,
            contracts_limit=contracts_limit,
        )
        await self._put(
            f"/portfolio/order_groups/{_seg(order_group_id, name='order_group_id')}/limit",
            json=body,
            extra_headers=extra_headers,
        )
