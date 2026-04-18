# TODOS

## North Star

**100% Kalshi endpoint coverage** — every REST operation in `specs/openapi.yaml` and every WebSocket channel in `specs/asyncapi.yaml` must have:
1. An SDK implementation (sync + async)
2. A unit test (happy path + error path + edge cases)
3. A real integration test against the Kalshi demo server

No new features, no publishing, no polish sweeps until this is closed. Side quests live in `BACKLOG.md`.

### Current state (audit 2026-04-18, updated post-v0.9.0)

| Status | REST endpoints | % |
|---|---:|---:|
| FULL (SDK + unit + integration) | 31 | 35% |
| SDK + unit, no integration | 12 | 13% |
| Not implemented | 46 | 52% |
| **Total** | **89** | |

WebSocket: 15/32 message types dispatched, 3 integration tests (connectivity only).

Meta-coverage test green as of v0.9.0.

**Path B demo-feasibility audit — completed 2026-04-18.** Ran `scripts/audit_demo_feasibility.py` against demo, probing all 47 uncovered endpoints with minimal payloads (empty body on POST/PUT, placeholder IDs on path params). Results:

| Classification | Count | Notes |
|---|---:|---|
| `demo-supported` | 44 | Route exists — 2xx on happy probes, 4xx validation on minimal-body probes, 404 on placeholder-ID probes. Safe to write full integration tests. |
| `auth-gated` | 2 | `GET /communications/quotes` (403), `GET /portfolio/summary/total_resting_order_value` (403). Demo account lacks permission. Mark `@pytest.mark.integration_real_api_only`. |
| `demo-broken` | 1 | `GET /portfolio/subaccounts/netting` returns 500 `{service:"users", code:"internal_server_error"}` on demo regardless of input. Mark `@pytest.mark.integration_real_api_only` (or xfail) with a link to this audit line. |
| `demo-501` | 0 | No endpoint responded 501. Every uncovered endpoint is wired up on demo. |

**Side findings worth capturing before v0.11.0:**
- Endpoint count drifted: audit found 47 uncovered (not 53 as pre-v0.9.0 snapshot indicated) — multivariate/forecast/series endpoints covered since last count.
- `POST /portfolio/subaccounts` returned **201 on empty body** — demo appears to create a subaccount from thin air. Worth probing behavior more carefully when implementing v0.11.0 (do we need a cleanup fixture? does it tie to the parent account?).
- TODOS previously listed `POST /portfolio/order_groups` but spec is `POST /portfolio/order_groups/create`. Reset/trigger/limit are `PUT`, not `POST` as drafted. v0.10.0 plan below corrected.
- TODOS previously listed "API Keys (5)" but spec has 4 endpoints (`GET/POST /api_keys`, `POST /api_keys/generate`, `DELETE /api_keys/{api_key}`). v0.12.0 count corrected.

Re-run with `uv run python scripts/audit_demo_feasibility.py` before any phase if the spec bumps.

---

## Active phases

### v0.11.0 — Communications / RFQ + Subaccounts
**What:** Two new resource subsystems. Pydantic models, sync+async resources, unit + integration tests, contract map registration for all 17 endpoints.

**Communications / RFQ (11 endpoints):**
- `GET /communications/id` — demo-supported
- `GET /communications/rfqs` — demo-supported
- `POST /communications/rfqs` — demo-supported
- `GET /communications/rfqs/{rfq_id}` — demo-supported
- `DELETE /communications/rfqs/{rfq_id}` — demo-supported
- `GET /communications/quotes` — **auth-gated** (403 on demo) → `integration_real_api_only`
- `POST /communications/quotes` — demo-supported
- `GET /communications/quotes/{quote_id}` — demo-supported
- `DELETE /communications/quotes/{quote_id}` — demo-supported
- `PUT /communications/quotes/{quote_id}/accept` — demo-supported
- `PUT /communications/quotes/{quote_id}/confirm` — demo-supported

**Subaccounts (6 endpoints):**
- `POST /portfolio/subaccounts` — demo-supported (⚠ returns **201 on empty body**; probe already created subaccount #1 with $0 on demo — confirmed via `GET /portfolio/subaccounts/balances`. Integration tests will need a cleanup fixture or server-side delete endpoint; spec shows no DELETE so probably permanent until admin reset)
- `POST /portfolio/subaccounts/transfer` — demo-supported
- `GET /portfolio/subaccounts/balances` — demo-supported
- `GET /portfolio/subaccounts/transfers` — demo-supported
- `PUT /portfolio/subaccounts/netting` — demo-supported
- `GET /portfolio/subaccounts/netting` — **demo-broken** (demo returns 500 `users/internal_server_error` on any request) → `integration_real_api_only` or xfail

**Why:** OTC market access + multi-account workflows. Two of the largest "not implemented" buckets.
**Estimate:** ~11h.

### v0.12.0 — API Keys + Bulk/Batch + Milestones
**What:** Three smaller resource additions.
- **API Keys (4, not 5 — spec has no "get single"):** `GET /api_keys` (list), `POST /api_keys` (create), `POST /api_keys/generate`, `DELETE /api_keys/{api_key}`. All demo-supported.
- **Bulk / Batch (3):** `GET /markets/candlesticks`, `GET /markets/orderbooks`, `GET /markets/trades`. All demo-supported.
- **Milestones + live_data (6):** `GET /milestones`, `GET /milestones/{milestone_id}`, `GET /live_data/batch`, `GET /live_data/milestone/{milestone_id}`, `GET /live_data/milestone/{milestone_id}/game_stats`, `GET /live_data/{type}/milestone/{milestone_id}`. All demo-supported (path-params 404 on bad IDs as expected).

Each with models, sync+async resources, unit + integration tests, contract map entries.
**Estimate:** ~8h.

### v0.13.0 — Remaining endpoints + WebSocket parity
**What:**
- Implement remaining endpoints (10 confirmed, audit-classified):
  - `GET /exchange/user_data_timestamp` — demo-supported
  - `GET /account/limits` — demo-supported
  - `GET /search/tags_by_categories` — demo-supported
  - `GET /search/filters_by_sport` — demo-supported
  - `GET /incentive_programs` — demo-supported
  - `GET /structured_targets` — demo-supported
  - `GET /structured_targets/{structured_target_id}` — demo-supported (404 on bad ID)
  - `GET /fcm/orders` — demo-supported
  - `GET /fcm/positions` — demo-supported
  - `GET /portfolio/summary/total_resting_order_value` — **auth-gated** (403) → `integration_real_api_only`
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

### P3: Register Order Groups response models in `_contract_map.py`
**What:** Add `OrderGroup`, `GetOrderGroupResponse`, and `CreateOrderGroupResponse` to `kalshi/_contract_map.py` so response-side spec drift is caught by contract tests. Currently drift on new fields (e.g., if Kalshi adds `is_suspended: bool` to `OrderGroup`) would silently go unnoticed.
**Why:** Every other resource (Order, Market, Fill, Settlement, Series, etc.) registers its response models here. Order Groups was shipped in v0.10.0 without this registration to keep the PR focused.
**Added:** 2026-04-18 (flagged by claude[bot] code review on PR #33).

### P3: Harden `_put()` against 204 No Content responses
**What:** `kalshi/resources/_base.py::_put()` unconditionally calls `response.json()`. If a Kalshi endpoint ever returns 204 (empty body) on a PUT, `_put` will raise `JSONDecodeError`. Mirror the `_delete()` pattern (`if response.status_code == 204: return None`).
**Why:** `_delete()` already handles this. `_put()` is inconsistent and brittle. The risk is currently latent — spec defines 200 responses with empty-object bodies, but spec can change. `OrderGroupsResource.update_limit` is the first `_put()` caller where a spec change could surface this.
**Added:** 2026-04-18 (flagged by claude[bot] code review on PR #33).

---

## Completed

### ~~v0.10.0 — Order Groups resource~~
**Completed:** 2026-04-18. `OrderGroupsResource` + `AsyncOrderGroupsResource` covering 7 endpoints (GET/POST/DELETE/PUT across `/portfolio/order_groups/*`). 5 Pydantic models: `OrderGroup`, `GetOrderGroupResponse`, `CreateOrderGroupResponse`, `CreateOrderGroupRequest`, `UpdateOrderGroupLimitRequest` (all request models `extra="forbid"`, response models with `NullableList[str]` on `orders`). 41 unit tests (wire-shape, happy path, auth-guard, error-path, client-wiring) + 9 integration tests (5 sync + 4 async) against demo — all green. Registered in `METHOD_ENDPOINT_MAP` (7 entries), `BODY_MODEL_MAP` (2 entries), `EXCLUSIONS` (2 entries for `contracts_limit_fp` — SDK commits to integer form only, matching the `count_fp` precedent), and the integration coverage harness (9th resource class). Version bumped to 0.10.0. **Integration testing surfaced two real SDK bugs caught before ship:** (1) `reset`/`trigger` PUT endpoints were sending requests without `Content-Type: application/json` (httpx omits the header when no body is passed); demo server rejected with `invalid_content_type`. Fixed by passing `json={}` in both sync and async variants. (2) Async `create → get` had a race condition on demo (eventual consistency) — added a 0.5s sleep mirroring the `test_orders.py` pattern.

### ~~v0.9.0 — Close Series + Multivariate integration gap~~
**Completed:** 2026-04-18. Added `kalshi.resources.series` and `kalshi.resources.multivariate` to `RESOURCE_MODULES` (made 11 silently-absent methods visible to the meta-coverage test). Created `tests/integration/test_series.py` (5 methods × sync+async = 10 tests) and `tests/integration/test_multivariate.py` (6 methods × sync+async = 12 tests). Extended `tests/integration/test_events.py` with `list_multivariate` + `list_all_multivariate` coverage (4 new tests). Bumped discovery expectation from 6 → 8 resource classes. **Integration tests surfaced two real issues:** (1) `Series.tags` was typed `list[str]` but demo returns `null` for some series — fixed via `@field_validator(mode="before")` coercing None→[] on `tags`, `settlement_sources`, `additional_prohibitions`; (2) the semantic oracle in `tests/integration/assertions.py` rejected ALL floats as DollarDecimal failures, misfiring on `Series.fee_multiplier: float` — now uses an annotation-aware `_annotation_contains(Decimal)` check so it only flags floats where the field is actually typed Decimal. Coverage result: 40 passed, 5 skipped (destructive create_market + lookup_tickers skip when demo collection lacks associated events with markets; forecast skip when no history). FULL-covered endpoints 13 → 24; NO_INT 23 → 12; meta-coverage test green.

### ~~P3: Integration test — series and multivariate event endpoints~~
**Completed:** v0.6.0 (2026-04-16). Added SeriesResource (5 methods: list, get, fee_changes, event_candlesticks, forecast_percentile_history) and MultivariateCollectionsResource (5 methods: list, get, create_market, lookup_tickers, lookup_history). Added list_multivariate/list_all_multivariate to EventsResource. Fixed EventsResource.list() param drift (added with_milestones, min_close_ts, min_updated_ts). 11 new endpoints, 50+ new tests, 4 contract map entries. Auth guards on forecast_percentile_history, create_market, lookup_tickers.
**Note:** v0.6.0 shipped the SDK + unit tests but integration tests and `SCENARIO_REGISTRY` registration landed later in v0.9.0 (2026-04-18).

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
