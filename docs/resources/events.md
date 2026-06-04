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
| `fee_changes(...)` | `GET /events/fee_changes` | no |
| `fee_changes_all(...)` | walks `fee_changes` | no |

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

    - `Event.product_metadata` is typed `dict[str, Any] | None` and defaults
      to `None`. The live demo server omits the key on most events. As of
      OpenAPI v3.20.0 the spec also marks it optional, so this is no longer a
      spec deviation — the SDK simply keeps it nullable to match reality.
    - `EventMetadata.market_details: list[MarketMetadata]` — when the live
      server sends JSON `null`, the SDK coerces it to `[]` (via `NullableList`)
      so callers always see a list. The spec contract (key present) is still
      enforced.

## Event fee changes

`fee_changes()` returns the paginated feed of scheduled **event-level** fee
overrides (`GET /events/fee_changes`, added in v3.20.0). Event fees layer on
top of the parent series' fee structure.

```python
page = client.events.fee_changes(event_ticker="KXPRES-24", limit=100)
for change in page:
    if change.fee_type_override is None:
        print(change.event_ticker, "override cleared")
    else:
        print(change.event_ticker, change.fee_type_override, change.fee_multiplier_override)

# Or auto-paginate across every page:
for change in client.events.fee_changes_all(event_ticker="KXPRES-24"):
    ...
```

`EventFeeChange.fee_type_override` and `fee_multiplier_override` are both
`None` when an override has been **cleared** (the event falls back to the
series fee). Both keys are always present in the payload — `None` is a
meaningful "cleared" signal, not a missing field. The live `event_fee_update`
WebSocket message on the `market_lifecycle_v2` channel carries the same
override shape (see [WebSocket](../websockets.md)).

For the series-level equivalent, see
[`series.fee_changes`](series.md).

## Reference

::: kalshi.resources.events.EventsResource
    options:
      heading_level: 3

::: kalshi.resources.events.AsyncEventsResource
    options:
      heading_level: 3
