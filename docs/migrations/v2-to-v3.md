# Migrating from v2.x to v3.0.0

v3.0.0 renames three groups of public methods. All old names continue to work
in v3.0.0 as `@typing_extensions.deprecated` aliases that emit
`DeprecationWarning` on every call. The aliases will be removed no sooner than
**v3.1.0**, so migrate before then.

The wire protocol is unchanged. v3 is purely a Python-API ergonomics break.

## TL;DR — search and replace cheat sheet

| Find | Replace |
|---|---|
| `.communications.list_rfqs(` | `.communications.rfqs.list(` |
| `.communications.list_all_rfqs(` | `.communications.rfqs.list_all(` |
| `.communications.get_rfq(` | `.communications.rfqs.get(` |
| `.communications.create_rfq(` | `.communications.rfqs.create(` |
| `.communications.delete_rfq(` | `.communications.rfqs.delete(` |
| `.communications.list_quotes(` | `.communications.quotes.list(` |
| `.communications.list_all_quotes(` | `.communications.quotes.list_all(` |
| `.communications.get_quote(` | `.communications.quotes.get(` |
| `.communications.create_quote(` | `.communications.quotes.create(` |
| `.communications.delete_quote(` | `.communications.quotes.delete(` |
| `.communications.accept_quote(` | `.communications.quotes.accept(` |
| `.communications.confirm_quote(` | `.communications.quotes.confirm(` |
| `.markets.list_trades_all(` | `.markets.list_all_trades(` |
| `.orders.fills(` | `.portfolio.fills(` |
| `.orders.fills_all(` | `.portfolio.fills_all(` |

These map 1:1 — argument signatures and return types are identical. The only
behavioral difference is that the old names emit a `DeprecationWarning`.

## 1. CommunicationsResource sub-namespaces (#348)

The flat noun-prefixed methods on `CommunicationsResource` collapse into two
sub-resources matching the OpenAPI v3.18.0 tag structure.

### Before (v2.x)

```python
from kalshi import KalshiClient

client = KalshiClient.from_env()

rfqs = client.communications.list_rfqs(limit=50)
rfq = client.communications.get_rfq("rfq-123")
new = client.communications.create_rfq(market_ticker="MKT-1", rest_remainder=True)
client.communications.delete_rfq("rfq-123")

quotes = client.communications.list_quotes(quote_creator_user_id="u1")
client.communications.accept_quote("q-456", accepted_side="yes")
client.communications.confirm_quote("q-456")
```

### After (v3.0.0)

```python
from kalshi import KalshiClient

client = KalshiClient.from_env()

rfqs = client.communications.rfqs.list(limit=50)
rfq = client.communications.rfqs.get("rfq-123")
new = client.communications.rfqs.create(market_ticker="MKT-1", rest_remainder=True)
client.communications.rfqs.delete("rfq-123")

quotes = client.communications.quotes.list(quote_creator_user_id="u1")
client.communications.quotes.accept("q-456", accepted_side="yes")
client.communications.quotes.confirm("q-456")
```

### Notes

- `client.communications.get_id(...)` (the misc endpoint) **stays at the top
  level** — no sub-noun.
- The async API mirrors the sync API: `async_client.communications.rfqs.list(...)`.
- If you type-annotate sub-resource attributes, import the new classes from the
  top level:
  ```python
  from kalshi import RFQsResource, QuotesResource, AsyncRFQsResource, AsyncQuotesResource
  ```

## 2. `*_all` naming standardization (#349)

`MarketsResource.list_trades_all` was the only outlier still using the
`list_<noun>_all` suffix form. Renamed to `list_all_<noun>` (prefix form) to
match the other three resources.

### Before (v2.x)

```python
for trade in client.markets.list_trades_all(ticker="MKT-1", limit=200):
    process(trade)
```

### After (v3.0.0)

```python
for trade in client.markets.list_all_trades(ticker="MKT-1", limit=200):
    process(trade)
```

Same iterator semantics, same filter kwargs.

## 3. `fills` relocation: orders → portfolio (#351)

The `/portfolio/fills` endpoint now sits on `PortfolioResource` alongside
`settlements`, `deposits`, and `withdrawals` — matching the URL family.

### Before (v2.x)

```python
page = client.orders.fills(ticker="MKT-1", min_ts=since)
for fill in client.orders.fills_all(order_id="ord-1"):
    process(fill)
```

### After (v3.0.0)

```python
page = client.portfolio.fills(ticker="MKT-1", min_ts=since)
for fill in client.portfolio.fills_all(order_id="ord-1"):
    process(fill)
```

Signatures and return types are identical (`Page[Fill]` with `cursor`,
`min_ts`, `max_ts`, `ticker`, `order_id`, etc.).

## Detecting deprecated calls during migration

The aliases use `@typing_extensions.deprecated` (PEP 702), which type checkers
recognize. Add a stricter pytest config for the duration of your migration:

```toml
# pyproject.toml
[tool.pytest.ini_options]
filterwarnings = [
    "error::DeprecationWarning:kalshi.*",
]
```

This turns every deprecated kalshi call into a test failure until you update.

For a softer approach, log warnings instead of erroring:

```python
import warnings
warnings.filterwarnings("default", category=DeprecationWarning, module=r"kalshi(\..*)?")
```

## Why a major version for renames?

Per project policy (CHANGELOG §2.7.0), bug-surfacing behavioral fences ship in
minor releases; intentional public-API renames are reserved for major releases.
v3.0.0 is the first major version under this policy. v2.5–v2.7 each shipped
behavioral fences in minor versions because they surfaced silent bugs;
v3.0.0 renames previously-correct method names purely for API ergonomics.

## Removal schedule

The deprecated aliases will be removed no sooner than **v3.1.0**. Migration
done before then is forward-compatible across all v3.x.
