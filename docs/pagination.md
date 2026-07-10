# Pagination

Every "list" endpoint that can return more than a server-imposed cap returns a
`Page[T]`. A page is iterable, knows whether there's a next page, and carries
the opaque cursor you'd hand back to fetch it.

## Anatomy

```python
page = client.markets.list(status="open", limit=200)

for market in page:       # Page is iterable
    print(market.ticker)

len(page)                 # items on this page
page.items                # the underlying list[Market]
page.cursor               # next-page cursor (None or "" if you're on the last page)
page.has_next             # bool — True iff cursor is set and non-empty
```

`Page` is a Pydantic model with `extra="allow"`, so any envelope fields the
server attaches (totals, debug keys) survive on the instance and you can read
them with normal attribute access.

## Walking pages manually

```python
cursor = None
while True:
    page = client.orders.list(status="resting", cursor=cursor, limit=200)
    for order in page:
        process(order)
    if not page.has_next:
        break
    cursor = page.cursor
```

## `list_all()` — the easy way

Every resource that has a `list()` also has a `list_all()` that walks cursors
for you:

```python
# Sync: returns an Iterator[T]
for market in client.markets.list_all(status="open"):
    ...

# Async: returns an AsyncIterator[T] — async for works directly
async for market in async_client.markets.list_all(status="open"):
    ...
```

`list_all()` accepts the same kwargs as `list()` (minus `cursor`) plus an
optional `max_pages` cap. It walks until the server returns no more pages.

### Cursor-loop safety

`list_all()` keeps a set of cursors it has already used. If the server returns
a cursor that already appeared, it raises `KalshiError("Cursor loop detected
on …")`. This catches server-side pagination bugs that would otherwise spin
forever.

There is **no** built-in 1000-page cap. If you want one, pass
`max_pages=1000`.

## Endpoints that don't paginate

A few list endpoints return a plain `list[T]`, not `Page[T]`:

- `client.series.list(...)` — flat list of series.
- `client.exchange.announcements()` — a flat list (deprecated in v7.0.0; the
  endpoint was removed upstream and now 404s).
- `client.order_groups.list()` — no cursor.
- `client.account.limits()` / `client.exchange.status()` — single objects.
- `client.markets.bulk_orderbooks(...)` / `bulk_candlesticks(...)` — flat list of up to 100 items.

These don't need pagination; they're sized at most by the API's natural caps.

## Endpoints with a non-`Page` shape

`client.portfolio.positions()` and `client.fcm.positions()` return
`PositionsResponse`, not `Page`. It carries two parallel lists
(`market_positions` and `event_positions`) plus its own `cursor` /
`has_next`. There is no `positions_all()` helper — walk it manually:

```python
cursor = None
while True:
    resp = client.portfolio.positions(cursor=cursor)
    for pos in resp.market_positions:
        ...
    if not resp.has_next:
        break
    cursor = resp.cursor
```

`client.incentive_programs.list()` uses the server-side cursor key
`next_cursor` instead of `cursor`. The SDK normalizes this — pass `cursor=`
and read `.cursor` exactly like any other list call.

## DataFrames

`Page[T]` carries `.to_dataframe()` and `.to_polars()`. They convert **only the
current page** — not all pages. See [DataFrames](dataframes.md).

```python
df = client.markets.list(status="open", limit=500).to_dataframe()
```

## Reference

::: kalshi.models.common.Page
