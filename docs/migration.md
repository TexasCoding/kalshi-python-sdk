# Migration

## v1.x → v2.0

v2.0 is mostly additive (new `max_pages` kwarg, `KalshiConfig.http2`/`limits`,
`RateLimit` model export). There are **3 deliberate breaking changes** —
all on the response-model surface, all driven by spec-or-server reality.
Migrate by find/replace.

### `Order.type` → `Order.order_type`

Renamed to avoid shadowing the Python builtin (matching the existing
`milestone_type` / `target_type` / `incentive_type` pattern). Wire format
is unchanged — incoming JSON `type` still populates the field via
`validation_alias`.

```python
# v1
order = client.portfolio.orders.get(order_id="...")
print(order.type)        # → AttributeError after upgrade

# v2
print(order.order_type)  # str | None — "limit" or "market"
```

### `AccountApiLimits.read_limit` / `.write_limit` removed

Replaced with `AccountApiLimits.read` / `.write` of type `RateLimit`. The
published OpenAPI spec declares the limits as ints; the live server
actually returns nested token buckets. v2 matches the server. The old int
fields never worked against the live API.

```python
# v1
limits = client.account.limits()
limits.read_limit   # → AttributeError after upgrade

# v2
limits.read.bucket_capacity   # int
limits.read.refill_rate       # int
# new model exposed: kalshi.RateLimit
```

### Response-model count/size/volume fields retyped

Fields like `Market.volume`, `Fill.count`, `Trade.count`,
`MarketPosition.position` were annotated `DollarDecimal` but semantically
represent integer counts. v2 retypes them to `FixedPointCount`. Runtime
values still come back as `Decimal` — only the type annotation changed,
so `mypy --strict` users may need to update narrow assertions.
`isinstance(x, Decimal)` checks remain valid.

### Non-breaking but worth knowing

- **`*_all()` is now unbounded by default.** The previous internal 1000-page
  cap silently truncated callers iterating beyond ~100k items. Cursor-repeat
  guard is still the safety net against server bugs. Pass `max_pages=N` for
  an explicit cap.
- **Response models uniformly use `extra="allow"`.** 5 models (`Page`,
  `Orderbook`, `OrderbookLevel`, `BidAskDistribution`, `PriceDistribution`)
  that previously silently dropped unknown fields now preserve them on
  `__pydantic_extra__`.
- **WS callbacks no longer suppress queue delivery.** Holding both an `@on()`
  callback and an iterator on the same channel now sees both fire. A
  WARNING logs at register-time so the change is visible to upgraders.

See [CHANGELOG.md](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/CHANGELOG.md)
for the full list including the WS recv-loop overhaul (5 reconnect races
fixed), URL/trade-data log-leak scrubs, and spec-sync supply-chain
hardening.

---

## From `kalshi_python_async`

If you're coming from `kalshi_python_async` (the predecessor community
client referenced in the project README), this page summarizes the
v1 SDK differences you'll hit. **If you don't recognize that name, you can
skip this page** — there's nothing here that applies to a greenfield
project on `kalshi-sdk`.

The v1 SDK is a clean rewrite rather than an in-place upgrade, so the move
is closer to a port than a patch. Concrete details below are sourced from
the current SDK; predecessor specifics are documented where they exist
in-tree and called out as **unverified** where they don't.

## Why migrate

- **One transport, two surfaces.** v1 ships hand-crafted sync (`KalshiClient`)
  and async (`AsyncKalshiClient`) clients sharing one transport
  implementation — neither sync-wraps-async nor vice versa.
- **Spec-aligned with drift guards.** Models are generated from the Kalshi
  OpenAPI/AsyncAPI specs, and contract tests fail CI when query, request
  body, or WebSocket payload shapes drift from the spec.
- **`mypy --strict` clean**, `py.typed` shipped, Pydantic v2 models
  end-to-end.
- **Safe-by-default retries.** Only `GET`/`HEAD`/`OPTIONS` retry on transient
  errors; `POST`/`DELETE` never do.
- **v1 stability promise.** Public API is stable as of `1.0.0`; breaking
  changes go through a deprecation cycle.

## Imports

Top-level imports come from `kalshi`:

```python
# v1
from kalshi import (
    KalshiClient,
    AsyncKalshiClient,
    KalshiAuth,
    KalshiConfig,
    CreateOrderRequest,
    Market, Order, Page,
    SideLiteral, ActionLiteral, TimeInForceLiteral,
    KalshiError, KalshiNotFoundError, KalshiRateLimitError,
)
```

WebSocket primitives live in `kalshi.ws`:

```python
from kalshi.ws import KalshiWebSocket, OverflowStrategy, ConnectionState
```

The full export list is in
[`kalshi/__init__.py`](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/__init__.py).

If you previously imported `from kalshi_python_async import ...`, swap to
`from kalshi import ...`. The exact symbol-by-symbol map is **unverified**
— the v1 surface is not a renaming of an upstream surface, it's a new one
that happens to talk to the same API.

## Auth and client construction

```python
# v1 — three equivalent paths
from kalshi import KalshiClient, KalshiAuth

# A) key file path
client = KalshiClient(
    key_id="your-key-id",
    private_key_path="~/.kalshi/private_key.pem",
    demo=True,
)

# B) environment
#   KALSHI_KEY_ID, KALSHI_PRIVATE_KEY_PATH | KALSHI_PRIVATE_KEY,
#   KALSHI_DEMO=true, KALSHI_API_BASE_URL=...
client = KalshiClient.from_env()

# C) pre-built KalshiAuth (useful for sharing auth with the WebSocket client)
auth = KalshiAuth.from_key_path("your-key-id", "~/.kalshi/private_key.pem")
client = KalshiClient(auth=auth, demo=True)
```

Calling private endpoints on an unauthenticated client raises
`AuthRequiredError` before any network call. Public endpoints (market
data, events, exchange status) work on an unauthenticated client.

`demo=True` selects the sandbox base URL and WebSocket URL together. There
is no separate "base URL switch" you have to remember.

The signing scheme — RSA-PSS / SHA256 / MGF1(SHA256) / salt = digest length —
is identical to what every other Kalshi client uses. You don't touch it
yourself; pass the PEM and key id and you're done.

## Resource calls

The v1 resource methods accept two equivalent input styles:

```python
# kwargs (default for most call sites)
order = client.orders.create(
    ticker="KXPRES-24-DJT",
    side="yes",
    action="buy",
    count=10,
    yes_price="0.65",
    time_in_force="good_till_canceled",
)

# request model
from kalshi import CreateOrderRequest
order = client.orders.create(request=CreateOrderRequest(
    ticker="KXPRES-24-DJT",
    side="yes",
    action="buy",
    count=10,
    yes_price="0.65",
    time_in_force="good_till_canceled",
))
```

Mixing the two raises `TypeError`. Phantom kwargs (anything not on the
underlying request model) also raise `TypeError`. Enum-valued kwargs use
`Literal[...]` types (`SideLiteral`, `ActionLiteral`,
`TimeInForceLiteral`, etc.) so typos fail mypy and IDEs auto-complete the
values.

Prices and counts are decimal dollars. Pass `Decimal`, `int`, or `str`;
never `float`. Internally the SDK uses `Decimal` via the custom
`DollarDecimal` Pydantic type.

The async surface mirrors sync method-for-method on `AsyncKalshiClient`.

## WebSockets

The WebSocket client is async-only:

```python
import asyncio
from kalshi import KalshiAuth, KalshiConfig
from kalshi.ws import KalshiWebSocket

async def main() -> None:
    auth = KalshiAuth.from_key_path("your-key-id", "~/.kalshi/private_key.pem")
    config = KalshiConfig.demo()

    ws = KalshiWebSocket(auth=auth, config=config)
    async with ws.connect() as session:
        stream = await session.subscribe_orderbook_delta(tickers=["KXPRES-24-DJT"])
        async for msg in stream:
            print(msg)

asyncio.run(main())
```

If your predecessor used a sync-style streaming API, wrap the entry point
in `asyncio.run(...)`. The Kalshi feed is push-driven; a real sync API would
have to spawn a thread and bridge a queue, which is exactly what we don't
want to ship as a public surface. See
[WebSocket Streaming](websockets.md) for the full guide, including
per-channel subscribe methods, sequence-gap recovery, backpressure
strategies, and automatic reconnection semantics.

## Errors

The exception hierarchy is rooted at `KalshiError`. Subclasses correspond
to HTTP statuses (`KalshiAuthError` for 401/403, `KalshiNotFoundError` for
404, `KalshiValidationError` for 400, `KalshiRateLimitError` for 429,
`KalshiServerError` for 5xx) plus WebSocket-specific siblings
(`KalshiConnectionError`, `KalshiSubscriptionError`, etc.). See
[Error Handling](errors.md) for the full tree and the status-to-exception
map.

If your predecessor raised string-based errors or untyped exceptions, the
common rewrite is to catch the specific class:

```python
# Before (predecessor — unverified shape):
# try:
#     market = api.get_market(ticker)
# except Exception as e:
#     ...

# After
from kalshi import KalshiNotFoundError, KalshiRateLimitError

try:
    market = client.markets.get(ticker)
except KalshiNotFoundError:
    ...
except KalshiRateLimitError as e:
    backoff_seconds = e.retry_after
```

## Pagination

`Page[T]` replaces ad-hoc list responses:

```python
page = client.markets.list(status="open", limit=200)

for market in page:        # iterable over .items
    ...
len(page)                  # items on this page
page.cursor                # next-page cursor (None on the last page)
page.has_next              # bool

# pandas / polars (optional extras)
df = page.to_dataframe()
df = page.to_polars()
```

For multi-page traversal:

```python
# Sync — Iterator[T]
for market in client.markets.list_all(status="open"):
    ...

# Async — AsyncIterator[T], works directly with `async for`
async for market in async_client.markets.list_all(status="open"):
    ...
```

`list_all()` walks cursors until the server returns no more pages, with a
1000-page safety cap and a cursor-repeat detector that raises `KalshiError`
if the server hands back a duplicate cursor.

## Still missing?

If you're porting a specific predecessor call and can't find the v1
equivalent, the [API Reference](reference.md) is the auto-generated
ground truth. Open an issue on
[`TexasCoding/kalshi-python-sdk`](https://github.com/TexasCoding/kalshi-python-sdk/issues)
with the predecessor call and the closest match you found and we'll either
fill in the gap or point to the right method.
