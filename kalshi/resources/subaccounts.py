"""Subaccounts resource — multi-account workflows under one authenticated user."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from typing import Any, Literal, overload
from uuid import UUID

from kalshi.models.common import Page
from kalshi.models.subaccounts import (
    ApplySubaccountPositionTransferRequest,
    ApplySubaccountPositionTransferResponse,
    ApplySubaccountTransferRequest,
    CreateSubaccountRequest,
    CreateSubaccountResponse,
    GetSubaccountBalancesResponse,
    GetSubaccountNettingResponse,
    LockSubaccountForSettlementAdvanceRequest,
    LockSubaccountForSettlementAdvanceResponse,
    SubaccountTransfer,
    UnlockSubaccountForSettlementAdvanceRequest,
    UpdateSubaccountNettingRequest,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _params,
    _validate_limit,
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
            client_transfer_id is None
            or from_subaccount is None
            or to_subaccount is None
            or amount_cents is None
        ):
            raise TypeError(
                "transfer() requires `client_transfer_id`, `from_subaccount`, "
                "`to_subaccount`, and `amount_cents` (or pass `request=...`)"
            )
        # Accept str for caller ergonomics; coerce once to surface a clean
        # ValueError on malformed strings before the model validator sees them.
        uid = (
            client_transfer_id if isinstance(client_transfer_id, UUID) else UUID(client_transfer_id)
        )
        request = ApplySubaccountTransferRequest(
            client_transfer_id=uid,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            amount_cents=amount_cents,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_position_transfer_body(
    request: ApplySubaccountPositionTransferRequest | None,
    *,
    client_transfer_id: UUID | str | None,
    from_subaccount: int | None,
    to_subaccount: int | None,
    market_ticker: str | None,
    side: Literal["yes", "no"] | None,
    count: int | None,
    price: Decimal | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        client_transfer_id=client_transfer_id,
        from_subaccount=from_subaccount,
        to_subaccount=to_subaccount,
        market_ticker=market_ticker,
        side=side,
        count=count,
        price=price,
    )
    if request is None:
        if (
            client_transfer_id is None
            or from_subaccount is None
            or to_subaccount is None
            or market_ticker is None
            or side is None
            or count is None
            or price is None
        ):
            raise TypeError(
                "transfer_position() requires `client_transfer_id`, `from_subaccount`, "
                "`to_subaccount`, `market_ticker`, `side`, `count`, and `price` "
                "(or pass `request=...`)"
            )
        # Accept str for caller ergonomics; coerce once to surface a clean
        # ValueError on malformed strings before the model validator sees them.
        uid = (
            client_transfer_id if isinstance(client_transfer_id, UUID) else UUID(client_transfer_id)
        )
        request = ApplySubaccountPositionTransferRequest(
            client_transfer_id=uid,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            market_ticker=market_ticker,
            side=side,
            count=count,
            price=price,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_update_netting_body(
    request: UpdateSubaccountNettingRequest | None,
    *,
    subaccount_number: int | None,
    enabled: bool | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        subaccount_number=subaccount_number,
        enabled=enabled,
    )
    if request is None:
        if subaccount_number is None or enabled is None:
            raise TypeError(
                "update_netting() requires `subaccount_number` and `enabled` "
                "(or pass `request=...`)"
            )
        request = UpdateSubaccountNettingRequest(
            subaccount_number=subaccount_number,
            enabled=enabled,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_lock_settlement_advance_body(
    request: LockSubaccountForSettlementAdvanceRequest | None,
    *,
    subaccount_number: int | None,
    exchange_index: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        subaccount_number=subaccount_number,
        exchange_index=exchange_index,
    )
    if request is None:
        if subaccount_number is None:
            raise TypeError(
                "lock_settlement_advance() requires `subaccount_number` "
                "(or pass `request=...`)"
            )
        request = LockSubaccountForSettlementAdvanceRequest(
            subaccount_number=subaccount_number,
            exchange_index=exchange_index,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_unlock_settlement_advance_body(
    request: UnlockSubaccountForSettlementAdvanceRequest | None,
    *,
    subaccount_number: int | None,
    exchange_index: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        subaccount_number=subaccount_number,
        exchange_index=exchange_index,
    )
    if request is None:
        if subaccount_number is None:
            raise TypeError(
                "unlock_settlement_advance() requires `subaccount_number` "
                "(or pass `request=...`)"
            )
        request = UnlockSubaccountForSettlementAdvanceRequest(
            subaccount_number=subaccount_number,
            exchange_index=exchange_index,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


class SubaccountsResource(SyncResource):
    """Sync subaccounts API.

    Subaccount 0 is the primary account; positive integers identify numbered
    subaccounts (spec prose says ``1-63`` but defines no JSON-schema upper
    bound, and demo has been observed allocating numbers above 32).
    POST /portfolio/subaccounts spins up the next subaccount; ``exchange_index``
    optionally targets a specific exchange shard (spec v3.23.0).
    """

    def create(
        self,
        *,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateSubaccountResponse:
        self._require_auth()
        # Spec v3.23.0 defines an optional CreateSubaccountRequest body (a single
        # optional exchange_index). When exchange_index is None the body is `{}`,
        # which still forces Content-Type: application/json — demo rejects the
        # POST with `invalid_content_type` when no body is passed at all.
        body = CreateSubaccountRequest(exchange_index=exchange_index).model_dump(
            exclude_none=True, by_alias=True, mode="json"
        )
        data = self._post("/portfolio/subaccounts", json=body, extra_headers=extra_headers)
        return CreateSubaccountResponse.model_validate(data)

    @overload
    def transfer(
        self,
        *,
        request: ApplySubaccountTransferRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def transfer(
        self,
        *,
        client_transfer_id: UUID | str,
        from_subaccount: int,
        to_subaccount: int,
        amount_cents: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def transfer(
        self,
        *,
        request: ApplySubaccountTransferRequest | None = None,
        client_transfer_id: UUID | str | None = None,
        from_subaccount: int | None = None,
        to_subaccount: int | None = None,
        amount_cents: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_transfer_body(
            request,
            client_transfer_id=client_transfer_id,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            amount_cents=amount_cents,
        )
        self._post("/portfolio/subaccounts/transfer", json=body, extra_headers=extra_headers)

    @overload
    def transfer_position(
        self,
        *,
        request: ApplySubaccountPositionTransferRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> ApplySubaccountPositionTransferResponse: ...
    @overload
    def transfer_position(
        self,
        *,
        client_transfer_id: UUID | str,
        from_subaccount: int,
        to_subaccount: int,
        market_ticker: str,
        side: Literal["yes", "no"],
        count: int,
        price: Decimal,
        extra_headers: dict[str, str] | None = None,
    ) -> ApplySubaccountPositionTransferResponse: ...
    def transfer_position(
        self,
        *,
        request: ApplySubaccountPositionTransferRequest | None = None,
        client_transfer_id: UUID | str | None = None,
        from_subaccount: int | None = None,
        to_subaccount: int | None = None,
        market_ticker: str | None = None,
        side: Literal["yes", "no"] | None = None,
        count: int | None = None,
        price: Decimal | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> ApplySubaccountPositionTransferResponse:
        """Move an open position between subaccounts (spec v3.24.0).

        Unlike the cash-only :meth:`transfer`, this moves ``count`` contracts of
        ``market_ticker`` (``side``) and returns the server-generated
        ``position_transfer_id``. ``price`` is the per-contract cost basis in
        fixed-point dollars (0-1.0) — pass a ``Decimal``, e.g. ``Decimal("0.50")``.
        Spec v3.24.0 renamed this ``price_cents`` (integer cents) → ``price``.
        """
        self._require_auth()
        body = _build_position_transfer_body(
            request,
            client_transfer_id=client_transfer_id,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            market_ticker=market_ticker,
            side=side,
            count=count,
            price=price,
        )
        data = self._post(
            "/portfolio/subaccounts/positions/transfer", json=body, extra_headers=extra_headers
        )
        return ApplySubaccountPositionTransferResponse.model_validate(data)

    def list_balances(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSubaccountBalancesResponse:
        self._require_auth()
        data = self._get("/portfolio/subaccounts/balances", extra_headers=extra_headers)
        return GetSubaccountBalancesResponse.model_validate(data)

    def list_transfers(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[SubaccountTransfer]:
        self._require_auth()
        _validate_limit(limit, hi=1000)
        params = _params(cursor=cursor, limit=limit)
        return self._list(
            "/portfolio/subaccounts/transfers",
            SubaccountTransfer,
            "transfers",
            params=params,
            extra_headers=extra_headers,
        )

    def list_all_transfers(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[SubaccountTransfer]:
        self._require_auth()
        _validate_max_pages(max_pages)
        _validate_limit(limit, hi=1000)
        params = _params(limit=limit)
        return self._list_all(
            "/portfolio/subaccounts/transfers",
            SubaccountTransfer,
            "transfers",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @overload
    def update_netting(
        self,
        *,
        request: UpdateSubaccountNettingRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def update_netting(
        self, *, subaccount_number: int, enabled: bool, extra_headers: dict[str, str] | None = None
    ) -> None: ...
    def update_netting(
        self,
        *,
        request: UpdateSubaccountNettingRequest | None = None,
        subaccount_number: int | None = None,
        enabled: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_update_netting_body(
            request,
            subaccount_number=subaccount_number,
            enabled=enabled,
        )
        self._put("/portfolio/subaccounts/netting", json=body, extra_headers=extra_headers)

    def get_netting(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSubaccountNettingResponse:
        self._require_auth()
        data = self._get("/portfolio/subaccounts/netting", extra_headers=extra_headers)
        return GetSubaccountNettingResponse.model_validate(data)

    @overload
    def lock_settlement_advance(
        self,
        *,
        request: LockSubaccountForSettlementAdvanceRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> LockSubaccountForSettlementAdvanceResponse: ...
    @overload
    def lock_settlement_advance(
        self,
        *,
        subaccount_number: int,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LockSubaccountForSettlementAdvanceResponse: ...
    def lock_settlement_advance(
        self,
        *,
        request: LockSubaccountForSettlementAdvanceRequest | None = None,
        subaccount_number: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LockSubaccountForSettlementAdvanceResponse:
        """Lock a subaccount for settlement-advance computation.

        Cancels resting orders, prevents trading, and returns a new
        ``settlement_advance_state`` CAS token. Auth required.
        """
        self._require_auth()
        body = _build_lock_settlement_advance_body(
            request,
            subaccount_number=subaccount_number,
            exchange_index=exchange_index,
        )
        data = self._put(
            "/portfolio/subaccounts/settlement-advance-lock",
            json=body,
            extra_headers=extra_headers,
        )
        return LockSubaccountForSettlementAdvanceResponse.model_validate(data)

    @overload
    def unlock_settlement_advance(
        self,
        *,
        request: UnlockSubaccountForSettlementAdvanceRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def unlock_settlement_advance(
        self,
        *,
        subaccount_number: int,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def unlock_settlement_advance(
        self,
        *,
        request: UnlockSubaccountForSettlementAdvanceRequest | None = None,
        subaccount_number: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Unlock a subaccount previously locked for settlement advance.

        Rejected while the subaccount has an outstanding settlement advance.
        Auth required. Returns ``None`` (empty success body).
        """
        self._require_auth()
        body = _build_unlock_settlement_advance_body(
            request,
            subaccount_number=subaccount_number,
            exchange_index=exchange_index,
        )
        self._delete_with_body(
            "/portfolio/subaccounts/settlement-advance-lock",
            json=body,
            extra_headers=extra_headers,
        )


class AsyncSubaccountsResource(AsyncResource):
    """Async subaccounts API."""

    async def create(
        self,
        *,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateSubaccountResponse:
        self._require_auth()
        # Spec v3.23.0 optional CreateSubaccountRequest body; `{}` when
        # exchange_index is None still forces Content-Type: application/json —
        # demo rejects the POST with `invalid_content_type` when no body is sent.
        body = CreateSubaccountRequest(exchange_index=exchange_index).model_dump(
            exclude_none=True, by_alias=True, mode="json"
        )
        data = await self._post("/portfolio/subaccounts", json=body, extra_headers=extra_headers)
        return CreateSubaccountResponse.model_validate(data)

    @overload
    async def transfer(
        self,
        *,
        request: ApplySubaccountTransferRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def transfer(
        self,
        *,
        client_transfer_id: UUID | str,
        from_subaccount: int,
        to_subaccount: int,
        amount_cents: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def transfer(
        self,
        *,
        request: ApplySubaccountTransferRequest | None = None,
        client_transfer_id: UUID | str | None = None,
        from_subaccount: int | None = None,
        to_subaccount: int | None = None,
        amount_cents: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_transfer_body(
            request,
            client_transfer_id=client_transfer_id,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            amount_cents=amount_cents,
        )
        await self._post("/portfolio/subaccounts/transfer", json=body, extra_headers=extra_headers)

    @overload
    async def transfer_position(
        self,
        *,
        request: ApplySubaccountPositionTransferRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> ApplySubaccountPositionTransferResponse: ...
    @overload
    async def transfer_position(
        self,
        *,
        client_transfer_id: UUID | str,
        from_subaccount: int,
        to_subaccount: int,
        market_ticker: str,
        side: Literal["yes", "no"],
        count: int,
        price: Decimal,
        extra_headers: dict[str, str] | None = None,
    ) -> ApplySubaccountPositionTransferResponse: ...
    async def transfer_position(
        self,
        *,
        request: ApplySubaccountPositionTransferRequest | None = None,
        client_transfer_id: UUID | str | None = None,
        from_subaccount: int | None = None,
        to_subaccount: int | None = None,
        market_ticker: str | None = None,
        side: Literal["yes", "no"] | None = None,
        count: int | None = None,
        price: Decimal | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> ApplySubaccountPositionTransferResponse:
        """Move an open position between subaccounts (spec v3.23.0).

        Async counterpart of :meth:`SubaccountsResource.transfer_position`.
        """
        self._require_auth()
        body = _build_position_transfer_body(
            request,
            client_transfer_id=client_transfer_id,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            market_ticker=market_ticker,
            side=side,
            count=count,
            price=price,
        )
        data = await self._post(
            "/portfolio/subaccounts/positions/transfer", json=body, extra_headers=extra_headers
        )
        return ApplySubaccountPositionTransferResponse.model_validate(data)

    async def list_balances(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSubaccountBalancesResponse:
        self._require_auth()
        data = await self._get("/portfolio/subaccounts/balances", extra_headers=extra_headers)
        return GetSubaccountBalancesResponse.model_validate(data)

    async def list_transfers(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[SubaccountTransfer]:
        self._require_auth()
        _validate_limit(limit, hi=1000)
        params = _params(cursor=cursor, limit=limit)
        return await self._list(
            "/portfolio/subaccounts/transfers",
            SubaccountTransfer,
            "transfers",
            params=params,
            extra_headers=extra_headers,
        )

    def list_all_transfers(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[SubaccountTransfer]:
        # Plain `def` (not `async def`) so _require_auth and _validate_max_pages
        # run at call time, not when the returned AsyncIterator is awaited.
        self._require_auth()
        _validate_max_pages(max_pages)
        _validate_limit(limit, hi=1000)
        params = _params(limit=limit)
        return self._list_all(
            "/portfolio/subaccounts/transfers",
            SubaccountTransfer,
            "transfers",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @overload
    async def update_netting(
        self,
        *,
        request: UpdateSubaccountNettingRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def update_netting(
        self, *, subaccount_number: int, enabled: bool, extra_headers: dict[str, str] | None = None
    ) -> None: ...
    async def update_netting(
        self,
        *,
        request: UpdateSubaccountNettingRequest | None = None,
        subaccount_number: int | None = None,
        enabled: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        body = _build_update_netting_body(
            request,
            subaccount_number=subaccount_number,
            enabled=enabled,
        )
        await self._put("/portfolio/subaccounts/netting", json=body, extra_headers=extra_headers)

    async def get_netting(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSubaccountNettingResponse:
        self._require_auth()
        data = await self._get("/portfolio/subaccounts/netting", extra_headers=extra_headers)
        return GetSubaccountNettingResponse.model_validate(data)

    @overload
    async def lock_settlement_advance(
        self,
        *,
        request: LockSubaccountForSettlementAdvanceRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> LockSubaccountForSettlementAdvanceResponse: ...
    @overload
    async def lock_settlement_advance(
        self,
        *,
        subaccount_number: int,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LockSubaccountForSettlementAdvanceResponse: ...
    async def lock_settlement_advance(
        self,
        *,
        request: LockSubaccountForSettlementAdvanceRequest | None = None,
        subaccount_number: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LockSubaccountForSettlementAdvanceResponse:
        """Lock a subaccount for settlement-advance computation.

        Async counterpart of :meth:`SubaccountsResource.lock_settlement_advance`.
        """
        self._require_auth()
        body = _build_lock_settlement_advance_body(
            request,
            subaccount_number=subaccount_number,
            exchange_index=exchange_index,
        )
        data = await self._put(
            "/portfolio/subaccounts/settlement-advance-lock",
            json=body,
            extra_headers=extra_headers,
        )
        return LockSubaccountForSettlementAdvanceResponse.model_validate(data)

    @overload
    async def unlock_settlement_advance(
        self,
        *,
        request: UnlockSubaccountForSettlementAdvanceRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def unlock_settlement_advance(
        self,
        *,
        subaccount_number: int,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def unlock_settlement_advance(
        self,
        *,
        request: UnlockSubaccountForSettlementAdvanceRequest | None = None,
        subaccount_number: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Unlock a subaccount previously locked for settlement advance.

        Async counterpart of :meth:`SubaccountsResource.unlock_settlement_advance`.
        """
        self._require_auth()
        body = _build_unlock_settlement_advance_body(
            request,
            subaccount_number=subaccount_number,
            exchange_index=exchange_index,
        )
        await self._delete_with_body(
            "/portfolio/subaccounts/settlement-advance-lock",
            json=body,
            extra_headers=extra_headers,
        )
