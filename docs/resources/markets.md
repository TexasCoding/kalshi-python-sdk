# Markets

Operate on Kalshi markets — the leaf-level YES/NO contracts. List, fetch a
single market, pull its orderbook, get candlesticks (single or bulk), list
recent trades.

## Quick reference

| Method | Endpoint | Auth |
|---|---|---|
| `list(...)` | `GET /markets` | no |
| `list_all(...)` | walks `list` | no |
| `get(ticker)` | `GET /markets/{ticker}` | no |
| `orderbook(ticker, depth=None)` | `GET /markets/{ticker}/orderbook` | **yes** |
| `candlesticks(series_ticker, ticker, *, start_ts, end_ts, period_interval, ...)` | `GET /series/{series_ticker}/markets/{ticker}/candlesticks` | no |
| `bulk_candlesticks(*, market_tickers, ...)` | `GET /markets/candlesticks` | no |
| `bulk_orderbooks(*, tickers)` | `GET /markets/orderbooks` | **yes** |
| `list_trades(...)` | `GET /markets/trades` | no |
| `list_all_trades(...)` | walks `list_trades` | no |

!!! warning "Orderbook endpoints require auth"
    `orderbook()` and `bulk_orderbooks()` raise `AuthRequiredError` on an
    unauthenticated client. The rest of the market-data surface is public.

## List markets

```python
page = client.markets.list(
    status="open",                 # MarketStatusLiteral
    series_ticker="KXPRES",
    event_ticker="KXPRES-24",
    tickers=["KXPRES-24-DJT", "KXPRES-24-KH"],  # or "KXPRES-24-DJT,KXPRES-24-KH"
    min_close_ts=1_700_000_000,
    max_close_ts=1_800_000_000,
    mve_filter="exclude",          # MveFilterLiteral
    limit=200,
)
for market in page:
    print(market.ticker, market.yes_bid, market.yes_ask)
```

`tickers` accepts a `list[str]` or a comma-joined string — the SDK comma-joins
for the wire (this endpoint uses comma-join form, **not** the explode form
used by `bulk_orderbooks`).

All the `*_ts` filters (`min_close_ts`, `max_close_ts`, `min_open_ts`,
`max_open_ts`, `min_settle_ts`, `max_settle_ts`, `min_volume_24h`,
`min_total_volume`, `min_total_open_interest`) are Unix-second ints. Pair them
with `min_open_ts`/`max_open_ts` etc. as needed.

`list_all(...)` walks cursors and returns an iterator — see
[Pagination](../pagination.md).

## Get one market

```python
market = client.markets.get("KXPRES-24-DJT")
print(market.status, market.yes_bid, market.yes_ask, market.volume)
```

## Orderbook (single)

```python
ob = client.markets.orderbook("KXPRES-24-DJT", depth=20)
print(ob.yes[:5])   # list[OrderbookLevel], best-first
print(ob.no[:5])
```

`depth` is the number of price levels per side (default unbounded). Wire keys
`orderbook_fp.yes_dollars` / `no_dollars` are normalized to `ob.yes` / `ob.no`
of type `Decimal`.

## Bulk orderbooks

```python
books = client.markets.bulk_orderbooks(tickers=["KXPRES-24-DJT", "KXPRES-24-KH"])
for ob in books:
    print(ob.market_ticker, ob.yes[0])
```

- **Cap: 100 tickers per call.**
- **Wire format:** explode (`?tickers=a&tickers=b`). The SDK builds this for
  you regardless of whether you pass `list[str]` or a comma-joined string.
- Auth required.

## Candlesticks

```python
candles = client.markets.candlesticks(
    series_ticker="KXPRES",
    ticker="KXPRES-24-DJT",
    start_ts=1_700_000_000,
    end_ts=1_700_100_000,
    period_interval=60,            # seconds: 60, 3600, 86400
    include_latest_before_start=True,
)
for c in candles.candlesticks:
    print(c.end_period_ts, c.yes_bid)
```

`include_latest_before_start` includes the most recent candle before
`start_ts` for seamless rendering.

## Bulk candlesticks

```python
batches = client.markets.bulk_candlesticks(
    market_tickers=["KXPRES-24-DJT", "KXPRES-24-KH"],   # 1–100 tickers
    series_ticker="KXPRES",                              # optional shard hint
    start_ts=1_700_000_000,
    end_ts=1_700_100_000,
    period_interval=3600,
)
for batch in batches:                # list[MarketCandlesticks]
    print(batch.market_ticker, len(batch.candlesticks))
```

Comma-joined wire form (`?market_tickers=a,b,c`). 100-ticker cap.

## List trades

```python
page = client.markets.list_trades(
    ticker="KXPRES-24-DJT",
    min_ts=1_700_000_000,
    max_ts=1_700_100_000,
    limit=200,
)
for trade in page:
    print(trade.trade_id, trade.taker_side, trade.yes_price, trade.count)
```

!!! warning "Deprecated since v3.0.0"
    `list_trades_all` is the legacy name; it still works but emits
    `DeprecationWarning` and will be removed in a future release. Use
    `list_all_trades` instead — see [#349][issue-349].

    [issue-349]: https://github.com/TexasCoding/kalshi-python-sdk/issues/349

## Reference

::: kalshi.resources.markets.MarketsResource
    options:
      heading_level: 3

::: kalshi.resources.markets.AsyncMarketsResource
    options:
      heading_level: 3
