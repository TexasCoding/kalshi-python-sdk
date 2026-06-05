# DataFrames

`Page[T]` carries `.to_dataframe()` (pandas) and `.to_polars()` (polars).
Neither library is a hard dependency.

## Install

```bash
pip install 'kalshi-sdk[pandas]'
# or
pip install 'kalshi-sdk[polars]'
# or both
pip install 'kalshi-sdk[all]'
```

Calling either method without the corresponding library installed raises
`ImportError` with the exact `pip install` hint.

## Quick example

```python
df = client.markets.list(status="open", limit=500).to_dataframe()
print(df[["ticker", "yes_bid", "yes_ask", "volume_24h"]].head())
```

## How it works

Both methods build a column-oriented `dict[field, list[value]]` over
`page.items` (`getattr` per field — deliberately avoiding a per-row
`model_dump`) and hand it to `pd.DataFrame(...)` / `pl.DataFrame(...)`. Nested
model cells are dumped to dicts per column (so polars can infer a `Struct`
dtype) while scalar cells pass through unchanged.

This means:

- **`Decimal` stays `Decimal`.** Prices come through as Decimals in a pandas
  object-dtype column. Cast to float yourself if you want numeric ops:

    ```python
    df["yes_bid"] = df["yes_bid"].astype(float)
    ```

- **`datetime` stays `datetime`.** Timestamp fields are real datetimes, not
  ISO strings.

- **Nested models become nested structures.** A `Candlestick` row has
  `yes_bid: BidAskDistribution` (a `BaseModel`). After `model_dump`, that field
  becomes a `dict`. Polars infers a struct; pandas keeps it as an object column.

## One page only

Both methods convert **the current page**, not every page across cursors. To
flatten a multi-page result into one frame:

```python
import pandas as pd
from kalshi import KalshiClient

with KalshiClient.from_env() as client:
    rows = list(client.orders.list_all(status="resting"))

df = pd.DataFrame([o.model_dump(mode="python") for o in rows])
```

`list_all()` returns the items already unwrapped (not `Page` objects), so you
work with `BaseModel`s directly.

## Async

The async client's `list_all()` returns an `AsyncIterator[T]`. Materialize it
once before converting:

```python
import asyncio
import polars as pl
from kalshi import AsyncKalshiClient

async def collect() -> list:
    async with AsyncKalshiClient.from_env() as c:
        return [o async for o in c.orders.list_all(status="resting")]

rows = asyncio.run(collect())
df = pl.DataFrame([o.model_dump(mode="python") for o in rows])
```

## Reference

::: kalshi.models.common.Page.to_dataframe

::: kalshi.models.common.Page.to_polars
