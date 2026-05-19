# Kalshi Python SDK

A professional, spec-first Python SDK for the [Kalshi](https://kalshi.com) prediction
markets API.

- **Full REST coverage** — 85 endpoints across 19 resources (OpenAPI v3.18.0),
  every kwarg drift-tested against the spec.
- **V2 event-market orders** — new `create_v2` / `amend_v2` / `decrease_v2` /
  `cancel_v2` family on `/portfolio/events/orders/*`. Legacy `/portfolio/orders`
  keeps working; deprecation no earlier than May 6, 2026.
- **Funding + cost introspection** — `portfolio.deposits()`,
  `portfolio.withdrawals()`, `account.endpoint_costs()`.
- **Full WebSocket coverage** — 13 channels with sequence-gap detection, automatic
  reconnection, backpressure strategies, and an in-memory orderbook builder.
- **Sync and async parity** — `KalshiClient` and `AsyncKalshiClient` share one
  transport implementation; method names, kwargs, return types, and error behavior
  are identical.
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
| Catch the right exception | [Errors](errors.md) · [Retries & idempotency](retries.md) |
| Find every method on a resource | [Resources](resources/index.md) |
| Test your code without hitting the API | [Testing](testing.md) |

Source: [github.com/TexasCoding/kalshi-python-sdk](https://github.com/TexasCoding/kalshi-python-sdk).
