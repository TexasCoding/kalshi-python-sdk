# FCM

Futures Commission Merchant routes. **FCM-member accounts only** — non-FCM
calls come back 401/403. Auth required throughout.

`subtrader_id` is required on positions. On orders it is required **unless**
`client_order_ids` is supplied (the two filters are alternatives).

## Quick reference

| Method | Endpoint |
|---|---|
| `orders(*, subtrader_id=None, client_order_ids=None, ...)` | `GET /fcm/orders` |
| `orders_all(*, subtrader_id=None, client_order_ids=None, ...)` | walks `orders` |
| `positions(*, subtrader_id, ...)` | `GET /fcm/positions` |

## List orders

```python
page = client.fcm.orders(
    subtrader_id="st_alpha",
    ticker="KXPRES-24-DJT",
    event_ticker="KXPRES-24",
    status="resting",              # OrderStatusLiteral
    min_ts=1_700_000_000,
    max_ts=1_800_000_000,
    limit=200,
)
for o in page:
    print(o.order_id, o.status, o.remaining_count)

for o in client.fcm.orders_all(subtrader_id="st_alpha", status="resting"):
    ...
```

Same `Order` model as [Orders](orders.md). Standard `Page[Order]` pagination
on `orders()`.

## Positions

```python
resp = client.fcm.positions(
    subtrader_id="st_alpha",
    event_ticker="KXPRES-24",
    count_filter="position",
    settlement_status="unsettled",     # SettlementStatusLiteral
    limit=200,
)
for mp in resp.market_positions:
    print(mp.ticker, mp.position)
```

`positions()` returns a `PositionsResponse` (same shape as
[`portfolio.positions`](portfolio.md#positions)), **not** a `Page`. For cursor
traversal use `positions_all()`, which auto-paginates `/fcm/positions` and yields
each `MarketPosition` (it mirrors `portfolio.positions_all()` and takes the same
filters — `subtrader_id`, `ticker`, `event_ticker`, `count_filter`,
`settlement_status`, `limit`, `max_pages`):

```python
for mp in client.fcm.positions_all(subtrader_id="st_alpha", settlement_status="unsettled"):
    print(mp.ticker, mp.position)
# async: `async for mp in client.fcm.positions_all(...)`
```

`settlement_status` is the FCM-specific kwarg that does **not** exist on
`portfolio.positions()`.

## Reference

::: kalshi.resources.fcm.FcmResource
    options:
      heading_level: 3

::: kalshi.resources.fcm.AsyncFcmResource
    options:
      heading_level: 3
