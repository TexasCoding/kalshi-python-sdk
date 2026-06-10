# Kalshi Python SDK

A professional, spec-first Python SDK for the [Kalshi](https://kalshi.com) prediction
markets API.

- **Full REST coverage** — 99 operations across 19 resources (OpenAPI v3.20.0),
  every kwarg drift-tested against the spec.
- **V2 event-market orders** — new `create_v2` / `amend_v2` / `decrease_v2` /
  `cancel_v2` family on `/portfolio/events/orders/*`. Legacy `/portfolio/orders`
  keeps working; deprecation no earlier than May 6, 2026.
- **Funding + cost introspection** — `portfolio.deposits()`,
  `portfolio.withdrawals()`, `account.endpoint_costs()`.
- **Full WebSocket coverage** — 12 channels with sequence-gap detection, automatic
  reconnection (with resubscribe-window frame stashing for high-volume channels),
  backpressure strategies, and an in-memory orderbook builder. Async-only —
  access via `AsyncKalshiClient.ws`.
- **Perps (margin) API** — standalone `PerpsClient` / `AsyncPerpsClient` +
  `PerpsWebSocket` for the perpetual-futures exchange (34 REST operations, 6 WS
  channels), and a `KlearClient` for the Self-Clearing-Member settlement API
  (9 operations, Bearer token auth). See [Perps](perps.md).
- **FIX protocol** — a hand-rolled, async-first FIX engine (FIXT.1.1 / FIX50SP2)
  for both products: order-entry, drop-copy, market-data, post-trade (prediction),
  and RFQ (prediction) sessions — plus order-group management over the order-entry
  session — with typed message models, automatic sequence recovery, and order-book
  / settlement reassembly. `from kalshi import FixClient` (prediction) /
  `MarginFixClient` (margin). See [FIX](fix.md).
- **Sync and async parity** — `KalshiClient` and `AsyncKalshiClient` share one
  transport implementation; method names, kwargs, return types, and error behavior
  are identical. The one exception is WebSocket access, which is async-only.
- **Typed end-to-end** — Pydantic v2 models, `Literal` types for enums,
  `mypy --strict` clean. Request bodies use `extra="forbid"` so phantom kwargs fail
  fast.
- **Money safety** — prices are `Decimal` via a custom `DollarDecimal` type. No
  floats anywhere on the price path.

## Install

```bash
pip install kalshi-sdk
```

Requires Python 3.12+. Optional DataFrame extras:

```bash
pip install 'kalshi-sdk[pandas]'   # pandas
pip install 'kalshi-sdk[polars]'   # polars
pip install 'kalshi-sdk[all]'      # both
```

## Hello, markets

```python
from kalshi import KalshiClient

with KalshiClient(demo=True) as client:
    for market in client.markets.list_all(status="open"):
        print(market.ticker, market.yes_bid, market.yes_ask)
```

No credentials needed for most market data. To place orders, see
[Authentication](authentication.md).

## Where to go next

| If you want to… | Read |
|---|---|
| Place your first authenticated request | [Quickstart](getting-started.md) |
| Understand RFQs, milestones, subaccounts, etc. | [Concepts](concepts.md) |
| Tune timeouts, retries, HTTP/2 | [Configuration](configuration.md) |
| Walk pages or convert to DataFrames | [Pagination](pagination.md) · [DataFrames](dataframes.md) |
| Build a live-data app | [WebSocket](websockets.md) |
| Trade over FIX (low latency) | [FIX](fix.md) |
| Catch the right exception | [Errors](errors.md) · [Retries & idempotency](retries.md) |
| Find every method on a resource | [Resources](resources/index.md) |
| Test your code without hitting the API | [Testing](testing.md) |

Source: [github.com/TexasCoding/kalshi-python-sdk](https://github.com/TexasCoding/kalshi-python-sdk).
