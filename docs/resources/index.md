# Resources

These are the REST resources. For the streaming and session interfaces see
[WebSocket](../websockets.md), [FIX protocol](../fix.md), and
[Perps](../perps.md).

A **resource** in this SDK is a thin client over a group of related Kalshi
endpoints. You reach each one as an attribute on the client:

```python
with KalshiClient.from_env() as client:
    market = client.markets.get("KXPRES-24-DJT")
    positions = client.portfolio.positions()
```

Every resource exists in two parity-checked flavors — sync (e.g.
`MarketsResource`, exposed as `client.markets`) and async
(`AsyncMarketsResource`, exposed as `async_client.markets`). Method names,
keyword arguments, return shapes, and error behavior are identical. Pick sync
or async based on the rest of your codebase — internally the two share one
transport implementation.

## Resource catalog

| Resource | Class | Page |
|---|---|---|
| `client.markets` | `MarketsResource` | [Markets](markets.md) |
| `client.events` | `EventsResource` | [Events](events.md) |
| `client.series` | `SeriesResource` | [Series](series.md) |
| `client.exchange` | `ExchangeResource` | [Exchange](exchange.md) |
| `client.historical` | `HistoricalResource` | [Historical](historical.md) |
| `client.search` | `SearchResource` | [Search](search.md) |
| `client.orders` | `OrdersResource` | [Orders](orders.md) |
| `client.portfolio` | `PortfolioResource` | [Portfolio](portfolio.md) |
| `client.order_groups` | `OrderGroupsResource` | [Order groups](order-groups.md) |
| `client.account` | `AccountResource` | [Account](account.md) |
| `client.api_keys` | `ApiKeysResource` | [API keys](api-keys.md) |
| `client.subaccounts` | `SubaccountsResource` | [Subaccounts](subaccounts.md) |
| `client.fcm` | `FcmResource` | [FCM](fcm.md) |
| `client.communications` | `CommunicationsResource` | [Communications (RFQ/Quote)](communications.md) |
| `client.multivariate_collections` | `MultivariateCollectionsResource` | [Multivariate](multivariate.md) |
| `client.milestones` | `MilestonesResource` | [Milestones](milestones.md) |
| `client.structured_targets` | `StructuredTargetsResource` | [Structured targets](structured-targets.md) |
| `client.incentive_programs` | `IncentiveProgramsResource` | [Incentive programs](incentive-programs.md) |
| `client.live_data` | `LiveDataResource` | [Live data](live-data.md) |

The async equivalents share the same attribute names on `AsyncKalshiClient`
(`async_client.markets` returns `AsyncMarketsResource`, etc.).

## Common patterns

### Pagination

See [Pagination](../pagination.md) for the full story. Quick form:

```python
page = client.markets.list(status="open", limit=200)
for market in page:
    ...
for market in client.markets.list_all(status="open"):
    ...
```

### Request models or kwargs

Mutating endpoints (POST / PUT / DELETE with a body) accept their parameters
two ways — individual kwargs or a pre-built request model. See
[Request models](../request-models.md).

### Typed enum kwargs

Kwargs that map to fixed enums use `Literal[...]`. See [Types & literals](../types.md).

### Auth requirements

Every resource method that touches user data calls `self._require_auth()`,
which raises [`AuthRequiredError`](../errors.md) **before** the network if the
client was constructed without credentials.

A few public-looking endpoints also require auth at the SDK layer:

- `markets.orderbook()` and `markets.bulk_orderbooks()` — Kalshi gates the L2
  book behind auth.
- `series.forecast_percentile_history()` — auth required.
- `exchange.user_data_timestamp()` — auth required.
- All of `historical.fills` / `historical.orders` / `historical.positions`
  (user data).

Use `client.is_authenticated` to branch on it explicitly:

```python
with KalshiClient.from_env() as client:
    if client.is_authenticated:
        balance = client.portfolio.balance()
    markets = client.markets.list(status="open")   # works either way
```

## Ticker formats

| Form | Example | Used for |
|---|---|---|
| series_ticker | `KXPRES` | A recurring family of events |
| event_ticker | `KXPRES-24` | One instance under a series |
| market_ticker | `KXPRES-24-DJT` | A single YES/NO contract |

A few methods take a path-shaped pair (`series_ticker, ticker`) where `ticker`
is actually an **event** ticker — for example
`series.event_candlesticks(series_ticker, ticker)`. The pages call those out
where they appear.

## Wire-format quirks

- **Prices** are returned as FixedPointDollars strings (`"0.5600"`) with a
  `_dollars` suffix in the response key (`yes_bid_dollars`). The SDK normalizes
  them to short names (`yes_bid: Decimal`). See [Types & literals](../types.md).
- **Tickers in batches** use two different wire formats depending on the
  endpoint. `markets.list`, `historical.markets`, `markets.bulk_candlesticks`
  comma-join (`?tickers=a,b,c`). `markets.bulk_orderbooks` and
  `series.forecast_percentile_history` use explode form (`?tickers=a&tickers=b`).
  Both surfaces accept `list[str] | str`; the SDK builds the right wire form.

## Reference

The [API Reference](../reference.md) page is auto-generated from docstrings
on every public method — that's the source of truth for the exact set of
kwargs, return types, and per-method notes.
