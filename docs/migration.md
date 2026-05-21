# Migration

## v2.2 → v2.3

v2.3 is additive on the REST surface and **soft-breaking on the WebSocket
surface** in one place: `KalshiWebSocket.run_forever()` no longer returns
silently when nothing has been subscribed. Everything else is opt-in.

### `run_forever()` requires an active subscription

Per closed #175 / #185, `KalshiWebSocket.run_forever()` now raises
`KalshiSubscriptionError` at the call site when no `subscribe_*` call has
landed on the session. The previous silent no-op masked a common mistake —
registering an `@ws.on(channel)` callback without subscribing, then
wondering why no frames arrived (the server only sends frames for channels
the client explicitly subscribed to).

```python
# v2.2 — silently returned, recv loop never ran
async with ws.connect() as session:
    await session.run_forever()

# v2.3 — wrap a subscribe_* call before run_forever()
async with ws.connect() as session:
    await session.subscribe_ticker(tickers=["EXAMPLE-25-T"])
    await session.run_forever()
```

No production usage of the silent shape is known; the foot-gun was the
bug.

### Cooperative shutdown via `run_forever(stop_event=...)`

Per closed #177 / #186, `run_forever()` now accepts an optional
`stop_event: asyncio.Event | None = None`. When set, the recv loop
closes the connection and exits cleanly without raising `CancelledError`
— typically wired to `SIGINT` so Ctrl+C drains in-flight dispatches:

```python
import asyncio
import signal

stop = asyncio.Event()
asyncio.get_running_loop().add_signal_handler(signal.SIGINT, stop.set)

async with ws.connect() as session:
    await session.subscribe_ticker(tickers=["EXAMPLE-25-T"])
    await session.run_forever(stop_event=stop)
```

Omitting `stop_event` preserves v2.2 behavior — external cancellation
still propagates.

### WS resubscribe-window frame stashing

Per #176, the reconnect path used to silently drop data frames that
arrived between the moment `SubscriptionManager` cleared its
`sid → client_id` map and the moment the new sids landed in the
subscribe-response handler. Under burst reconnects on high-volume
channels (`ticker`, `trade`, `fill`), this lost tens of messages per
reconnect.

`SubscriptionManager` now stashes those frames in a per-sid bounded
`collections.deque(maxlen=stash_maxlen)` (default 1000 per sid). After
`resubscribe_all` completes, the stash is drained through the normal
dispatch path so seq trackers advance, orderbook state applies, and
iterator consumers receive the frames in arrival order. No API change —
behavior change only.

### Async RSA-PSS sign offload — `KalshiAuth.close()` for standalone users

Per #178, `KalshiAuth.sign_request_async()` now routes the RSA-PSS sign
through a dedicated `ThreadPoolExecutor(max_workers=2)` lazy-initialised
on first use, so signs don't queue behind `getaddrinfo` / file I/O / other
`to_thread()` work during WS reconnect storms.

If you use `KalshiAuth` **through** `KalshiClient` / `AsyncKalshiClient`,
`client.close()` already tears the executor down for you and no migration
is required. If you instantiate `KalshiAuth` **standalone** (e.g. signing
requests through a custom transport), call `auth.close()` to release the
executor:

```python
from kalshi import KalshiAuth

auth = KalshiAuth.from_key_path("your-key-id", "~/.kalshi/private_key.pem")
try:
    headers = await auth.sign_request_async("GET", "/trade-api/v2/markets")
    ...
finally:
    auth.close()
```

---

## v2.1 → v2.2

v2.2 is **soft-breaking at the response-parse boundary only** (per
#157 / #172). The wire format is unchanged. The behavior change: server
omission of a previously-optional spec-required field now raises
`pydantic.ValidationError` at parse time, instead of silently producing
`field=None` and pushing the surprise to a downstream `NoneType`
attribute access.

### What changed

226 fields across REST models, WS payloads, and helper classes flipped
from `Optional[X] = None` to required, matching what the OpenAPI /
AsyncAPI specs already declared.

Affected response model categories include `Market`, `Order`, `Fill`,
`Event`, `EventMetadata`, `Settlement`, `Trade`, `IncentiveProgram`,
`RFQ`, `Quote`, `OrderGroup` plus its three group-response shapes, and
11 WebSocket payloads — including the new `*_ts_ms` millisecond
timestamps and the `outcome_side` / `book_side` direction encoding the
server already emits. See `CHANGELOG.md` for the full per-model
breakdown.

### Recovery

If you parse live responses and previously branched on `field is None`
for an optional you read from the SDK, you may now hit
`pydantic.ValidationError` at the parse site when the server omits the
field on a malformed event. Wrap the call site:

```python
from pydantic import ValidationError

try:
    market = client.markets.get(ticker)
except ValidationError as exc:
    logger.warning("skipping malformed market %s: %s", ticker, exc)
    continue
```

The vast majority of fields were already populated in practice — only
models with legitimate live-server omission gaps need the try/except.
Two known cases (`Event.product_metadata`, `EventMetadata.market_details`)
ship in v2.3 with `server_omits_despite_required` exclusions baked in
and need no caller action.

### `extra="allow"` everywhere

All WS envelope and helper classes (and the five REST helpers from the
v2.0 sweep — `Page`, `Orderbook`, `OrderbookLevel`, `BidAskDistribution`,
`PriceDistribution`) now uniformly use `model_config = ConfigDict(extra="allow")`.
Additive server fields no longer raise; they land on
`__pydantic_extra__` and round-trip through `model_dump()`.

---

## v2.0 → v2.1

v2.1 syncs the SDK to OpenAPI spec v3.18.0. It's **additive at the resource
surface** — eight new endpoints, several new optional kwargs on existing
methods, and one soft-breaking model-construction change called out below.
Code that only consumes the SDK's responses needs no edits; code that
constructs models directly in tests/mocks needs one small update.

### `Balance.balance_dollars` — required, soft-breaking at construction

Spec v3.18.0 adds `balance_dollars: FixedPointDollars` to
`GetBalanceResponse` as a required field. The server now guarantees it, so
callers parsing API responses (`client.portfolio.balance()`) are unaffected.
**But** any code that builds `Balance(...)` directly — typically test mocks
— will hit `ValidationError` until it adds the field.

```python
# v2.0 — broken in v2.1
Balance(balance=50000, portfolio_value=75000, updated_ts=ts)

# v2.1
Balance(
    balance=50000,
    balance_dollars=Decimal("500.00"),   # new required field
    portfolio_value=75000,
    updated_ts=ts,
)
```

The accompanying optional `balance_breakdown: list[IndexedBalance] | None`
splits the total across exchange shards when present. `IndexedBalance.balance`
is `DollarDecimal` (matching `balance_dollars` units), not cents — same
field name as `Balance.balance` but a different type. Be deliberate when
reading from `balance.balance_breakdown[i].balance`.

### V2 event-market orders

Six new methods on `OrdersResource` / `AsyncOrdersResource` hit the new
`/portfolio/events/orders/*` paths:

- `create_v2(*, request: CreateOrderV2Request)`
- `cancel_v2(order_id, *, subaccount, exchange_index)`
- `amend_v2(order_id, *, request: AmendOrderV2Request, subaccount)`
- `decrease_v2(order_id, *, request: DecreaseOrderV2Request, subaccount)`
- `batch_create_v2(*, request: BatchCreateOrdersV2Request)`
- `batch_cancel_v2(*, request: BatchCancelOrdersV2Request)`

Legacy `/portfolio/orders` keeps working and will be deprecated no earlier
than May 6, 2026. No migration is required to stay on v1 paths. New
event-market trading should target the V2 family for the cleaner shape
(single `bid`/`ask` side, single `price` field, explicit idempotency).

Two important differences from V1:

1. **`client_order_id` is required** on `CreateOrderV2Request` and acts as
   the server-side idempotency key. Reusing a value returns the original
   order rather than placing a new one. Use a fresh UUID4 per call.
2. **`side` uses `BookSideLiteral` (`"bid"` / `"ask"`)**, not V1's
   `SideLiteral` (`"yes"` / `"no"`).

### Spec-driven asymmetry on V2 amend/decrease

`amend_v2` and `decrease_v2` accept `subaccount` as a **resource-method
kwarg** (query param on the wire) but read `exchange_index` from the
**request body**. `cancel_v2` differs again — both are query params there,
because that endpoint has no body. This mirrors the spec exactly:

```python
client.orders.amend_v2(
    "ord-1",
    subaccount=3,                          # query param
    request=AmendOrderV2Request(
        ticker="EVENT-MKT", side="bid",
        price=Decimal("0.55"),
        count=Decimal("10"),
        exchange_index=0,                  # body field
    ),
)
```

### New optional kwargs on existing endpoints

All additive — existing call sites keep working:

- `orders.cancel(*, exchange_index)`, `order_groups.delete(*, exchange_index)`
- `communications.list_rfqs(*, user_filter)`, `communications.list_all_rfqs(*, user_filter)`
- `communications.list_quotes(*, user_filter, rfq_user_filter)`, `communications.list_all_quotes(*, user_filter, rfq_user_filter)`. `user_filter="self"` and `rfq_user_filter="self"` are now standalone satisfiers for the server-side filter requirement (previously only `quote_creator_user_id` / `rfq_creator_user_id` worked).
- `incentive_programs.list(*, incentive_description)` and the `list_all` variant.
- `CreateQuoteRequest.post_only` — pass `post_only=True` to `create_quote()`.
- `exchange_index` on order/amend/decrease/batch-cancel request models.

### New endpoints (additive)

- `portfolio.deposits()` / `portfolio.deposits_all()` — deposit history.
- `portfolio.withdrawals()` / `portfolio.withdrawals_all()` — withdrawal history.
- `account.endpoint_costs()` — token costs for endpoints whose cost differs
  from the default.

### New public types

Added to `kalshi.*` and `kalshi.models.*`:

- Literals: `BookSideLiteral`, `UserFilterLiteral`, `PaymentStatusLiteral`, `PaymentTypeLiteral`.
- Models: `Deposit`, `Withdrawal`, `IndexedBalance`, `AccountEndpointCosts`, `EndpointTokenCost`, and the V2 request/response family.

---

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

`list_all()` is unbounded by default — it walks cursors until the server
returns no more pages. Pass `max_pages=N` for an explicit cap; passing
`max_pages=0` raises `ValueError`. The cursor-repeat detector still raises
`KalshiError` if the server hands back a duplicate cursor. See
[Pagination](pagination.md) for the canonical contract.

## Still missing?

If you're porting a specific predecessor call and can't find the v1
equivalent, the [API Reference](reference.md) is the auto-generated
ground truth. Open an issue on
[`TexasCoding/kalshi-python-sdk`](https://github.com/TexasCoding/kalshi-python-sdk/issues)
with the predecessor call and the closest match you found and we'll either
fill in the gap or point to the right method.
