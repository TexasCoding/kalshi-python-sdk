# Events

An **event** is one instance of a series (e.g. `KXPRES-24`). It groups one or
more markets that share a resolution.

## Quick reference

| Method | Endpoint | Auth |
|---|---|---|
| `list(...)` | `GET /events` | no |
| `list_all(...)` | walks `list` | no |
| `list_multivariate(...)` | `GET /events/multivariate` | no |
| `list_all_multivariate(...)` | walks `list_multivariate` | no |
| `get(event_ticker, *, with_nested_markets=False)` | `GET /events/{event_ticker}` | no |
| `metadata(event_ticker)` | `GET /events/{event_ticker}/metadata` | no |

## List events

```python
page = client.events.list(
    status="open",                   # EventStatusLiteral
    series_ticker="KXPRES",
    with_nested_markets=False,
    with_milestones=False,
    min_close_ts=1_700_000_000,
    min_updated_ts=1_700_000_000,
    collection_ticker=None,          # only events under a specific multivariate collection
    limit=200,
)
for event in page:
    print(event.event_ticker, event.title, event.status)
```

`EventStatusLiteral` has values `"unopened" | "open" | "closed" | "settled"`.
Unlike [`MarketStatusLiteral`](../types.md), there is no `"paused"`.

## Multivariate events

`list_multivariate(...)` returns only events that participate in a
multivariate event collection. Same kwargs as `list`. See
[Multivariate](multivariate.md) for the surrounding API.

## Get one event

```python
event = client.events.get("KXPRES-24", with_nested_markets=True)
for market in event.markets:
    print(market.ticker)
```

`with_nested_markets` defaults to `False` — you'll get the event metadata only
unless you opt in.

## Event metadata

```python
md = client.events.metadata("KXPRES-24")
print(md.tags, md.category)
```

`EventMetadata` carries tags, categories, and other non-trading attributes.

!!! note "Server omissions on optional-shaped fields"
    Two `EventMetadata`-adjacent fields are typed as nullable to absorb live
    server behavior:

    - `Event.product_metadata` is typed `dict[str, Any] | None`. The OpenAPI
      spec marks it `required`, but the live demo server omits the key on
      most events. Defaults to `None`.
    - `EventMetadata.market_details` uses `NullableList[MarketMetadata]`,
      which coerces a JSON `null` payload to `[]`. The spec contract (key
      present) is still enforced; callers always see a list.

    Both are tracked under `server_omits_despite_required` in the SDK's
    EXCLUSIONS map.
## Reference

::: kalshi.resources.events.EventsResource
    options:
      heading_level: 3

::: kalshi.resources.events.AsyncEventsResource
    options:
      heading_level: 3
