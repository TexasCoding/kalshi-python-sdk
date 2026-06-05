# Retries & idempotency

Retries are conservative by design: the wrong retry on the wrong verb is how
duplicate orders happen.

## What retries

| Verb | Retries on |
|---|---|
| `GET`, `HEAD`, `OPTIONS` | `408`, `425`, `429`, `500`, `502`, `503`, `504`, `520`, `521`, `522`, `523`, `524` |
| `POST`, `PUT`, `DELETE` | **never** |

POST/DELETE/PUT are write paths. Retrying them risks duplicate orders,
duplicate cancels, duplicate transfers — even with `client_order_id`, you
still need to know whether the first attempt landed. The SDK forces that
decision back to your application code.

What does **not** retry, even on a retryable verb:

- `400`, `401`, `403`, `404` — permanent client errors. Fix the request.
- Non-timeout transport errors (DNS resolution failure, TLS handshake,
  connection reset) — raised immediately as `KalshiError`.
- Pydantic response-validation failure — raised immediately.

## Backoff

When a retry is scheduled, the wait time uses **AWS Full Jitter**:

```
sleep = random.uniform(0, min(retry_base_delay * 2 ** attempt, retry_max_delay))
```

Full jitter spreads colliding clients evenly across the whole capped window —
the opposite of fixed-magnitude jitter, which bunches retries into a narrow
sub-window and amplifies thundering-herd patterns.

With defaults (`retry_base_delay=0.5`, `retry_max_delay=30.0`,
`max_retries=3`), worst-case sleeps are:

| Attempt | Cap (s) | Range (s) |
|---|---|---|
| 0 | 0.5 | 0 – 0.5 |
| 1 | 1.0 | 0 – 1.0 |
| 2 | 2.0 | 0 – 2.0 |

Total worst-case retry wait: **~3.5 seconds** with defaults. Three attempts
plus the original = four requests max.

## `Retry-After` handling

On `429`, the server's `Retry-After` header is honored — **capped** at
`retry_max_delay`. The cap is a safety: a hostile or misconfigured server
can't stall the client with `Retry-After: 99999`.

The header is only honored when it parses as a non-negative finite number.
`Retry-After: 0` is honored (sleeps 0). HTTP-date form, `NaN`, negatives, and
non-numeric values fall back to the computed full-jitter backoff.

When retries are exhausted, the last `KalshiRateLimitError` is raised with
`.retry_after` populated from the header — so application-level retry logic
can see the hint.

## Timeouts

`KalshiConfig.timeout` is a single float that maps to `httpx.Timeout(timeout)`
— it applies to connect, read, write, and pool together. There is no per-phase
configuration today; pass a single value or accept the 30-second default.

- Timeout on a retryable verb (`GET`/`HEAD`/`OPTIONS`) retries with the same
  backoff schedule. The final timeout is wrapped in `KalshiError` with
  `__cause__` set to the underlying `httpx.TimeoutException`.
- Timeout on `POST`/`DELETE` raises `KalshiError` immediately, no retry. **The
  request may or may not have landed** — reconcile with a follow-up `get` or
  `list`.

## Tuning

```python
from kalshi import KalshiClient, KalshiConfig

config = KalshiConfig(
    timeout=10.0,
    max_retries=5,
    retry_base_delay=0.25,
    retry_max_delay=15.0,
)
client = KalshiClient(key_id="...", private_key_path="...", config=config)
```

There are no environment variables for these knobs — pass a `KalshiConfig`
explicitly.

## Idempotency

POST/DELETE/PUT not retrying means **idempotency is your responsibility** on
write paths. The patterns that work:

### `client_order_id` on `orders.create` / `orders.amend`

Set a unique `client_order_id` (a UUID is fine). On a network failure between
"server processed the order" and "you got the response":

1. Catch the exception.
2. Call `client.orders.list(min_ts=..., max_ts=...)` and look for the
   `client_order_id` you supplied.
3. If it's there, the order landed. If it isn't, retry safely.

```python
import uuid
from kalshi import KalshiClient, KalshiError

with KalshiClient.from_env() as client:
    cid = str(uuid.uuid4())
    try:
        order = client.orders.create(
            ticker="X", side="yes", action="buy", count=10,
            yes_price="0.65", client_order_id=cid,
        )
    except KalshiError:
        # Did it land? Find out before retrying.
        existing = next(
            (o for o in client.orders.list_all() if o.client_order_id == cid),
            None,
        )
        if existing is None:
            order = client.orders.create(
                ticker="X", side="yes", action="buy", count=10,
                yes_price="0.65", client_order_id=cid,
            )
        else:
            order = existing
```

### `client_transfer_id` on `subaccounts.transfer`

Same pattern as `client_order_id`, but for inter-subaccount money movement.
Reconcile via `subaccounts.list_transfers()`.

### Cancels

`client.orders.cancel(order_id)` and `client.orders.batch_cancel(...)` are
already idempotent server-side: re-canceling a canceled order is a no-op. You
can safely retry these from your app layer without dedupe logic.

### Reads

Just call them again. The transport's built-in retry covers transient 5xx.

## Reconciliation after a 5xx on a write

`KalshiServerError` from `POST /portfolio/orders` is ambiguous — the order
might have made it into the book before the server gave up. The recovery:

1. Wait briefly (a few seconds — orders propagate fast).
2. List recent orders matching your `client_order_id`.
3. If present, you're done. If absent, retry with the same `client_order_id`.

The `client_order_id` round-trips on `Order.client_order_id`, so step 2 is
just a `next(...)` over `client.orders.list_all(status="resting")`.

## WebSocket retries

The WebSocket has its own retry budget: `KalshiConfig.ws_max_retries` (default
10). Same full-jitter formula, same `retry_base_delay` / `retry_max_delay`
caps. If the budget runs out, the receive loop pushes sentinels to every
active iterator (so `async for` terminates cleanly) and the connection state
ends at `CLOSED`. Call `ws.connect()` again from your app to restart.
