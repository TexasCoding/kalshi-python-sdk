"""Orders resource — get, list, queue positions, and V2 event-market order writes.

The legacy V1 order-write endpoints (``POST/DELETE /portfolio/orders``,
``/portfolio/orders/batched``, ``/portfolio/orders/{id}/amend|decrease``) were
removed from the Kalshi OpenAPI spec in v3.22.0. Order writes now go exclusively
through the V2 ``/portfolio/events/orders`` family below. The read endpoints
(``get``, ``list``, ``queue_positions``) and ``fills`` are unchanged.
"""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from typing import Any

from typing_extensions import deprecated

from kalshi.errors import KalshiError
from kalshi.models.common import Page
from kalshi.models.orders import (
    AmendOrderV2Request,
    AmendOrderV2Response,
    BatchCancelOrdersV2Request,
    BatchCancelOrdersV2Response,
    BatchCreateOrdersV2Request,
    BatchCreateOrdersV2Response,
    CancelOrderV2Response,
    CreateOrderV2Request,
    CreateOrderV2Response,
    DecreaseOrderV2Request,
    DecreaseOrderV2Response,
    Fill,
    Order,
    OrderQueuePosition,
    OrderStatusLiteral,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _fills_params,
    _join_tickers,
    _params,
    _seg,
    _validate_limit,
    _validate_max_pages,
)
from kalshi.types import to_decimal


def _list_orders_params(
    *,
    ticker: str | None,
    event_ticker: builtins.list[str] | str | None,
    status: OrderStatusLiteral | None,
    min_ts: int | None,
    max_ts: int | None,
    limit: int | None,
    cursor: str | None,
    subaccount: int | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000)
    return _params(
        ticker=ticker,
        # Spec MultipleEventTickerQuery: comma-joined, max 10.
        event_ticker=_join_tickers(event_ticker, max_items=10),
        status=status,
        min_ts=min_ts,
        max_ts=max_ts,
        limit=limit,
        cursor=cursor,
        subaccount=subaccount,
    )


def _queue_positions_params(
    *,
    market_tickers: builtins.list[str] | str | None,
    event_ticker: str | None,
    subaccount: int | None,
) -> dict[str, Any]:
    return _params(
        market_tickers=_join_tickers(market_tickers),
        event_ticker=event_ticker,
        subaccount=subaccount,
    )


def _parse_queue_position(data: dict[str, Any]) -> Decimal:
    raw = data.get("queue_position_fp")
    if raw is None:
        raw = data.get("queue_position")
    if raw is None:
        raise KalshiError(
            "Unexpected response for queue_position: "
            f"missing 'queue_position_fp' and 'queue_position' in {data!r}"
        )
    return to_decimal(raw)


class OrdersResource(SyncResource):
    """Sync orders API."""

    def get(self, order_id: str, *, extra_headers: dict[str, str] | None = None) -> Order:
        self._require_auth()
        data = self._get(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}", extra_headers=extra_headers
        )
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    def list(
        self,
        *,
        ticker: str | None = None,
        event_ticker: builtins.list[str] | str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _list_orders_params(
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
        )
        return self._list(
            "/portfolio/orders", Order, "orders", params=params, extra_headers=extra_headers
        )

    def list_all(
        self,
        *,
        ticker: str | None = None,
        event_ticker: builtins.list[str] | str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        subaccount: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Order]:
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_orders_params(
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
            subaccount=subaccount,
        )
        return self._list_all(
            "/portfolio/orders",
            Order,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @deprecated(
        "OrdersResource.fills is deprecated; use client.portfolio.fills instead."
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
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Fill]:
        """List trade fills."""
        self._require_auth()
        params = _fills_params(
            ticker=ticker,
            order_id=order_id,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
        )
        return self._list(
            "/portfolio/fills", Fill, "fills", params=params, extra_headers=extra_headers
        )

    @deprecated(
        "OrdersResource.fills_all is deprecated; use client.portfolio.fills_all instead."
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
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Fill]:
        """Auto-paginate trade fills."""
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
        )
        return self._list_all(
            "/portfolio/fills",
            Fill,
            "fills",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    def queue_positions(
        self,
        *,
        market_tickers: builtins.list[str] | str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[OrderQueuePosition]:
        self._require_auth()
        params = _queue_positions_params(
            market_tickers=market_tickers,
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        data = self._get(
            "/portfolio/orders/queue_positions", params=params, extra_headers=extra_headers
        )
        raw = data.get("queue_positions", [])
        return [OrderQueuePosition.model_validate(item) for item in raw]

    def queue_position(
        self, order_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> Decimal:
        self._require_auth()
        data = self._get(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}/queue_position",
            extra_headers=extra_headers,
        )
        return _parse_queue_position(data)

    # ------------------------------------------------------------------
    # V2 event-market orders (spec v3.18.0, paths /portfolio/events/orders).
    # Model-only API surface — pass a fully-constructed request model.
    # ------------------------------------------------------------------

    def create_v2(
        self, *, request: CreateOrderV2Request, extra_headers: dict[str, str] | None = None
    ) -> CreateOrderV2Response:
        self._require_auth()
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post("/portfolio/events/orders", json=body, extra_headers=extra_headers)
        return CreateOrderV2Response.model_validate(data)

    def cancel_v2(
        self,
        order_id: str,
        *,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        market_ticker: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CancelOrderV2Response:
        """Cancel an event-market order (V2).

        ``market_ticker`` (spec v3.22.0) is required when ``exchange_index``
        is ``-1`` (auto-route by ticker); omit it otherwise.
        """
        self._require_auth()
        params = _params(
            subaccount=subaccount, exchange_index=exchange_index, market_ticker=market_ticker
        )
        data = self._delete(
            f"/portfolio/events/orders/{_seg(order_id, name='order_id')}",
            params=params,
            extra_headers=extra_headers,
        )
        if data is None:
            raise KalshiError("Expected CancelOrderV2Response body, got 204 No Content.")
        return CancelOrderV2Response.model_validate(data)

    def amend_v2(
        self,
        order_id: str,
        *,
        request: AmendOrderV2Request,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendOrderV2Response:
        """Amend an event-market order (V2).

        Per OpenAPI spec v3.18.0, this endpoint's ``subaccount`` is a
        **query** parameter while ``exchange_index`` lives in the request
        **body** (on ``AmendOrderV2Request``). The asymmetry mirrors the
        spec exactly — do not move ``exchange_index`` into ``params``.
        """
        self._require_auth()
        params = _params(subaccount=subaccount)
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post(
            f"/portfolio/events/orders/{_seg(order_id, name='order_id')}/amend",
            params=params,
            json=body,
            extra_headers=extra_headers,
        )
        return AmendOrderV2Response.model_validate(data)

    def decrease_v2(
        self,
        order_id: str,
        *,
        request: DecreaseOrderV2Request,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> DecreaseOrderV2Response:
        """Decrease an event-market order (V2).

        Same spec-driven asymmetry as :meth:`amend_v2`: ``subaccount`` is
        a query param; ``exchange_index`` lives on the body model. Note
        also that ``cancel_v2`` carries both as query params (no body) —
        that endpoint declares ``ExchangeIndexQuery`` in its parameters
        list, while amend/decrease declare only ``SubaccountQueryDefaultPrimary``.
        """
        self._require_auth()
        params = _params(subaccount=subaccount)
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post(
            f"/portfolio/events/orders/{_seg(order_id, name='order_id')}/decrease",
            params=params,
            json=body,
            extra_headers=extra_headers,
        )
        return DecreaseOrderV2Response.model_validate(data)

    def batch_create_v2(
        self, *, request: BatchCreateOrdersV2Request, extra_headers: dict[str, str] | None = None
    ) -> BatchCreateOrdersV2Response:
        self._require_auth()
        body = request.model_dump_json(exclude_none=True, by_alias=True).encode()
        data = self._post_json(
            "/portfolio/events/orders/batched", content=body, extra_headers=extra_headers
        )
        return BatchCreateOrdersV2Response.model_validate(data)

    def batch_cancel_v2(
        self, *, request: BatchCancelOrdersV2Request, extra_headers: dict[str, str] | None = None
    ) -> BatchCancelOrdersV2Response:
        self._require_auth()
        body = request.model_dump_json(exclude_none=True, by_alias=True).encode()
        data = self._delete_with_body_json(
            "/portfolio/events/orders/batched", content=body, extra_headers=extra_headers
        )
        if data is None:
            raise KalshiError("Expected BatchCancelOrdersV2Response body, got 204 No Content.")
        return BatchCancelOrdersV2Response.model_validate(data)


class AsyncOrdersResource(AsyncResource):
    """Async orders API."""

    async def get(self, order_id: str, *, extra_headers: dict[str, str] | None = None) -> Order:
        self._require_auth()
        data = await self._get(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}", extra_headers=extra_headers
        )
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    async def list(
        self,
        *,
        ticker: str | None = None,
        event_ticker: builtins.list[str] | str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _list_orders_params(
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
        )
        return await self._list(
            "/portfolio/orders", Order, "orders", params=params, extra_headers=extra_headers
        )

    def list_all(
        self,
        *,
        ticker: str | None = None,
        event_ticker: builtins.list[str] | str | None = None,
        status: OrderStatusLiteral | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        subaccount: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Order]:
        """Returns an async iterator — use ``async for``."""
        self._require_auth()
        _validate_max_pages(max_pages)
        params = _list_orders_params(
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=None,
            subaccount=subaccount,
        )
        return self._list_all(
            "/portfolio/orders",
            Order,
            "orders",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    @deprecated(
        "AsyncOrdersResource.fills is deprecated; use client.portfolio.fills instead."
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
        extra_headers: dict[str, str] | None = None,
    ) -> Page[Fill]:
        """List trade fills (async)."""
        self._require_auth()
        params = _fills_params(
            ticker=ticker,
            order_id=order_id,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
        )
        return await self._list(
            "/portfolio/fills", Fill, "fills", params=params, extra_headers=extra_headers
        )

    @deprecated(
        "AsyncOrdersResource.fills_all is deprecated; use client.portfolio.fills_all instead."
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
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[Fill]:
        """Auto-paginate trade fills (async). Use ``async for``."""
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
        )
        return self._list_all(
            "/portfolio/fills",
            Fill,
            "fills",
            params=params,
            max_pages=max_pages,
            extra_headers=extra_headers,
        )

    async def queue_positions(
        self,
        *,
        market_tickers: builtins.list[str] | str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[OrderQueuePosition]:
        self._require_auth()
        params = _queue_positions_params(
            market_tickers=market_tickers,
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        data = await self._get(
            "/portfolio/orders/queue_positions", params=params, extra_headers=extra_headers
        )
        raw = data.get("queue_positions", [])
        return [OrderQueuePosition.model_validate(item) for item in raw]

    async def queue_position(
        self, order_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> Decimal:
        self._require_auth()
        data = await self._get(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}/queue_position",
            extra_headers=extra_headers,
        )
        return _parse_queue_position(data)

    # V2 event-market orders (spec v3.18.0). See OrdersResource counterparts.

    async def create_v2(
        self, *, request: CreateOrderV2Request, extra_headers: dict[str, str] | None = None
    ) -> CreateOrderV2Response:
        self._require_auth()
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post("/portfolio/events/orders", json=body, extra_headers=extra_headers)
        return CreateOrderV2Response.model_validate(data)

    async def cancel_v2(
        self,
        order_id: str,
        *,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        market_ticker: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CancelOrderV2Response:
        """Cancel an event-market order (V2).

        ``market_ticker`` (spec v3.22.0) is required when ``exchange_index``
        is ``-1`` (auto-route by ticker); omit it otherwise.
        """
        self._require_auth()
        params = _params(
            subaccount=subaccount, exchange_index=exchange_index, market_ticker=market_ticker
        )
        data = await self._delete(
            f"/portfolio/events/orders/{_seg(order_id, name='order_id')}",
            params=params,
            extra_headers=extra_headers,
        )
        if data is None:
            raise KalshiError("Expected CancelOrderV2Response body, got 204 No Content.")
        return CancelOrderV2Response.model_validate(data)

    async def amend_v2(
        self,
        order_id: str,
        *,
        request: AmendOrderV2Request,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendOrderV2Response:
        """Amend an event-market order (V2).

        Per OpenAPI spec v3.18.0, this endpoint's ``subaccount`` is a
        **query** parameter while ``exchange_index`` lives in the request
        **body** (on ``AmendOrderV2Request``). The asymmetry mirrors the
        spec exactly — do not move ``exchange_index`` into ``params``.
        """
        self._require_auth()
        params = _params(subaccount=subaccount)
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post(
            f"/portfolio/events/orders/{_seg(order_id, name='order_id')}/amend",
            params=params,
            json=body,
            extra_headers=extra_headers,
        )
        return AmendOrderV2Response.model_validate(data)

    async def decrease_v2(
        self,
        order_id: str,
        *,
        request: DecreaseOrderV2Request,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> DecreaseOrderV2Response:
        """Decrease an event-market order (V2).

        Same spec-driven asymmetry as :meth:`amend_v2`: ``subaccount`` is
        a query param; ``exchange_index`` lives on the body model. Note
        also that ``cancel_v2`` carries both as query params (no body) —
        that endpoint declares ``ExchangeIndexQuery`` in its parameters
        list, while amend/decrease declare only ``SubaccountQueryDefaultPrimary``.
        """
        self._require_auth()
        params = _params(subaccount=subaccount)
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post(
            f"/portfolio/events/orders/{_seg(order_id, name='order_id')}/decrease",
            params=params,
            json=body,
            extra_headers=extra_headers,
        )
        return DecreaseOrderV2Response.model_validate(data)

    async def batch_create_v2(
        self, *, request: BatchCreateOrdersV2Request, extra_headers: dict[str, str] | None = None
    ) -> BatchCreateOrdersV2Response:
        self._require_auth()
        body = request.model_dump_json(exclude_none=True, by_alias=True).encode()
        data = await self._post_json(
            "/portfolio/events/orders/batched", content=body, extra_headers=extra_headers
        )
        return BatchCreateOrdersV2Response.model_validate(data)

    async def batch_cancel_v2(
        self, *, request: BatchCancelOrdersV2Request, extra_headers: dict[str, str] | None = None
    ) -> BatchCancelOrdersV2Response:
        self._require_auth()
        body = request.model_dump_json(exclude_none=True, by_alias=True).encode()
        data = await self._delete_with_body_json(
            "/portfolio/events/orders/batched", content=body, extra_headers=extra_headers
        )
        if data is None:
            raise KalshiError("Expected BatchCancelOrdersV2Response body, got 204 No Content.")
        return BatchCancelOrdersV2Response.model_validate(data)
