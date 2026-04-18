"""Orders resource — create, get, cancel, list, batch operations."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from typing import Any

from kalshi.errors import KalshiError
from kalshi.models.common import Page
from kalshi.models.orders import (
    AmendOrderRequest,
    AmendOrderResponse,
    BatchCancelOrdersRequest,
    BatchCancelOrdersRequestOrder,
    BatchCreateOrdersRequest,
    CreateOrderRequest,
    DecreaseOrderRequest,
    Fill,
    Order,
    OrderQueuePosition,
)
from kalshi.resources._base import AsyncResource, SyncResource, _join_tickers, _params
from kalshi.types import to_decimal


class OrdersResource(SyncResource):
    """Sync orders API."""

    def create(
        self,
        *,
        ticker: str,
        side: str,
        action: str = "buy",
        count: int = 1,
        yes_price: float | str | int | None = None,
        no_price: float | str | int | None = None,
        client_order_id: str | None = None,
        expiration_ts: int | None = None,
        buy_max_cost: int | None = None,
        time_in_force: str | None = None,
        post_only: bool | None = None,
        reduce_only: bool | None = None,
        self_trade_prevention_type: str | None = None,
        order_group_id: str | None = None,
        cancel_order_on_pause: bool | None = None,
        subaccount: int | None = None,
    ) -> Order:
        """Place a new order.

        ``buy_max_cost`` is integer cents per OpenAPI spec (e.g., 500 for $5.00).

        ``time_in_force`` accepts ``"fill_or_kill"``, ``"good_till_canceled"``,
        ``"immediate_or_cancel"``. Passing ``None`` omits the field and lets
        Kalshi apply its server-side default (``good_till_canceled``).

        v0.8.0 removed the ``type`` kwarg: the field was never defined in
        the OpenAPI spec. Callers passing ``type="limit"`` now get a
        ``TypeError``.
        """
        self._require_auth()
        req = CreateOrderRequest(
            ticker=ticker,
            side=side,
            action=action,
            count=to_decimal(count),
            yes_price=to_decimal(yes_price) if yes_price is not None else None,
            no_price=to_decimal(no_price) if no_price is not None else None,
            client_order_id=client_order_id,
            expiration_ts=expiration_ts,
            buy_max_cost=buy_max_cost,
            time_in_force=time_in_force,
            post_only=post_only,
            reduce_only=reduce_only,
            self_trade_prevention_type=self_trade_prevention_type,
            order_group_id=order_group_id,
            cancel_order_on_pause=cancel_order_on_pause,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post("/portfolio/orders", json=body)
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    def get(self, order_id: str) -> Order:
        self._require_auth()
        data = self._get(f"/portfolio/orders/{order_id}")
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    def cancel(self, order_id: str, *, subaccount: int | None = None) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        self._delete(f"/portfolio/orders/{order_id}", params=params)

    def list(
        self,
        *,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        subaccount: int | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _params(
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
        )
        return self._list("/portfolio/orders", Order, "orders", params=params)

    def list_all(
        self,
        *,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        subaccount: int | None = None,
    ) -> Iterator[Order]:
        self._require_auth()
        params = _params(
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            subaccount=subaccount,
        )
        return self._list_all("/portfolio/orders", Order, "orders", params=params)

    def batch_create(
        self, orders: builtins.list[CreateOrderRequest],
    ) -> builtins.list[Order]:
        self._require_auth()
        req = BatchCreateOrdersRequest(orders=list(orders))
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post("/portfolio/orders/batched", json=body)
        raw_orders = data.get("orders", [])
        return [Order.model_validate(o.get("order", o)) for o in raw_orders]

    def batch_cancel(
        self,
        orders: builtins.list[BatchCancelOrdersRequestOrder] | builtins.list[str],
    ) -> None:
        """Batch-cancel orders.

        Accepts either:
        - ``list[BatchCancelOrdersRequestOrder]`` for full control including
          per-order ``subaccount`` routing;
        - ``list[str]`` of order IDs as a convenience shortcut — internally
          each ID is wrapped as ``BatchCancelOrdersRequestOrder(order_id=id)``.

        BREAKING in v0.8.0: previously the method signature was
        ``batch_cancel(order_ids: list[str])`` and the wire body used the
        spec-deprecated ``ids`` field. v0.8.0 emits the spec-preferred
        ``orders`` field and renames the kwarg. Callers passing a plain
        list of order-id strings still work without code changes via the
        convenience shortcut.
        """
        self._require_auth()
        normalized = [
            (
                BatchCancelOrdersRequestOrder(order_id=o) if isinstance(o, str) else o
            )
            for o in orders
        ]
        req = BatchCancelOrdersRequest(orders=normalized)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        self._delete_with_body("/portfolio/orders/batched", json=body)

    def _delete_with_body(self, path: str, *, json: dict[str, Any]) -> None:
        """DELETE with a request body (batch cancel)."""
        self._transport.request("DELETE", path, json=json)

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
    ) -> Page[Fill]:
        self._require_auth()
        params = _params(
            ticker=ticker,
            order_id=order_id,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
        )
        return self._list("/portfolio/fills", Fill, "fills", params=params)

    def fills_all(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        subaccount: int | None = None,
    ) -> Iterator[Fill]:
        self._require_auth()
        params = _params(
            ticker=ticker,
            order_id=order_id,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            subaccount=subaccount,
        )
        return self._list_all("/portfolio/fills", Fill, "fills", params=params)

    def amend(
        self,
        order_id: str,
        *,
        ticker: str,
        side: str,
        action: str,
        yes_price: float | str | int | None = None,
        no_price: float | str | int | None = None,
        count: int | None = None,
        client_order_id: str | None = None,
        updated_client_order_id: str | None = None,
        subaccount: int | None = None,
    ) -> AmendOrderResponse:
        self._require_auth()
        if yes_price is None and no_price is None and count is None:
            raise ValueError("amend() requires at least one of yes_price, no_price, or count")
        req = AmendOrderRequest(
            ticker=ticker,
            side=side,
            action=action,
            yes_price=to_decimal(yes_price) if yes_price is not None else None,
            no_price=to_decimal(no_price) if no_price is not None else None,
            count=to_decimal(count) if count is not None else None,
            client_order_id=client_order_id,
            updated_client_order_id=updated_client_order_id,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post(f"/portfolio/orders/{order_id}/amend", json=body)
        return AmendOrderResponse.model_validate(data)

    def decrease(
        self,
        order_id: str,
        *,
        reduce_by: int | None = None,
        reduce_to: int | None = None,
        subaccount: int | None = None,
    ) -> Order:
        self._require_auth()
        if reduce_by is None and reduce_to is None:
            raise ValueError("decrease() requires either reduce_by or reduce_to")
        if reduce_by is not None and reduce_to is not None:
            raise ValueError("decrease() accepts reduce_by or reduce_to, not both")
        req = DecreaseOrderRequest(
            reduce_by=reduce_by,
            reduce_to=reduce_to,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post(f"/portfolio/orders/{order_id}/decrease", json=body)
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    def queue_positions(
        self,
        *,
        market_tickers: builtins.list[str] | str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
    ) -> builtins.list[OrderQueuePosition]:
        self._require_auth()
        params = _params(
            market_tickers=_join_tickers(market_tickers),
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        data = self._get("/portfolio/orders/queue_positions", params=params)
        raw = data.get("queue_positions", [])
        return [OrderQueuePosition.model_validate(item) for item in raw]

    def queue_position(self, order_id: str) -> Decimal:
        self._require_auth()
        data = self._get(f"/portfolio/orders/{order_id}/queue_position")
        raw = data.get("queue_position_fp")
        if raw is None:
            raw = data.get("queue_position")
        if raw is None:
            raise KalshiError(
                "Unexpected response for queue_position: "
                f"missing 'queue_position_fp' and 'queue_position' in {data!r}"
            )
        return to_decimal(raw)


class AsyncOrdersResource(AsyncResource):
    """Async orders API."""

    async def create(
        self,
        *,
        ticker: str,
        side: str,
        action: str = "buy",
        count: int = 1,
        yes_price: float | str | int | None = None,
        no_price: float | str | int | None = None,
        client_order_id: str | None = None,
        expiration_ts: int | None = None,
        buy_max_cost: int | None = None,
        time_in_force: str | None = None,
        post_only: bool | None = None,
        reduce_only: bool | None = None,
        self_trade_prevention_type: str | None = None,
        order_group_id: str | None = None,
        cancel_order_on_pause: bool | None = None,
        subaccount: int | None = None,
    ) -> Order:
        """Place a new order.

        ``buy_max_cost`` is integer cents per OpenAPI spec (e.g., 500 for $5.00).

        ``time_in_force`` accepts ``"fill_or_kill"``, ``"good_till_canceled"``,
        ``"immediate_or_cancel"``. Passing ``None`` omits the field and lets
        Kalshi apply its server-side default (``good_till_canceled``).

        v0.8.0 removed the ``type`` kwarg: the field was never defined in
        the OpenAPI spec. Callers passing ``type="limit"`` now get a
        ``TypeError``.
        """
        self._require_auth()
        req = CreateOrderRequest(
            ticker=ticker,
            side=side,
            action=action,
            count=to_decimal(count),
            yes_price=to_decimal(yes_price) if yes_price is not None else None,
            no_price=to_decimal(no_price) if no_price is not None else None,
            client_order_id=client_order_id,
            expiration_ts=expiration_ts,
            buy_max_cost=buy_max_cost,
            time_in_force=time_in_force,
            post_only=post_only,
            reduce_only=reduce_only,
            self_trade_prevention_type=self_trade_prevention_type,
            order_group_id=order_group_id,
            cancel_order_on_pause=cancel_order_on_pause,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post("/portfolio/orders", json=body)
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    async def get(self, order_id: str) -> Order:
        self._require_auth()
        data = await self._get(f"/portfolio/orders/{order_id}")
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    async def cancel(self, order_id: str, *, subaccount: int | None = None) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount)
        await self._delete(f"/portfolio/orders/{order_id}", params=params)

    async def list(
        self,
        *,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        subaccount: int | None = None,
    ) -> Page[Order]:
        self._require_auth()
        params = _params(
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
        )
        return await self._list("/portfolio/orders", Order, "orders", params=params)

    def list_all(
        self,
        *,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        subaccount: int | None = None,
    ) -> AsyncIterator[Order]:
        """Non-async method that returns an async iterator for direct use with `async for`."""
        self._require_auth()
        params = _params(
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            subaccount=subaccount,
        )
        return self._list_all("/portfolio/orders", Order, "orders", params=params)

    async def batch_create(
        self, orders: builtins.list[CreateOrderRequest],
    ) -> builtins.list[Order]:
        self._require_auth()
        req = BatchCreateOrdersRequest(orders=list(orders))
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post("/portfolio/orders/batched", json=body)
        raw_orders = data.get("orders", [])
        return [Order.model_validate(o.get("order", o)) for o in raw_orders]

    async def batch_cancel(
        self,
        orders: builtins.list[BatchCancelOrdersRequestOrder] | builtins.list[str],
    ) -> None:
        """Batch-cancel orders.

        Accepts either:
        - ``list[BatchCancelOrdersRequestOrder]`` for full control including
          per-order ``subaccount`` routing;
        - ``list[str]`` of order IDs as a convenience shortcut — internally
          each ID is wrapped as ``BatchCancelOrdersRequestOrder(order_id=id)``.

        BREAKING in v0.8.0: previously the method signature was
        ``batch_cancel(order_ids: list[str])`` and the wire body used the
        spec-deprecated ``ids`` field. v0.8.0 emits the spec-preferred
        ``orders`` field and renames the kwarg. Callers passing a plain
        list of order-id strings still work without code changes via the
        convenience shortcut.
        """
        self._require_auth()
        normalized = [
            (
                BatchCancelOrdersRequestOrder(order_id=o) if isinstance(o, str) else o
            )
            for o in orders
        ]
        req = BatchCancelOrdersRequest(orders=normalized)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        await self._transport.request("DELETE", "/portfolio/orders/batched", json=body)

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
    ) -> Page[Fill]:
        self._require_auth()
        params = _params(
            ticker=ticker,
            order_id=order_id,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            cursor=cursor,
            subaccount=subaccount,
        )
        return await self._list("/portfolio/fills", Fill, "fills", params=params)

    def fills_all(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        subaccount: int | None = None,
    ) -> AsyncIterator[Fill]:
        self._require_auth()
        params = _params(
            ticker=ticker,
            order_id=order_id,
            min_ts=min_ts,
            max_ts=max_ts,
            limit=limit,
            subaccount=subaccount,
        )
        return self._list_all("/portfolio/fills", Fill, "fills", params=params)

    async def amend(
        self,
        order_id: str,
        *,
        ticker: str,
        side: str,
        action: str,
        yes_price: float | str | int | None = None,
        no_price: float | str | int | None = None,
        count: int | None = None,
        client_order_id: str | None = None,
        updated_client_order_id: str | None = None,
        subaccount: int | None = None,
    ) -> AmendOrderResponse:
        self._require_auth()
        if yes_price is None and no_price is None and count is None:
            raise ValueError("amend() requires at least one of yes_price, no_price, or count")
        req = AmendOrderRequest(
            ticker=ticker,
            side=side,
            action=action,
            yes_price=to_decimal(yes_price) if yes_price is not None else None,
            no_price=to_decimal(no_price) if no_price is not None else None,
            count=to_decimal(count) if count is not None else None,
            client_order_id=client_order_id,
            updated_client_order_id=updated_client_order_id,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post(f"/portfolio/orders/{order_id}/amend", json=body)
        return AmendOrderResponse.model_validate(data)

    async def decrease(
        self,
        order_id: str,
        *,
        reduce_by: int | None = None,
        reduce_to: int | None = None,
        subaccount: int | None = None,
    ) -> Order:
        self._require_auth()
        if reduce_by is None and reduce_to is None:
            raise ValueError("decrease() requires either reduce_by or reduce_to")
        if reduce_by is not None and reduce_to is not None:
            raise ValueError("decrease() accepts reduce_by or reduce_to, not both")
        req = DecreaseOrderRequest(
            reduce_by=reduce_by,
            reduce_to=reduce_to,
            subaccount=subaccount,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post(f"/portfolio/orders/{order_id}/decrease", json=body)
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    async def queue_positions(
        self,
        *,
        market_tickers: builtins.list[str] | str | None = None,
        event_ticker: str | None = None,
        subaccount: int | None = None,
    ) -> builtins.list[OrderQueuePosition]:
        self._require_auth()
        params = _params(
            market_tickers=_join_tickers(market_tickers),
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        data = await self._get("/portfolio/orders/queue_positions", params=params)
        raw = data.get("queue_positions", [])
        return [OrderQueuePosition.model_validate(item) for item in raw]

    async def queue_position(self, order_id: str) -> Decimal:
        self._require_auth()
        data = await self._get(f"/portfolio/orders/{order_id}/queue_position")
        raw = data.get("queue_position_fp")
        if raw is None:
            raw = data.get("queue_position")
        if raw is None:
            raise KalshiError(
                "Unexpected response for queue_position: "
                f"missing 'queue_position_fp' and 'queue_position' in {data!r}"
            )
        return to_decimal(raw)
