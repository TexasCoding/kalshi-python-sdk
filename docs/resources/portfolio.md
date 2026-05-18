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

## Balance

```python
bal = client.portfolio.balance()
print(bal.balance, bal.portfolio_value, bal.updated_ts)
```

`Balance.balance` and `portfolio_value` are **integer cents**, not dollars.

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

!!! warning "`positions()` does not return Page[T]"
    It returns `PositionsResponse` — two parallel lists (`market_positions`
    and `event_positions`) plus its own `cursor` and `has_next`. There is no
    `positions_all()` helper. Walk it manually:

    ```python
    cursor = None
    while True:
        resp = client.portfolio.positions(cursor=cursor)
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
