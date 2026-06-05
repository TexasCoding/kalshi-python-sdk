"""Perps transfers & subaccounts resource (#396).

Three authenticated POST endpoints on the perps ``/portfolio/*`` host:

- ``transfer_instance`` — ``POST /portfolio/intra_exchange_instance_transfer``
  (move funds between the ``event_contract`` and ``margined`` instances). The
  spec marks this endpoint **"currently not available"**; it is implemented for
  forward compatibility and may return an error until the server enables it.
- ``create_subaccount`` — ``POST /portfolio/margin/subaccounts`` (no request
  body; returns the new subaccount number, HTTP 201). Max 32 subaccounts/user,
  numbered sequentially from 1.
- ``transfer_subaccount`` — ``POST /portfolio/margin/subaccounts/transfer``
  (move funds between subaccounts ``0``-``32``; returns an empty body -> ``None``).

All three require RSA-PSS auth and are guarded client-side with
``_require_auth()`` so an unauthenticated caller gets ``AuthRequiredError``
instead of a server 401. POST is never retried.
"""

from __future__ import annotations

from typing import Any, overload
from uuid import UUID

from kalshi.perps.models.transfers import (
    ApplySubaccountTransferRequest,
    CreateSubaccountResponse,
    ExchangeInstanceLiteral,
    IntraExchangeInstanceTransferRequest,
    IntraExchangeInstanceTransferResponse,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
)

# Shared module-level body builders (mirror the event-contract `_build_*_body`).


def _build_instance_transfer_body(
    request: IntraExchangeInstanceTransferRequest | None,
    *,
    source: ExchangeInstanceLiteral | None,
    destination: ExchangeInstanceLiteral | None,
    amount: int | None,
    source_exchange_shard: int | None,
    destination_exchange_shard: int | None,
) -> dict[str, Any]:
    # Shards are part of the kwargs path — included in the exclusivity check so
    # `request=...` together with an explicit shard raises instead of silently
    # dropping the shard. They default to 0 only when building from kwargs.
    _check_request_exclusive(
        request,
        source=source,
        destination=destination,
        amount=amount,
        source_exchange_shard=source_exchange_shard,
        destination_exchange_shard=destination_exchange_shard,
    )
    if request is None:
        if source is None or destination is None or amount is None:
            raise TypeError(
                "transfer_instance() requires `source`, `destination`, and "
                "`amount` (or pass `request=...`)"
            )
        request = IntraExchangeInstanceTransferRequest(
            source=source,
            destination=destination,
            amount=amount,
            source_exchange_shard=source_exchange_shard or 0,
            destination_exchange_shard=destination_exchange_shard or 0,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_subaccount_transfer_body(
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
                "transfer_subaccount() requires `client_transfer_id`, "
                "`from_subaccount`, `to_subaccount`, and `amount_cents` "
                "(or pass `request=...`)"
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


class TransfersResource(SyncResource):
    """Sync perps transfers & subaccounts API."""

    @overload
    def transfer_instance(
        self,
        *,
        request: IntraExchangeInstanceTransferRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> IntraExchangeInstanceTransferResponse: ...
    @overload
    def transfer_instance(
        self,
        *,
        source: ExchangeInstanceLiteral,
        destination: ExchangeInstanceLiteral,
        amount: int,
        source_exchange_shard: int = 0,
        destination_exchange_shard: int = 0,
        extra_headers: dict[str, str] | None = None,
    ) -> IntraExchangeInstanceTransferResponse: ...
    def transfer_instance(
        self,
        *,
        request: IntraExchangeInstanceTransferRequest | None = None,
        source: ExchangeInstanceLiteral | None = None,
        destination: ExchangeInstanceLiteral | None = None,
        amount: int | None = None,
        source_exchange_shard: int | None = None,
        destination_exchange_shard: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> IntraExchangeInstanceTransferResponse:
        """Move funds between exchange instances.

        Spec marks this endpoint "currently not available" — it is implemented
        forward-compatibly and may return an error until the server enables it.
        """
        self._require_auth()
        body = _build_instance_transfer_body(
            request,
            source=source,
            destination=destination,
            amount=amount,
            source_exchange_shard=source_exchange_shard,
            destination_exchange_shard=destination_exchange_shard,
        )
        data = self._post(
            "/portfolio/intra_exchange_instance_transfer",
            json=body,
            extra_headers=extra_headers,
        )
        return IntraExchangeInstanceTransferResponse.model_validate(data)

    def create_subaccount(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> CreateSubaccountResponse:
        """Create a new margin subaccount (returns its sequential number)."""
        self._require_auth()
        # Spec defines no requestBody, but httpx omits Content-Type when no body
        # is passed and demo rejects the POST with `invalid_content_type`.
        # json={} forces Content-Type: application/json — same workaround as the
        # event-contract SubaccountsResource.create. Response is HTTP 201.
        data = self._post("/portfolio/margin/subaccounts", json={}, extra_headers=extra_headers)
        return CreateSubaccountResponse.model_validate(data)

    @overload
    def transfer_subaccount(
        self,
        *,
        request: ApplySubaccountTransferRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def transfer_subaccount(
        self,
        *,
        client_transfer_id: UUID | str,
        from_subaccount: int,
        to_subaccount: int,
        amount_cents: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def transfer_subaccount(
        self,
        *,
        request: ApplySubaccountTransferRequest | None = None,
        client_transfer_id: UUID | str | None = None,
        from_subaccount: int | None = None,
        to_subaccount: int | None = None,
        amount_cents: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Move funds between margin subaccounts (returns ``None``)."""
        self._require_auth()
        body = _build_subaccount_transfer_body(
            request,
            client_transfer_id=client_transfer_id,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            amount_cents=amount_cents,
        )
        self._post(
            "/portfolio/margin/subaccounts/transfer",
            json=body,
            extra_headers=extra_headers,
        )


class AsyncTransfersResource(AsyncResource):
    """Async perps transfers & subaccounts API."""

    @overload
    async def transfer_instance(
        self,
        *,
        request: IntraExchangeInstanceTransferRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> IntraExchangeInstanceTransferResponse: ...
    @overload
    async def transfer_instance(
        self,
        *,
        source: ExchangeInstanceLiteral,
        destination: ExchangeInstanceLiteral,
        amount: int,
        source_exchange_shard: int = 0,
        destination_exchange_shard: int = 0,
        extra_headers: dict[str, str] | None = None,
    ) -> IntraExchangeInstanceTransferResponse: ...
    async def transfer_instance(
        self,
        *,
        request: IntraExchangeInstanceTransferRequest | None = None,
        source: ExchangeInstanceLiteral | None = None,
        destination: ExchangeInstanceLiteral | None = None,
        amount: int | None = None,
        source_exchange_shard: int | None = None,
        destination_exchange_shard: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> IntraExchangeInstanceTransferResponse:
        """Move funds between exchange instances.

        Spec marks this endpoint "currently not available" — it is implemented
        forward-compatibly and may return an error until the server enables it.
        """
        self._require_auth()
        body = _build_instance_transfer_body(
            request,
            source=source,
            destination=destination,
            amount=amount,
            source_exchange_shard=source_exchange_shard,
            destination_exchange_shard=destination_exchange_shard,
        )
        data = await self._post(
            "/portfolio/intra_exchange_instance_transfer",
            json=body,
            extra_headers=extra_headers,
        )
        return IntraExchangeInstanceTransferResponse.model_validate(data)

    async def create_subaccount(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> CreateSubaccountResponse:
        """Create a new margin subaccount (returns its sequential number)."""
        self._require_auth()
        # json={} forces Content-Type: application/json — demo rejects the
        # bodyless POST with `invalid_content_type`. Response is HTTP 201.
        data = await self._post(
            "/portfolio/margin/subaccounts", json={}, extra_headers=extra_headers
        )
        return CreateSubaccountResponse.model_validate(data)

    @overload
    async def transfer_subaccount(
        self,
        *,
        request: ApplySubaccountTransferRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def transfer_subaccount(
        self,
        *,
        client_transfer_id: UUID | str,
        from_subaccount: int,
        to_subaccount: int,
        amount_cents: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def transfer_subaccount(
        self,
        *,
        request: ApplySubaccountTransferRequest | None = None,
        client_transfer_id: UUID | str | None = None,
        from_subaccount: int | None = None,
        to_subaccount: int | None = None,
        amount_cents: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Move funds between margin subaccounts (returns ``None``)."""
        self._require_auth()
        body = _build_subaccount_transfer_body(
            request,
            client_transfer_id=client_transfer_id,
            from_subaccount=from_subaccount,
            to_subaccount=to_subaccount,
            amount_cents=amount_cents,
        )
        await self._post(
            "/portfolio/margin/subaccounts/transfer",
            json=body,
            extra_headers=extra_headers,
        )
