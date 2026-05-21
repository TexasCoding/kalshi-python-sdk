# Orders

Place, amend, cancel, and inspect orders. The largest single resource in the
SDK and the surface you'll spend the most time with as a trader.

Every method here requires auth.

## Quick reference

### V1 (legacy `/portfolio/orders/*`) — deprecated no earlier than May 6, 2026

| Method | Endpoint | Retry |
|---|---|---|
| `create(...)` | `POST /portfolio/orders` | **never** — see [Retries & idempotency](../retries.md) |
| `batch_create(orders)` | `POST /portfolio/orders/batched` | never |
| `get(order_id)` | `GET /portfolio/orders/{order_id}` | yes (GET) |
| `list(...)` / `list_all(...)` | `GET /portfolio/orders` | yes |
| `cancel(order_id, *, subaccount=None, exchange_index=None)` | `DELETE /portfolio/orders/{order_id}` | never |
| `batch_cancel(orders)` | `DELETE /portfolio/orders/batched` | never |
| `amend(order_id, ...)` | `POST /portfolio/orders/{order_id}/amend` | never |
| `decrease(order_id, *, reduce_by, reduce_to)` | `POST /portfolio/orders/{order_id}/decrease` | never |
| `fills(...)` / `fills_all(...)` | `GET /portfolio/fills` | yes |
| `queue_positions(*, market_tickers, event_ticker)` | `GET /portfolio/orders/queue_positions` | yes |
| `queue_position(order_id)` | `GET /portfolio/orders/{order_id}/queue_position` | yes |

### V2 event-market orders (`/portfolio/events/orders/*`) — recommended for new code

| Method | Endpoint | Retry |
|---|---|---|
| `create_v2(*, request)` | `POST /portfolio/events/orders` | never |
| `batch_create_v2(*, request)` | `POST /portfolio/events/orders/batched` | never |
| `cancel_v2(order_id, *, subaccount, exchange_index)` | `DELETE /portfolio/events/orders/{order_id}` | never |
| `batch_cancel_v2(*, request)` | `DELETE /portfolio/events/orders/batched` | never |
| `amend_v2(order_id, *, request, subaccount)` | `POST /portfolio/events/orders/{order_id}/amend` | never |
| `decrease_v2(order_id, *, request, subaccount)` | `POST /portfolio/events/orders/{order_id}/decrease` | never |

V2 uses `BookSideLiteral` (`"bid"` / `"ask"`), a single `price` field
(not paired yes/no), and requires `client_order_id` as a server-side
idempotency key. The surface is **model-only** — every method takes a
pre-built request model rather than kwargs.

## Place an order

```python
import uuid
from kalshi import KalshiClient

with KalshiClient.from_env() as client:
    order = client.orders.create(
        ticker="KXPRES-24-DJT",
        side="yes",                    # SideLiteral
        action="buy",                  # ActionLiteral, defaults to "buy"
        count=10,
        yes_price="0.65",              # str or Decimal — never float
        client_order_id=str(uuid.uuid4()),
        time_in_force="good_till_canceled",   # TimeInForceLiteral
        post_only=False,
        reduce_only=False,
        self_trade_prevention_type="taker_at_cross",
        cancel_order_on_pause=False,
        # buy_max_cost=500,            # integer cents — $5.00 limit. Not dollars.
        # expiration_ts=1_800_000_000, # Unix seconds
        # order_group_id="og_abc",     # attach to an order group
        # subaccount=1,                # route to subaccount 1
    )
    print(order.order_id, order.status)
```

### Limit vs market

A market order is just a `create()` with no `yes_price` / `no_price`. The
order type is server-derived from price presence.

### Time-in-force

| Value | Behavior |
|---|---|
| `"fill_or_kill"` | Fill instantly in full or cancel. |
| `"good_till_canceled"` | Rest until canceled or filled. Server default if you omit. |
| `"immediate_or_cancel"` | Fill whatever you can immediately, cancel the rest. |

### `buy_max_cost` is integer cents

```python
client.orders.create(..., buy_max_cost=500)   # cap at $5.00
```

The model rejects `Decimal` or `float` at construction. The rule: any field
whose name ends in `_cents` or that is `buy_max_cost` is `int` cents; price
fields (`yes_price`, `no_price`) are `Decimal` dollars.

### `client_order_id` for safe retries

`POST /portfolio/orders` is **never automatically retried**. Set a fresh
`client_order_id` per call so you can safely retry from your app layer
without double-filling. See [Retries & idempotency](../retries.md).

### Self-trade prevention

`SelfTradePreventionTypeLiteral` values:

- `"taker_at_cross"` — your taker order is canceled if it would cross your own resting order.
- `"maker"` — your resting maker order is canceled if a taker side of yours crosses it.

## Batch create

```python
from kalshi import CreateOrderRequest

orders = [
    CreateOrderRequest(ticker="X-YES", side="yes", action="buy", count=10, yes_price="0.60"),
    CreateOrderRequest(ticker="X-NO",  side="no",  action="buy", count=10, no_price="0.42"),
]
created = client.orders.batch_create(orders)
for o in created:
    print(o.order_id, o.status)
```

Each child has `extra="forbid"`, so a typo in any leg fails at construction
before the round trip.

## Cancel

```python
client.orders.cancel("ord_abc")                         # single
client.orders.batch_cancel(["ord_abc", "ord_def"])       # convenience: list of strings
```

For per-entry subaccount routing, build the request explicitly:

```python
from kalshi import BatchCancelOrdersRequestOrder

client.orders.batch_cancel([
    BatchCancelOrdersRequestOrder(order_id="ord_abc", subaccount=0),
    BatchCancelOrdersRequestOrder(order_id="ord_def", subaccount=1),
])
```

!!! note "v0.8.0 wire change"
    The body field is `orders` (an array of objects). The previous `ids`
    field is no longer emitted. If you talk to the API directly elsewhere,
    keep that in mind.

!!! info "Cancel is not server-idempotent"
    `cancel(order_id)` (and `cancel_v2(...)`, `batch_cancel(...)`) propagate
    a 404 as `KalshiNotFoundError` when the order is already canceled, fully
    filled, or never existed. The SDK does **not** automatically swallow
    that — the caller owns safe-retry idempotency. Treat 404 as "already
    canceled" only if you can rule out a typo'd `order_id`:

    ```python
    from kalshi.errors import KalshiNotFoundError

    try:
        client.orders.cancel(order_id)
    except KalshiNotFoundError:
        pass  # already canceled — idempotent
    ```

## Amend

```python
resp = client.orders.amend(
    "ord_abc",
    ticker="KXPRES-24-DJT",   # required — same shape as create
    side="yes",               # required
    action="buy",             # required
    yes_price="0.66",         # at least one of yes_price / no_price / count
    updated_client_order_id="cid-2",
)
print(resp.old_order.order_id, resp.order.order_id)
```

`AmendOrderResponse` carries both the previous and the new order. `ticker`,
`side`, and `action` are required even though you're amending an existing
order — they're part of the API's amend payload.

## Decrease

Reduce the size of a resting order without canceling. Exactly one of
`reduce_by` or `reduce_to`:

```python
order = client.orders.decrease("ord_abc", reduce_by=3)    # decrease size by 3
order = client.orders.decrease("ord_abc", reduce_to=5)    # decrease size to 5
```

Passing neither or both raises `ValidationError` at construction (XOR enforced
by the model).

## List orders and fills

```python
for order in client.orders.list_all(status="resting"):
    print(order.order_id, order.ticker, order.remaining_count)

for fill in client.orders.fills_all(ticker="KXPRES-24-DJT"):
    print(fill.fill_id, fill.price, fill.count, fill.is_taker)
```

`status` accepts an `OrderStatusLiteral`: `"resting"`, `"canceled"`,
`"executed"`. `min_ts` / `max_ts` (Unix seconds) bound by created time.

## Queue position

```python
positions = client.orders.queue_positions(market_tickers=["KXPRES-24-DJT"])
for p in positions:
    print(p.order_id, p.queue_position)

q = client.orders.queue_position("ord_abc")  # returns Decimal
```

`queue_position(order_id)` returns a bare `Decimal`, not a model — that's the
shape Kalshi's endpoint emits.

## V2 event-market orders

Spec v3.18.0 introduced the `/portfolio/events/orders/*` family. Legacy
`/portfolio/orders` keeps working and will be deprecated **no earlier than
May 6, 2026** — start new event-market integrations on V2.

### How V2 differs from V1

| | V1 (`/portfolio/orders`) | V2 (`/portfolio/events/orders`) |
|---|---|---|
| Side enum | `SideLiteral` — `"yes"` / `"no"` | `BookSideLiteral` — `"bid"` / `"ask"` |
| Price | Paired `yes_price` / `no_price` | Single `price: DollarDecimal` |
| `client_order_id` | Optional | **Required** + acts as server-side idempotency key |
| Kwarg API | Yes (kwargs or request model) | Model-only — pass a request model |
| Side filter | n/a | per-spec query/body asymmetry — see [Asymmetry](#asymmetry) |

### Place a V2 order

```python
import uuid
from decimal import Decimal
from kalshi import KalshiClient, CreateOrderV2Request

with KalshiClient.from_env() as client:
    resp = client.orders.create_v2(request=CreateOrderV2Request(
        ticker="EVENT-MKT-A",
        client_order_id=str(uuid.uuid4()),   # required — idempotency key
        side="bid",                          # BookSideLiteral
        count=Decimal("10"),
        price=Decimal("0.50"),
        time_in_force="good_till_canceled",
        self_trade_prevention_type="taker_at_cross",
        # post_only=False, reduce_only=False, cancel_order_on_pause=False,
        # subaccount=0, order_group_id="og_abc", exchange_index=0,
    ))
    print(resp.order_id, resp.remaining_count, resp.fill_count)
```

Reusing a `client_order_id` for a second call returns the **original**
order rather than placing a new one. Generate a fresh UUID4 per request.

### Cancel V2

```python
result = client.orders.cancel_v2("ord_v2_1", subaccount=0, exchange_index=0)
print(result.reduced_by, result.ts_ms)   # FixedPointCount, int
```

`cancel_v2` returns a `CancelOrderV2Response` (with the count actually
canceled), not `None` like the V1 `cancel`. A 204 No Content from the
server is treated as a protocol violation and raises `KalshiError`.

### Amend V2 / Decrease V2

```python
from decimal import Decimal
from kalshi import AmendOrderV2Request, DecreaseOrderV2Request

resp = client.orders.amend_v2(
    "ord_v2_1",
    subaccount=0,                              # query param
    request=AmendOrderV2Request(
        ticker="EVENT-MKT-A",
        side="bid",
        price=Decimal("0.55"),
        count=Decimal("12"),                   # total/max fillable count
        exchange_index=0,                      # body field
    ),
)

resp = client.orders.decrease_v2(
    "ord_v2_1",
    subaccount=0,
    request=DecreaseOrderV2Request(
        reduce_by=Decimal("3"),                # exactly one of reduce_by | reduce_to
    ),
)
```

`DecreaseOrderV2Request` enforces XOR on `reduce_by` / `reduce_to` at
construction — passing both or neither raises `ValidationError`.

### Batch V2

```python
from kalshi import (
    BatchCreateOrdersV2Request, BatchCancelOrdersV2Request,
    BatchCancelOrdersV2RequestOrder,
)

# Create
result = client.orders.batch_create_v2(request=BatchCreateOrdersV2Request(
    orders=[
        CreateOrderV2Request(...),    # per-order builds, same shape as create_v2
        CreateOrderV2Request(...),
    ],
))
for entry in result.orders:
    if entry.error is not None:
        print("failed:", entry.error)
    else:
        print(entry.order_id, entry.fill_count)

# Cancel
result = client.orders.batch_cancel_v2(request=BatchCancelOrdersV2Request(
    orders=[
        BatchCancelOrdersV2RequestOrder(order_id="ord_a", subaccount=0),
        BatchCancelOrdersV2RequestOrder(order_id="ord_b"),
    ],
))
```

Per-entry error handling is built into `BatchCreateOrdersV2ResponseEntry`
and `BatchCancelOrdersV2ResponseEntry` — successful entries carry the
order/fill data, failed entries carry an `error` dict with the rest of the
fields nulled (create) or zeroed (cancel).

### Asymmetry { #asymmetry }

This trips people up. The V2 spec routes `subaccount` and `exchange_index`
to **different places** depending on the endpoint:

| Endpoint | `subaccount` | `exchange_index` |
|---|---|---|
| `cancel_v2` | query | query |
| `amend_v2` | query | **body** (on `AmendOrderV2Request`) |
| `decrease_v2` | query | **body** (on `DecreaseOrderV2Request`) |
| `create_v2` / `batch_*_v2` | n/a — body on request model | body |

This is faithful to OpenAPI v3.18.0 — `amend_v2`/`decrease_v2` only
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
