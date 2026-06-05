# Multivariate event collections

A **multivariate event collection** is a template that lets you bet on
combinations of outcomes — e.g. "Will it rain in NYC AND the Yankees win
Saturday?" The collection holds the building-block markets; `create_market`
with a list of leg selections mints a derived YES/NO contract.

Public listing, auth-required minting. Attribute name on the client:
`multivariate_collections`.

!!! warning "Deprecated methods"
    `create_market()`, `lookup_tickers()`, and `lookup_history()` are
    deprecated — "This endpoint predates RFQs and should not be used for new
    integrations." Calling them emits a `DeprecationWarning`. Use the
    [Communications (RFQ/Quote)](communications.md) surface instead. `list()` /
    `list_all()` / `get()` remain supported.

## Quick reference

| Method | Endpoint | Auth |
|---|---|---|
| `list(...)` / `list_all(...)` | `GET /multivariate_event_collections` | no |
| `get(collection_ticker)` | `GET /multivariate_event_collections/{ticker}` | no |
| `create_market(collection_ticker, *, selected_markets, with_market_payload=False)` | `POST /multivariate_event_collections/{ticker}` | yes |
| `lookup_tickers(collection_ticker, *, selected_markets)` | `PUT /multivariate_event_collections/{ticker}/lookup` | yes |
| `lookup_history(collection_ticker, *, lookback_seconds)` | `GET /multivariate_event_collections/{ticker}/lookup` (with `lookback_seconds` query param) | no |

## List collections

```python
page = client.multivariate_collections.list(
    status="open",                  # MultivariateCollectionStatusLiteral
    series_ticker="KXWEATHER",
    limit=100,
)
for c in page:
    print(c.collection_ticker, c.title)
```

## Select legs

A leg is a `TickerPair(event_ticker=..., market_ticker=...)` — one event-side
selection. To bet on "rain in NYC AND Yankees win":

```python
from kalshi import TickerPair

legs = [
    TickerPair(event_ticker="KXNYRAIN-26", market_ticker="KXNYRAIN-26-YES"),
    TickerPair(event_ticker="KXYANKEES-26-SAT", market_ticker="KXYANKEES-26-SAT-WIN"),
]
```

## Lookup the auto-generated ticker (no mint)

```python
resp = client.multivariate_collections.lookup_tickers(
    "KXWEATHER-SPORTS-COMBO",
    selected_markets=legs,
)
print(resp.market_ticker, resp.event_ticker)
```

Wire-level note: this endpoint is a `PUT` — unusual for a read operation, but
matches the OpenAPI spec.

## Mint a combo market

```python
resp = client.multivariate_collections.create_market(
    "KXWEATHER-SPORTS-COMBO",
    selected_markets=legs,
    with_market_payload=True,        # also return the full Market body
)
print(resp.market_ticker, resp.event_ticker)
if resp.market is not None:
    print(resp.market.yes_bid, resp.market.yes_ask)
```

## Recent lookup history

```python
history = client.multivariate_collections.lookup_history(
    "KXWEATHER-SPORTS-COMBO",
    lookback_seconds=3600,
)
for point in history:
    print(point.last_queried_ts, point.market_ticker, point.event_ticker)
```

## Reference

::: kalshi.resources.multivariate.MultivariateCollectionsResource
    options:
      heading_level: 3

::: kalshi.resources.multivariate.AsyncMultivariateCollectionsResource
    options:
      heading_level: 3
