"""Orders resource — create, get, cancel, list, batch operations."""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Iterator, Sequence
from decimal import Decimal
from typing import Any, overload

from kalshi.errors import KalshiError
from kalshi.models.common import Page
from kalshi.models.orders import (
    ActionLiteral,
    AmendOrderRequest,
    AmendOrderResponse,
    AmendOrderV2Request,
    AmendOrderV2Response,
    BatchCancelOrdersRequest,
    BatchCancelOrdersRequestOrder,
    BatchCancelOrdersResponse,
    BatchCancelOrdersV2Request,
    BatchCancelOrdersV2Response,
    BatchCreateOrdersRequest,
    BatchCreateOrdersResponse,
    BatchCreateOrdersV2Request,
    BatchCreateOrdersV2Response,
    CancelOrderV2Response,
    CreateOrderRequest,
    CreateOrderV2Request,
    CreateOrderV2Response,
    DecreaseOrderRequest,
    DecreaseOrderV2Request,
    DecreaseOrderV2Response,
    Fill,
    Order,
    OrderQueuePosition,
    OrderStatusLiteral,
    SelfTradePreventionTypeLiteral,
    SideLiteral,
    TimeInForceLiteral,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _join_tickers,
    _params,
    _seg,
    _validate_limit,
    _validate_max_pages,
)
from kalshi.types import to_decimal

# ---------------------------------------------------------------------------
# Shared request-body builders (issue #46: dedup sync/async resource bodies).
#
# These helpers are pure: kwargs in, ``dict[str, Any]`` out. Both the sync and
# async resource methods call the same builder so dispatcher logic, model
# construction, and serialization live in one place.
# ---------------------------------------------------------------------------


def _build_create_order_body(
    request: CreateOrderRequest | None,
    *,
    ticker: str | None,
    side: SideLiteral | None,
    action: ActionLiteral | None,
    count: int | None,
    yes_price: float | str | int | None,
    no_price: float | str | int | None,
    client_order_id: str | None,
    expiration_ts: int | None,
    buy_max_cost: int | None,
    time_in_force: TimeInForceLiteral | None,
    post_only: bool | None,
    reduce_only: bool | None,
    self_trade_prevention_type: SelfTradePreventionTypeLiteral | None,
    order_group_id: str | None,
    cancel_order_on_pause: bool | None,
    subaccount: int | None,
    exchange_index: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        ticker=ticker,
        side=side,
        action=action,
        count=count,
        yes_price=yes_price,
        no_price=no_price,
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
        exchange_index=exchange_index,
    )
    if request is None:
        if ticker is None or side is None or count is None or action is None:
            raise TypeError(
                "create() requires `ticker`, `side`, `count`, and `action` "
                "(or pass `request=...`). Pre-#242 the SDK silently defaulted "
                'missing `count` to 1 contract and missing `action` to "buy" — '
                "that has been removed: a missing arg would otherwise translate "
                "into a real 1-contract BUY on the wire."
            )
        request = CreateOrderRequest(
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
            exchange_index=exchange_index,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_batch_create_body(
    request: BatchCreateOrdersRequest | None,
    orders: Sequence[CreateOrderRequest] | None,
) -> bytes:
    """Serialize the batch-create body directly to JSON bytes.

    Skips the intermediate ``model_dump(mode="json")`` dict-walk: with up
    to 100 orders x ~10 Decimal fields, the dict version pays the
    serializer cost twice (once here, once in httpx's json encoder).
    """
    _check_request_exclusive(request, orders=orders)
    if request is None:
        if orders is None:
            raise TypeError("batch_create() requires `orders` (or pass `request=...`)")
        request = BatchCreateOrdersRequest(orders=list(orders))
    return request.model_dump_json(exclude_none=True, by_alias=True).encode()


def _build_batch_cancel_body(
    request: BatchCancelOrdersRequest | None,
    orders: Sequence[BatchCancelOrdersRequestOrder | str] | None,
) -> bytes:
    """Serialize the batch-cancel body directly to JSON bytes. See
    :func:`_build_batch_create_body` for the perf rationale."""
    _check_request_exclusive(request, orders=orders)
    if request is None:
        if orders is None:
            raise TypeError("batch_cancel() requires `orders` (or pass `request=...`)")
        normalized = [
            (BatchCancelOrdersRequestOrder(order_id=o) if isinstance(o, str) else o) for o in orders
        ]
        request = BatchCancelOrdersRequest(orders=normalized)
    return request.model_dump_json(exclude_none=True, by_alias=True).encode()


def _build_amend_body(
    request: AmendOrderRequest | None,
    *,
    ticker: str | None,
    side: SideLiteral | None,
    action: ActionLiteral | None,
    yes_price: float | str | int | None,
    no_price: float | str | int | None,
    count: int | None,
    client_order_id: str | None,
    updated_client_order_id: str | None,
    subaccount: int | None,
    exchange_index: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        ticker=ticker,
        side=side,
        action=action,
        yes_price=yes_price,
        no_price=no_price,
        count=count,
        client_order_id=client_order_id,
        updated_client_order_id=updated_client_order_id,
        subaccount=subaccount,
        exchange_index=exchange_index,
    )
    if request is None:
        if ticker is None or side is None or action is None:
            raise TypeError(
                "amend() requires `ticker`, `side`, and `action` (or pass `request=...`)"
            )
        if yes_price is None and no_price is None and count is None:
            raise ValueError("amend() requires at least one of yes_price, no_price, or count")
        request = AmendOrderRequest(
            ticker=ticker,
            side=side,
            action=action,
            yes_price=to_decimal(yes_price) if yes_price is not None else None,
            no_price=to_decimal(no_price) if no_price is not None else None,
            count=to_decimal(count) if count is not None else None,
            client_order_id=client_order_id,
            updated_client_order_id=updated_client_order_id,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_decrease_body(
    request: DecreaseOrderRequest | None,
    *,
    reduce_by: int | None,
    reduce_to: int | None,
    subaccount: int | None,
    exchange_index: int | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        reduce_by=reduce_by,
        reduce_to=reduce_to,
        subaccount=subaccount,
        exchange_index=exchange_index,
    )
    if request is None:
        # Method-level guards mirror DecreaseOrderRequest._enforce_reduce_xor
        # by design: the model-first v0.9 API will rely on the model validator,
        # but this path preserves nicer ValueError messages for current callers.
        if reduce_by is None and reduce_to is None:
            raise ValueError("decrease() requires either reduce_by or reduce_to")
        if reduce_by is not None and reduce_to is not None:
            raise ValueError("decrease() accepts reduce_by or reduce_to, not both")
        request = DecreaseOrderRequest(
            reduce_by=reduce_by,
            reduce_to=reduce_to,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


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


def _fills_params(
    *,
    ticker: str | None,
    order_id: str | None,
    min_ts: int | None,
    max_ts: int | None,
    limit: int | None,
    cursor: str | None,
    subaccount: int | None,
) -> dict[str, Any]:
    limit = _validate_limit(limit, hi=1000)
    return _params(
        ticker=ticker,
        order_id=order_id,
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

    @overload
    def create(
        self, *, request: CreateOrderRequest, extra_headers: dict[str, str] | None = None
    ) -> Order: ...
    @overload
    def create(
        self,
        *,
        ticker: str,
        side: SideLiteral,
        action: ActionLiteral | None = ...,
        count: int | None = ...,
        yes_price: float | str | int | None = ...,
        no_price: float | str | int | None = ...,
        client_order_id: str | None = ...,
        expiration_ts: int | None = ...,
        buy_max_cost: int | None = ...,
        time_in_force: TimeInForceLiteral | None = ...,
        post_only: bool | None = ...,
        reduce_only: bool | None = ...,
        self_trade_prevention_type: SelfTradePreventionTypeLiteral | None = ...,
        order_group_id: str | None = ...,
        cancel_order_on_pause: bool | None = ...,
        subaccount: int | None = ...,
        exchange_index: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> Order: ...
    def create(
        self,
        *,
        request: CreateOrderRequest | None = None,
        ticker: str | None = None,
        side: SideLiteral | None = None,
        action: ActionLiteral | None = None,
        count: int | None = None,
        yes_price: float | str | int | None = None,
        no_price: float | str | int | None = None,
        client_order_id: str | None = None,
        expiration_ts: int | None = None,
        buy_max_cost: int | None = None,
        time_in_force: TimeInForceLiteral | None = None,
        post_only: bool | None = None,
        reduce_only: bool | None = None,
        self_trade_prevention_type: SelfTradePreventionTypeLiteral | None = None,
        order_group_id: str | None = None,
        cancel_order_on_pause: bool | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Order:
        """Place a new order.

        ``buy_max_cost`` is integer cents per OpenAPI spec (e.g., 500 for $5.00).

        ``time_in_force`` accepts ``"fill_or_kill"``, ``"good_till_canceled"``,
        ``"immediate_or_cancel"``. Passing ``None`` omits the field and lets
        Kalshi apply its server-side default (``good_till_canceled``).

        v0.8.0 removed the ``type`` kwarg: the field was never defined in
        the OpenAPI spec. Callers passing ``type="limit"`` now get a
        ``TypeError``.

        #242 (v2.5): on the kwarg path, ``count`` and ``action`` are now
        REQUIRED — passing neither raises ``TypeError`` before any HTTP
        request. Previously the SDK silently defaulted to ``count=1`` and
        ``action="buy"``, which converted a missing-arg bug into a real
        1-contract BUY fill. The ``request=CreateOrderRequest(...)``
        overload is unaffected (the model itself now declares them required).

        v1.1 (#56): pass a pre-built ``request=CreateOrderRequest(...)`` instead
        of individual kwargs. Mutually exclusive with the kwarg form.
        """
        self._require_auth()
        body = _build_create_order_body(
            request,
            ticker=ticker,
            side=side,
            action=action,
            count=count,
            yes_price=yes_price,
            no_price=no_price,
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
            exchange_index=exchange_index,
        )
        data = self._post("/portfolio/orders", json=body, extra_headers=extra_headers)
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    def get(self, order_id: str, *, extra_headers: dict[str, str] | None = None) -> Order:
        self._require_auth()
        data = self._get(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}", extra_headers=extra_headers
        )
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    def cancel(
        self,
        order_id: str,
        *,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount, exchange_index=exchange_index)
        self._delete(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}",
            params=params,
            extra_headers=extra_headers,
        )

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

    @overload
    def batch_create(
        self, *, request: BatchCreateOrdersRequest, extra_headers: dict[str, str] | None = None
    ) -> BatchCreateOrdersResponse: ...
    @overload
    def batch_create(
        self, orders: Sequence[CreateOrderRequest], *, extra_headers: dict[str, str] | None = None
    ) -> BatchCreateOrdersResponse: ...
    def batch_create(
        self,
        orders: Sequence[CreateOrderRequest] | None = None,
        *,
        request: BatchCreateOrdersRequest | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> BatchCreateOrdersResponse:
        """Place a batch of orders.

        Changed in v2.4.0 (breaking): previously returned ``list[Order]`` and would
        crash with ``ValidationError`` on any partially-failed batch
        (the spec marks each entry's ``order`` and ``error`` as nullable;
        the old ``Order.model_validate(o.get("order", o))`` blew up the
        instant the server returned ``{"order": null, "error": {...}}``).
        Now returns :class:`BatchCreateOrdersResponse` so callers can
        pair the per-leg ``client_order_id`` with ``order``/``error``.
        """
        self._require_auth()
        body = _build_batch_create_body(request, orders)
        data = self._post_json(
            "/portfolio/orders/batched", content=body, extra_headers=extra_headers
        )
        return BatchCreateOrdersResponse.model_validate(data)

    @overload
    def batch_cancel(
        self, *, request: BatchCancelOrdersRequest, extra_headers: dict[str, str] | None = None
    ) -> BatchCancelOrdersResponse: ...
    @overload
    def batch_cancel(
        self,
        orders: Sequence[BatchCancelOrdersRequestOrder | str],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> BatchCancelOrdersResponse: ...
    def batch_cancel(
        self,
        orders: Sequence[BatchCancelOrdersRequestOrder | str] | None = None,
        *,
        request: BatchCancelOrdersRequest | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> BatchCancelOrdersResponse:
        """Batch-cancel orders.

        Accepts a sequence of either ``BatchCancelOrdersRequestOrder``
        entries (for per-order ``subaccount`` routing), plain order-id
        strings (convenience shortcut — each is wrapped internally), or a
        mix of both. String entries are wrapped as
        ``BatchCancelOrdersRequestOrder(order_id=<id>)`` before serialization.

        Changed in v2.4.0 (breaking): previously returned ``None`` and discarded
        the server's per-leg response. Now returns
        :class:`BatchCancelOrdersResponse` so callers can read the
        load-bearing ``reduced_by_fp`` per entry (cents canceled) plus
        any per-leg ``error`` blocks. A server that returns 204
        No Content raises :class:`KalshiError` — every modern Kalshi
        environment returns 200 with the typed body.
        """
        self._require_auth()
        body = _build_batch_cancel_body(request, orders)
        data = self._delete_with_body_json(
            "/portfolio/orders/batched", content=body, extra_headers=extra_headers
        )
        if data is None:
            raise KalshiError("Expected BatchCancelOrdersResponse body, got 204 No Content.")
        return BatchCancelOrdersResponse.model_validate(data)

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

    @overload
    def amend(
        self,
        order_id: str,
        *,
        request: AmendOrderRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendOrderResponse: ...
    @overload
    def amend(
        self,
        order_id: str,
        *,
        ticker: str,
        side: SideLiteral,
        action: ActionLiteral,
        yes_price: float | str | int | None = ...,
        no_price: float | str | int | None = ...,
        count: int | None = ...,
        client_order_id: str | None = ...,
        updated_client_order_id: str | None = ...,
        subaccount: int | None = ...,
        exchange_index: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendOrderResponse: ...
    def amend(
        self,
        order_id: str,
        *,
        request: AmendOrderRequest | None = None,
        ticker: str | None = None,
        side: SideLiteral | None = None,
        action: ActionLiteral | None = None,
        yes_price: float | str | int | None = None,
        no_price: float | str | int | None = None,
        count: int | None = None,
        client_order_id: str | None = None,
        updated_client_order_id: str | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendOrderResponse:
        self._require_auth()
        body = _build_amend_body(
            request,
            ticker=ticker,
            side=side,
            action=action,
            yes_price=yes_price,
            no_price=no_price,
            count=count,
            client_order_id=client_order_id,
            updated_client_order_id=updated_client_order_id,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        data = self._post(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}/amend",
            json=body,
            extra_headers=extra_headers,
        )
        return AmendOrderResponse.model_validate(data)

    @overload
    def decrease(
        self,
        order_id: str,
        *,
        request: DecreaseOrderRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> Order: ...
    @overload
    def decrease(
        self,
        order_id: str,
        *,
        reduce_by: int | None = ...,
        reduce_to: int | None = ...,
        subaccount: int | None = ...,
        exchange_index: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> Order: ...
    def decrease(
        self,
        order_id: str,
        *,
        request: DecreaseOrderRequest | None = None,
        reduce_by: int | None = None,
        reduce_to: int | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Order:
        self._require_auth()
        body = _build_decrease_body(
            request,
            reduce_by=reduce_by,
            reduce_to=reduce_to,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        data = self._post(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}/decrease",
            json=body,
            extra_headers=extra_headers,
        )
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

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
        extra_headers: dict[str, str] | None = None,
    ) -> CancelOrderV2Response:
        self._require_auth()
        params = _params(subaccount=subaccount, exchange_index=exchange_index)
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
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post(
            "/portfolio/events/orders/batched", json=body, extra_headers=extra_headers
        )
        return BatchCreateOrdersV2Response.model_validate(data)

    def batch_cancel_v2(
        self, *, request: BatchCancelOrdersV2Request, extra_headers: dict[str, str] | None = None
    ) -> BatchCancelOrdersV2Response:
        self._require_auth()
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._delete_with_body(
            "/portfolio/events/orders/batched", json=body, extra_headers=extra_headers
        )
        if data is None:
            raise KalshiError("Expected BatchCancelOrdersV2Response body, got 204 No Content.")
        return BatchCancelOrdersV2Response.model_validate(data)


class AsyncOrdersResource(AsyncResource):
    """Async orders API."""

    @overload
    async def create(
        self, *, request: CreateOrderRequest, extra_headers: dict[str, str] | None = None
    ) -> Order: ...
    @overload
    async def create(
        self,
        *,
        ticker: str,
        side: SideLiteral,
        action: ActionLiteral | None = ...,
        count: int | None = ...,
        yes_price: float | str | int | None = ...,
        no_price: float | str | int | None = ...,
        client_order_id: str | None = ...,
        expiration_ts: int | None = ...,
        buy_max_cost: int | None = ...,
        time_in_force: TimeInForceLiteral | None = ...,
        post_only: bool | None = ...,
        reduce_only: bool | None = ...,
        self_trade_prevention_type: SelfTradePreventionTypeLiteral | None = ...,
        order_group_id: str | None = ...,
        cancel_order_on_pause: bool | None = ...,
        subaccount: int | None = ...,
        exchange_index: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> Order: ...
    async def create(
        self,
        *,
        request: CreateOrderRequest | None = None,
        ticker: str | None = None,
        side: SideLiteral | None = None,
        action: ActionLiteral | None = None,
        count: int | None = None,
        yes_price: float | str | int | None = None,
        no_price: float | str | int | None = None,
        client_order_id: str | None = None,
        expiration_ts: int | None = None,
        buy_max_cost: int | None = None,
        time_in_force: TimeInForceLiteral | None = None,
        post_only: bool | None = None,
        reduce_only: bool | None = None,
        self_trade_prevention_type: SelfTradePreventionTypeLiteral | None = None,
        order_group_id: str | None = None,
        cancel_order_on_pause: bool | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Order:
        """Place a new order.

        ``buy_max_cost`` is integer cents per OpenAPI spec (e.g., 500 for $5.00).

        ``time_in_force`` accepts ``"fill_or_kill"``, ``"good_till_canceled"``,
        ``"immediate_or_cancel"``. Passing ``None`` omits the field and lets
        Kalshi apply its server-side default (``good_till_canceled``).

        v0.8.0 removed the ``type`` kwarg: the field was never defined in
        the OpenAPI spec. Callers passing ``type="limit"`` now get a
        ``TypeError``.

        #242 (v2.5): on the kwarg path, ``count`` and ``action`` are now
        REQUIRED — passing neither raises ``TypeError`` before any HTTP
        request. Previously the SDK silently defaulted to ``count=1`` and
        ``action="buy"``, which converted a missing-arg bug into a real
        1-contract BUY fill. The ``request=CreateOrderRequest(...)``
        overload is unaffected (the model itself now declares them required).

        v1.1 (#56): pass a pre-built ``request=CreateOrderRequest(...)`` instead
        of individual kwargs. Mutually exclusive with the kwarg form.
        """
        self._require_auth()
        body = _build_create_order_body(
            request,
            ticker=ticker,
            side=side,
            action=action,
            count=count,
            yes_price=yes_price,
            no_price=no_price,
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
            exchange_index=exchange_index,
        )
        data = await self._post("/portfolio/orders", json=body, extra_headers=extra_headers)
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    async def get(self, order_id: str, *, extra_headers: dict[str, str] | None = None) -> Order:
        self._require_auth()
        data = await self._get(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}", extra_headers=extra_headers
        )
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

    async def cancel(
        self,
        order_id: str,
        *,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._require_auth()
        params = _params(subaccount=subaccount, exchange_index=exchange_index)
        await self._delete(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}",
            params=params,
            extra_headers=extra_headers,
        )

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
        """Non-async method that returns an async iterator for direct use with `async for`."""
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

    @overload
    async def batch_create(
        self, *, request: BatchCreateOrdersRequest, extra_headers: dict[str, str] | None = None
    ) -> BatchCreateOrdersResponse: ...
    @overload
    async def batch_create(
        self, orders: Sequence[CreateOrderRequest], *, extra_headers: dict[str, str] | None = None
    ) -> BatchCreateOrdersResponse: ...
    async def batch_create(
        self,
        orders: Sequence[CreateOrderRequest] | None = None,
        *,
        request: BatchCreateOrdersRequest | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> BatchCreateOrdersResponse:
        """Place a batch of orders. See :meth:`OrdersResource.batch_create`."""
        self._require_auth()
        body = _build_batch_create_body(request, orders)
        data = await self._post_json(
            "/portfolio/orders/batched", content=body, extra_headers=extra_headers
        )
        return BatchCreateOrdersResponse.model_validate(data)

    @overload
    async def batch_cancel(
        self, *, request: BatchCancelOrdersRequest, extra_headers: dict[str, str] | None = None
    ) -> BatchCancelOrdersResponse: ...
    @overload
    async def batch_cancel(
        self,
        orders: Sequence[BatchCancelOrdersRequestOrder | str],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> BatchCancelOrdersResponse: ...
    async def batch_cancel(
        self,
        orders: Sequence[BatchCancelOrdersRequestOrder | str] | None = None,
        *,
        request: BatchCancelOrdersRequest | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> BatchCancelOrdersResponse:
        """Batch-cancel orders. See :meth:`OrdersResource.batch_cancel`."""
        self._require_auth()
        body = _build_batch_cancel_body(request, orders)
        data = await self._delete_with_body_json(
            "/portfolio/orders/batched", content=body, extra_headers=extra_headers
        )
        if data is None:
            raise KalshiError("Expected BatchCancelOrdersResponse body, got 204 No Content.")
        return BatchCancelOrdersResponse.model_validate(data)

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

    @overload
    async def amend(
        self,
        order_id: str,
        *,
        request: AmendOrderRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendOrderResponse: ...
    @overload
    async def amend(
        self,
        order_id: str,
        *,
        ticker: str,
        side: SideLiteral,
        action: ActionLiteral,
        yes_price: float | str | int | None = ...,
        no_price: float | str | int | None = ...,
        count: int | None = ...,
        client_order_id: str | None = ...,
        updated_client_order_id: str | None = ...,
        subaccount: int | None = ...,
        exchange_index: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendOrderResponse: ...
    async def amend(
        self,
        order_id: str,
        *,
        request: AmendOrderRequest | None = None,
        ticker: str | None = None,
        side: SideLiteral | None = None,
        action: ActionLiteral | None = None,
        yes_price: float | str | int | None = None,
        no_price: float | str | int | None = None,
        count: int | None = None,
        client_order_id: str | None = None,
        updated_client_order_id: str | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AmendOrderResponse:
        self._require_auth()
        body = _build_amend_body(
            request,
            ticker=ticker,
            side=side,
            action=action,
            yes_price=yes_price,
            no_price=no_price,
            count=count,
            client_order_id=client_order_id,
            updated_client_order_id=updated_client_order_id,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        data = await self._post(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}/amend",
            json=body,
            extra_headers=extra_headers,
        )
        return AmendOrderResponse.model_validate(data)

    @overload
    async def decrease(
        self,
        order_id: str,
        *,
        request: DecreaseOrderRequest,
        extra_headers: dict[str, str] | None = None,
    ) -> Order: ...
    @overload
    async def decrease(
        self,
        order_id: str,
        *,
        reduce_by: int | None = ...,
        reduce_to: int | None = ...,
        subaccount: int | None = ...,
        exchange_index: int | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> Order: ...
    async def decrease(
        self,
        order_id: str,
        *,
        request: DecreaseOrderRequest | None = None,
        reduce_by: int | None = None,
        reduce_to: int | None = None,
        subaccount: int | None = None,
        exchange_index: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Order:
        self._require_auth()
        body = _build_decrease_body(
            request,
            reduce_by=reduce_by,
            reduce_to=reduce_to,
            subaccount=subaccount,
            exchange_index=exchange_index,
        )
        data = await self._post(
            f"/portfolio/orders/{_seg(order_id, name='order_id')}/decrease",
            json=body,
            extra_headers=extra_headers,
        )
        order_data = data.get("order", data)
        return Order.model_validate(order_data)

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
        extra_headers: dict[str, str] | None = None,
    ) -> CancelOrderV2Response:
        self._require_auth()
        params = _params(subaccount=subaccount, exchange_index=exchange_index)
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
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post(
            "/portfolio/events/orders/batched", json=body, extra_headers=extra_headers
        )
        return BatchCreateOrdersV2Response.model_validate(data)

    async def batch_cancel_v2(
        self, *, request: BatchCancelOrdersV2Request, extra_headers: dict[str, str] | None = None
    ) -> BatchCancelOrdersV2Response:
        self._require_auth()
        body = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._delete_with_body(
            "/portfolio/events/orders/batched", json=body, extra_headers=extra_headers
        )
        if data is None:
            raise KalshiError("Expected BatchCancelOrdersV2Response body, got 204 No Content.")
        return BatchCancelOrdersV2Response.model_validate(data)
