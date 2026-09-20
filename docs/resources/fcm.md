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
| `list_subtraders()` | `GET /fcm/subtraders` |
| `create_subtrader(*, subtrader_suffix)` | `POST /fcm/subtraders` |
| `blocked_categories(*, subtrader_id)` | `GET /fcm/subtraders/blocked_categories` |
| `update_blocked_categories(*, subtrader_id, category, blocked)` | `PUT /fcm/subtraders/blocked_categories` |
| `event_contract_daily_cap(*, subtrader_id=None)` | `GET /fcm/subtraders/event_contract_daily_cap` |
| `update_event_contract_daily_cap(*, subtrader_id, limit)` | `PUT /fcm/subtraders/event_contract_daily_cap` |
| `delete_event_contract_daily_cap(*, subtrader_id)` | `DELETE /fcm/subtraders/event_contract_daily_cap` |

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

## Subtrader admin

List and create subtraders, block event categories, and set a daily
event-contract notional cap. POST/PUT/DELETE are never retried.

```python
owned = client.fcm.list_subtraders()
created = client.fcm.create_subtrader(subtrader_suffix="desk1")
client.fcm.update_blocked_categories(
    subtrader_id=created.subtrader_id, category="Politics", blocked=True
)
client.fcm.update_event_contract_daily_cap(
    subtrader_id=created.subtrader_id, limit="10000.00"
)
```

`create_subtrader` composes the full id server-side as
`{account_id}_{suffix}` (suffix is 1–16 ASCII alphanumeric characters).

## Reference

::: kalshi.resources.fcm.FcmResource
    options:
      heading_level: 3

::: kalshi.resources.fcm.AsyncFcmResource
    options:
      heading_level: 3
