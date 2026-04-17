# Resource Method / Spec Parameter Audit (v0.7.0)

Generated: 2026-04-16 during Session 1a (feat/resource-spec-alignment).

This is the working audit doc for the v0.7.0 resource/spec alignment work. Each
row below represents a single decision about one parameter on one method. Session
1b applies the dispositions in code.

## Dispositions

- **ADD** — spec has this param, SDK doesn't. Add the kwarg.
- **REMOVE** — SDK exposes a param that isn't in the spec. Remove the kwarg. **BREAKING.**
- **RENAME** — SDK name ≠ spec name for the same logical param. Rename to spec. **BREAKING.**
- **RESERIALIZE** — wire format differs (e.g., comma-join vs explode:true). Fix serialization. May or may not be breaking depending on server tolerance.
- **EXCLUDE** — spec has it but intentionally not exposed. Reasons limited to `deprecated: true`, operator-only, paginator-handled.
- **TRANSLATED** — SDK uses a different name on purpose (bespoke translation preserved, documented).
- **OK** — spec and SDK agree. No action; row kept for completeness.

## Methodology

Rows produced by cross-referencing `METHOD_ENDPOINT_MAP` against `specs/openapi.yaml`
via `tests/_contract_support.py::_resolve_path_params`. Dispositions assigned per
the rules in the design doc. Inline body dicts (`amend`, `decrease`, `create`,
`batch_create`, `batch_cancel`, `create_market`, `lookup_tickers`) are **out of
scope** for this audit; covered by the separate inline-body-dict TODO.

## Summary

- **37 actionable rows** across 6 resources (events, exchange, multivariate have no findings).
- **2 REMOVE** (breaking): phantom kwargs `market_type` on markets.list, `settlement_status` on portfolio.positions.
- **2 RENAME** (breaking): path arg `event_ticker` → `ticker` on series.event_candlesticks and forecast_percentile_history.
- **1 QUERY RENAME** (breaking): historical.markets `ticker` → `tickers`.
- **32 ADD** (non-breaking).
- **0 RESERIALIZE** — `percentiles` explode:true already handled correctly by httpx (documented below for clarity).
- Under the 40-row split threshold → ships as a single v0.7.0.

---

## markets.py

### `MarketsResource.list` + `list_all` — `GET /markets`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| `market_type` | — | — | — | **REMOVE** | Phantom. Not in spec. Tested at `test_markets.py:63` — test also gets updated to drop this. |
| — | `min_created_ts` | int | query | **ADD** | |
| — | `max_created_ts` | int | query | **ADD** | |
| — | `min_updated_ts` | int | query | **ADD** | |
| — | `max_close_ts` | int | query | **ADD** | |
| — | `min_close_ts` | int | query | **ADD** | |
| — | `min_settled_ts` | int | query | **ADD** | |
| — | `max_settled_ts` | int | query | **ADD** | |
| — | `tickers` | string | query | **ADD** | Comma-separated list per spec description. Kwarg type `list[str] \| str \| None`, comma-join at method body (same pattern as `orders.queue_positions`). |
| — | `mve_filter` | string | query | **ADD** | Multi-value enum filter. Kwarg type `str \| None`. |
| `status` | `status` | string | query | OK | |
| `series_ticker` | `series_ticker` | string | query | OK | |
| `event_ticker` | `event_ticker` | string | query | OK | |
| `limit` | `limit` | int | query | OK | |
| `cursor` | `cursor` | string | query | OK | `list_all` omits `cursor` (paginator-handled). |

### `MarketsResource.get` — `GET /markets/{ticker}`
All OK. Path arg `ticker` matches spec.

### `MarketsResource.orderbook` — `GET /markets/{ticker}/orderbook`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| — | `depth` | int | query | **ADD** | Kwarg type `int \| None`. |
| `ticker` | `ticker` | string | path | OK | |

### `MarketsResource.candlesticks` — `GET /series/{series_ticker}/markets/{ticker}/candlesticks`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| — | `include_latest_before_start` | bool | query | **ADD** | Kwarg type `bool \| None`, "true or omit" rule. |
| `series_ticker` | `series_ticker` | string | path | OK | |
| `ticker` | `ticker` | string | path | OK | |
| `start_ts` | `start_ts` | int | query | OK | |
| `end_ts` | `end_ts` | int | query | OK | |
| `period_interval` | `period_interval` | int | query | OK | |

---

## events.py

All 6 methods match spec. v0.6.0 audit already covered `EventsResource.list()` drift.

- `list` / `list_all` — OK
- `list_multivariate` / `list_all_multivariate` — OK
- `get` — OK
- `metadata` — OK

---

## exchange.py

No parameters on any endpoint. All 3 methods OK.

---

## historical.py

### `HistoricalResource.markets` + `markets_all` — `GET /historical/markets`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| `ticker` | `tickers` | string | query | **RENAME** | **BREAKING.** Spec uses plural; comma-separated list. Kwarg becomes `tickers: list[str] \| str \| None`. Migration: `historical.markets(ticker="X")` → `historical.markets(tickers="X")` or `tickers=["X", "Y"]`. |
| — | `mve_filter` | string | query | **ADD** | |
| `limit` | `limit` | int | query | OK | |
| `cursor` | `cursor` | string | query | OK | `markets_all` omits `cursor`. |
| `event_ticker` | `event_ticker` | string | query | OK | |
| `series_ticker` | `series_ticker` | string | query | OK | |

### `HistoricalResource.cutoff` — `GET /historical/cutoff`
No params. OK.

### `HistoricalResource.market` — `GET /historical/markets/{ticker}`
All OK.

### `HistoricalResource.candlesticks` — `GET /historical/markets/{ticker}/candlesticks`
All OK.

### `HistoricalResource.fills` + `fills_all` — `GET /historical/fills`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| — | `max_ts` | int | query | **ADD** | |
| `ticker` | `ticker` | string | query | OK | |
| `limit` | `limit` | int | query | OK | |
| `cursor` | `cursor` | string | query | OK | |

### `HistoricalResource.orders` + `orders_all` — `GET /historical/orders`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| — | `max_ts` | int | query | **ADD** | |
| all others | | | | OK | same pattern as fills |

### `HistoricalResource.trades` + `trades_all` — `GET /historical/trades`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| — | `min_ts` | int | query | **ADD** | |
| — | `max_ts` | int | query | **ADD** | |
| all others | | | | OK | |

---

## orders.py

### `OrdersResource.cancel` — `DELETE /portfolio/orders/{order_id}`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| — | `subaccount` | int | query | **ADD** | |
| `order_id` | `order_id` | string | path | OK | |

### `OrdersResource.list` + `list_all` — `GET /portfolio/orders`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| — | `event_ticker` | string | query | **ADD** | |
| — | `min_ts` | int | query | **ADD** | |
| — | `max_ts` | int | query | **ADD** | |
| — | `subaccount` | int | query | **ADD** | |
| `ticker` | `ticker` | string | query | OK | Manual `if ticker:` truthiness pattern currently (orders.py:80-81). `_params()` standardization refactor applies here — see design doc. |
| `status` | `status` | string | query | OK | Same truthiness issue; standardize via `_params()`. |
| `limit` | `limit` | int | query | OK | |
| `cursor` | `cursor` | string | query | OK | `list_all` omits. |

### `OrdersResource.fills` + `fills_all` — `GET /portfolio/fills`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| — | `min_ts` | int | query | **ADD** | |
| — | `max_ts` | int | query | **ADD** | |
| — | `subaccount` | int | query | **ADD** | |
| all others | | | | OK | |

### Other orders methods
- `create` — body audit out of scope (inline body dict TODO)
- `get` — OK
- `batch_create` / `batch_cancel` — body audit out of scope
- `amend` / `decrease` — body audit out of scope; path args OK
- `queue_positions` — OK
- `queue_position` — OK

---

## portfolio.py

### `PortfolioResource.balance` — `GET /portfolio/balance`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| — | `subaccount` | int | query | **ADD** | |

### `PortfolioResource.positions` — `GET /portfolio/positions`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| `settlement_status` | — | — | — | **REMOVE** | Phantom. Spec has `count_filter` instead (different semantic). **BREAKING.** Migration note: users passing `settlement_status` must switch to `count_filter`. |
| — | `count_filter` | string | query | **ADD** | Replaces phantom `settlement_status` semantically. |
| — | `ticker` | string | query | **ADD** | |
| — | `subaccount` | int | query | **ADD** | |
| `limit` | `limit` | int | query | OK | |
| `cursor` | `cursor` | string | query | OK | |
| `event_ticker` | `event_ticker` | string | query | OK | |

### `PortfolioResource.settlements` + `settlements_all` — `GET /portfolio/settlements`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| — | `event_ticker` | string | query | **ADD** | |
| — | `min_ts` | int | query | **ADD** | |
| — | `max_ts` | int | query | **ADD** | |
| — | `subaccount` | int | query | **ADD** | |
| all others | | | | OK | |

---

## series.py

### `SeriesResource.list` — `GET /series`
All OK.

### `SeriesResource.get` — `GET /series/{series_ticker}`
All OK.

### `SeriesResource.fee_changes` — `GET /series/fee_changes`
All OK.

### `SeriesResource.event_candlesticks` — spec path `GET /series/{series_ticker}/events/{ticker}/candlesticks`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| `event_ticker` (arg name) | `ticker` | string | path | **RENAME** | **BREAKING.** Spec path template uses `{ticker}`; SDK arg is named `event_ticker`. Rename positional arg: `event_candlesticks(series_ticker, event_ticker, *, ...)` → `event_candlesticks(series_ticker, ticker, *, ...)`. URL f-string template updates too. Migration: `series.event_candlesticks("X", "Y", start_ts=...)` unchanged (positional); named `event_ticker=` callers must switch to `ticker=`. |
| `series_ticker` | `series_ticker` | string | path | OK | |
| `start_ts` / `end_ts` / `period_interval` | same | int | query | OK | |

### `SeriesResource.forecast_percentile_history` — spec path `GET /series/{series_ticker}/events/{ticker}/forecast_percentile_history`

| SDK Param | Spec Param | Spec Type | Style | Disposition | Notes |
|-----------|------------|-----------|-------|-------------|-------|
| `event_ticker` (arg name) | `ticker` | string | path | **RENAME** | **BREAKING.** Same rename as above. |
| `percentiles` | `percentiles` | array of int | `style: form, explode: true` | OK (documented) | Current SDK passes the list directly to `_params()`; httpx serializes as `?percentiles=25&percentiles=50` which matches `explode: true`. **Do not change to comma-join in Session 1b.** This row documents the correct serialization style per spec `openapi.yaml:1832`. |
| `series_ticker` | `series_ticker` | string | path | OK | |
| `start_ts` / `end_ts` / `period_interval` | same | int | query | OK | |

---

## multivariate.py

All 6 methods OK. `create_market` and `lookup_tickers` have body schemas which are
out of scope for this audit (inline body dict TODO).

---

## Session 1b Checklist (derived from dispositions above)

**Breaking changes (must be in CHANGELOG with migration):**
- `markets.list` / `list_all` — drop `market_type` kwarg
- `portfolio.positions` — drop `settlement_status` kwarg (users switch to `count_filter`)
- `historical.markets` / `markets_all` — rename `ticker` kwarg to `tickers`
- `series.event_candlesticks` — rename `event_ticker` positional arg to `ticker`
- `series.forecast_percentile_history` — rename `event_ticker` positional arg to `ticker`

**Non-breaking additions:**
- `markets.list` / `list_all`: +9 kwargs (min_created_ts, max_created_ts, min_updated_ts, max_close_ts, min_close_ts, min_settled_ts, max_settled_ts, tickers, mve_filter)
- `markets.orderbook`: +`depth`
- `markets.candlesticks`: +`include_latest_before_start`
- `historical.markets` / `markets_all`: +`mve_filter` (in addition to the rename)
- `historical.fills` / `fills_all`: +`max_ts`
- `historical.orders` / `orders_all`: +`max_ts`
- `historical.trades` / `trades_all`: +`min_ts`, +`max_ts`
- `orders.cancel`: +`subaccount`
- `orders.list` / `list_all`: +`event_ticker`, +`min_ts`, +`max_ts`, +`subaccount`
- `orders.fills` / `fills_all`: +`min_ts`, +`max_ts`, +`subaccount`
- `portfolio.balance`: +`subaccount`
- `portfolio.positions`: +`count_filter`, +`ticker`, +`subaccount` (alongside settlement_status REMOVE)
- `portfolio.settlements` / `settlements_all`: +`event_ticker`, +`min_ts`, +`max_ts`, +`subaccount`

**Refactor while touching (per design doc):**
- `orders.list` — standardize from manual dict + truthiness (`if ticker:`) to `_params()` helper. Fixes empty-string-drop behavior. Add regression test `test_empty_string_ticker_passes_through`.
- `orders.list_all` — same standardization.
- `orders.create` — manual dict building; standardize for consistency when touching.

**Tests (one per method, sync + async):**
- Consolidated test per method that calls with ALL new/renamed kwargs and asserts they reach the wire (per design doc test density decision).
- Dedicated regression tests for each REMOVE and RENAME (documents the breaking change).
- Dedicated test for `percentiles` explode:true serialization (prevents accidental future regression).
