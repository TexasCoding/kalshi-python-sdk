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
| `fills(...)` / `fills_all(...)` | `GET /historical/fills` | **yes** |
| `orders(...)` / `orders_all(...)` | `GET /historical/orders` | **yes** |

## Cutoff

```python
co = client.historical.cutoff()
print(co.cutoff_ts)
```

The "everything older than this timestamp is finalized" boundary. Use it to
decide whether to query the historical archive or the live `markets.*` /
`portfolio.*` endpoints.

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
for fill in client.historical.fills_all(ticker="KXPRES-24-DJT"):
    print(fill.fill_id, fill.price, fill.count)

for order in client.historical.orders_all(status="executed"):
    print(order.order_id, order.client_order_id)
```

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
