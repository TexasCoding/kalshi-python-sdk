"""Order Groups resource — rolling 15-second contracts-limit groups for linked orders."""

from __future__ import annotations

import builtins

from kalshi.models.order_groups import (
    CreateOrderGroupRequest,
    CreateOrderGroupResponse,
    GetOrderGroupResponse,
    OrderGroup,
    UpdateOrderGroupLimitRequest,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


class OrderGroupsResource(SyncResource):
    """Sync order groups API."""

    def list(self, *, subaccount: int | None = None) -> builtins.list[OrderGroup]:
        # Returns plain list (not Page) — spec response has no cursor.
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._get("/portfolio/order_groups", params=params)
        raw = data.get("order_groups", [])
        return [OrderGroup.model_validate(item) for item in raw]

    def get(
        self, order_group_id: str, *, subaccount: int | None = None,
    ) -> GetOrderGroupResponse:
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._get(f"/portfolio/order_groups/{order_group_id}", params=params)
        return GetOrderGroupResponse.model_validate(data)

    def create(
        self, *, contracts_limit: int, subaccount: int | None = None,
    ) -> CreateOrderGroupResponse:
        # POST path is /order_groups/create, not /order_groups.
        self._require_auth()
        req = CreateOrderGroupRequest(
            contracts_limit=contracts_limit,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post("/portfolio/order_groups/create", json=body)
        return CreateOrderGroupResponse.model_validate(data)

    def delete(self, order_group_id: str, *, subaccount: int | None = None) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        self._delete(f"/portfolio/order_groups/{order_group_id}", params=params)

    def reset(self, order_group_id: str, *, subaccount: int | None = None) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        # json={} forces Content-Type: application/json — demo rejects the PUT without it.
        self._transport.request(
            "PUT", f"/portfolio/order_groups/{order_group_id}/reset",
            params=params, json={},
        )

    def trigger(self, order_group_id: str, *, subaccount: int | None = None) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        # json={} forces Content-Type: application/json — demo rejects the PUT without it.
        self._transport.request(
            "PUT", f"/portfolio/order_groups/{order_group_id}/trigger",
            params=params, json={},
        )

    def update_limit(self, order_group_id: str, *, contracts_limit: int) -> None:
        # No subaccount kwarg — spec omits SubaccountQuery on /limit.
        self._require_auth()
        req = UpdateOrderGroupLimitRequest(contracts_limit=contracts_limit)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        self._put(f"/portfolio/order_groups/{order_group_id}/limit", json=body)


class AsyncOrderGroupsResource(AsyncResource):
    async def list(self, *, subaccount: int | None = None) -> builtins.list[OrderGroup]:
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = await self._get("/portfolio/order_groups", params=params)
        raw = data.get("order_groups", [])
        return [OrderGroup.model_validate(item) for item in raw]

    async def get(
        self, order_group_id: str, *, subaccount: int | None = None,
    ) -> GetOrderGroupResponse:
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = await self._get(
            f"/portfolio/order_groups/{order_group_id}", params=params,
        )
        return GetOrderGroupResponse.model_validate(data)

    async def create(
        self, *, contracts_limit: int, subaccount: int | None = None,
    ) -> CreateOrderGroupResponse:
        self._require_auth()
        req = CreateOrderGroupRequest(
            contracts_limit=contracts_limit, subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post("/portfolio/order_groups/create", json=body)
        return CreateOrderGroupResponse.model_validate(data)

    async def delete(
        self, order_group_id: str, *, subaccount: int | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        await self._delete(f"/portfolio/order_groups/{order_group_id}", params=params)

    async def reset(
        self, order_group_id: str, *, subaccount: int | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        # json={} forces Content-Type: application/json — demo rejects the PUT without it.
        await self._transport.request(
            "PUT", f"/portfolio/order_groups/{order_group_id}/reset",
            params=params, json={},
        )

    async def trigger(
        self, order_group_id: str, *, subaccount: int | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        # json={} forces Content-Type: application/json — demo rejects the PUT without it.
        await self._transport.request(
            "PUT", f"/portfolio/order_groups/{order_group_id}/trigger",
            params=params, json={},
        )

    async def update_limit(
        self, order_group_id: str, *, contracts_limit: int,
    ) -> None:
        self._require_auth()
        req = UpdateOrderGroupLimitRequest(contracts_limit=contracts_limit)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        await self._put(f"/portfolio/order_groups/{order_group_id}/limit", json=body)
