"""Orders resource — create, get, cancel, list, batch operations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from kalshi.models.common import Page
from kalshi.models.orders import CreateOrderRequest, Fill, Order
from kalshi.resources._base import AsyncResource, SyncResource
from kalshi.types import to_decimal


class OrdersResource(SyncResource):
    """Sync orders API."""

    def create(
        self,
        *,
        ticker: str,
        side: str,
        type: str = "limit",
        action: str = "buy",
        count: int = 1,
        yes_price: float | str | int | None = None,
        no_price: float | str | int | None = None,
        client_order_id: str | None = None,
        expiration_ts: int | None = None,
    ) -> Order:
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "type": type,
            "action": action,
            "count": count,
        }
        if yes_price is not None:
            body["yes_price"] = str(to_decimal(yes_price))
        if no_price is not None:
            body["no_price"] = str(to_decimal(no_price))
        if client_order_id:
            body["client_order_id"] = client_order_id
        if expiration_ts is not None:
            body["expiration_ts"] = expiration_ts

        data = self._post("/portfolio/orders", json=body)
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    def get(self, order_id: str) -> Order:
        data = self._get(f"/portfolio/orders/{order_id}")
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    def cancel(self, order_id: str) -> None:
        self._delete(f"/portfolio/orders/{order_id}")

    def list(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Order]:
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        if limit is not None:
            params["limit"] = limit
        if cursor:
            params["cursor"] = cursor
        return self._list("/portfolio/orders", Order, "orders", params=params)

    def list_all(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> Iterator[Order]:
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        if limit is not None:
            params["limit"] = limit
        return self._list_all("/portfolio/orders", Order, "orders", params=params)

    def batch_create(self, orders: list[CreateOrderRequest]) -> list[Order]:
        body = {"orders": [o.model_dump(exclude_none=True) for o in orders]}
        data = self._post("/portfolio/orders/batched", json=body)
        raw_orders = data.get("orders", [])
        return [Order.model_validate(o) for o in raw_orders]

    def batch_cancel(self, order_ids: list[str]) -> None:
        body = {"ids": order_ids}
        self._delete_with_body("/portfolio/orders/batched", json=body)

    def _delete_with_body(self, path: str, *, json: dict[str, Any]) -> None:
        """DELETE with a request body (batch cancel)."""
        self._transport.request("DELETE", path, json=json)

    def fills(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Fill]:
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if order_id:
            params["order_id"] = order_id
        if limit is not None:
            params["limit"] = limit
        if cursor:
            params["cursor"] = cursor
        return self._list("/portfolio/fills", Fill, "fills", params=params)


class AsyncOrdersResource(AsyncResource):
    """Async orders API."""

    async def create(
        self,
        *,
        ticker: str,
        side: str,
        type: str = "limit",
        action: str = "buy",
        count: int = 1,
        yes_price: float | str | int | None = None,
        no_price: float | str | int | None = None,
        client_order_id: str | None = None,
        expiration_ts: int | None = None,
    ) -> Order:
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "type": type,
            "action": action,
            "count": count,
        }
        if yes_price is not None:
            body["yes_price"] = str(to_decimal(yes_price))
        if no_price is not None:
            body["no_price"] = str(to_decimal(no_price))
        if client_order_id:
            body["client_order_id"] = client_order_id
        if expiration_ts is not None:
            body["expiration_ts"] = expiration_ts

        data = await self._post("/portfolio/orders", json=body)
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    async def get(self, order_id: str) -> Order:
        data = await self._get(f"/portfolio/orders/{order_id}")
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    async def cancel(self, order_id: str) -> None:
        await self._delete(f"/portfolio/orders/{order_id}")

    async def list(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Order]:
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        if limit is not None:
            params["limit"] = limit
        if cursor:
            params["cursor"] = cursor
        return await self._list("/portfolio/orders", Order, "orders", params=params)

    def list_all(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Order]:
        """Non-async method that returns an async iterator for direct use with `async for`."""
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        if limit is not None:
            params["limit"] = limit
        return self._list_all("/portfolio/orders", Order, "orders", params=params)

    async def batch_create(self, orders: list[CreateOrderRequest]) -> list[Order]:
        body = {"orders": [o.model_dump(exclude_none=True) for o in orders]}
        data = await self._post("/portfolio/orders/batched", json=body)
        raw_orders = data.get("orders", [])
        return [Order.model_validate(o) for o in raw_orders]

    async def batch_cancel(self, order_ids: list[str]) -> None:
        body = {"ids": order_ids}
        await self._transport.request("DELETE", "/portfolio/orders/batched", json=body)

    async def fills(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Fill]:
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if order_id:
            params["order_id"] = order_id
        if limit is not None:
            params["limit"] = limit
        if cursor:
            params["cursor"] = cursor
        return await self._list("/portfolio/fills", Fill, "fills", params=params)
