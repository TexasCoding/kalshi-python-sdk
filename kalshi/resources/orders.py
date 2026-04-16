"""Orders resource — create, get, cancel, list, batch operations."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from typing import Any

from kalshi.errors import KalshiError
from kalshi.models.common import Page
from kalshi.models.orders import (
    AmendOrderResponse,
    CreateOrderRequest,
    Fill,
    Order,
    OrderQueuePosition,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params
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
        self._require_auth()
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "type": type,
            "action": action,
            "count": count,
        }
        if yes_price is not None:
            body["yes_price_dollars"] = str(to_decimal(yes_price))
        if no_price is not None:
            body["no_price_dollars"] = str(to_decimal(no_price))
        if client_order_id:
            body["client_order_id"] = client_order_id
        if expiration_ts is not None:
            body["expiration_ts"] = expiration_ts

        data = self._post("/portfolio/orders", json=body)
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    def get(self, order_id: str) -> Order:
        self._require_auth()
        data = self._get(f"/portfolio/orders/{order_id}")
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    def cancel(self, order_id: str) -> None:
        self._require_auth()
        self._delete(f"/portfolio/orders/{order_id}")

    def list(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Order]:
        self._require_auth()
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
        self._require_auth()
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        if limit is not None:
            params["limit"] = limit
        return self._list_all("/portfolio/orders", Order, "orders", params=params)

    def batch_create(self, orders: builtins.list[CreateOrderRequest]) -> builtins.list[Order]:
        self._require_auth()
        body = {"orders": [o.model_dump(exclude_none=True, by_alias=True) for o in orders]}
        data = self._post("/portfolio/orders/batched", json=body)
        raw_orders = data.get("orders", [])
        return [Order.model_validate(o.get("order", o)) for o in raw_orders]

    def batch_cancel(self, order_ids: builtins.list[str]) -> None:
        self._require_auth()
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
        self._require_auth()
        params = _params(ticker=ticker, order_id=order_id, limit=limit, cursor=cursor)
        return self._list("/portfolio/fills", Fill, "fills", params=params)

    def fills_all(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        limit: int | None = None,
    ) -> Iterator[Fill]:
        self._require_auth()
        params = _params(ticker=ticker, order_id=order_id, limit=limit)
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
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "action": action,
        }
        if yes_price is not None:
            body["yes_price_dollars"] = str(to_decimal(yes_price))
        if no_price is not None:
            body["no_price_dollars"] = str(to_decimal(no_price))
        if count is not None:
            body["count_fp"] = str(to_decimal(count))
        if client_order_id is not None:
            body["client_order_id"] = client_order_id
        if updated_client_order_id is not None:
            body["updated_client_order_id"] = updated_client_order_id
        if subaccount is not None:
            body["subaccount"] = subaccount

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
        body: dict[str, Any] = {}
        if reduce_by is not None:
            body["reduce_by"] = reduce_by
        if reduce_to is not None:
            body["reduce_to"] = reduce_to
        if subaccount is not None:
            body["subaccount"] = subaccount

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
        tickers_str = ",".join(market_tickers) if isinstance(market_tickers, list) else market_tickers
        params = _params(
            market_tickers=tickers_str,
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        data = self._get("/portfolio/orders/queue_positions", params=params)
        raw = data.get("queue_positions", [])
        return [OrderQueuePosition.model_validate(item) for item in raw]

    def queue_position(self, order_id: str) -> Decimal:
        self._require_auth()
        data = self._get(f"/portfolio/orders/{order_id}/queue_position")
        raw = data.get("queue_position_fp") or data.get("queue_position")
        if raw is None:
            raise KalshiError(
                f"Unexpected response for queue_position: missing 'queue_position_fp' in {data!r}"
            )
        return to_decimal(raw)


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
        self._require_auth()
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "type": type,
            "action": action,
            "count": count,
        }
        if yes_price is not None:
            body["yes_price_dollars"] = str(to_decimal(yes_price))
        if no_price is not None:
            body["no_price_dollars"] = str(to_decimal(no_price))
        if client_order_id:
            body["client_order_id"] = client_order_id
        if expiration_ts is not None:
            body["expiration_ts"] = expiration_ts

        data = await self._post("/portfolio/orders", json=body)
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    async def get(self, order_id: str) -> Order:
        self._require_auth()
        data = await self._get(f"/portfolio/orders/{order_id}")
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    async def cancel(self, order_id: str) -> None:
        self._require_auth()
        await self._delete(f"/portfolio/orders/{order_id}")

    async def list(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Order]:
        self._require_auth()
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
        self._require_auth()
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        if limit is not None:
            params["limit"] = limit
        return self._list_all("/portfolio/orders", Order, "orders", params=params)

    async def batch_create(
        self, orders: builtins.list[CreateOrderRequest]
    ) -> builtins.list[Order]:
        self._require_auth()
        body = {"orders": [o.model_dump(exclude_none=True, by_alias=True) for o in orders]}
        data = await self._post("/portfolio/orders/batched", json=body)
        raw_orders = data.get("orders", [])
        return [Order.model_validate(o.get("order", o)) for o in raw_orders]

    async def batch_cancel(self, order_ids: builtins.list[str]) -> None:
        self._require_auth()
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
        self._require_auth()
        params = _params(ticker=ticker, order_id=order_id, limit=limit, cursor=cursor)
        return await self._list("/portfolio/fills", Fill, "fills", params=params)

    def fills_all(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Fill]:
        self._require_auth()
        params = _params(ticker=ticker, order_id=order_id, limit=limit)
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
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "action": action,
        }
        if yes_price is not None:
            body["yes_price_dollars"] = str(to_decimal(yes_price))
        if no_price is not None:
            body["no_price_dollars"] = str(to_decimal(no_price))
        if count is not None:
            body["count_fp"] = str(to_decimal(count))
        if client_order_id is not None:
            body["client_order_id"] = client_order_id
        if updated_client_order_id is not None:
            body["updated_client_order_id"] = updated_client_order_id
        if subaccount is not None:
            body["subaccount"] = subaccount

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
        body: dict[str, Any] = {}
        if reduce_by is not None:
            body["reduce_by"] = reduce_by
        if reduce_to is not None:
            body["reduce_to"] = reduce_to
        if subaccount is not None:
            body["subaccount"] = subaccount

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
        tickers_str = ",".join(market_tickers) if isinstance(market_tickers, list) else market_tickers
        params = _params(
            market_tickers=tickers_str,
            event_ticker=event_ticker,
            subaccount=subaccount,
        )
        data = await self._get("/portfolio/orders/queue_positions", params=params)
        raw = data.get("queue_positions", [])
        return [OrderQueuePosition.model_validate(item) for item in raw]

    async def queue_position(self, order_id: str) -> Decimal:
        self._require_auth()
        data = await self._get(f"/portfolio/orders/{order_id}/queue_position")
        raw = data.get("queue_position_fp") or data.get("queue_position")
        if raw is None:
            raise KalshiError(
                f"Unexpected response for queue_position: missing 'queue_position_fp' in {data!r}"
            )
        return to_decimal(raw)
