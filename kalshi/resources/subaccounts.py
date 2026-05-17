"""Subaccounts resource — multi-account workflows under one authenticated user."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, overload
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
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _params,
    _validate_max_pages,
)

# Shared body builders (issue #46).


def _build_transfer_body(
    request: ApplySubaccountTransferRequest | None,
    *,
    client_transfer_id: UUID | str | None,
    from_subaccount: int | None,
    to_subaccount: int | None,
    amount_cents: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        client_transfer_id=client_transfer_id,
        from_subaccount=from_subaccount,
        to_subaccount=to_subaccount,
        amount_cents=amount_cents,
    )
    if request is None:
        if (
            client_transfer_id is None or from_subaccount is None
            or to_subaccount is None or amount_cents is None
        ):
            raise TypeError(
                "transfer() requires `client_transfer_id`, `from_subaccount`, "
                "`to_subaccount`, and `amount_cents` (or pass `request=...`)"
            )
        # Accept str for caller ergonomics; coerce once to surface a clean
        # ValueError on malformed strings before the model validator sees them.
        uid = (
            client_transfer_id
            if isinstance(client_transfer_id, UUID)
            else UUID(client_transfer_id)
        )
        request = ApplySubaccountTransferRequest(
            client_transfer_id=uid,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            amount_cents=amount_cents,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_update_netting_body(
    request: UpdateSubaccountNettingRequest | None,
    *,
    subaccount_number: int | None,
    enabled: bool | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request, subaccount_number=subaccount_number, enabled=enabled,
    )
    if request is None:
        if subaccount_number is None or enabled is None:
            raise TypeError(
                "update_netting() requires `subaccount_number` and `enabled` "
                "(or pass `request=...`)"
            )
        request = UpdateSubaccountNettingRequest(
            subaccount_number=subaccount_number, enabled=enabled,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


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

    @overload
    def transfer(self, *, request: ApplySubaccountTransferRequest) -> None: ...
    @overload
    def transfer(
        self,
        *,
        client_transfer_id: UUID | str,
        from_subaccount: int,
        to_subaccount: int,
        amount_cents: int,
    ) -> None: ...
    def transfer(
        self,
        *,
        request: ApplySubaccountTransferRequest | None = None,
        client_transfer_id: UUID | str | None = None,
        from_subaccount: int | None = None,
        to_subaccount: int | None = None,
        amount_cents: int | None = None,
    ) -> None:
        self._require_auth()
        body = _build_transfer_body(
            request,
            client_transfer_id=client_transfer_id,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            amount_cents=amount_cents,
        )
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
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
    ) -> Iterator[SubaccountTransfer]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _params(limit=limit)
        return self._list_all(
            "/portfolio/subaccounts/transfers",
            SubaccountTransfer,
            "transfers",
            params=params,
            max_pages=max_pages,
        )

    @overload
    def update_netting(
        self, *, request: UpdateSubaccountNettingRequest,
    ) -> None: ...
    @overload
    def update_netting(
        self, *, subaccount_number: int, enabled: bool,
    ) -> None: ...
    def update_netting(
        self,
        *,
        request: UpdateSubaccountNettingRequest | None = None,
        subaccount_number: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._require_auth()
        body = _build_update_netting_body(
            request, subaccount_number=subaccount_number, enabled=enabled,
        )
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

    @overload
    async def transfer(
        self, *, request: ApplySubaccountTransferRequest,
    ) -> None: ...
    @overload
    async def transfer(
        self,
        *,
        client_transfer_id: UUID | str,
        from_subaccount: int,
        to_subaccount: int,
        amount_cents: int,
    ) -> None: ...
    async def transfer(
        self,
        *,
        request: ApplySubaccountTransferRequest | None = None,
        client_transfer_id: UUID | str | None = None,
        from_subaccount: int | None = None,
        to_subaccount: int | None = None,
        amount_cents: int | None = None,
    ) -> None:
        self._require_auth()
        body = _build_transfer_body(
            request,
            client_transfer_id=client_transfer_id,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            amount_cents=amount_cents,
        )
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

    def list_all_transfers(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[SubaccountTransfer]:
        # Plain `def` (not `async def`) so _require_auth and _validate_max_pages
        # run at call time, not when the returned AsyncIterator is awaited.
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _params(limit=limit)
        return self._list_all(
            "/portfolio/subaccounts/transfers",
            SubaccountTransfer,
            "transfers",
            params=params,
            max_pages=max_pages,
        )

    @overload
    async def update_netting(
        self, *, request: UpdateSubaccountNettingRequest,
    ) -> None: ...
    @overload
    async def update_netting(
        self, *, subaccount_number: int, enabled: bool,
    ) -> None: ...
    async def update_netting(
        self,
        *,
        request: UpdateSubaccountNettingRequest | None = None,
        subaccount_number: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._require_auth()
        body = _build_update_netting_body(
            request, subaccount_number=subaccount_number, enabled=enabled,
        )
        await self._put("/portfolio/subaccounts/netting", json=body)

    async def get_netting(self) -> GetSubaccountNettingResponse:
        self._require_auth()
        data = await self._get("/portfolio/subaccounts/netting")
        return GetSubaccountNettingResponse.model_validate(data)
