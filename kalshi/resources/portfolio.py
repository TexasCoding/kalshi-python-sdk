"""Portfolio resource — balance, positions, settlements."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from kalshi.models.common import Page
from kalshi.models.orders import Fill
from kalshi.models.portfolio import (
    Balance,
    Deposit,
    GetTargetBalanceAllocationResponse,
    IntraExchangeInstanceTransfer,
    MarketPosition,
    PositionsResponse,
    SetTargetBalanceAllocationRequest,
    Settlement,
    TargetBalanceAllocationInput,
    TotalRestingOrderValue,
    Withdrawal,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _fills_params,
    _params,
    _seg,
    _validate_limit,
    _validate_max_pages,
)

# Shared param builders (issue #46).


def _positions_params(
    *,
    limit: int | None,
    cursor: str | None,
    count_filter: str | None,
    ticker: str | None,
    event_ticker: str | None,
    subaccount: int | None,
    exchange_index: int | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000)
    return _params(
        limit=limit,
        cursor=cursor,
        count_filter=count_filter,
        ticker=ticker,
        event_ticker=event_ticker,
        subaccount=subaccount,
        exchange_index=exchange_index,
    )


def _settlements_params(
    *,
    limit: int | None,
    cursor: str | None,
    ticker: str | None,
    event_ticker: str | None,
    min_ts: int | None,
    max_ts: int | None,
    subaccount: int | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000)
    return _params(
        limit=limit,
        cursor=cursor,
        ticker=ticker,
        event_ticker=event_ticker,
        min_ts=min_ts,
        max_ts=max_ts,
        subaccount=subaccount,
    )

class PortfolioResource(SyncResource):
    """Sync portfolio API."""

    def balance(
        self,
        *,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Balance:
        self._require_auth()
        # Spec v3.24.0 added the optional `exchange_index` query param (target a
        # specific exchange shard; defaults to 0 server-side).
        params = _params(subaccount=subaccount, exchange_index=exchange_index)
        data = self._get("/portfolio/balance", params=params, extra_headers=extra_headers)
        return Balance.model_validate(data)

    def positions(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        count_filter: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> PositionsResponse:
        self._require_auth()
        params = _positions_params(
            limit=limit,
            cursor=cursor,
            count_filter=count_filter,
            ticker=ticker,
            event_ticker=event_ticker,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        data = self._get("/portfolio/positions", params=params, extra_headers=extra_headers)
        return PositionsResponse.model_validate(data)

    def positions_all(
        self,
        *,
        limit: int | None = None,
        count_filter: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[MarketPosition]:
        """Auto-paginate ``/portfolio/positions``, yielding each ``MarketPosition``.

        Mirrors :meth:`settlements_all`. The endpoint response also carries
        ``event_positions`` (aggregate roll-ups over the same underlying
        markets); those are *not* surfaced here because page boundaries cut
        the aggregate arbitrarily and concatenating across pages would not
        recompute a meaningful event-level total. Callers that need the
        event view should iterate :meth:`positions` page-by-page.
        """
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _positions_params(
            limit=limit,
            cursor=None,
            count_filter=count_filter,
            ticker=ticker,
            event_ticker=event_ticker,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        return self._list_all(
            "/portfolio/positions",
            MarketPosition,
            "market_positions",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def settlements(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Settlement]:
        self._require_auth()
        params = _settlements_params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            event_ticker=event_ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            subaccount=subaccount,
        )
        return self._list(
            "/portfolio/settlements",
            Settlement,
            "settlements",
            params=params,
            extra_headers=extra_headers,
        )

    def settlements_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        subaccount: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Settlement]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _settlements_params(
            limit=limit,
            cursor=None,
            ticker=ticker,
            event_ticker=event_ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            subaccount=subaccount,
        )
        return self._list_all(
            "/portfolio/settlements",
            Settlement,
            "settlements",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def fills(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Fill]:
        """List trade fills (``GET /portfolio/fills``).

        Moved from :class:`OrdersResource` in v3.0.0 (issue #351) to group
        with the rest of the ``/portfolio/*`` family (``settlements``,
        ``deposits``, ``withdrawals``).
        """
        self._require_auth()
        params = _fills_params(
            ticker=ticker,
            order_id=order_id,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        return self._list(
            "/portfolio/fills", Fill, "fills", params=params, extra_headers=extra_headers
        )

    def fills_all(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Fill]:
        """Auto-paginate trade fills. Moved from :class:`OrdersResource` in v3.0.0."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fills_params(
            ticker=ticker,
            order_id=order_id,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        return self._list_all(
            "/portfolio/fills",
            Fill,
            "fills",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def total_resting_order_value(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> TotalRestingOrderValue:
        """Total value of resting orders in cents. FCM-members only.

        Non-FCM accounts receive 403; demo mirrors prod on this route
        per Path B audit (2026-04-18).
        """
        self._require_auth()
        data = self._get(
            "/portfolio/summary/total_resting_order_value", extra_headers=extra_headers
        )
        return TotalRestingOrderValue.model_validate(data)

    def deposits(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Deposit]:
        self._require_auth()
        _validate_limit(limit, hi=500)
        params = _params(limit=limit, cursor=cursor)
        return self._list(
            "/portfolio/deposits", Deposit, "deposits", params=params, extra_headers=extra_headers
        )

    def deposits_all(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Deposit]:
        self._require_auth()
        _validate_max_pages(max_pages)
        _validate_limit(limit, hi=500)
        params = _params(limit=limit)
        return self._list_all(
            "/portfolio/deposits",
            Deposit,
            "deposits",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def withdrawals(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Withdrawal]:
        self._require_auth()
        _validate_limit(limit, hi=500)
        params = _params(limit=limit, cursor=cursor)
        return self._list(
            "/portfolio/withdrawals",
            Withdrawal,
            "withdrawals",
            params=params,
            extra_headers=extra_headers,
        )

    def withdrawals_all(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Withdrawal]:
        self._require_auth()
        _validate_max_pages(max_pages)
        _validate_limit(limit, hi=500)
        params = _params(limit=limit)
        return self._list_all(
            "/portfolio/withdrawals",
            Withdrawal,
            "withdrawals",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def intra_exchange_transfers(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[IntraExchangeInstanceTransfer]:
        """List intra-exchange instance transfer history.

        ``GET /portfolio/intra_exchange_instance_transfers``. Complements
        :meth:`~kalshi.perps.resources.transfers.TransfersResource.transfer_instance`
        (POST create on the margin product).
        """
        self._require_auth()
        _validate_limit(limit, hi=500)
        params = _params(limit=limit, cursor=cursor)
        return self._list(
            "/portfolio/intra_exchange_instance_transfers",
            IntraExchangeInstanceTransfer,
            "transfers",
            params=params,
            extra_headers=extra_headers,
        )

    def intra_exchange_transfers_all(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[IntraExchangeInstanceTransfer]:
        """Auto-paginate intra-exchange instance transfers."""
        self._require_auth()
        _validate_max_pages(max_pages)
        _validate_limit(limit, hi=500)
        params = _params(limit=limit)
        return self._list_all(
            "/portfolio/intra_exchange_instance_transfers",
            IntraExchangeInstanceTransfer,
            "transfers",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def get_intra_exchange_transfer(
        self,
        transfer_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> IntraExchangeInstanceTransfer:
        """Get a single intra-exchange instance transfer by id."""
        self._require_auth()
        data = self._get(
            f"/portfolio/intra_exchange_instance_transfers/"
            f"{_seg(transfer_id, name='transfer_id')}",
            extra_headers=extra_headers,
        )
        return IntraExchangeInstanceTransfer.model_validate(data.get("transfer", data))

    def target_balance_allocation(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetTargetBalanceAllocationResponse:
        """``GET /portfolio/target_balance_allocation`` — per-shard sweep targets."""
        self._require_auth()
        data = self._get(
            "/portfolio/target_balance_allocation", extra_headers=extra_headers
        )
        return GetTargetBalanceAllocationResponse.model_validate(data)

    def set_target_balance_allocation(
        self,
        *,
        request: SetTargetBalanceAllocationRequest | None = None,
        allocations: list[TargetBalanceAllocationInput] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """``POST /portfolio/target_balance_allocation`` — replace sweep targets.

        Not retried (POST).
        """
        self._require_auth()
        _check_request_exclusive(request, allocations=allocations)
        if request is None:
            if allocations is None:
                raise TypeError(
                    "set_target_balance_allocation() requires `allocations` "
                    "(or pass `request=...`)"
                )
            request = SetTargetBalanceAllocationRequest(allocations=allocations)
        self._post_void(
            "/portfolio/target_balance_allocation",
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )


class AsyncPortfolioResource(AsyncResource):
    """Async portfolio API."""

    async def balance(
        self,
        *,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Balance:
        self._require_auth()
        # Spec v3.24.0 added the optional `exchange_index` query param (target a
        # specific exchange shard; defaults to 0 server-side).
        params = _params(subaccount=subaccount, exchange_index=exchange_index)
        data = await self._get("/portfolio/balance", params=params, extra_headers=extra_headers)
        return Balance.model_validate(data)

    async def positions(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        count_filter: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> PositionsResponse:
        self._require_auth()
        params = _positions_params(
            limit=limit,
            cursor=cursor,
            count_filter=count_filter,
            ticker=ticker,
            event_ticker=event_ticker,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        data = await self._get("/portfolio/positions", params=params, extra_headers=extra_headers)
        return PositionsResponse.model_validate(data)

    def positions_all(
        self,
        *,
        limit: int | None = None,
        count_filter: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[MarketPosition]:
        """Async counterpart of :meth:`PortfolioResource.positions_all`. Use ``async for``.

        Mirrors :meth:`settlements_all`. The endpoint response also carries
        ``event_positions`` (aggregate roll-ups over the same underlying
        markets); those are *not* surfaced here because page boundaries cut
        the aggregate arbitrarily and concatenating across pages would not
        recompute a meaningful event-level total. Callers that need the
        event view should iterate :meth:`positions` page-by-page.
        """
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _positions_params(
            limit=limit,
            cursor=None,
            count_filter=count_filter,
            ticker=ticker,
            event_ticker=event_ticker,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        return self._list_all(
            "/portfolio/positions",
            MarketPosition,
            "market_positions",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def settlements(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Settlement]:
        self._require_auth()
        params = _settlements_params(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            event_ticker=event_ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            subaccount=subaccount,
        )
        return await self._list(
            "/portfolio/settlements",
            Settlement,
            "settlements",
            params=params,
            extra_headers=extra_headers,
        )

    def settlements_all(
        self,
        *,
        limit: int | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        subaccount: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Settlement]:
        """Returns an async iterator — use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _settlements_params(
            limit=limit,
            cursor=None,
            ticker=ticker,
            event_ticker=event_ticker,
            min_ts=min_ts,
            max_ts=max_ts,
            subaccount=subaccount,
        )
        return self._list_all(
            "/portfolio/settlements",
            Settlement,
            "settlements",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def fills(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Fill]:
        """List trade fills (``GET /portfolio/fills``, async).

        Moved from :class:`AsyncOrdersResource` in v3.0.0 (issue #351).
        """
        self._require_auth()
        params = _fills_params(
            ticker=ticker,
            order_id=order_id,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        return await self._list(
            "/portfolio/fills", Fill, "fills", params=params, extra_headers=extra_headers
        )

    def fills_all(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Fill]:
        """Auto-paginate trade fills (async). Use ``async for``.

        Moved from :class:`AsyncOrdersResource` in v3.0.0 (issue #351).
        """
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fills_params(
            ticker=ticker,
            order_id=order_id,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        return self._list_all(
            "/portfolio/fills",
            Fill,
            "fills",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def total_resting_order_value(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> TotalRestingOrderValue:
        """Total value of resting orders in cents. FCM-members only.

        Non-FCM accounts receive 403; demo mirrors prod on this route
        per Path B audit (2026-04-18).
        """
        self._require_auth()
        data = await self._get(
            "/portfolio/summary/total_resting_order_value", extra_headers=extra_headers
        )
        return TotalRestingOrderValue.model_validate(data)

    async def deposits(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Deposit]:
        self._require_auth()
        _validate_limit(limit, hi=500)
        params = _params(limit=limit, cursor=cursor)
        return await self._list(
            "/portfolio/deposits", Deposit, "deposits", params=params, extra_headers=extra_headers
        )

    def deposits_all(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Deposit]:
        """Returns an async iterator — use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        _validate_limit(limit, hi=500)
        params = _params(limit=limit)
        return self._list_all(
            "/portfolio/deposits",
            Deposit,
            "deposits",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def withdrawals(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Withdrawal]:
        self._require_auth()
        _validate_limit(limit, hi=500)
        params = _params(limit=limit, cursor=cursor)
        return await self._list(
            "/portfolio/withdrawals",
            Withdrawal,
            "withdrawals",
            params=params,
            extra_headers=extra_headers,
        )

    def withdrawals_all(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Withdrawal]:
        """Returns an async iterator — use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        _validate_limit(limit, hi=500)
        params = _params(limit=limit)
        return self._list_all(
            "/portfolio/withdrawals",
            Withdrawal,
            "withdrawals",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def intra_exchange_transfers(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[IntraExchangeInstanceTransfer]:
        """List intra-exchange instance transfer history (async)."""
        self._require_auth()
        _validate_limit(limit, hi=500)
        params = _params(limit=limit, cursor=cursor)
        return await self._list(
            "/portfolio/intra_exchange_instance_transfers",
            IntraExchangeInstanceTransfer,
            "transfers",
            params=params,
            extra_headers=extra_headers,
        )

    def intra_exchange_transfers_all(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[IntraExchangeInstanceTransfer]:
        """Auto-paginate intra-exchange instance transfers (async)."""
        self._require_auth()
        _validate_max_pages(max_pages)
        _validate_limit(limit, hi=500)
        params = _params(limit=limit)
        return self._list_all(
            "/portfolio/intra_exchange_instance_transfers",
            IntraExchangeInstanceTransfer,
            "transfers",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def get_intra_exchange_transfer(
        self,
        transfer_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> IntraExchangeInstanceTransfer:
        """Get a single intra-exchange instance transfer by id (async)."""
        self._require_auth()
        data = await self._get(
            f"/portfolio/intra_exchange_instance_transfers/"
            f"{_seg(transfer_id, name='transfer_id')}",
            extra_headers=extra_headers,
        )
        return IntraExchangeInstanceTransfer.model_validate(data.get("transfer", data))

    async def target_balance_allocation(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetTargetBalanceAllocationResponse:
        """Async :meth:`PortfolioResource.target_balance_allocation`."""
        self._require_auth()
        data = await self._get(
            "/portfolio/target_balance_allocation", extra_headers=extra_headers
        )
        return GetTargetBalanceAllocationResponse.model_validate(data)

    async def set_target_balance_allocation(
        self,
        *,
        request: SetTargetBalanceAllocationRequest | None = None,
        allocations: list[TargetBalanceAllocationInput] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Async :meth:`PortfolioResource.set_target_balance_allocation`."""
        self._require_auth()
        _check_request_exclusive(request, allocations=allocations)
        if request is None:
            if allocations is None:
                raise TypeError(
                    "set_target_balance_allocation() requires `allocations` "
                    "(or pass `request=...`)"
                )
            request = SetTargetBalanceAllocationRequest(allocations=allocations)
        await self._post_void(
            "/portfolio/target_balance_allocation",
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
