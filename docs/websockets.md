# WebSocket

The SDK ships an async-only WebSocket client, `KalshiWebSocket`, that covers
all 12 Kalshi channels. It handles RSA-PSS auth on the upgrade handshake,
per-subscription sequence-gap detection, automatic reconnection with
re-subscription, and a configurable backpressure strategy on each per-channel
queue.

There is no sync WebSocket client. Wrap calls in `asyncio.run(...)` from sync
code.

The wire protocol is documented in the
[AsyncAPI spec](https://docs.kalshi.com/asyncapi.yaml). This page is the
SDK's perspective on it.

## Overview

`KalshiWebSocket` exposes:

- A `connect()` async context manager that opens the underlying socket and
  starts the background receive loop.
- A typed `subscribe_<channel>()` method per channel, each returning an async
  iterator of fully-parsed Pydantic messages.
- A generic `subscribe(channel, params=..., overflow=..., maxsize=...)` for
  forward compatibility.
- An `@ws.on(channel)` decorator for a callback-style API (which **fans out
  alongside** iterators rather than replacing them).
- An `orderbook(ticker)` helper that yields a maintained `Orderbook` snapshot
  on every delta.
- `on_state_change=` and `on_error=` hooks on the constructor for observability.

## The 12 channels

| SDK method | Wire channel | Message `type` field | Message class | Auth |
|---|---|---|---|---|
| `subscribe_ticker` | `ticker` | `ticker` | `TickerMessage` | public |
| `subscribe_trade` | `trade` | `trade` | `TradeMessage` | public |
| `subscribe_orderbook_delta` | `orderbook_delta` | `orderbook_snapshot` → `orderbook_delta` | `OrderbookSnapshotMessage` / `OrderbookDeltaMessage` | public |
| `subscribe_market_lifecycle` | `market_lifecycle_v2` | `market_lifecycle_v2` / `event_fee_update` | `MarketLifecycleMessage` / `EventFeeUpdateMessage` | public |
| `subscribe_multivariate` | `multivariate` | `multivariate_lookup` | `MultivariateMessage` | public |
| `subscribe_multivariate_lifecycle` | `multivariate_market_lifecycle` | `multivariate_market_lifecycle` | `MultivariateLifecycleMessage` | public |
| `subscribe_fill` | `fill` | `fill` | `FillMessage` | private |
| `subscribe_user_orders` | `user_orders` | `user_order` (singular) | `UserOrdersMessage` | private |
| `subscribe_market_positions` | `market_positions` | `market_position` (singular) | `MarketPositionsMessage` | private |
| `subscribe_order_group` | `order_group_updates` | `order_group_updates` | `OrderGroupMessage` | private |
| `subscribe_communications` | `communications` | `communications` | `CommunicationsMessage` | private |
| `subscribe_cfbenchmarks_value` | `cfbenchmarks_value` | `cfbenchmarks_value` / `cfbenchmarks_value_indexlist` | `CFBenchmarksValueMessage` / `CFBenchmarksIndexListMessage` | private |

The `type` column matters when filtering raw logs — note the singular forms
for `user_order`, `market_position`, and the `multivariate_lookup` /
`multivariate` mismatch.

!!! warning "Migration (v3.1.0): `event_fee_update` rides `market_lifecycle_v2`"
    Since the v3.20.0 spec sync (SDK v3.1.0) the `market_lifecycle_v2` channel
    also emits `event_fee_update` frames (event-level fee override set or
    cleared), so
    `subscribe_market_lifecycle()` now yields
    `MarketLifecycleMessage | EventFeeUpdateMessage`. **Existing consumers must
    discriminate on `.type` before touching payload fields** — an
    `EventFeeUpdatePayload` has no `market_ticker`, so naive access raises
    `AttributeError`:

    ```python
    async for msg in session.subscribe_market_lifecycle():
        if msg.type == "event_fee_update":
            print(msg.msg.event_ticker, msg.msg.fee_type_override)  # None when cleared
        else:  # market_lifecycle_v2
            print(msg.msg.market_ticker, msg.msg.event_type)
    ```

    This is a second message **type** on the same channel — it does not add a
    channel. The override payload mirrors the REST
    [`EventFeeChange`](resources/events.md#event-fee-changes):
    `EventFeeUpdatePayload` carries `event_ticker`, `fee_type_override`, and
    `fee_multiplier_override` (the latter two `None` when the override is
    cleared).

Two channels carry monotonic `seq` numbers and have built-in sequence-gap
recovery: `orderbook_delta` (which delivers both snapshot and delta envelopes
under one subscription) and `order_group_updates`.

## CF Benchmarks index values

The auth-required `cfbenchmarks_value` channel (new in v4.0.0) streams CF
Benchmarks reference index values — e.g. `BRTI` (Bitcoin Real-Time Index) and
`ETHUSD_RTI` — each with a trailing 60-second average and, only in the final
minute before a quarter-hour close (`:00`/`:15`/`:30`/`:45`), a quarter-hour
windowed average.

Seed the index list at subscribe time with `index_ids` (`["all"]` tracks every
available index). The stream yields a **union** of `CFBenchmarksValueMessage`
(data) and `CFBenchmarksIndexListMessage` (the response to an `indexlist`
action), so discriminate with `isinstance` (or `msg.type`) before reading
`msg.msg`. The `data` field is the raw upstream CF Benchmarks JSON frame as a
string — call `json.loads(...)` to parse it.

```python
import json
from kalshi.ws.models import CFBenchmarksIndexListMessage, CFBenchmarksValueMessage

async for msg in session.subscribe_cfbenchmarks_value(index_ids=["BRTI", "ETHUSD_RTI"]):
    if isinstance(msg, CFBenchmarksValueMessage):
        frame = json.loads(msg.msg.data)            # raw upstream frame
        avg60 = msg.msg.avg_60s_data.value          # trailing 60s average (Decimal)
        q15 = msg.msg.last_60s_windowed_average_15min  # None outside the final minute
    else:  # CFBenchmarksIndexListMessage
        print(msg.msg.index_ids)                    # available index IDs
```

Subscribing with no `index_ids` yields nothing until indices are added; this
channel does not accept `market_ticker`/`market_tickers`. The
`CFBenchmarksValueMessage`, `CFBenchmarksValuePayload`, `CFBenchmarksAvgData`,
`CFBenchmarksIndexListMessage`, and `CFBenchmarksIndexListPayload` models are
exported from `kalshi.ws.models`.

## Connect and subscribe

```python
import asyncio
from kalshi import KalshiAuth, KalshiConfig
from kalshi.ws import KalshiWebSocket

async def main() -> None:
    auth = KalshiAuth.from_key_path("your-key-id", "~/.kalshi/private_key.pem")
    config = KalshiConfig.demo()  # or KalshiConfig.production()

    ws = KalshiWebSocket(auth=auth, config=config)
    async with ws.connect() as session:
        stream = await session.subscribe_ticker(tickers=["KXPRES-24-DJT"])
        async for msg in stream:
            print(msg.msg.market_ticker, msg.msg.yes_bid, msg.msg.yes_ask)

asyncio.run(main())
```

`ws.connect()` returns an async context manager. Inside the block, `session`
is the same `KalshiWebSocket` — re-bound for clarity that the socket is now
open. Exiting the block sends graceful sentinels to all active iterators and
closes the socket with code 1000.

`subscribe_*` methods return an async iterator. Iterate it directly with
`async for`; the iterator stops when the socket closes or the subscription is
torn down.

You can hold multiple subscriptions in parallel — each has its own bounded
queue, and the background receive loop fans messages out:

```python
async with ws.connect() as session:
    ticker_stream = await session.subscribe_ticker(tickers=["KXPRES-24-DJT"])
    fill_stream = await session.subscribe_fill()

    async def pump_tickers() -> None:
        async for msg in ticker_stream:
            ...

    async def pump_fills() -> None:
        async for msg in fill_stream:
            ...

    await asyncio.gather(pump_tickers(), pump_fills())
```

### Callback style

Register handlers with `@ws.on(channel)`. The message passed to your callback
is the typed Pydantic model for that channel.

```python
from kalshi.ws.models import TickerMessage

ws = KalshiWebSocket(auth=auth, config=config)

@ws.on("ticker")
async def on_ticker(msg: TickerMessage) -> None:
    print(msg.msg.yes_bid)

async with ws.connect() as session:
    # Subscribing is what tells the server to send frames; the @ws.on
    # callback above is purely the routing destination. The iterator
    # returned by subscribe_ticker is unused here — callbacks fan out
    # alongside iterators, so registering the callback is enough.
    await session.subscribe_ticker(tickers=["EXAMPLE-25-T"])
    await session.run_forever()
```

`run_forever()` raises ``KalshiSubscriptionError`` if no ``subscribe_*`` call
has landed in the session — a callback alone doesn't tell the server to
send frames, and the previous silent-no-op behavior was a foot-gun (#175).

### Cooperative shutdown

Pass an ``asyncio.Event`` to ``run_forever(stop_event=...)`` to terminate
the recv loop without raising ``CancelledError``. The canonical pattern
wires the event to ``SIGINT`` so Ctrl+C drains in-flight dispatches,
closes the WebSocket cleanly, and returns:

```python
import asyncio
import signal

stop = asyncio.Event()
asyncio.get_running_loop().add_signal_handler(signal.SIGINT, stop.set)

async with ws.connect() as session:
    await session.subscribe_ticker(tickers=["EXAMPLE-25-T"])
    await session.run_forever(stop_event=stop)
```

When the event fires, ``run_forever()`` clears ``_running``, closes the
connection, and awaits the recv loop's natural exit. No ``CancelledError``
leaks out (#177). Without ``stop_event``, external cancellation still
propagates as before.

`on()` works both before and after `connect()`; callbacks registered before
the socket opens are buffered and applied when the session starts.

!!! info "Callbacks fan out, they don't replace iterators"
    When a callback is registered for a channel that also has an active
    `subscribe_*` iterator, **both** the callback and the iterator receive the
    message. A warning is logged so you know it's happening. If you want
    callback-only routing, don't call `subscribe_*` on the same channel.

### Generic `subscribe()`

For channels the SDK adds later than your installed version, the generic
escape hatch is:

```python
stream = await session.subscribe(
    "some_new_channel",
    params={"market_tickers": [...]},
)
async for raw in stream:
    ...  # raw is a dict; you parse it
```

Only these param keys are forwarded to the server (others are silently
dropped): `market_ticker`, `market_tickers`, `market_id`, `market_ids`,
`shard_factor`, `shard_key`, `send_initial_snapshot`, `skip_ticker_ack`.

## Sequence-gap detection

`orderbook_delta` and `order_group_updates` messages carry a monotonic `seq`.
The SDK tracks the last `seq` per server `sid` and flags a gap when it sees
`seq > last + 1`.

When a gap is detected:

1. The offending message is **dropped** without being dispatched.
2. The per-`sid` sequence tracker is reset, and for `orderbook_delta` the
   local book for the affected ticker is cleared.
3. The next server snapshot rebootstraps state.
4. Duplicates (`seq <= last`) are silently ignored.

The built-in receive loop **does not raise** `KalshiSequenceGapError` — it
recovers silently. The exception class exists for callers wiring their own
resync logic on top of `subscribe(channel, ...)` against a custom tracker.

If recovery never lands — e.g. the server stops sending the channel — your
iterator stays open but produces nothing. Watch
[connection state](#connection-state) for clues.

## Backpressure

Every per-channel iterator is fed by a bounded `MessageQueue`. What happens
when the queue fills depends on `OverflowStrategy`:

| Strategy | Behavior | Default for |
|---|---|---|
| `DROP_OLDEST` | Ring-buffer: evict oldest, keep newest. | `ticker`, `trade`, `fill`, `user_orders`, `market_positions`, `market_lifecycle`, `multivariate`, `multivariate_lifecycle`, `communications` |
| `ERROR` | Raise `KalshiBackpressureError` from the producer side. | `orderbook_delta`, `order_group_updates` |

The choice tracks state semantics: latest-wins channels (`ticker`) survive a
drop; stateful, sequenced channels (`orderbook_delta`) can't — a missed delta
is a corrupted book, which is exactly what sequence-gap detection catches.

Override per call:

```python
from kalshi.ws import OverflowStrategy

stream = await session.subscribe_ticker(tickers=[...], maxsize=10_000)
stream = await session.subscribe(
    "orderbook_delta",
    params={"market_tickers": [...], "send_initial_snapshot": True},
    overflow=OverflowStrategy.DROP_OLDEST,  # don't do this unless you know
    maxsize=10_000,
)
```

Default `maxsize=1000` for explicit subscriptions, `100` for the `orderbook()`
helper.

!!! danger "Backpressure on ERROR channels is fatal"
    When `KalshiBackpressureError` fires in the receive loop, it is treated as
    **fatal**: the loop broadcasts sentinels to every active iterator and
    exits. Your `async for` blocks end via `StopAsyncIteration`. The connection
    state moves to `CLOSED`. Wire `on_error=` and `on_state_change=` on the
    constructor to observe this.

    The same fatal-teardown behavior applies to `KalshiSubscriptionError`
    encountered mid-stream.

## Orderbook helper

If you want full books rather than raw deltas:

```python
async with ws.connect() as session:
    async for book in await session.orderbook("KXPRES-24-DJT"):
        print(book.yes[0], book.no[0])
```

`orderbook()` wraps `subscribe_orderbook_delta`, applies snapshots/deltas to
an internal `OrderbookManager`, and yields a fresh `kalshi.models.markets.Orderbook`
on each update. Each yielded book is a new instance — your consumer can hold
on to it without worrying about mutation.

A delta arriving before a snapshot logs a warning and is dropped. A `seq` gap
triggers a snapshot-driven rebuild as described above.

## Reconnection

If the underlying socket drops (server hangup, transient network error, ping
timeout), the receive loop transitions to `RECONNECTING` and retries the
connect with the same full-jitter formula as the REST transport
(`random.uniform(0, min(retry_base_delay * 2 ** attempt, retry_max_delay))`),
up to `KalshiConfig.ws_max_retries` (default 10).

On a successful reconnect:

1. All active subscriptions are re-issued. Server `sid`s change; the SDK
   tracks each subscription by a durable client-side id and rebuilds the
   `sid → client_id` map. Per-sub failures are isolated — a failing
   resubscribe drops just that one queue, the rest continue.
2. Sequence trackers are reset.
3. The local orderbook cache is cleared. `orderbook_delta` subscriptions are
   re-issued with `send_initial_snapshot: true` so the book is re-bootstrapped
   from a fresh snapshot.
4. Active iterators keep yielding — they reference the durable client-side
   ids, not the server `sid`s.

### Resubscribe-window frame stashing

Between the moment `resubscribe_all` clears the `sid → client_id` map (to
prevent stale-sid mis-routing on per-sub failures) and the moment the new
sids land in the wait-for-subscribe-response handler, the server can already
send data frames on the freshly-assigned sids. Without buffering, those
frames have no destination yet and would be silently dropped. Under burst
reconnects on high-volume channels (`ticker`, `trade`, `fill`), this could
lose tens of messages per reconnect.

`SubscriptionManager` stashes those frames in a per-sid bounded
`collections.deque(maxlen=stash_maxlen)` for the duration of
`resubscribe_all`. After resubscribe completes, `_handle_reconnect` drains
the stash through the normal dispatch path so the seq tracker advances,
orderbook state applies, and iterator consumers receive them in arrival
order.

The stash is bounded by an internal `stash_maxlen=1000` per sid — generous
enough for normal market-burst reconnects, low enough to bound memory if
resubscribe stalls (not user-configurable on `KalshiWebSocket`). On
overflow, oldest evicts (deque semantics) and a WARNING fires **once per
sid per resubscribe cycle** so the caller notices congestion without log
spam. Worst-case memory is bounded at
`stash_maxlen × len(active_subs) × avg_frame_size`. Frames whose sid never
gets re-mapped (a per-sub failure during resubscribe) are dropped on drain
with a debug log — there's no consumer to deliver them to.

If `ws_max_retries` is exhausted, the receive loop pushes sentinels to all
active queues (so `async for` terminates cleanly) and exits. The connection
state ends at `CLOSED`.

### Connection state

```python
from kalshi.ws import ConnectionState

async def on_state(old: ConnectionState, new: ConnectionState) -> None:
    print(f"{old.value} -> {new.value}")

ws = KalshiWebSocket(auth=auth, config=config, on_state_change=on_state)
```

Possible states: `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `STREAMING`,
`RECONNECTING`, `CLOSED`.

### Heartbeat

Heartbeat uses `websockets`' built-in keepalive: `ping_interval=20`,
`ping_timeout=heartbeat_timeout` (constructor arg, default 30s). A missed pong
trips reconnect.

## Error observability

```python
from kalshi.ws.models import ErrorMessage

async def on_error(err: ErrorMessage) -> None:
    print("WS error:", err.msg.code, err.msg.message)

ws = KalshiWebSocket(auth=auth, config=config, on_error=on_error)
```

The `on_error` hook receives both server-sent error envelopes and synthesized
errors from internal failures (e.g. unknown message types, dispatch
exceptions). Pair it with `on_state_change` for a complete picture of session
health.

## Auth on the WebSocket

`KalshiWebSocket` signs an RSA-PSS `GET` against the WebSocket URL's path and
sends the signature as headers on the upgrade handshake — same scheme as
REST. There's no token in the URL, no signed message after open. The signature
is re-computed on every reconnect attempt.

Public channels (ticker, trade, orderbook_delta, market_lifecycle,
multivariate, multivariate_lifecycle) work without auth — pass
`auth=None` if you don't need private channels.

## Performance

The WebSocket client is built for sustained automated-trading workloads, but
throughput is bounded by a few knobs you control. This section is the practical
tuning guide.

### Typical message rates per channel

Observed at-the-money on active election / sports markets. Treat as orders of
magnitude, not SLAs — Kalshi's wire rates vary with volatility, time-of-day,
and how busy the underlying market is.

| Channel | Typical msg/s (active market) | Burst peak |
|---|---|---|
| `ticker` | 1–10 | 100s during pricing events |
| `trade` | 0.1–5 | 100s on bulk fills |
| `orderbook_delta` | 10–200 | low thousands during market open / news |
| `fill` / `user_orders` | 0.1–10 (your own activity) | bounded by your order rate |
| `market_lifecycle` / `multivariate_lifecycle` | < 1 | bursts on bulk settlement |
| `market_positions` | < 1 (one update per position change) | bounded by your activity |
| `order_group_updates` | < 1 per group | bounded by group size |
| `communications` | < 1 (RFQ/Quote lifecycle) | bursts during quote storms |

### Queue sizing rule of thumb

Each per-channel iterator is fed by a bounded `MessageQueue` of size `maxsize`.
The safe default is:

```
maxsize >= 2 * peak_burst_per_second
```

That gives a 500ms cushion before backpressure triggers — long enough to absorb
typical GIL stalls / GC pauses, short enough that a slow consumer surfaces
quickly. For `orderbook_delta` on hot markets, prefer `maxsize=10_000` and an
ERROR overflow strategy so a stuck consumer halts the loop rather than
silently corrupting book state.

### Overflow strategy choice

| Strategy | Use for | Why |
|---|---|---|
| `DROP_OLDEST` | Read-only / coalesced feeds: `ticker`, `trade`, `market_lifecycle`, `multivariate*`, `user_orders` | Newest sample is the one that matters; an evicted old frame is recoverable from the next one. |
| `ERROR` | Stateful, sequenced feeds: `orderbook_delta`, `order_group_updates` | A dropped delta corrupts derived state (the reconstructed book / order-group tracking). Surface the backpressure to the consumer rather than continuing on corrupted state. |

`ERROR` is fatal — the recv loop broadcasts sentinels and exits when it fires
(see [Backpressure](#backpressure)). Wire `on_error=` / `on_state_change=` to
observe.

### `orderbook_delta` cost vs orderbook depth

`orderbook_delta` carries the highest CPU cost of any channel: every frame
triggers Pydantic validation, dispatch routing, sequence-tracker update, and
(if you use the `orderbook()` helper) a fresh `Orderbook` snapshot allocation.
If you only need top-of-book, use `ticker` instead — it's an order of magnitude
cheaper per message.

If you do need the full book, hold the `Orderbook` references your consumer
received rather than re-fetching depth on demand; the SDK already maintains the
book incrementally per-ticker.

### Pluggable JSON loader

The default loader is `json.loads`. For high-volume channels (`ticker`,
`orderbook_delta`), swap in [`orjson`](https://github.com/ijl/orjson) — typically
2–3x faster on the parse path:

```python
import orjson
from kalshi import KalshiConfig

config = KalshiConfig(
    ws_json_loads=orjson.loads,
    ws_json_dumps=orjson.dumps,
)
```

`orjson.dumps` returns `bytes`; the SDK passes that straight to the underlying
`websockets` client, which accepts both `bytes` and `str` payloads. Set either
loader independently; `None` (the default) falls back to the stdlib `json`
module.

### Single-threaded recv loop

Dispatch runs on a single asyncio task. Any blocking work in `on_error=`,
`on_state_change=`, or `@ws.on(channel)` callbacks blocks every other channel
for the duration. The rules:

- Keep callbacks `async`-only and non-blocking. Push work to a background task
  / queue if you need to do anything that takes more than ~1ms.
- Don't do synchronous I/O (network, disk, `print()` to a slow tty) in a
  callback.
- Use the iterator API for heavy consumers — each iterator runs on its own
  task, so a slow consumer only stalls its own queue (until `maxsize` fills,
  which then triggers your overflow strategy).

A slow `on_error` handler is the most common foot-gun: it runs inline on the
recv loop, so a 500ms blocking log call multiplies the effective error
recovery time.

## Reference

::: kalshi.ws.client.KalshiWebSocket

::: kalshi.ws.connection.ConnectionState

::: kalshi.ws.backpressure.OverflowStrategy

::: kalshi.ws.backpressure.MessageQueue
