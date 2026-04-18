"""Order Groups resource — rolling 15-second contracts-limit groups for
linked orders. Spec: ``/portfolio/order_groups/*`` endpoints.
"""

from __future__ import annotations

import builtins

from kalshi.models.order_groups import (
    CreateOrderGroupRequest,
    CreateOrderGroupResponse,
    GetOrderGroupResponse,
    OrderGroup,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


class OrderGroupsResource(SyncResource):
    """Sync order groups API."""

    def list(self, *, subaccount: int | None = None) -> builtins.list[OrderGroup]:
        """List all order groups. Spec path: ``GET /portfolio/order_groups``.

        Returns a plain ``list[OrderGroup]`` (not a ``Page``) because the spec
        response ``GetOrderGroupsResponse`` has no cursor — Kalshi does not
        paginate this endpoint.
        """
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._get("/portfolio/order_groups", params=params)
        raw = data.get("order_groups", [])
        return [OrderGroup.model_validate(item) for item in raw]

    def get(
        self, order_group_id: str, *, subaccount: int | None = None,
    ) -> GetOrderGroupResponse:
        """Get one order group including member order IDs."""
        self._require_auth()
        params = _params(subaccount=subaccount)
        data = self._get(f"/portfolio/order_groups/{order_group_id}", params=params)
        return GetOrderGroupResponse.model_validate(data)

    def create(
        self, *, contracts_limit: int, subaccount: int | None = None,
    ) -> CreateOrderGroupResponse:
        """Create an order group. POST goes to ``/create`` (not the base path)."""
        self._require_auth()
        req = CreateOrderGroupRequest(
            contracts_limit=contracts_limit,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post("/portfolio/order_groups/create", json=body)
        return CreateOrderGroupResponse.model_validate(data)


class AsyncOrderGroupsResource(AsyncResource):
    """Async order groups API — methods added in Task 5."""
