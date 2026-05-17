# Resources

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
keyword arguments, return shapes, and error behavior are identical. Pick
sync or async based on the rest of your codebase — internally the two
share one transport implementation, so neither is "the real one wrapping
the other".

## Common patterns

### Pagination

List endpoints return a `Page[T]`:

```python
page = client.markets.list(status="open", limit=200)
for market in page:   # Page is iterable
    print(market.ticker)

len(page)             # items on this page
page.cursor           # next-page cursor (None if you're on the last page)
page.has_next         # bool
```

For "give me everything across pages", use `list_all()`:

```python
# Sync: returns an Iterator
for market in client.markets.list_all(status="open"):
    ...

# Async: returns an AsyncIterator — works directly with `async for`
async for market in async_client.markets.list_all(status="open"):
    ...
```

`list_all()` walks cursors until the server returns no more pages, with a
1000-page safety cap and a cursor-repeat guard that raises `KalshiError` if
the server returns the same cursor twice (a known way to detect server-side
pagination bugs in production).

### DataFrames

`Page[T]` carries `.to_dataframe()` (pandas) and `.to_polars()` (polars).
Both are optional extras:

```bash
pip install 'kalshi-sdk[pandas]'
# or
pip install 'kalshi-sdk[polars]'
```

```python
df = client.markets.list(status="open", limit=500).to_dataframe()
```

Calling either method without the corresponding library installed raises
`ImportError` with the exact `pip install` hint.

### Request models or kwargs (your call)

Mutating endpoints (POST / PUT / DELETE-with-body) accept their parameters
two ways:

```python
# Form 1 — individual kwargs (default for most call sites)
order = client.orders.create(
    ticker="KXPRES-24-DJT",
    side="yes",
    action="buy",
    count=10,
    yes_price="0.65",
    time_in_force="good_till_canceled",
)

# Form 2 — pass a pre-built request model
from kalshi import CreateOrderRequest

req = CreateOrderRequest(
    ticker="KXPRES-24-DJT",
    side="yes",
    action="buy",
    count=10,
    yes_price="0.65",
    time_in_force="good_till_canceled",
)
order = client.orders.create(request=req)
```

The two forms are **mutually exclusive** — passing `request=` together with
any kwarg raises `TypeError`. The request-model form is useful when you
build orders out of band (config, queue, test harness) and want to type-check
the whole payload at construction time.

Request models all have `extra="forbid"` — a misspelled or removed field
fails at construction. The same models drive the body-drift contract tests,
so the kwargs and the wire format stay in lockstep with the OpenAPI spec.

### Typed enum kwargs

Kwargs that map to fixed enums use `Literal[...]` types so your IDE
auto-completes the values and `mypy` rejects typos:

```python
from kalshi import SideLiteral, ActionLiteral, TimeInForceLiteral
# SideLiteral = Literal["yes", "no"]
# ActionLiteral = Literal["buy", "sell"]
# TimeInForceLiteral = Literal["fill_or_kill", "good_till_canceled", "immediate_or_cancel"]
```

The literal aliases are re-exported from `kalshi` for use in your own type
signatures.

### Auth requirements

Every resource method that touches user data calls `self._require_auth()`,
which raises [`AuthRequiredError`](../errors.md) *before* the network if
the client was constructed without credentials. Public endpoints (market
data, events, exchange status, series, historical) work on an
unauthenticated client.

Use `client.is_authenticated` to branch on it explicitly:

```python
with KalshiClient.from_env() as client:
    if client.is_authenticated:
        balance = client.portfolio.balance()
    markets = client.markets.list(status="open")   # works either way
```

## Resource catalog

| Attribute | Class | Source |
|---|---|---|
| `client.markets` | `MarketsResource` | [markets.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/markets.py) |
| `client.events` | `EventsResource` | [events.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/events.py) |
| `client.series` | `SeriesResource` | [series.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/series.py) |
| `client.exchange` | `ExchangeResource` | [exchange.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/exchange.py) |
| `client.historical` | `HistoricalResource` | [historical.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/historical.py) |
| `client.orders` | `OrdersResource` | [orders.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/orders.py) |
| `client.portfolio` | `PortfolioResource` | [portfolio.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/portfolio.py) |
| `client.order_groups` | `OrderGroupsResource` | [order_groups.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/order_groups.py) |
| `client.subaccounts` | `SubaccountsResource` | [subaccounts.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/subaccounts.py) |
| `client.api_keys` | `ApiKeysResource` | [api_keys.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/api_keys.py) |
| `client.communications` | `CommunicationsResource` | [communications.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/communications.py) |
| `client.multivariate_collections` | `MultivariateCollectionsResource` | [multivariate.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/multivariate.py) |
| `client.fcm` | `FcmResource` | [fcm.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/fcm.py) |
| `client.milestones` | `MilestonesResource` | [milestones.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/milestones.py) |
| `client.structured_targets` | `StructuredTargetsResource` | [structured_targets.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/structured_targets.py) |
| `client.incentive_programs` | `IncentiveProgramsResource` | [incentive_programs.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/incentive_programs.py) |
| `client.live_data` | `LiveDataResource` | [live_data.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/live_data.py) |
| `client.search` | `SearchResource` | [search.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/search.py) |
| `client.account` | `AccountResource` | [account.py](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/resources/account.py) |

The async equivalents share the same attribute names on `AsyncKalshiClient`
(`async_client.markets` returns `AsyncMarketsResource`, etc.).

## Reference

The [API Reference](../reference.md) page is auto-generated from docstrings
on every public method — that's the source of truth for the exact set of
kwargs, return types, and per-method notes.
