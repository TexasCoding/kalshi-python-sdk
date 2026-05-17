# WebSocket Streaming

The SDK ships an async-only WebSocket client, `KalshiWebSocket`, that covers
all 11 Kalshi channels. It handles RSA-PSS auth on the upgrade handshake,
per-subscription sequence-gap detection, automatic reconnection with
re-subscription, and a configurable backpressure strategy on each per-channel
queue.

There is no sync WebSocket client. The Kalshi API is push-driven and live
data is fundamentally async — wrap it in `asyncio.run(...)` if you need to
call it from sync code.

The wire protocol is documented in the
[AsyncAPI spec](https://docs.kalshi.com/asyncapi.yaml). This page is the
SDK's perspective on it.

## Overview

`KalshiWebSocket` exposes:

- A `connect()` async context manager that opens the underlying socket and
  starts the background receive loop.
- A typed `subscribe_<channel>()` method per channel, each returning an
  async iterator of fully-parsed Pydantic messages.
- A generic `subscribe(channel, params=...)` for forward compatibility.
- An `on(channel)` decorator for a callback-style API.
- An `orderbook(ticker)` helper that yields a maintained `Orderbook`
  snapshot on every delta.

The 11 channels:

| Channel | Auth | Per-message | Description |
|---|---|---|---|
| `ticker` | public | `TickerMessage` | Best bid/ask + volume per market. |
| `trade` | public | `TradeMessage` | Executed prints. |
| `orderbook_delta` | public | `OrderbookSnapshotMessage` then `OrderbookDeltaMessage` | Full L2 book deltas, sequenced. |
| `market_lifecycle_v2` | public | `MarketLifecycleMessage` | Market open/close/settle transitions. |
| `multivariate` | public | `MultivariateMessage` | Multivariate market events. |
| `multivariate_market_lifecycle` | public | `MultivariateLifecycleMessage` | Multivariate market lifecycle. |
| `fill` | private | `FillMessage` | Your fills. |
| `user_orders` | private | `UserOrdersMessage` | Your order status changes. |
| `market_positions` | private | `MarketPositionsMessage` | Your position deltas. |
| `order_group_updates` | private | `OrderGroupMessage` | Order-group state changes, sequenced. |
| `communications` | private | `CommunicationsMessage` | RFQ / quote events. |

`subscribe_market_lifecycle()`, `subscribe_order_group()`,
`subscribe_multivariate_lifecycle()` map to the wire channel names in the
table above. The SDK method names drop the `_v2` / `_updates` /
`_market_lifecycle` suffixes for ergonomics.

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
`async for`; the iterator stops when the socket closes.

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

If you'd rather register handlers than iterate, use `ws.on(channel)`. The
message passed to your callback is the typed Pydantic model for that channel
— `TickerMessage` here, `FillMessage` for `fill`, etc. — not a raw `dict`.

```python
from kalshi.ws.models import TickerMessage

ws = KalshiWebSocket(auth=auth, config=config)

@ws.on("ticker")
async def on_ticker(msg: TickerMessage) -> None:
    print(msg.payload.yes_bid)

async with ws.connect():
    await ws.run_forever()
```

`on()` works both before and after `connect()`; callbacks registered before
the socket opens are buffered and applied when the session starts.

Registering a callback for a channel **takes over routing** for that channel —
messages on that channel won't appear in an iterator returned by
`subscribe_<channel>()`. Pick one style per channel.

## Channel reference

Each `subscribe_*` method returns an async iterator of one Pydantic message
type. Messages have a uniform envelope: `type: str`, `sid: int` (server
subscription id), `seq: int | None`, and `msg: <Payload>`.

### `subscribe_ticker(tickers=...)`

Yields [`TickerMessage`](reference.md). `tickers` filters to a market list;
omit it for the full-firehose. Latest-wins channel — the SDK's queue uses
`DROP_OLDEST` so a slow consumer falls behind silently instead of erroring.

### `subscribe_trade(tickers=...)`

Yields [`TradeMessage`](reference.md). Each print: ticker, side, count, price,
ts. `DROP_OLDEST` overflow.

### `subscribe_orderbook_delta(tickers=...)`

Yields [`OrderbookSnapshotMessage`](reference.md) (initial; one per ticker
when subscribing) then [`OrderbookDeltaMessage`](reference.md) updates.
**Sequenced** — gaps trigger an automatic resync (see below).
`ERROR` overflow because deltas are stateful — silently dropping one
corrupts the book.

If you want full books rather than raw deltas:

```python
async with ws.connect() as session:
    async for book in await session.orderbook("KXPRES-24-DJT"):
        print(book.yes[0], book.no[0])
```

`orderbook()` wraps `subscribe_orderbook_delta`, applies deltas to an
internal `OrderbookManager`, and yields a fresh `Orderbook` on each update.

### `subscribe_fill()`

Yields [`FillMessage`](reference.md). Private — requires auth. Fired when one
of your orders fills. `DROP_OLDEST`.

### `subscribe_user_orders()`

Yields [`UserOrdersMessage`](reference.md). Private. Order lifecycle
transitions: `resting`, `canceled`, `executed`, etc.

### `subscribe_market_positions()`

Yields [`MarketPositionsMessage`](reference.md). Private. Your aggregate
position per market.

### `subscribe_order_group()`

Yields [`OrderGroupMessage`](reference.md). Private, **sequenced**. State
changes on order groups. `ERROR` overflow.

### `subscribe_market_lifecycle(tickers=...)`

Yields [`MarketLifecycleMessage`](reference.md). Market created, opened,
closed, settled. `DROP_OLDEST`.

### `subscribe_multivariate()`

Yields [`MultivariateMessage`](reference.md). Multivariate market updates.
`DROP_OLDEST`.

### `subscribe_multivariate_lifecycle()`

Yields [`MultivariateLifecycleMessage`](reference.md). Lifecycle for
multivariate markets. `DROP_OLDEST`.

### `subscribe_communications(shard_factor=..., shard_key=...)`

Yields [`CommunicationsMessage`](reference.md). RFQ / quote lifecycle.
`shard_factor` / `shard_key` let you partition the stream across consumers.
`DROP_OLDEST`.

The Pydantic models live in
[`kalshi.ws.models`](https://github.com/TexasCoding/kalshi-python-sdk/tree/main/kalshi/ws/models).
Field aliases match the AsyncAPI wire format (`yes_bid_dollars` →
`yes_bid: Decimal`, `volume_fp` → `volume: str`, etc.).

## Sequence-gap detection

The `orderbook_delta` subscription (which delivers both snapshot and delta
messages) and `order_group_updates` carry monotonic `seq` numbers. The SDK
tracks the last `seq` per `sid` and flags a gap when it sees `seq > last + 1`.

When a gap is detected:

1. The offending message is **dropped** without being dispatched.
2. For `orderbook_delta`, the SDK clears the affected ticker's local book
   and the per-`sid` sequence tracker — the next snapshot from the server
   re-bootstraps it.
3. Duplicates (`seq <= last`) are silently ignored.

If recovery never lands — e.g. the server stops sending the channel — your
iterator stays open but produces nothing. The `KalshiSequenceGapError`
exception class exists in the hierarchy for callers that want to wire their
own resync logic via `subscribe(channel, ...)` against a custom tracker, but
the default path is silent recovery; it is not raised by the built-in
managers today.

The list of sequenced channels lives in
[`SEQUENCED_CHANNELS`](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/ws/sequence.py)
— add your own resync hook there if you fork the client.

## Backpressure

Every per-channel iterator is fed by a bounded `MessageQueue` (default
`maxsize=1000`). What happens when the queue fills depends on
`OverflowStrategy`:

| Strategy | Behavior | SDK default for |
|---|---|---|
| `DROP_OLDEST` | Ring-buffer: evict oldest, keep newest. | `ticker`, `trade`, `fill`, `user_orders`, `market_positions`, `market_lifecycle`, `multivariate`, `multivariate_lifecycle`, `communications` |
| `ERROR` | Raise `KalshiBackpressureError` from the producer side. | `orderbook_delta`, `order_group_updates` |

The choice tracks state semantics: latest-wins channels (`ticker`) survive a
drop; stateful, sequenced channels (`orderbook_delta`) can't — a missed
delta is a corrupted book, which is exactly what sequence-gap detection
catches.

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

`KalshiBackpressureError` is raised inside the receive loop, logged, and the
loop continues — your iterator keeps yielding (after some lost messages).
If you want hard failure on backpressure, catch it via a custom callback
registered with `ws.on(...)` or watch the connection state via
`on_state_change` on `KalshiWebSocket(...)`.

## Reconnection

If the underlying socket drops (server hangup, transient network error,
ping timeout), the receive loop transitions to `RECONNECTING` and retries
the connect with the same exponential-backoff-and-jitter formula as the
REST transport (`retry_base_delay * 2**attempt + jitter`, capped at
`retry_max_delay`), up to `KalshiConfig.ws_max_retries` (default 10).

On a successful reconnect:

1. All active subscriptions are re-issued. Server `sid`s change; the SDK
   tracks each subscription by a durable client-side id and rebuilds the
   `sid → client_id` map.
2. Sequence trackers are reset (`SequenceTracker.reset_all()`).
3. The local orderbook cache is cleared. `orderbook_delta` subscriptions
   are re-issued with `send_initial_snapshot: true` so the book is
   re-bootstrapped from a fresh snapshot.
4. Active iterators keep yielding — they reference the durable client-side
   ids, not the server `sid`s.

If `ws_max_retries` is exhausted, the receive loop pushes sentinels to all
active queues (so `async for` terminates cleanly) and exits. The connection
state ends at `CLOSED`.

Wire the `on_state_change` callback to observe transitions:

```python
from kalshi.ws import ConnectionState

async def on_state(old: ConnectionState, new: ConnectionState) -> None:
    print(f"{old.value} -> {new.value}")

ws = KalshiWebSocket(auth=auth, config=config, on_state_change=on_state)
```

See `kalshi.ws.ConnectionState` for the full state machine.
