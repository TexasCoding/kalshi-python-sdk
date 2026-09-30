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
| `fills(*, min_ts=None, max_ts=None, cursor=None)` | `GET /fcm/fills` |
| `fills_all(*, min_ts=None, max_ts=None, max_pages=None)` | walks `fills` |
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

## Fills

Fills across the member's subtraders. Query params are only `min_ts`,
`max_ts`, and `cursor` — there is no `limit` or `subtrader_id` filter.
`fills()` returns `GetFcmFillsResponse` (`fills`, `cursor`). `fills_all()`
walks that cursor and yields each `FcmFill`. Prices are `Decimal`
(`yes_price` accepts `yes_price_dollars`); `count` accepts `count_fp`.

```python
resp = client.fcm.fills(min_ts=1_700_000_000, max_ts=1_800_000_000)
for fill in resp.fills:
    print(fill.fill_id, fill.ticker, fill.taker_outcome_side, fill.yes_price, fill.count)

for fill in client.fcm.fills_all(min_ts=1_700_000_000):
    print(fill.maker_subtrader_id, fill.taker_subtrader_id, fill.maker_fee_cost)
```

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

`settlement_status` is also accepted on
[`portfolio.positions`](portfolio.md#positions) / `positions_all` (OpenAPI
3.32.0). Both endpoints default to `unsettled` when the kwarg is omitted.

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
