# Series

A **series** is a recurring family of events — `KXPRES` for presidential
elections, `KXNYRAIN` for rain in NYC, etc. List, fetch, inspect fee history,
pull event/forecast candlesticks.

## Quick reference

| Method | Endpoint | Auth |
|---|---|---|
| `list(*, category, tags, include_product_metadata, include_volume, min_updated_ts)` | `GET /series` | no |
| `get(series_ticker, *, include_volume=None)` | `GET /series/{series_ticker}` | no |
| `fee_changes(*, series_ticker=None, show_historical=None)` | `GET /series/fee_changes` | no |
| `event_candlesticks(series_ticker, ticker, *, start_ts, end_ts, period_interval)` | `GET /series/{series_ticker}/events/{ticker}/candlesticks` | no |
| `forecast_percentile_history(series_ticker, ticker, *, percentiles, start_ts, end_ts, period_interval)` | `GET /series/{series_ticker}/events/{ticker}/forecast_percentile_history` | **yes** |

!!! note "`series.list()` returns a flat list, not a Page"
    Series are a small finite set; the endpoint doesn't paginate.

## List series

```python
all_series = client.series.list(
    category="Elections",
    tags=["2024"],
    include_product_metadata=True,
    include_volume=True,
)
for s in all_series:
    print(s.series_ticker, s.title)
```

## Get one series

```python
s = client.series.get("KXPRES", include_volume=True)
print(s.title, s.volume)
```

## Fee history

```python
changes = client.series.fee_changes(series_ticker="KXPRES", show_historical=True)
for ch in changes:
    print(ch.effective_ts, ch.maker_fee, ch.taker_fee)
```

## Event candlesticks

Note: the second path parameter is an **event** ticker, not a market ticker.

```python
candles = client.series.event_candlesticks(
    series_ticker="KXPRES",
    ticker="KXPRES-24",                  # event ticker
    start_ts=1_700_000_000,
    end_ts=1_700_100_000,
    period_interval=3600,
)
```

## Forecast percentile history

Auth-required. Returns historical percentile points for a forecasted event.

```python
hist = client.series.forecast_percentile_history(
    series_ticker="KXTEMP",
    ticker="KXTEMP-24-DEC",              # event ticker
    percentiles=[25, 50, 75],            # explode form on the wire
    start_ts=1_700_000_000,
    end_ts=1_700_100_000,
    period_interval=86400,
)
for point in hist.forecast_percentiles:
    print(point.ts, point.percentile, point.value)
```

`percentiles` serializes as `?percentiles=25&percentiles=50&percentiles=75`
(explode form, unlike `tickers` on other endpoints).

## Reference

::: kalshi.resources.series.SeriesResource
    options:
      heading_level: 3

::: kalshi.resources.series.AsyncSeriesResource
    options:
      heading_level: 3
