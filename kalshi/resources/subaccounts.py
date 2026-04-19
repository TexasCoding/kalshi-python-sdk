"""Subaccounts resource — multi-account workflows under one authenticated user."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import UUID

from kalshi.models.common import Page
from kalshi.models.subaccounts import (
    ApplySubaccountTransferRequest,
    CreateSubaccountResponse,
    GetSubaccountBalancesResponse,
    GetSubaccountNettingResponse,
    SubaccountTransfer,
    UpdateSubaccountNettingRequest,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


class SubaccountsResource(SyncResource):
    """Sync subaccounts API.

    Subaccount 0 is the primary account; 1-32 are numbered subaccounts.
    POST /portfolio/subaccounts spins up the next subaccount with an
    empty body (spec takes no request payload).
    """

    def create(self) -> CreateSubaccountResponse:
        self._require_auth()
        # Spec defines no requestBody, but httpx omits Content-Type when no
        # body is passed and demo rejects the POST with `invalid_content_type`.
        # json={} forces Content-Type: application/json — same workaround
        # used on order_groups reset/trigger PUTs.
        data = self._post("/portfolio/subaccounts", json={})
        return CreateSubaccountResponse.model_validate(data)

    def transfer(
        self,
        *,
        client_transfer_id: UUID | str,
        from_subaccount: int,
        to_subaccount: int,
        amount_cents: int,
    ) -> None:
        self._require_auth()
        # Accept str for caller ergonomics; coerce once to surface a clean
        # ValueError on malformed strings before the model validator sees them.
        uid = (
            client_transfer_id
            if isinstance(client_transfer_id, UUID)
            else UUID(client_transfer_id)
        )
        req = ApplySubaccountTransferRequest(
            client_transfer_id=uid,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            amount_cents=amount_cents,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        self._post("/portfolio/subaccounts/transfer", json=body)

    def list_balances(self) -> GetSubaccountBalancesResponse:
        self._require_auth()
        data = self._get("/portfolio/subaccounts/balances")
        return GetSubaccountBalancesResponse.model_validate(data)

    def list_transfers(
        self, *, cursor: str | None = None, limit: int | None = None,
    ) -> Page[SubaccountTransfer]:
        self._require_auth()
        params = _params(cursor=cursor, limit=limit)
        return self._list(
            "/portfolio/subaccounts/transfers",
            SubaccountTransfer,
            "transfers",
            params=params,
        )

    def list_all_transfers(
        self, *, limit: int | None = None,
    ) -> Iterator[SubaccountTransfer]:
        self._require_auth()
        params = _params(limit=limit)
        yield from self._list_all(
            "/portfolio/subaccounts/transfers",
            SubaccountTransfer,
            "transfers",
            params=params,
        )

    def update_netting(
        self, *, subaccount_number: int, enabled: bool,
    ) -> None:
        self._require_auth()
        req = UpdateSubaccountNettingRequest(
            subaccount_number=subaccount_number, enabled=enabled,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        self._put("/portfolio/subaccounts/netting", json=body)

    def get_netting(self) -> GetSubaccountNettingResponse:
        self._require_auth()
        data = self._get("/portfolio/subaccounts/netting")
        return GetSubaccountNettingResponse.model_validate(data)


class AsyncSubaccountsResource(AsyncResource):
    """Async subaccounts API."""

    async def create(self) -> CreateSubaccountResponse:
        self._require_auth()
        # json={} forces Content-Type: application/json — demo rejects the
        # POST with `invalid_content_type` when no body is passed.
        data = await self._post("/portfolio/subaccounts", json={})
        return CreateSubaccountResponse.model_validate(data)

    async def transfer(
        self,
        *,
        client_transfer_id: UUID | str,
        from_subaccount: int,
        to_subaccount: int,
        amount_cents: int,
    ) -> None:
        self._require_auth()
        uid = (
            client_transfer_id
            if isinstance(client_transfer_id, UUID)
            else UUID(client_transfer_id)
        )
        req = ApplySubaccountTransferRequest(
            client_transfer_id=uid,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            amount_cents=amount_cents,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        await self._post("/portfolio/subaccounts/transfer", json=body)

    async def list_balances(self) -> GetSubaccountBalancesResponse:
        self._require_auth()
        data = await self._get("/portfolio/subaccounts/balances")
        return GetSubaccountBalancesResponse.model_validate(data)

    async def list_transfers(
        self, *, cursor: str | None = None, limit: int | None = None,
    ) -> Page[SubaccountTransfer]:
        self._require_auth()
        params = _params(cursor=cursor, limit=limit)
        return await self._list(
            "/portfolio/subaccounts/transfers",
            SubaccountTransfer,
            "transfers",
            params=params,
        )

    async def list_all_transfers(
        self, *, limit: int | None = None,
    ) -> AsyncIterator[SubaccountTransfer]:
        self._require_auth()
        params = _params(limit=limit)
        async for item in self._list_all(
            "/portfolio/subaccounts/transfers",
            SubaccountTransfer,
            "transfers",
            params=params,
        ):
            yield item

    async def update_netting(
        self, *, subaccount_number: int, enabled: bool,
    ) -> None:
        self._require_auth()
        req = UpdateSubaccountNettingRequest(
            subaccount_number=subaccount_number, enabled=enabled,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        await self._put("/portfolio/subaccounts/netting", json=body)

    async def get_netting(self) -> GetSubaccountNettingResponse:
        self._require_auth()
        data = await self._get("/portfolio/subaccounts/netting")
        return GetSubaccountNettingResponse.model_validate(data)
