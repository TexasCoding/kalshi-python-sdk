# TODOS

## North Star

**100% Kalshi endpoint coverage** — every REST operation in `specs/openapi.yaml` and every WebSocket channel in `specs/asyncapi.yaml` must have:
1. An SDK implementation (sync + async)
2. A unit test (happy path + error path + edge cases)
3. A real integration test against the Kalshi demo server

No new features, no publishing, no polish sweeps until this is closed. Side quests live in `BACKLOG.md`.

### Current state (audit 2026-04-18)

| Status | REST endpoints | % |
|---|---:|---:|
| FULL (SDK + unit + integration) | 13 | 14% |
| SDK + unit, no integration | 23 | 26% |
| Not implemented | 53 | 59% |
| **Total** | **89** | |

WebSocket: 15/32 message types dispatched, 3 integration tests (connectivity only).

`tests/integration/test_coverage.py` is currently red because Series (5 methods) and Multivariate Collections (6 methods) shipped without registration in `SCENARIO_REGISTRY`.

---

## Active phases

### v0.9.0 — Close Series + Multivariate integration gap (IMMEDIATE)
**What:** Register SeriesResource (5 methods) and MultivariateCollectionsResource (6 methods) in `SCENARIO_REGISTRY` (`tests/integration/coverage_harness.py`). Add real integration tests against the demo server. Also cover `EventsResource.list_multivariate` / `list_all_multivariate`.
**Why:** v0.6.0 and v0.7.0 shipped these resources with unit tests but skipped integration. Meta-coverage test is red on main. Smallest, highest-leverage move.
**Endpoints (11):**
- `GET /series`, `GET /series/{series_ticker}`, `GET /series/{series_ticker}/fee_changes`, `GET /series/{series_ticker}/events/{event_ticker}/candlesticks`, `GET /series/{series_ticker}/forecast_percentile_history`
- `GET /multivariate_event_collections`, `GET /multivariate_event_collections/{collection_ticker}`, `POST /multivariate_event_collections/{collection_ticker}/markets`, `GET /multivariate_event_collections/{collection_ticker}/lookup`, `GET /multivariate_event_collections/{collection_ticker}/lookup_history`
- `GET /events` with multivariate variant
**Impact:** NO_INT drops 23 → 12. Meta-coverage test goes green.
**Estimate:** ~3h.

### v0.10.0 — Order Groups resource
**What:** Implement `OrderGroupsResource` + `AsyncOrderGroupsResource` covering 7 endpoints. Pydantic models (request models with `extra="forbid"`), sync+async resources, unit tests (happy/error/auth-guard), integration tests, `METHOD_ENDPOINT_MAP` registration, `BODY_MODEL_MAP` entries for POST bodies.
**Why:** Advanced order strategies (OCO, if-then). Entire resource class missing today.
**Endpoints (7):**
- `GET /portfolio/order_groups`
- `GET /portfolio/order_groups/{order_group_id}`
- `POST /portfolio/order_groups`
- `DELETE /portfolio/order_groups/{order_group_id}`
- `POST /portfolio/order_groups/{order_group_id}/reset`
- `POST /portfolio/order_groups/{order_group_id}/trigger`
- `POST /portfolio/order_groups/{order_group_id}/limit`
**Estimate:** ~5h.

### v0.11.0 — Communications / RFQ + Subaccounts
**What:** Two new resource subsystems. Pydantic models, sync+async resources, unit + integration tests, contract map registration for all 17 endpoints.

**Communications / RFQ (11 endpoints):** quote CRUD + accept/confirm, RFQ CRUD. Concrete endpoints to confirm against spec during plan phase.
**Subaccounts (6 endpoints):** create, transfer, balances, netting (get+put), transfers list.

**Why:** OTC market access + multi-account workflows. Two of the largest "not implemented" buckets.
**Estimate:** ~11h.

### v0.12.0 — API Keys + Bulk/Batch + Milestones
**What:** Three smaller resource additions.
- **API Keys (5):** get, create, generate, delete, list — programmatic API key management.
- **Bulk / Batch (3):** batch markets candlesticks, batch orderbooks, batch trades — efficient data pulls.
- **Milestones (5):** list, get, live_data variants — milestone market tracking.

Each with models, sync+async resources, unit + integration tests, contract map entries.
**Estimate:** ~8h.

### v0.13.0 — Remaining endpoints + WebSocket parity
**What:**
- Implement ~16 remaining endpoints: FCM orders/positions, incentive programs, structured targets, search filters, `exchange.user_data_timestamp`, portfolio summary.
- Resolve WebSocket dispatch singular/plural drift (`user_orders` vs `user_order`, `market_positions` vs `market_position`, `multivariate_lookup` vs `multivariate`) via live capture against demo WS.
- Expand WebSocket integration coverage beyond the 3-test connectivity smoke: exercise each of the 15 dispatched message types end-to-end where demo allows.
**Why:** Final push to 100% REST + parity on WebSocket.
**Estimate:** ~10h.

---

## Reliability (gates CI trust for integration tests)

### P3: Integration test — handle transient 500 errors from demo API
**What:** `TestOrdersSync::test_list_all` intermittently fails with `KalshiServerError: HTTP 500` when paginating orders on the demo server. Investigate whether this is a known demo server issue or a bug in cursor handling. Consider adding a retry wrapper or `pytest.mark.flaky` for demo-specific transient failures.
**Why:** Transient 500s cause false test failures, making CI unreliable. The SDK's retry logic already handles 500s for GET requests, but `list_all()` re-raises after exhausting retries. Either retry count is too low for demo, or the demo server has a known instability on the orders list endpoint with cursors.
**Depends on:** Integration test suite stable (done).
**Added:** 2026-04-14

---

## Completed

### ~~P3: Integration test — series and multivariate event endpoints~~
**Completed:** v0.6.0 (2026-04-16). Added SeriesResource (5 methods: list, get, fee_changes, event_candlesticks, forecast_percentile_history) and MultivariateCollectionsResource (5 methods: list, get, create_market, lookup_tickers, lookup_history). Added list_multivariate/list_all_multivariate to EventsResource. Fixed EventsResource.list() param drift (added with_milestones, min_close_ts, min_updated_ts). 11 new endpoints, 50+ new tests, 4 contract map entries. Auth guards on forecast_percentile_history, create_market, lookup_tickers.
**Note:** v0.6.0 shipped the SDK + unit tests but **integration tests and `SCENARIO_REGISTRY` registration were not done** — see v0.9.0 phase above to close the gap.

### ~~P3: Integration test — order amendments and decrease~~
**Completed:** v0.5.0 (2026-04-15). Added `amend()`, `decrease()`, `queue_positions()`, and `queue_position()` to OrdersResource and AsyncOrdersResource. AmendOrderResponse and OrderQueuePosition models. 29 new tests (sync/async happy paths, error paths, serialization, auth guards). Contract map entries for spec drift coverage. Also added queue position endpoints (GET /portfolio/orders/queue_positions, GET /portfolio/orders/{order_id}/queue_position) as natural companion to amend.

### ~~P3: Piece 2 — automated contract test for request-param drift~~
**Completed:** v0.8.0 (2026-04-18). `TestRequestParamDrift` (query+path, 94 parametrized cases across 47 endpoints × sync+async) and `TestRequestBodyDrift` (body, 7 parametrized cases) in `tests/test_contracts.py`. Hard-fail on any drift; `EXCLUSIONS` allowlist in `tests/_contract_support.py` with reason strings. `test_exclusion_map_is_current` lint guards against stale allowlist entries. 25 bootstrap exclusions covering deprecated fields, paginator-handled cursor, count_fp wire normalization, deferred _fp variants on DecreaseOrderRequest, deprecated ids on BatchCancelOrdersRequest, and body-vs-query-param distinctions.

### ~~P3: Audit inline body dicts~~
**Completed:** v0.8.0 (2026-04-18). All POST/PUT/DELETE bodies routed through Pydantic models. CreateOrderRequest extended with 7 fields (time_in_force, post_only, reduce_only, self_trade_prevention_type, order_group_id, cancel_order_on_pause, subaccount) + buy_max_cost wired through. AmendOrderRequest, DecreaseOrderRequest, BatchCreateOrdersRequest, BatchCancelOrdersRequest (+ BatchCancelOrdersRequestOrder), and two multivariate request models added. Phantom `type` field on orders.create removed; buy_max_cost type fixed to int cents (spec-compliant); count wire key normalized to count_fp; batch_cancel migrated from deprecated `ids` wire field to preferred `orders` field with per-order subaccount support.

### ~~Normalize resource methods against OpenAPI spec surface (v0.7.0 major)~~
**Completed:** v0.7.0 (2026-04-16). Resource method query/path parameter surface aligned to spec across markets, historical, orders, portfolio, series. 5 BREAKING (2 phantom REMOVE: `markets.list.market_type`, `portfolio.positions.settlement_status`; 3 RENAME: `historical.markets.ticker`→`tickers`, series positional `event_ticker`→`ticker` on `event_candlesticks` + `forecast_percentile_history`). 32 ADD across the 5 resources (subaccount, *_ts ranges, mve_filter, count_filter, depth, include_latest_before_start, etc). Plus `_params()` standardization on `orders.list`/`list_all` (fixes pre-existing empty-string truthiness drop on `ticker` AND `status`), `_join_tickers` helper lifted to `_base.py`, `_delete()` extended to accept `params=`. 60+ new unit tests including 5 BREAKING regression tests, 4 dedicated tickers comma-join tests, 2 dedicated percentiles explode:true tests, 2 dedicated bool "true or omit" tests, 4 _params standardization regression tests. Migration guide in CHANGELOG. AUDIT.md `settlement_status` migration text corrected during /plan-eng-review round 2 (count_filter is NOT a semantic replacement — verified spec lines 2206-2221).

### ~~Extend spec drift pipeline to cover WebSocket models~~
**Completed:** 2026-04-15. Added AliasChoices to all 15 WS payload models matching AsyncAPI spec field naming (e.g., `yes_bid_dollars` -> `yes_bid`). Added `WS_CONTRACT_MAP` with 15 entries reusing existing `ContractEntry` dataclass. Added `TestWsSpecDrift` class with additive drift, required drift, schema coverage, completeness, and envelope type drift tests. Added `extra="allow"` to OrderbookSnapshotPayload and OrderbookDeltaPayload. Pipeline catches additive drift for TickerPayload (missing `price_dollars`, `time`) and several other models. Envelope type test detects 3 mismatches: `user_order` vs `user_orders`, `market_position` vs `market_positions`, `multivariate_lookup` vs `multivariate`.

### ~~Verify Kalshi price format (cents vs dollars)~~
**Completed:** 2026-04-14. Integration tests confirm DollarDecimal fields parse correctly from real API responses. Price fields use `_dollars` suffix and return decimal dollar values (e.g., "0.5600"), not integer cents. Verified across markets, orders, portfolio, and historical endpoints.

### ~~Verify candlestick endpoint paths and response format~~
**Completed:** 2026-04-14. Both MarketsResource.candlesticks() and HistoricalResource.candlesticks() now pass required params (start_ts, end_ts, period_interval) and parse responses correctly. The nested Candlestick model (BidAskDistribution/PriceDistribution) works against the real API.

### ~~Endpoint-level contract tests for resource methods~~
**Completed:** 2026-04-14. Integration tests now serve this role — every resource method is verified against the real API. Found and fixed 3 bugs: candlestick missing required params, batch_create count serialization, batch_create response unwrapping.

### ~~Async test coverage~~
**Completed:** v0.1.2 (2026-04-12). PR #20. Files: test_async_client.py, test_async_markets.py, test_async_orders.py.

### ~~KalshiClient constructor + from_env() tests~~
**Completed:** v0.1.2 (2026-04-12). File: test_client.py (315 lines).

### ~~Add py.typed marker for PEP 561 compliance~~
**Completed:** v0.1.0 (2026-04-12). File at `kalshi/py.typed`.

### ~~Auth path percent-encoding canonicalization~~
**Completed:** 2026-04-14. Added `_normalize_percent_encoding()` in `kalshi/auth.py` to normalize percent-encoded hex digits to uppercase per RFC 3986 section 2.1. Test vector corpus with 7 parametrized cases added to `tests/test_auth.py`.

### ~~Integration test — deeper field assertions on model responses~~
**Completed:** 2026-04-14. Created `tests/integration/assertions.py` with `assert_model_fields()` semantic oracle. Validates Decimal types (no floats), price ranges [0,1] for 18 named fields, datetime parsing, required-field presence, and recurses into nested BaseModel and list[BaseModel] fields. Wired into all 6 integration test files (markets, events, exchange, historical, orders, portfolio).

### ~~Integration test — error path coverage~~
**Completed:** 2026-04-14. Created `tests/integration/test_errors.py` with 5 tests for 404 (KalshiNotFoundError), 400 (KalshiValidationError), and 401 (KalshiAuthError) error paths against the demo API. Verifies status_code, message, and type-specific attributes (details, retry_after). Sync-only (error mapping is transport-shared via _map_error()).

### ~~Integration test — WebSocket live connection~~
**Completed:** 2026-04-14 (PR #24). Created `tests/integration/test_websocket.py` with 3 tests: WS connect+auth, orderbook snapshot subscribe+receive, disconnect lifecycle. Uses `ws_session` fixture wrapping `KalshiWebSocket` and `retry_transient` decorator (7 unit tests in `test_helpers.py`). Also fixed `demo=True` not setting `ws_base_url` to demo, and extended `_assert_demo_url` safety gate to check WS URL.

### ~~Integration test — order lifecycle with fills verification~~
**Completed:** 2026-04-14 (PR #24). Created `test_order_fill_lifecycle` in `test_orders.py` with `fill_guarantee` helper in `helpers.py`. Places opposing buy+sell orders, verifies fill data when available. Demo server blocks self-trading (sell side canceled), so test verifies order placement and statuses as fallback. Fill field assertions use canonical `ticker` field per OpenAPI spec.

### ~~Integration test — pagination correctness~~
**Completed:** 2026-04-14 (PR #24). Added 3 tests to `test_markets.py`: `test_pagination_no_overlap` (cursor returns disjoint pages), `test_pagination_cursor_terminates` (cursor becomes None or safety cap at 20 pages), `test_list_all_no_duplicates` (SDK abstraction produces unique tickers). All tests skip gracefully on insufficient demo data.

### ~~Unauthenticated client path for public endpoints~~
**Completed:** v0.4.0 (2026-04-14, PR #25). `KalshiClient(demo=True)` works without RSA credentials. Optional auth in transport, `AuthRequiredError` guards on all private resources (orders, portfolio, historical fills/orders, WS), `try_from_env()`, `is_authenticated` property on clients. 30+ new tests.
