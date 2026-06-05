"""Perps (margin) order groups resource (#392).

The margin-exchange twin of :mod:`kalshi.resources.order_groups`, targeting
``/margin/order_groups`` on the perps base URL. Order groups are rolling
15-second contracts-limit buckets: when the matched-contracts counter hits the
limit the whole group's orders are cancelled (auto-cancel) and no new orders
place until reset.

Every endpoint carries a spec ``security`` block, so every method calls
``self._require_auth()`` first. ``GetOrderGroupsResponse`` has no cursor, so
``list`` returns a plain ``builtins.list[OrderGroup]`` (no ``list_all`` /
``Iterator``). POST/PUT/DELETE are never retried (transport-enforced).

Unlike the portfolio resource, the perps ``/limit`` endpoint DOES carry
``SubaccountQueryDefaultPrimary`` — perps ``update_limit`` accepts ``subaccount``.
"""

from __future__ import annotations

import builtins
from typing import Any, overload

from kalshi.perps.models.order_groups import (
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
    """Sync perps order groups API."""

    def list(
        self, *, subaccount: int | None = None, extra_headers: dict[str, str] | None = None
    ) -> builtins.list[OrderGroup]:
        # Returns plain list (not Page) — spec response has no cursor.
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._get("/margin/order_groups", params=params, extra_headers=extra_headers)
        # order_groups is OPTIONAL per spec (no `required` block), so stay
        # tolerant of a missing OR null array — `or []` covers both (#404).
        raw = data.get("order_groups") or []
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
            f"/margin/order_groups/{_seg(order_group_id, name='order_group_id')}",
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
        # POST path is /margin/order_groups/create, not /margin/order_groups.
        self._require_auth()
        body = _build_create_order_group_body(
            request,
            contracts_limit=contracts_limit,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        data = self._post("/margin/order_groups/create", json=body, extra_headers=extra_headers)
        return CreateOrderGroupResponse.model_validate(data)

    def delete(
        self,
        order_group_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        # Spec DELETE carries only SubaccountQueryDefaultPrimary (no exchange_index).
        self._require_auth()
        params = _params(subaccount=subaccount)
        self._delete(
            f"/margin/order_groups/{_seg(order_group_id, name='order_group_id')}",
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
            f"/margin/order_groups/{_seg(order_group_id, name='order_group_id')}/reset",
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
            f"/margin/order_groups/{_seg(order_group_id, name='order_group_id')}/trigger",
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
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def update_limit(
        self,
        order_group_id: str,
        *,
        contracts_limit: int,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def update_limit(
        self,
        order_group_id: str,
        *,
        request: UpdateOrderGroupLimitRequest | None = None,
        contracts_limit: int | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        # Unlike portfolio, perps /limit carries SubaccountQueryDefaultPrimary.
        self._require_auth()
        body = _build_update_limit_body(
            request,
            contracts_limit=contracts_limit,
        )
        params = _params(subaccount=subaccount)
        self._put(
            f"/margin/order_groups/{_seg(order_group_id, name='order_group_id')}/limit",
            params=params,
            json=body,
            extra_headers=extra_headers,
        )


class AsyncOrderGroupsResource(AsyncResource):
    """Async perps order groups API."""

    async def list(
        self, *, subaccount: int | None = None, extra_headers: dict[str, str] | None = None
    ) -> builtins.list[OrderGroup]:
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = await self._get("/margin/order_groups", params=params, extra_headers=extra_headers)
        # order_groups is OPTIONAL per spec (no `required` block), so stay
        # tolerant of a missing OR null array — `or []` covers both (#404).
        raw = data.get("order_groups") or []
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
            f"/margin/order_groups/{_seg(order_group_id, name='order_group_id')}",
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
            "/margin/order_groups/create", json=body, extra_headers=extra_headers
        )
        return CreateOrderGroupResponse.model_validate(data)

    async def delete(
        self,
        order_group_id: str,
        *,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        # Spec DELETE carries only SubaccountQueryDefaultPrimary (no exchange_index).
        self._require_auth()
        params = _params(subaccount=subaccount)
        await self._delete(
            f"/margin/order_groups/{_seg(order_group_id, name='order_group_id')}",
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
            f"/margin/order_groups/{_seg(order_group_id, name='order_group_id')}/reset",
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
            f"/margin/order_groups/{_seg(order_group_id, name='order_group_id')}/trigger",
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
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def update_limit(
        self,
        order_group_id: str,
        *,
        contracts_limit: int,
        subaccount: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def update_limit(
        self,
        order_group_id: str,
        *,
        request: UpdateOrderGroupLimitRequest | None = None,
        contracts_limit: int | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        # Unlike portfolio, perps /limit carries SubaccountQueryDefaultPrimary.
        self._require_auth()
        body = _build_update_limit_body(
            request,
            contracts_limit=contracts_limit,
        )
        params = _params(subaccount=subaccount)
        await self._put(
            f"/margin/order_groups/{_seg(order_group_id, name='order_group_id')}/limit",
            params=params,
            json=body,
            extra_headers=extra_headers,
        )
