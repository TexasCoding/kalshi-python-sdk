# Kalshi Python SDK — Consistency & Coverage Audit

**Date:** 2026-04-24
**Scope:** Current `main` branch. REST resources + WebSocket. Spec v3.13.0 (OpenAPI), v2.0.0 (AsyncAPI).
**Source docs:** `sdk-surface.md`, `openapi-endpoints.md`, `test-coverage.md` (this directory).

> ⚠️ The original `test-coverage.md` (agent-produced) contained substantial false positives — its "zero-unit-test" and "not-in-METHOD_ENDPOINT_MAP" lists were largely wrong. Numbers in this document were re-verified by direct grep + `METHOD_ENDPOINT_MAP` inspection. See §5 for the corrected test-coverage numbers.

---

## 1. Headline

| Dimension | Status |
|---|---|
| REST endpoint coverage vs spec | **100%** (89/89 operations) |
| `METHOD_ENDPOINT_MAP` drift registration | **100%** (89/89 tuples) |
| Sync + async parity | **100%** (19/19 resource pairs) |
| Paginators on cursor-paginated endpoints | **100%** |
| Request-body model discipline (v0.8.0+) | **100%** (except 4 documented `json={}` empty-body workarounds) |
| Unit-test coverage | **132/133 methods have ≥1 unit test** (1 true gap) |
| Integration-test coverage | **129/133 methods referenced** (4 true gaps, all in `orders`) |

**Bottom line:** no REST surface gap, no drift-map gap, no fundamental pattern break. The real remediation list is small and surgical: 1 missing unit test, 4 missing integration tests, 6 weakly-tested methods, and a handful of minor pattern cleanups.

---

## 2. Endpoint coverage (spec vs SDK)

From `openapi-endpoints.md` §3 — verified by diffing `set(spec_operations)` against `set(METHOD_ENDPOINT_MAP_tuples)`.

- **89 operations** in `specs/openapi.yaml` v3.13.0 (across 77 paths, 17 tags)
- **89 distinct `(method, path)` tuples** registered in `METHOD_ENDPOINT_MAP`
- `set(spec) - set(map) == ∅`
- `set(map) - set(spec) == ∅`
- **48 `EXCLUSIONS` entries** — all field/kwarg-level, all with documented `reason` strings (34 method-level, 14 model-level)

No endpoints are missing. No endpoints are phantom.

WebSocket: **11 data channels + 2 control channels** in `asyncapi.yaml` v2.0.0 → all 11 data channels implemented as typed subscribe methods on `KalshiWebSocket`.

---

## 3. Pattern consistency — clean

The v0.8.0 request-model discipline holds across the surface:

- Every POST / PUT / DELETE-with-body builds a Pydantic request model with `model_config = {"extra": "forbid"}`, serializes via `model_dump(exclude_none=True, by_alias=True, mode="json")`, and passes the result as `json=…`. No inline `dict` request bodies anywhere.
- Every paginated `list_X` endpoint has a matching `list_X_all` / `X_all` auto-paginator counterpart.
- Every async resource mirrors its sync counterpart one-for-one; no signature drift, no missing methods, no extra methods.
- Kwarg-shadow avoidance for Python built-ins is handled consistently: `incentive_type`, `milestone_type`, `target_type`, `accepted_side`. Each renamed param has a corresponding `EXCLUSIONS` entry with a `built-in shadow` reason.
- `Page[T]` return type is used uniformly for cursor-paginated list endpoints. `Iterator[T]` / `AsyncIterator[T]` are returned uniformly from `_all` variants (sync yields, async uses async-generator return without `async def`).

---

## 4. Pattern consistency — flagged

Six real but minor inconsistencies. None are bugs; none break contracts; all are cleanable.

### 4.1 `_all()` suffix placement varies

The paginator helper is always named — what varies is *where* `_all` lands relative to the object:

| Resource | `list` name | `_all` name | Form |
|---|---|---|---|
| markets | `list_trades` | `list_trades_all` | object first |
| orders | `fills` | `fills_all` | object first |
| portfolio | `settlements` | `settlements_all` | object first |
| subaccounts | `list_transfers` | `list_all_transfers` | action first |
| communications | `list_rfqs` | `list_all_rfqs` | action first |
| communications | `list_quotes` | `list_all_quotes` | action first |
| events | `list_multivariate` | `list_all_multivariate` | action first |

Both conventions exist. Pick one and migrate. Recommend **object-first** (`list_trades_all`, `list_transfers_all`) to match the plain `list → list_all` base case, where `list_all` = `list` + `_all` suffix (not `list_all_X`).

**Blast radius** — these are public API renames. Pre-release, so per CLAUDE.md memory we rename directly without deprecation shims.

### 4.2 `orders.queue_position()` has no response model

`kalshi/resources/orders.py:309–320` returns `Decimal` parsed by hand from the response dict, trying two legacy keys (`queue_position_fp`, then `queue_position`). Works, but it's the only GET in the SDK without a response model.

Fix: add a `QueuePositionResponse` Pydantic model to `kalshi/models/orders.py`, return the `Decimal` field off it.

### 4.3 `orders.batch_cancel()` bypasses `_delete()`

`orders.py:186–188` uses a custom `_delete_with_body()` helper; async version (`orders.py:482`) calls `self._transport.request("DELETE", …, json=…)` directly. DELETE-with-body is legitimately awkward in httpx, but the two implementations diverge from each other. Consider lifting a single `_delete_with_body` helper onto the base `SyncResource` / `AsyncResource` so both sides share one path.

### 4.4 Four documented `json={}` empty-body workarounds

These are fine — they're documented in-file — but worth cataloguing:

- `subaccounts.create()` — POST `/portfolio/subaccounts` with no body (demo server rejects without Content-Type)
- `order_groups.reset()` / `trigger()` — PUT with empty body (same reason)
- `communications.confirm_quote()` — PUT with empty body (same reason)

Acceptable. No action required.

### 4.5 `forecast_percentile_history` kwarg: `percentiles: list[int]`

Minor — every other list-valued query param uses a CSV-joined string via `_join_tickers()` / `_join()` helper. Check whether `percentiles` is serialized the same way or diverges. (Read from `series.py:forecast_percentile_history`.)

### 4.6 `Markets.candlesticks` vs `Historical.candlesticks` shape

- `Markets.candlesticks(series_ticker, ticker, …) → list[Candlestick]` via `/series/{series_ticker}/markets/{ticker}/candlesticks`
- `Historical.candlesticks(ticker, …) → list[Candlestick]` via `/historical/markets/{ticker}/candlesticks`

Both return `list[Candlestick]`, but the live endpoint requires `series_ticker` while the historical endpoint does not. That's spec-driven, not a defect — just note it in docs so users don't reach for the wrong one.

---

## 5. Test-coverage gaps (re-verified)

The agent-generated `test-coverage.md` is unreliable — it claimed 10 methods had 0 unit tests but direct grep finds only 1. Corrected numbers below (method names are `ResourceClass.method_name` shorthand):

### 5.1 Unit-test gaps — TRUE list

**1 method with zero unit tests:**
- `fcm.orders_all` — `tests/test_fcm.py` tests `orders` and `positions` but not the paginator wrapper.

**6 methods with exactly 1 unit test function (weak):**
- `markets.list_trades`
- `markets.list_trades_all`
- `orders.list_all`
- `multivariate.list_all`
- `live_data.get_typed`
- `structured_targets.list_all`

(Note: paginator `_all` methods often only test "iterates through pages" once; acceptable at 1 if the underlying `list` is well-tested. But `live_data.get_typed` at 1 test is genuinely weak because `get_typed` is the path-typed variant with its own routing, and `markets.list_trades` at 1 test is weak because the live trades endpoint has several query combos.)

### 5.2 Integration-test gaps — TRUE list

Integration tests exist for all 19 resources. **Four methods are absent from the integration suite, all in `orders`:**

- `orders.amend` — POST `/portfolio/orders/{order_id}/amend`
- `orders.decrease` — POST `/portfolio/orders/{order_id}/decrease`
- `orders.queue_positions` — GET `/portfolio/orders/queue_positions`
- `orders.queue_position` — GET `/portfolio/orders/{order_id}/queue_position`

All four are real order-management flows that the SDK ships for paper/live trading. Running them on demo requires a placed order to act on — `amend`/`decrease` are stateful mutations, `queue_position[s]` are reads but require existing resting orders.

### 5.3 Contract-drift map — FULLY COVERED

Agent 3 claimed 9 methods were missing from `METHOD_ENDPOINT_MAP` (multivariate ×6, structured_targets ×2, series.forecast ×1). **All 9 are present.** Verified via direct grep of `tests/_contract_support.py`:

- Multivariate entries at lines 600–646
- Structured targets entries at lines 585–597
- `series.forecast_percentile_history` entry at lines 534–544

`METHOD_ENDPOINT_MAP` is 100% complete. No action needed on this axis.

### 5.4 `BODY_MODEL_MAP` coverage

16 request models registered. Matches the count of POST/PUT/DELETE-with-body endpoints. No missing registrations.

---

## 6. Prioritized remediation list

### Tier 1 — required for the "100% coverage" claim

1. **Add unit test for `fcm.orders_all`** (`tests/test_fcm.py`). One test pattern: mock two pages via respx, iterate, assert total items + cursor progression. Pattern exists in `tests/test_markets.py::test_list_all_paginates`.
2. **Add integration tests for the 4 orders methods** in `tests/integration/test_orders.py`:
   - `test_amend_flow` — place order → amend → verify response fields → cancel
   - `test_decrease_flow` — place order → decrease → verify new count → cancel
   - `test_queue_positions` — place order(s) → list queue positions → assert shape
   - `test_queue_position` — place order → get queue position → assert Decimal return
   These need live demo keys; may want to gate behind a pytest marker.

### Tier 2 — coverage strengthening

3. **Strengthen weak-coverage methods** (add at least one additional unit test case each):
   - `markets.list_trades` — add a filter-combo test (ticker + ts range)
   - `markets.list_trades_all` — add multi-page iteration assertion
   - `orders.list_all` — add paginated iteration assertion
   - `multivariate.list_all` — add paginated iteration assertion
   - `live_data.get_typed` — test at least one non-default `milestone_type`
   - `structured_targets.list_all` — add paginated iteration assertion

### Tier 3 — pattern cleanups (pre-release, no shim needed)

4. **Standardize `_all()` placement** — rename to object-first form everywhere:
   - `subaccounts.list_all_transfers` → `list_transfers_all`
   - `communications.list_all_rfqs` → `list_rfqs_all`
   - `communications.list_all_quotes` → `list_quotes_all`
   - `events.list_all_multivariate` → `list_multivariate_all`
   Update `METHOD_ENDPOINT_MAP`, `EXCLUSIONS`, and integration tests in lockstep.
5. **Add `QueuePositionResponse` model** in `kalshi/models/orders.py` and wire into `orders.queue_position()` — replaces manual dict fallback with model validation. Drift-test entry already exists.
6. **Lift shared `_delete_with_body` helper** onto the sync + async resource bases so `orders.batch_cancel` doesn't hand-roll the path twice.

### Tier 4 — nice to have (non-blocking)

7. Audit `forecast_percentile_history` list-param serialization (§4.5).
8. Docstring cross-reference on `Markets.candlesticks` vs `Historical.candlesticks` to disambiguate (§4.6).

---

## 7. Does "100% coverage" hold today?

Headline-level **yes** — every REST spec operation is exposed, mapped for drift, and has at least one unit test + one integration test file.

Operationally **no** — the four `orders.{amend, decrease, queue_position, queue_positions}` methods have no integration test, and `fcm.orders_all` has no unit test. Close Tier 1 and the "every endpoint tested on both layers" claim is defensible.

Pattern consistency **yes modulo Tier 3** — the `_all` naming inconsistency and the hand-rolled dict parsing in `queue_position` are the only loose threads that a second pair of eyes would call out.

---

**Next step suggestion:** approve Tier 1 + 2 for immediate execution (small, mechanical, high-confidence). Defer Tier 3 pending a decision on the `_all` naming convention — that's the only step that touches public API surface.
