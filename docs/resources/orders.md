# Orders

Place, amend, cancel, and inspect orders. The largest single resource in the
SDK and the surface you'll spend the most time with as a trader.

Every method here requires auth.

## Quick reference

| Method | Endpoint | Retry |
|---|---|---|
| `create(...)` | `POST /portfolio/orders` | **never** — see [Retries & idempotency](../retries.md) |
| `batch_create(orders)` | `POST /portfolio/orders/batched` | never |
| `get(order_id)` | `GET /portfolio/orders/{order_id}` | yes (GET) |
| `list(...)` / `list_all(...)` | `GET /portfolio/orders` | yes |
| `cancel(order_id, *, subaccount=None)` | `DELETE /portfolio/orders/{order_id}` | never |
| `batch_cancel(orders)` | `DELETE /portfolio/orders/batched` | never |
| `amend(order_id, ...)` | `POST /portfolio/orders/{order_id}/amend` | never |
| `decrease(order_id, *, reduce_by, reduce_to)` | `POST /portfolio/orders/{order_id}/decrease` | never |
| `fills(...)` / `fills_all(...)` | `GET /portfolio/fills` | yes |
| `queue_positions(*, market_tickers, event_ticker)` | `GET /portfolio/orders/queue_positions` | yes |
| `queue_position(order_id)` | `GET /portfolio/orders/{order_id}/queue_position` | yes |

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

## Reference

::: kalshi.resources.orders.OrdersResource
    options:
      heading_level: 3

::: kalshi.resources.orders.AsyncOrdersResource
    options:
      heading_level: 3
