# Orders

Place, amend, cancel, and inspect orders. The largest single resource in the
SDK and the surface you'll spend the most time with as a trader.

Every method here requires auth.

## Quick reference

Order writes go through the V2 event-market family (`/portfolio/events/orders/*`).
Reads stay on `/portfolio/orders/*`.

| Method | Endpoint | Retry |
|---|---|---|
| `create_v2(*, request)` | `POST /portfolio/events/orders` | **never** — see [Retries & idempotency](../retries.md) |
| `batch_create_v2(*, request)` | `POST /portfolio/events/orders/batched` | never |
| `cancel_v2(order_id, *, subaccount, exchange_index, market_ticker)` | `DELETE /portfolio/events/orders/{order_id}` | never |
| `cancel_all_v2(*, subaccount)` | `DELETE /portfolio/events/orders` | never |
| `batch_cancel_v2(*, request)` | `DELETE /portfolio/events/orders/batched` | never |
| `amend_v2(order_id, *, request, subaccount)` | `POST /portfolio/events/orders/{order_id}/amend` | never |
| `decrease_v2(order_id, *, request, subaccount)` | `POST /portfolio/events/orders/{order_id}/decrease` | never |
| `get(order_id)` | `GET /portfolio/orders/{order_id}` | yes (GET) |
| `list(...)` / `list_all(..., exchange_index=None)` | `GET /portfolio/orders` | yes |
| ~~`fills(...)` / `fills_all(...)`~~ | moved to `PortfolioResource` in v3.0.0 — see [Portfolio › Fills](portfolio.md#fills); the old methods remain as deprecated aliases until removal in a future release. |
| `queue_positions(*, market_tickers, event_ticker)` | `GET /portfolio/orders/queue_positions` | yes |
| `queue_position(order_id)` | `GET /portfolio/orders/{order_id}/queue_position` | yes |

V2 uses `BookSideLiteral` (`"bid"` / `"ask"`), a single `price` field
(not paired yes/no), and requires `client_order_id` as a server-side
idempotency key. The surface is **model-only** — every write method takes a
pre-built request model rather than kwargs.

## Place an order

```python
import uuid
from decimal import Decimal
from kalshi import KalshiClient, CreateOrderV2Request

with KalshiClient.from_env() as client:
    resp = client.orders.create_v2(request=CreateOrderV2Request(
        ticker="KXPRES-24-DJT",
        client_order_id=str(uuid.uuid4()),    # required — idempotency key
        side="bid",                           # BookSideLiteral — "bid" / "ask"
        count=Decimal("10"),                  # Decimal — never float
        price=Decimal("0.65"),                # Decimal dollars — never float
        time_in_force="good_till_canceled",   # TimeInForceLiteral
        self_trade_prevention_type="taker_at_cross",
        # subaccount=1,                        # route to subaccount 1
        # exchange_index=0,
    ))
    print(resp.order_id, resp.remaining_count, resp.fill_count)
```

The write surface is **model-only**: there is no kwarg overload. Always build a
`CreateOrderV2Request`. `side` is the book side `"bid"` / `"ask"` (not
`"yes"` / `"no"`), `count` and `price` are `Decimal`, and `client_order_id`
is required.

### Time-in-force

| Value | Behavior |
|---|---|
| `"fill_or_kill"` | Fill instantly in full or cancel. |
| `"good_till_canceled"` | Rest until canceled or filled. Server default if you omit. |
| `"immediate_or_cancel"` | Fill whatever you can immediately, cancel the rest. |

### `client_order_id` for safe retries

`POST /portfolio/events/orders` is **never automatically retried**. Set a
fresh `client_order_id` per call so you can safely retry from your app layer
without double-filling. Reusing a `client_order_id` for a second call returns
the **original** order rather than placing a new one — generate a fresh UUID4
per request. See [Retries & idempotency](../retries.md).

### Self-trade prevention

`SelfTradePreventionTypeLiteral` values:

- `"taker_at_cross"` — your taker order is canceled if it would cross your own resting order.
- `"maker"` — your resting maker order is canceled if a taker side of yours crosses it.

## Batch create

```python
import uuid
from decimal import Decimal
from kalshi import BatchCreateOrdersV2Request, CreateOrderV2Request

result = client.orders.batch_create_v2(request=BatchCreateOrdersV2Request(
    orders=[
        CreateOrderV2Request(
            ticker="X-A", client_order_id=str(uuid.uuid4()),
            side="bid", count=Decimal("10"), price=Decimal("0.60"),
            time_in_force="good_till_canceled", self_trade_prevention_type="taker_at_cross",
        ),
        CreateOrderV2Request(
            ticker="X-B", client_order_id=str(uuid.uuid4()),
            side="ask", count=Decimal("10"), price=Decimal("0.42"),
            time_in_force="good_till_canceled", self_trade_prevention_type="taker_at_cross",
        ),
    ],
))
for entry in result.orders:
    if entry.error is not None:
        print("failed:", entry.error)
    else:
        print(entry.order_id, entry.fill_count)
```

Each child `CreateOrderV2Request` has `extra="forbid"`, so a typo in any leg
fails at construction before the round trip.

## Cancel

```python
result = client.orders.cancel_v2("ord_abc")
print(result.reduced_by, result.ts_ms)   # FixedPointCount, int
```

`cancel_v2` returns a `CancelOrderV2Response` (with the count actually
canceled). A 204 No Content from the server is treated as a protocol
violation and raises `KalshiError`.

For batch cancels, build a `BatchCancelOrdersV2Request`. Each entry can carry
its own `subaccount` / `market_ticker`:

```python
from kalshi import BatchCancelOrdersV2Request, BatchCancelOrdersV2RequestOrder

result = client.orders.batch_cancel_v2(request=BatchCancelOrdersV2Request(
    orders=[
        BatchCancelOrdersV2RequestOrder(order_id="ord_abc", subaccount=0),
        BatchCancelOrdersV2RequestOrder(order_id="ord_def", subaccount=1),
    ],
))
for entry in result.orders:
    if entry.error is not None:
        print("failed:", entry.order_id, entry.error)
    else:
        print(entry.order_id, "canceled")
```

!!! info "Cancel is not server-idempotent"
    `cancel_v2(...)` (and `batch_cancel_v2(...)`) propagate a 404 as
    `KalshiNotFoundError` when the order is already canceled, fully filled, or
    never existed. The SDK does **not** automatically swallow that — the
    caller owns safe-retry idempotency. Treat 404 as "already canceled" only
    if you can rule out a typo'd `order_id`:

    ```python
    from kalshi.errors import KalshiNotFoundError

    try:
        client.orders.cancel_v2(order_id)
    except KalshiNotFoundError:
        pass  # already canceled — idempotent
    ```

## Amend

```python
from decimal import Decimal
from kalshi import AmendOrderV2Request

resp = client.orders.amend_v2(
    "ord_abc",
    subaccount=0,                          # query param
    request=AmendOrderV2Request(
        ticker="KXPRES-24-DJT",            # same shape as create
        side="bid",                        # BookSideLiteral
        price=Decimal("0.66"),
        count=Decimal("12"),               # total/max fillable count
        exchange_index=0,                  # body field
    ),
)
print(resp.old_order.order_id, resp.order.order_id)
```

`AmendOrderV2Response` carries both the previous and the new order. `ticker`
and `side` are part of the API's amend payload.

## Decrease

Reduce the size of a resting order without canceling. Exactly one of
`reduce_by` or `reduce_to`:

```python
from decimal import Decimal
from kalshi import DecreaseOrderV2Request

resp = client.orders.decrease_v2(
    "ord_abc",
    subaccount=0,
    request=DecreaseOrderV2Request(reduce_by=Decimal("3")),   # decrease size by 3
)

resp = client.orders.decrease_v2(
    "ord_abc",
    request=DecreaseOrderV2Request(reduce_to=Decimal("5")),   # decrease size to 5
)
```

`DecreaseOrderV2Request` enforces XOR on `reduce_by` / `reduce_to` at
construction — passing both or neither raises `ValidationError`.

## List orders

```python
for order in client.orders.list_all(status="resting"):
    print(order.order_id, order.ticker, order.remaining_count)
```

`status` accepts an `OrderStatusLiteral`: `"resting"`, `"canceled"`,
`"executed"`. `min_ts` / `max_ts` (Unix seconds) bound by created time.
Optional `exchange_index` (OpenAPI 3.28.0) filters to one shard; omit it
to return orders from every shard.

Fills (`fills` / `fills_all`) moved to `PortfolioResource` in v3.0.0 — see
[Portfolio › Fills](portfolio.md#fills). `client.orders.fills(...)` /
`client.orders.fills_all(...)` still work in v3.0.0 but emit a
`DeprecationWarning` and will be removed in a future release.

## Queue position

```python
positions = client.orders.queue_positions(market_tickers=["KXPRES-24-DJT"])
for p in positions:
    print(p.order_id, p.queue_position)

q = client.orders.queue_position("ord_abc")  # returns Decimal
```

`queue_position(order_id)` returns a bare `Decimal`, not a model — that's the
shape Kalshi's endpoint emits.

## Batch error handling

Per-entry error handling is built into `BatchCreateOrdersV2ResponseEntry`
and `BatchCancelOrdersV2ResponseEntry` — successful entries carry the
order/fill data, failed entries carry an `error` dict with the rest of the
fields nulled (create) or zeroed (cancel).

## `subaccount` / `exchange_index` routing { #asymmetry }

This trips people up. The V2 spec routes `subaccount` and `exchange_index`
to **different places** depending on the endpoint:

| Endpoint | `subaccount` | `exchange_index` |
|---|---|---|
| `cancel_v2` | query | query |
| `amend_v2` | query | **body** (on `AmendOrderV2Request`) |
| `decrease_v2` | query | **body** (on `DecreaseOrderV2Request`) |
| `create_v2` / `batch_*_v2` | n/a — body on request model | body |

This is faithful to the OpenAPI spec — `amend_v2`/`decrease_v2` only
declare `SubaccountQueryDefaultPrimary` in their `parameters` list,
while `cancel_v2` declares both that and `ExchangeIndexQuery`. Don't try
to "normalize" it; the SDK matches the spec.

## Reference

::: kalshi.resources.orders.OrdersResource
    options:
      heading_level: 3

::: kalshi.resources.orders.AsyncOrdersResource
    options:
      heading_level: 3
