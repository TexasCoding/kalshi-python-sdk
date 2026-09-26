# Historical

Historical-data archives served from a slower, cheaper backing store than the
live `markets.*` and `portfolio.*` paths. Use these for backtests and
analytics; live trading needs the real-time surfaces.

## Quick reference

| Method | Endpoint | Auth |
|---|---|---|
| `cutoff()` | `GET /historical/cutoff` | no |
| `markets(...)` / `markets_all(...)` | `GET /historical/markets` | no |
| `market(ticker)` | `GET /historical/markets/{ticker}` | no |
| `candlesticks(ticker, *, start_ts, end_ts, period_interval)` | `GET /historical/markets/{ticker}/candlesticks` | no |
| `trades(...)` / `trades_all(...)` | `GET /historical/trades` | no |
| `fills(..., subaccount=None)` / `fills_all(..., subaccount=None)` | `GET /historical/fills` | **yes** |
| `orders(..., subaccount=None)` / `orders_all(..., subaccount=None)` | `GET /historical/orders` | **yes** |
| `positions(*, subaccount=None, ...)` / `positions_all(*, subaccount=None, ...)` | `GET /historical/positions` | **yes** |

## Cutoff

```python
co = client.historical.cutoff()
print(co.market_settled_ts)                 # settled markets archival boundary
print(co.trades_created_ts)
print(co.orders_updated_ts)
print(co.market_positions_last_updated_ts)  # v3.26.0; may be None on older payloads
```

Per-surface archival boundaries for the historical store. Data older than each
timestamp for that surface has been moved out of the live `markets.*` /
`portfolio.*` endpoints and must be read from the matching `historical.*`
method. Use `market_positions_last_updated_ts` to decide between
`historical.positions` and live `portfolio.positions` for settled positions.

## Historical markets

```python
page = client.historical.markets(
    series_ticker="KXPRES",
    event_ticker="KXPRES-24",
    tickers=["KXPRES-24-DJT"],         # comma-joined wire form
    status="settled",                  # MarketStatusLiteral
    min_close_ts=1_600_000_000,
    max_close_ts=1_650_000_000,
    mve_filter="exclude",
    limit=500,
)
for snapshot in page:
    print(snapshot.ticker, snapshot.settled_at)
```

## Historical trades

```python
trades = client.historical.trades(
    ticker="KXPRES-24-DJT",
    min_ts=1_600_000_000,
    max_ts=1_650_000_000,
    is_block_trade=False,   # v3.20.0: omit for all; True = only block, False = only non-block
    limit=1000,
)
```

## Historical fills and orders

Both require auth — these are your own trade history.

```python
for fill in client.historical.fills_all(
    ticker="KXPRES-24-DJT",
    min_ts=1_600_000_000,
    subaccount=1,  # omit to include every subaccount
):
    print(fill.fill_id, fill.count)

for order in client.historical.orders_all(ticker="KXPRES-24-DJT", min_ts=1_600_000_000):
    print(order.order_id, order.client_order_id)
```

`subaccount` is optional on both fills and orders (`0` is the primary subaccount).
Omit it to include every subaccount. A key restricted to one subaccount still
sees only that subaccount, and a supplied value must match the restriction.

## Historical positions

Auth required. Settled market positions archived to the historical database
(OpenAPI v3.26.0 / SDK v7.3.0). Positions whose markets were archived before
`market_positions_last_updated_ts` on `cutoff()` are available here; unsettled
positions remain on `portfolio.positions()`. Query params are a subset of the
live portfolio surface — no `count_filter` or `subaccount`.

```python
resp = client.historical.positions(
    ticker="KXPRES-24-DJT",
    event_ticker="KXPRES-24",
    limit=100,
)
for mp in resp.market_positions:
    print(mp.ticker, mp.position, mp.realized_pnl)

# Auto-paginate market_positions (event_positions are page-local aggregates;
# walk positions() page-by-page if you need the event view):
for mp in client.historical.positions_all(event_ticker="KXPRES-24"):
    print(mp.ticker, mp.position)
```

`positions()` returns `PositionsResponse` — the same shape as
[`portfolio.positions`](portfolio.md#positions) (`market_positions`,
`event_positions`, `cursor` / `has_next`).

## Historical candlesticks

```python
candles = client.historical.candlesticks(
    ticker="KXPRES-24-DJT",
    start_ts=1_600_000_000,
    end_ts=1_650_000_000,
    period_interval=3600,
)
```

## Reference

::: kalshi.resources.historical.HistoricalResource
    options:
      heading_level: 3

::: kalshi.resources.historical.AsyncHistoricalResource
    options:
      heading_level: 3
