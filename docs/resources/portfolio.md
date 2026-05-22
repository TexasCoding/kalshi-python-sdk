# Portfolio

Account balance, positions, settlements, and total resting order value.
Auth required throughout.

## Quick reference

| Method | Endpoint |
|---|---|
| `balance(*, subaccount=None)` | `GET /portfolio/balance` |
| `positions(*, ...)` | `GET /portfolio/positions` |
| `settlements(...)` / `settlements_all(...)` | `GET /portfolio/settlements` |
| `total_resting_order_value()` | `GET /portfolio/summary/total_resting_order_value` (FCM only) |
| `deposits(*, limit, cursor)` / `deposits_all(*, limit, max_pages)` | `GET /portfolio/deposits` |
| `withdrawals(*, limit, cursor)` / `withdrawals_all(*, limit, max_pages)` | `GET /portfolio/withdrawals` |

## Balance

```python
bal = client.portfolio.balance()
print(bal.balance, bal.balance_dollars, bal.portfolio_value, bal.updated_ts)
```

`Balance.balance` and `portfolio_value` are **integer cents**.
`Balance.balance_dollars` (required, new in v2.1.0) is the same amount as a
`DollarDecimal` — use whichever shape your code expects without manually
dividing by 100.

`Balance.balance_breakdown` (optional, also new in v2.1.0) splits the total
across exchange shards:

```python
if bal.balance_breakdown is not None:
    for shard in bal.balance_breakdown:
        # IndexedBalance.balance is DollarDecimal, not cents — same name
        # as Balance.balance but a different type. See note below.
        print(shard.exchange_index, shard.balance)
```

!!! warning "Type collision: `Balance.balance` vs. `IndexedBalance.balance`"
    `Balance.balance` is **integer cents**. `IndexedBalance.balance` (inside
    `balance_breakdown`) is `DollarDecimal` (dollars), matching
    `Balance.balance_dollars` units. Same field name, different types — be
    deliberate when iterating the breakdown.

!!! note "Constructing `Balance` directly"
    v2.1.0 made `balance_dollars` required to match spec v3.18.0. Existing
    code that calls `client.portfolio.balance()` is unaffected. Code that
    builds `Balance(...)` directly (typically in tests/mocks) needs the
    field added — see [Migration](../migration.md#v20-v21).

## Positions

```python
resp = client.portfolio.positions(
    limit=200,
    count_filter="position",        # only return rows with non-zero `position` (etc.)
    ticker="KXPRES-24-DJT",
    event_ticker="KXPRES-24",
)
for mp in resp.market_positions:
    print(mp.ticker, mp.position, mp.realized_pnl)
for ep in resp.event_positions:
    print(ep.event_ticker, ep.event_exposure)
```

!!! note "`positions()` does not return Page[T]"
    It returns `PositionsResponse` — two parallel lists (`market_positions`
    and `event_positions`) plus its own `cursor` and `has_next`. Use
    `positions_all()` (sync and async, shipped in v2.5.0) to auto-paginate
    over `market_positions` as an iterator of `MarketPosition`:

    ```python
    for mp in client.portfolio.positions_all(ticker="KXPRES-24-DJT"):
        print(mp.ticker, mp.position, mp.realized_pnl)
    ```

    `event_positions` are intentionally *not* surfaced by `positions_all()`:
    they are aggregate roll-ups over the same underlying markets, and page
    boundaries cut the aggregate arbitrarily — concatenating across pages
    would not recompute a meaningful event-level total. Callers that need
    the event view should iterate `positions()` page-by-page:

    ```python
    cursor = None
    while True:
        resp = client.portfolio.positions(cursor=cursor)
        for ep in resp.event_positions:
            ...
        if not resp.has_next:
            break
        cursor = resp.cursor
    ```

`count_filter` filters which fields the response **includes a row for** —
filtering by `"position"` returns only markets where your position is non-zero.

## Settlements

```python
page = client.portfolio.settlements(
    ticker="KXPRES-24-DJT",
    event_ticker="KXPRES-24",
    min_ts=1_700_000_000,
    max_ts=1_800_000_000,
    limit=200,
)
for s in page:
    print(s.ticker, s.settled_at, s.market_result, s.revenue)

# Or:
for s in client.portfolio.settlements_all():
    ...
```

Standard `Page[Settlement]` pagination — see [Pagination](../pagination.md).

## Total resting order value

```python
total = client.portfolio.total_resting_order_value()
print(total.total_value)
```

!!! warning "FCM members only"
    Non-FCM accounts get a `403` (mapped to `KalshiAuthError`). Demo mirrors
    production behavior here.

## Deposits and withdrawals

New in v2.1.0. Standard `Page[T]` pagination — see [Pagination](../pagination.md).

```python
# Most recent deposits
page = client.portfolio.deposits(limit=50)
for d in page:
    print(d.id, d.status, d.type, d.amount_cents, d.created_ts)

# All deposits
for d in client.portfolio.deposits_all():
    ...

# Withdrawals follow the same shape
for w in client.portfolio.withdrawals_all():
    print(w.id, w.status, w.amount_cents, w.fee_cents)
```

`Deposit` and `Withdrawal` are structurally identical: `id`, `status`
(`PaymentStatusLiteral`: `"pending"` / `"applied"` / `"failed"` /
`"returned"`), `type` (`PaymentTypeLiteral`: `"ach"` / `"wire"` /
`"crypto"` / `"debit"` / `"apm"`), `amount_cents` (int), `fee_cents`
(int), `created_ts` (int Unix seconds), and `finalized_ts: int | None`
which is `None` until the transfer settles.

Both `*_all` variants accept `max_pages=N` to bound iteration.

## Position fields

`MarketPosition` and `EventPosition` use the standard `_dollars` / `_fp`
wire-format aliases — on the wire you see `total_traded_dollars`,
`market_exposure_dollars`, `realized_pnl_dollars`, `fees_paid_dollars`,
`position_fp`. The SDK normalizes to short names returning `Decimal`.
`realized_pnl` is signed.

## Reference

::: kalshi.resources.portfolio.PortfolioResource
    options:
      heading_level: 3

::: kalshi.resources.portfolio.AsyncPortfolioResource
    options:
      heading_level: 3
