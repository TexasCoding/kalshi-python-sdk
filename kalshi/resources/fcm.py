"""FCM resource — Futures Commission Merchant endpoints.

Orders/positions filter by ``subtrader_id`` and reuse the existing Order and
PositionsResponse shapes. ``fills`` lists fills across the member's
subtraders (``min_ts`` / ``max_ts`` / ``cursor``). Subtrader admin routes
(list/create, blocked categories, event-contract daily cap) live on
``/fcm/subtraders*``.

Non-FCM accounts receive 401/403 on these routes. Demo does service them
(per Path B audit 2026-04-18) but typically returns empty lists for an
arbitrary subtrader_id.
"""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from typing import Any, overload

from kalshi.models.common import Page
from kalshi.models.fcm import (
    CreateFCMSubtraderRequest,
    CreateFCMSubtraderResponse,
    FcmFill,
    GetFCMEventContractDailyCapResponse,
    GetFcmFillsResponse,
    GetFCMSubtraderBlockedCategoriesResponse,
    ListFCMSubtradersResponse,
    UpdateFCMEventContractDailyCapRequest,
    UpdateFCMSubtraderBlockedCategoriesRequest,
    UpdateFCMSubtraderBlockedCategoriesResponse,
)
from kalshi.models.orders import Order, OrderStatusLiteral
from kalshi.models.portfolio import MarketPosition, PositionsResponse, SettlementStatusLiteral
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _params,
    _validate_limit,
    _validate_max_pages,
)
from kalshi.types import DollarDecimal

# Shared param builders (issue #46).


def _join_client_order_ids(
    ids: str | builtins.list[str] | None,
) -> str | None:
    """Serialize ``client_order_ids`` as a comma-separated string (spec max 100)."""
    if ids is None:
        return None
    parts = [p for p in ids.split(",") if p] if isinstance(ids, str) else list(ids)
    if len(parts) > 100:
        raise ValueError(
            f"client_order_ids accepts at most 100 entries per spec (got {len(parts)})"
        )
    return ",".join(parts) if parts else None


def _fcm_orders_params(
    *,
    subtrader_id: str | None,
    client_order_ids: str | builtins.list[str] | None,
    ticker: str | None,
    event_ticker: str | None,
    status: OrderStatusLiteral | None,
    min_ts: int | None,
    max_ts: int | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    joined = _join_client_order_ids(client_order_ids)
    if not subtrader_id and not joined:
        raise ValueError("fcm.orders requires subtrader_id or client_order_ids")
    limit = _validate_limit(limit, hi=1000)
    return _params(
        subtrader_id=subtrader_id,
        client_order_ids=joined,
        ticker=ticker,
        event_ticker=event_ticker,
        status=status,
        min_ts=min_ts,
        max_ts=max_ts,
        limit=limit,
        cursor=cursor,
    )


def _fcm_fills_params(
    *,
    min_ts: int | None,
    max_ts: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    return _params(min_ts=min_ts, max_ts=max_ts, cursor=cursor)


def _fcm_positions_params(
    *,
    subtrader_id: str,
    ticker: str | None,
    event_ticker: str | None,
    count_filter: str | None,
    settlement_status: SettlementStatusLiteral | None,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000)
    return _params(
        subtrader_id=subtrader_id,
        ticker=ticker,
        event_ticker=event_ticker,
        count_filter=count_filter,
        settlement_status=settlement_status,
        limit=limit,
        cursor=cursor,
    )


def _build_create_fcm_subtrader_body(
    request: CreateFCMSubtraderRequest | None,
    *,
    subtrader_suffix: str | None,
) -> dict[str, object]:
    _check_request_exclusive(request, subtrader_suffix=subtrader_suffix)
    if request is None:
        if subtrader_suffix is None:
            raise TypeError(
                "create_subtrader() requires `subtrader_suffix` (or pass `request=...`)"
            )
        request = CreateFCMSubtraderRequest(subtrader_suffix=subtrader_suffix)
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_update_blocked_categories_body(
    request: UpdateFCMSubtraderBlockedCategoriesRequest | None,
    *,
    subtrader_id: str | None,
    category: str | None,
    blocked: bool | None,
) -> dict[str, object]:
    _check_request_exclusive(request, subtrader_id=subtrader_id, category=category, blocked=blocked)
    if request is None:
        if subtrader_id is None or category is None or blocked is None:
            raise TypeError(
                "update_blocked_categories() requires `subtrader_id`, `category`, "
                "and `blocked` (or pass `request=...`)"
            )
        request = UpdateFCMSubtraderBlockedCategoriesRequest(
            subtrader_id=subtrader_id, category=category, blocked=blocked
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_update_daily_cap_body(
    request: UpdateFCMEventContractDailyCapRequest | None,
    *,
    subtrader_id: str | None,
    limit: DollarDecimal | Decimal | str | float | int | None,
) -> dict[str, object]:
    _check_request_exclusive(request, subtrader_id=subtrader_id, limit=limit)
    if request is None:
        if subtrader_id is None or limit is None:
            raise TypeError(
                "update_event_contract_daily_cap() requires `subtrader_id` and "
                "`limit` (or pass `request=...`)"
            )
        request = UpdateFCMEventContractDailyCapRequest(
            subtrader_id=subtrader_id,
            limit=limit,  # type: ignore[arg-type]
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


class FcmResource(SyncResource):
    """Sync FCM API — orders and positions filtered by subtrader_id."""

    def orders(
        self,
        *,
        subtrader_id: str | None = None,
        client_order_ids: str | builtins.list[str] | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _fcm_orders_params(
            subtrader_id=subtrader_id,
            client_order_ids=client_order_ids,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return self._list(
            "/fcm/orders", Order, "orders", params=params, extra_headers=extra_headers
        )

    def orders_all(
        self,
        *,
        subtrader_id: str | None = None,
        client_order_ids: str | builtins.list[str] | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Order]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fcm_orders_params(
            subtrader_id=subtrader_id,
            client_order_ids=client_order_ids,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/fcm/orders",
            Order,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def fills(
        self,
        *,
        min_ts: int | None = None,
        max_ts: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetFcmFillsResponse:
        """``GET /fcm/fills`` — fills across the authenticated FCM's subtraders."""
        self._require_auth()
        params = _fcm_fills_params(min_ts=min_ts, max_ts=max_ts, cursor=cursor)
        data = self._get("/fcm/fills", params=params, extra_headers=extra_headers)
        return GetFcmFillsResponse.model_validate(data)

    def fills_all(
        self,
        *,
        min_ts: int | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[FcmFill]:
        """Auto-paginate ``GET /fcm/fills``, yielding each :class:`FcmFill`."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fcm_fills_params(min_ts=min_ts, max_ts=max_ts, cursor=None)
        return self._list_all(
            "/fcm/fills",
            FcmFill,
            "fills",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def positions(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        count_filter: str | None = None,
        settlement_status: SettlementStatusLiteral | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> PositionsResponse:
        self._require_auth()
        params = _fcm_positions_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
            settlement_status=settlement_status,
            limit=limit,
            cursor=cursor,
        )
        data = self._get("/fcm/positions", params=params, extra_headers=extra_headers)
        return PositionsResponse.model_validate(data)

    def positions_all(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        count_filter: str | None = None,
        settlement_status: SettlementStatusLiteral | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[MarketPosition]:
        """Auto-paginate ``/fcm/positions``, yielding each ``MarketPosition``.

        Mirrors :meth:`PortfolioResource.positions_all`. ``event_positions``
        from the response envelope are intentionally not yielded; see that
        docstring for the rationale.
        """
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fcm_positions_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
            settlement_status=settlement_status,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/fcm/positions",
            MarketPosition,
            "market_positions",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def list_subtraders(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> ListFCMSubtradersResponse:
        """``GET /fcm/subtraders`` — list subtraders owned by the authenticated FCM."""
        self._require_auth()
        data = self._get("/fcm/subtraders", extra_headers=extra_headers)
        return ListFCMSubtradersResponse.model_validate(data)

    @overload
    def create_subtrader(
        self,
        *,
        request: CreateFCMSubtraderRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateFCMSubtraderResponse: ...
    @overload
    def create_subtrader(
        self,
        *,
        subtrader_suffix: str,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateFCMSubtraderResponse: ...
    def create_subtrader(
        self,
        *,
        request: CreateFCMSubtraderRequest | None = None,
        subtrader_suffix: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateFCMSubtraderResponse:
        """``POST /fcm/subtraders``. Not retried."""
        self._require_auth()
        body = _build_create_fcm_subtrader_body(request, subtrader_suffix=subtrader_suffix)
        data = self._post("/fcm/subtraders", json=body, extra_headers=extra_headers)
        return CreateFCMSubtraderResponse.model_validate(data)

    def blocked_categories(
        self, *, subtrader_id: str, extra_headers: dict[str, str] | None = None
    ) -> GetFCMSubtraderBlockedCategoriesResponse:
        """``GET /fcm/subtraders/blocked_categories``."""
        self._require_auth()
        params = _params(subtrader_id=subtrader_id)
        data = self._get(
            "/fcm/subtraders/blocked_categories", params=params, extra_headers=extra_headers
        )
        return GetFCMSubtraderBlockedCategoriesResponse.model_validate(data)

    @overload
    def update_blocked_categories(
        self,
        *,
        request: UpdateFCMSubtraderBlockedCategoriesRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> UpdateFCMSubtraderBlockedCategoriesResponse: ...
    @overload
    def update_blocked_categories(
        self,
        *,
        subtrader_id: str,
        category: str,
        blocked: bool,
        extra_headers: dict[str, str] | None = None,
    ) -> UpdateFCMSubtraderBlockedCategoriesResponse: ...
    def update_blocked_categories(
        self,
        *,
        request: UpdateFCMSubtraderBlockedCategoriesRequest | None = None,
        subtrader_id: str | None = None,
        category: str | None = None,
        blocked: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> UpdateFCMSubtraderBlockedCategoriesResponse:
        """``PUT /fcm/subtraders/blocked_categories``. Not retried."""
        self._require_auth()
        body = _build_update_blocked_categories_body(
            request, subtrader_id=subtrader_id, category=category, blocked=blocked
        )
        data = self._put(
            "/fcm/subtraders/blocked_categories", json=body, extra_headers=extra_headers
        )
        assert data is not None
        return UpdateFCMSubtraderBlockedCategoriesResponse.model_validate(data)

    def event_contract_daily_cap(
        self,
        *,
        subtrader_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetFCMEventContractDailyCapResponse:
        """``GET /fcm/subtraders/event_contract_daily_cap``."""
        self._require_auth()
        params = _params(subtrader_id=subtrader_id)
        data = self._get(
            "/fcm/subtraders/event_contract_daily_cap",
            params=params,
            extra_headers=extra_headers,
        )
        return GetFCMEventContractDailyCapResponse.model_validate(data)

    @overload
    def update_event_contract_daily_cap(
        self,
        *,
        request: UpdateFCMEventContractDailyCapRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    def update_event_contract_daily_cap(
        self,
        *,
        subtrader_id: str,
        limit: DollarDecimal | Decimal | str | float | int,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    def update_event_contract_daily_cap(
        self,
        *,
        request: UpdateFCMEventContractDailyCapRequest | None = None,
        subtrader_id: str | None = None,
        limit: DollarDecimal | Decimal | str | float | int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """``PUT /fcm/subtraders/event_contract_daily_cap``. Not retried."""
        self._require_auth()
        body = _build_update_daily_cap_body(request, subtrader_id=subtrader_id, limit=limit)
        self._put(
            "/fcm/subtraders/event_contract_daily_cap", json=body, extra_headers=extra_headers
        )

    def delete_event_contract_daily_cap(
        self, *, subtrader_id: str, extra_headers: dict[str, str] | None = None
    ) -> None:
        """``DELETE /fcm/subtraders/event_contract_daily_cap``. Not retried."""
        self._require_auth()
        self._delete(
            "/fcm/subtraders/event_contract_daily_cap",
            params=_params(subtrader_id=subtrader_id),
            extra_headers=extra_headers,
        )


class AsyncFcmResource(AsyncResource):
    """Async FCM API."""

    async def orders(
        self,
        *,
        subtrader_id: str | None = None,
        client_order_ids: str | builtins.list[str] | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _fcm_orders_params(
            subtrader_id=subtrader_id,
            client_order_ids=client_order_ids,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
        )
        return await self._list(
            "/fcm/orders", Order, "orders", params=params, extra_headers=extra_headers
        )

    def orders_all(
        self,
        *,
        subtrader_id: str | None = None,
        client_order_ids: str | builtins.list[str] | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Order]:
        """Returns an async iterator — use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fcm_orders_params(
            subtrader_id=subtrader_id,
            client_order_ids=client_order_ids,
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/fcm/orders",
            Order,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def fills(
        self,
        *,
        min_ts: int | None = None,
        max_ts: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetFcmFillsResponse:
        """Async :meth:`FcmResource.fills`."""
        self._require_auth()
        params = _fcm_fills_params(min_ts=min_ts, max_ts=max_ts, cursor=cursor)
        data = await self._get("/fcm/fills", params=params, extra_headers=extra_headers)
        return GetFcmFillsResponse.model_validate(data)

    def fills_all(
        self,
        *,
        min_ts: int | None = None,
        max_ts: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[FcmFill]:
        """Async counterpart of :meth:`FcmResource.fills_all`. Use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fcm_fills_params(min_ts=min_ts, max_ts=max_ts, cursor=None)
        return self._list_all(
            "/fcm/fills",
            FcmFill,
            "fills",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def positions(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        count_filter: str | None = None,
        settlement_status: SettlementStatusLiteral | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> PositionsResponse:
        self._require_auth()
        params = _fcm_positions_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
            settlement_status=settlement_status,
            limit=limit,
            cursor=cursor,
        )
        data = await self._get("/fcm/positions", params=params, extra_headers=extra_headers)
        return PositionsResponse.model_validate(data)

    def positions_all(
        self,
        *,
        subtrader_id: str,
        ticker: str | None = None,
        event_ticker: str | None = None,
        count_filter: str | None = None,
        settlement_status: SettlementStatusLiteral | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[MarketPosition]:
        """Async counterpart of :meth:`FcmResource.positions_all`. Use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _fcm_positions_params(
            subtrader_id=subtrader_id,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
            settlement_status=settlement_status,
            limit=limit,
            cursor=None,
        )
        return self._list_all(
            "/fcm/positions",
            MarketPosition,
            "market_positions",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def list_subtraders(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> ListFCMSubtradersResponse:
        """Async :meth:`FcmResource.list_subtraders`."""
        self._require_auth()
        data = await self._get("/fcm/subtraders", extra_headers=extra_headers)
        return ListFCMSubtradersResponse.model_validate(data)

    @overload
    async def create_subtrader(
        self,
        *,
        request: CreateFCMSubtraderRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateFCMSubtraderResponse: ...
    @overload
    async def create_subtrader(
        self,
        *,
        subtrader_suffix: str,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateFCMSubtraderResponse: ...
    async def create_subtrader(
        self,
        *,
        request: CreateFCMSubtraderRequest | None = None,
        subtrader_suffix: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateFCMSubtraderResponse:
        """Async :meth:`FcmResource.create_subtrader`."""
        self._require_auth()
        body = _build_create_fcm_subtrader_body(request, subtrader_suffix=subtrader_suffix)
        data = await self._post("/fcm/subtraders", json=body, extra_headers=extra_headers)
        return CreateFCMSubtraderResponse.model_validate(data)

    async def blocked_categories(
        self, *, subtrader_id: str, extra_headers: dict[str, str] | None = None
    ) -> GetFCMSubtraderBlockedCategoriesResponse:
        """Async :meth:`FcmResource.blocked_categories`."""
        self._require_auth()
        params = _params(subtrader_id=subtrader_id)
        data = await self._get(
            "/fcm/subtraders/blocked_categories", params=params, extra_headers=extra_headers
        )
        return GetFCMSubtraderBlockedCategoriesResponse.model_validate(data)

    @overload
    async def update_blocked_categories(
        self,
        *,
        request: UpdateFCMSubtraderBlockedCategoriesRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> UpdateFCMSubtraderBlockedCategoriesResponse: ...
    @overload
    async def update_blocked_categories(
        self,
        *,
        subtrader_id: str,
        category: str,
        blocked: bool,
        extra_headers: dict[str, str] | None = None,
    ) -> UpdateFCMSubtraderBlockedCategoriesResponse: ...
    async def update_blocked_categories(
        self,
        *,
        request: UpdateFCMSubtraderBlockedCategoriesRequest | None = None,
        subtrader_id: str | None = None,
        category: str | None = None,
        blocked: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> UpdateFCMSubtraderBlockedCategoriesResponse:
        """Async :meth:`FcmResource.update_blocked_categories`."""
        self._require_auth()
        body = _build_update_blocked_categories_body(
            request, subtrader_id=subtrader_id, category=category, blocked=blocked
        )
        data = await self._put(
            "/fcm/subtraders/blocked_categories", json=body, extra_headers=extra_headers
        )
        assert data is not None
        return UpdateFCMSubtraderBlockedCategoriesResponse.model_validate(data)

    async def event_contract_daily_cap(
        self,
        *,
        subtrader_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetFCMEventContractDailyCapResponse:
        """Async :meth:`FcmResource.event_contract_daily_cap`."""
        self._require_auth()
        params = _params(subtrader_id=subtrader_id)
        data = await self._get(
            "/fcm/subtraders/event_contract_daily_cap",
            params=params,
            extra_headers=extra_headers,
        )
        return GetFCMEventContractDailyCapResponse.model_validate(data)

    @overload
    async def update_event_contract_daily_cap(
        self,
        *,
        request: UpdateFCMEventContractDailyCapRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    @overload
    async def update_event_contract_daily_cap(
        self,
        *,
        subtrader_id: str,
        limit: DollarDecimal | Decimal | str | float | int,
        extra_headers: dict[str, str] | None = None,
    ) -> None: ...
    async def update_event_contract_daily_cap(
        self,
        *,
        request: UpdateFCMEventContractDailyCapRequest | None = None,
        subtrader_id: str | None = None,
        limit: DollarDecimal | Decimal | str | float | int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Async :meth:`FcmResource.update_event_contract_daily_cap`."""
        self._require_auth()
        body = _build_update_daily_cap_body(request, subtrader_id=subtrader_id, limit=limit)
        await self._put(
            "/fcm/subtraders/event_contract_daily_cap", json=body, extra_headers=extra_headers
        )

    async def delete_event_contract_daily_cap(
        self, *, subtrader_id: str, extra_headers: dict[str, str] | None = None
    ) -> None:
        """Async :meth:`FcmResource.delete_event_contract_daily_cap`."""
        self._require_auth()
        await self._delete(
            "/fcm/subtraders/event_contract_daily_cap",
            params=_params(subtrader_id=subtrader_id),
            extra_headers=extra_headers,
        )
