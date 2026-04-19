# TODOS

## North Star

**100% Kalshi endpoint coverage** — every REST operation in `specs/openapi.yaml` and every WebSocket channel in `specs/asyncapi.yaml` must have:
1. An SDK implementation (sync + async)
2. A unit test (happy path + error path + edge cases)
3. A real integration test against the Kalshi demo server

No new features, no publishing, no polish sweeps until this is closed. Side quests live in `BACKLOG.md`.

### Current state (audit 2026-04-19, updated post-v0.13.0)

| Status | REST endpoints | % |
|---|---:|---:|
| FULL (SDK + unit + integration) | 67 | 75% |
| SDK + unit, no integration | 20 | 22% |
| Not implemented | 0 | 0% |
| Auth-gated (`integration_real_api_only`) | 2 | 2% |
| **Total** | **89** | |

**REST coverage is complete as of v0.13.0.** Every endpoint in `specs/openapi.yaml` has an SDK implementation + unit tests + integration test (with `integration_real_api_only` marker on the two endpoints demo can't authenticate for). Remaining work is entirely WebSocket.

WebSocket: 12 message types dispatched with spec-aligned envelope types, 14 integration tests.

Meta-coverage test green as of v0.9.0.

**Path B demo-feasibility audit — completed 2026-04-18.** Ran `scripts/audit_demo_feasibility.py` against demo, probing all 47 uncovered endpoints with minimal payloads (empty body on POST/PUT, placeholder IDs on path params). Results:

| Classification | Count | Notes |
|---|---:|---|
| `demo-supported` | 44 | Route exists — 2xx on happy probes, 4xx validation on minimal-body probes, 404 on placeholder-ID probes. Safe to write full integration tests. |
| `auth-gated` | 2 | `GET /communications/quotes` (403), `GET /portfolio/summary/total_resting_order_value` (403). Demo account lacks permission. Mark `@pytest.mark.integration_real_api_only`. |
| `demo-broken` | 1 | `GET /portfolio/subaccounts/netting` returns 500 `{service:"users", code:"internal_server_error"}` on demo regardless of input. Mark `@pytest.mark.integration_real_api_only` (or xfail) with a link to this audit line. |
| `demo-501` | 0 | No endpoint responded 501. Every uncovered endpoint is wired up on demo. |

**Side findings still relevant for v0.11+ phases:**
- `POST /portfolio/subaccounts` returned **201 on empty body** during the audit — demo creates a subaccount from thin air. Audit probe created subaccount #1 with $0 on demo (confirmed via `GET /portfolio/subaccounts/balances`). Integration tests will need a cleanup fixture or a server-side delete endpoint; spec shows no DELETE so the demo subaccount is probably permanent until admin reset.
- API Keys v0.12 count is 4 endpoints (not 5 as originally drafted): spec has `GET/POST /api_keys`, `POST /api_keys/generate`, `DELETE /api_keys/{api_key}` — no "get single".

Re-run with `uv run python scripts/audit_demo_feasibility.py` before any phase if the spec bumps.

---

## Active phases

### v0.15.0 — WebSocket payload type drift sweep
**What:**
- Systematic audit of WS payload models against live demo wire format. Pre-existing class-of-bug surfaced during v0.14.0 Task 11 integration-test validation: SDK models type `_dollars`-aliased fields as `int` but demo sends dollar-decimal strings; SDK types `ts: int | None` across payloads but demo sends ISO datetime strings.
- Confirmed breakage: `OrderbookDeltaPayload.price` (int vs wire `"0.0200"`), `OrderbookDeltaPayload.ts` (int vs wire `"2026-04-19T18:43:37.662364Z"`), `UserOrdersPayload.yes_price` (int vs wire `"0.0100"` from Task 2 capture).
- Suspected across every `_dollars` field and every `ts: int` field in the 12 dispatched WS payload models (ticker, trade, fill, market_positions, multivariate, etc).
- Live-probe each channel, compare to model, fix all drifts to match the CLAUDE.md price convention (`DollarDecimal` for `_dollars` fields, `str | None` for ISO datetime `ts`).
- Expand `tests/test_contracts.py` WS drift coverage with a `test_ws_payload_field_type_drift` that cross-checks SDK model field types against the AsyncAPI spec schemas — would have caught this class of bug before v0.14.0 integration tests did.
**Why:** v0.14.0 closed envelope-type drift (dispatcher routing) but surfaced a deeper payload-type drift (model parsing). In the current SDK, every orderbook_delta frame and every user_order frame silently drops at `model_validate` even after v0.14.0's envelope fix — integration tests waiting for these frames time out and skip, masking the real breakage. `test_ws_connect_and_auth` still passes because it never subscribes.
**Estimate:** ~8h (systematic per-channel live probe + model type corrections + drift-test expansion).
**Added:** 2026-04-19 (discovered during v0.14.0 Task 11 verification).

---

## Reliability (gates CI trust for integration tests)

### P3: Integration test — handle transient 500 errors from demo API
**What:** `TestOrdersSync::test_list_all` intermittently fails with `KalshiServerError: HTTP 500` when paginating orders on the demo server. Investigate whether this is a known demo server issue or a bug in cursor handling. Consider adding a retry wrapper or `pytest.mark.flaky` for demo-specific transient failures.
**Why:** Transient 500s cause false test failures, making CI unreliable. The SDK's retry logic already handles 500s for GET requests, but `list_all()` re-raises after exhausting retries. Either retry count is too low for demo, or the demo server has a known instability on the orders list endpoint with cursors.
**Depends on:** Integration test suite stable (done).
**Added:** 2026-04-14

### P4: v0.11.0 follow-ups from claude[bot] PR #34 review
**What:**
- Verify `json={}` on `communications.confirm_quote` (and `subaccounts.create`, order_groups reset/trigger) is still required under production creds, not just demo. Drop the workaround per-endpoint as production confirms each route accepts empty-body POST/PUT without it.
- Consider an eager `ValueError` in `communications.list_quotes` / `list_all_quotes` when both `quote_creator_user_id` and `rfq_creator_user_id` are `None` (spec + demo require at least one). Currently the caller gets a `KalshiValidationError` round-trip. DX nit, not a correctness bug.

**Why:** Surfaced by PR #34 review. Both are minor and non-blocking — tracked so future cleanup passes don't silently drop them.
**Added:** 2026-04-18 (PR #34 review round 2).

### P3: Register Order Groups response models in `_contract_map.py`
**What:** Add `OrderGroup`, `GetOrderGroupResponse`, and `CreateOrderGroupResponse` to `kalshi/_contract_map.py` so response-side spec drift is caught by contract tests. Currently drift on new fields (e.g., if Kalshi adds `is_suspended: bool` to `OrderGroup`) would silently go unnoticed.
**Why:** Every other resource (Order, Market, Fill, Settlement, Series, etc.) registers its response models here. Order Groups was shipped in v0.10.0 without this registration to keep the PR focused.
**Added:** 2026-04-18 (flagged by claude[bot] code review on PR #33).

### P3: Coerce null envelope-level list fields in base `_list` / `_list_all`
**What:** `kalshi/resources/_base.py:_list` does `raw_items = data.get(items_key, [])` then iterates. If the server returns `{"items_key": null}` explicitly, `.get()` returns `None` (not `[]`), and the next line crashes with `TypeError: 'NoneType' object is not iterable`. Fix: `raw_items = data.get(items_key) or []`. Applies to both sync and async `_list`. Affects every paginated resource.
**Why:** Flagged during v0.13.0 adversarial review. Response models already use `NullableList[T]` to handle this at the envelope level (see Series.tags v0.9.0 fix, GetMilestonesResponse, GetApiKeysResponse). The base `_list` helper sidesteps those envelope models and reads the raw dict, so the NullableList protection doesn't apply there. Every resource using `_list` (structured_targets, FCM, portfolio.settlements, orders.list, markets.list, etc.) inherits the fragility. Low observed risk (Kalshi rarely sends explicit null for list fields) but newly exposed as v0.13.0 adds endpoints.
**Added:** 2026-04-19 (flagged by v0.13.0 adversarial review).

### P4: Cursor-loop detection in paginators
**What:** `_list_all` (sync + async) in `kalshi/resources/_base.py` caps iteration at `max_pages=1000` but has no detection for a cursor loop — if a buggy server returns the same cursor repeatedly, the SDK issues 1000 duplicate requests before bailing. Add: track seen cursors in a set; raise a `KalshiError` when a cursor repeats.
**Why:** Flagged during v0.13.0 adversarial review. No evidence Kalshi actually does this, but the safety-cap pattern silently papers over a buggy-server class of issue. Would be nice to surface rather than hide.
**Added:** 2026-04-19 (flagged by v0.13.0 adversarial review).

### P3: Tighten `_join_tickers` input validation
**What:** `kalshi/resources/_base.py:_join_tickers` currently passes `["A", "", "B"]` through as `"A,,B"` (empty element poisons the server-side filter) and `["FOO", "BAR,EVIL"]` through as `"FOO,BAR,EVIL"` (embedded comma silently expands the list). Add: raise `ValueError` if any element is empty or contains a comma.
**Why:** Predates v0.12.0 (used by `markets.list`, `events.list`, multiple other resources). Flagged during v0.12.0 adversarial review. Low user-facing risk today (most callers pass validated tickers) but silent data-corruption class: a wrong ticker CSV means the server returns data for a different market than requested and the caller has no signal anything went wrong.
**Added:** 2026-04-19 (flagged by v0.12.0 adversarial review).

---

## Completed

### ~~v0.14.0 — WebSocket parity (envelope drift only)~~
**Completed:** 2026-04-19. Resolved all three envelope-type drifts in the WS dispatcher (user_orders→user_order, market_positions→market_position, multivariate→multivariate_lookup) against live-captured evidence. Added `scripts/ws_capture.py` (raw-frame dumper) and `scripts/ws_provoke_user_order.py` (order-lifecycle probe) for evidence gathering. **Empirical finding**: demo emits singular `"type":"user_order"` on the user_orders channel; pre-v0.14.0 SDKs silently dropped every user-order frame as "Unknown message type" — real user-facing bug. market_position and multivariate_lookup drifts had `NONE_OBSERVED` on demo (idle account / no active collections) and were aligned to spec by analogy with the directly-confirmed pattern. Expanded `tests/integration/test_websocket.py` from 3 connectivity smoke tests to 14 per-message-type integration tests. Promoted `test_ws_envelope_type_drift` from a warning-only check to a hard assertion with an empty `_DEMO_DIVERGENCE_ALLOWLIST` escape hatch for future intentional divergences. **Known limitation (tracked as v0.15.0):** the envelope rename routes frames to the correct Message class, but a separate payload-type drift remains — `OrderbookDeltaPayload.price` / `UserOrdersPayload.yes_price` are typed `int` (demo sends dollar strings), `ts` fields are typed `int | None` (demo sends ISO datetime strings). Pydantic rejects these frames at `model_validate`, so the dispatcher still drops them — net user-visible behavior for orderbook_delta and user_orders is unchanged until v0.15.0 fixes the payload types. 13/14 integration tests skip because of this (only `test_ws_connect_and_auth` passes, since it never subscribes). Evidence: `docs/superpowers/plans/2026-04-19-ws-parity-v0.14.0-capture-notes.md` (gitignored working doc — plan also gitignored).

### ~~v0.13.0 — Remaining endpoints (REST coverage closed)~~
**Completed:** 2026-04-19. 10 new endpoints across 5 new resources + 2 extensions: `AccountResource.limits`, `StructuredTargetsResource.{list,list_all,get}`, `FcmResource.{orders,orders_all,positions}`, `SearchResource.{tags_by_categories,filters_by_sport}`, `IncentiveProgramsResource.{list,list_all}`, `exchange.user_data_timestamp`, `portfolio.total_resting_order_value`. 7 new Pydantic models + nested helpers (AccountApiLimits, StructuredTarget + envelopes, IncentiveProgram + envelope, SportFilterDetails/ScopeList + envelopes, UserDataTimestamp, TotalRestingOrderValue). 57 new unit tests + 25 integration tests (2 gated behind `integration_real_api_only` on `portfolio.total_resting_order_value` — FCM-member only, demo 403s; FCM resource tests use a try/except skip since demo tolerates the endpoints structurally). METHOD_ENDPOINT_MAP +13, contract map +7, EXCLUSIONS +16 (type/target_type/incentive_type shadow-avoidance + paginator cursors), coverage harness resource count 14 → 19. **Unique wire shape:** `GET /incentive_programs` paginates on `next_cursor` (not `cursor`) — rather than hand-rolling, the base `_list` / `_list_all` helpers now accept a `cursor_key: str = "cursor"` kwarg so any future non-standard cursor key is a one-line fix. FULL-covered endpoints 57 → 67 (75%); remaining 22 are SDK+unit with `integration_real_api_only` marker on 2 auth-gated routes. **REST coverage is now complete.** Post-review polish in this phase also: added `_require_auth()` to `exchange.user_data_timestamp` (spec has no security block but it reports lag on user-scoped data), renamed `StructuredTarget.type` → `target_type` with `validation_alias=AliasChoices("type", "target_type")` (shadow-avoidance convention), fixed `IncentiveProgram.target_size_fp` type (`DollarDecimal` → `FixedPointCount`), narrowed FCM integration test's tolerated-errors catch from base `KalshiError` to `(KalshiAuthError, KalshiNotFoundError)` so real bugs surface instead of being swallowed as "not FCM", and added 7 missing top-level `kalshi.*` re-exports for response envelopes. Remaining work (v0.14.0) is entirely WebSocket: resolve 3 singular/plural dispatch drifts via live capture + expand integration coverage beyond the 3-test connectivity smoke.

### ~~v0.12.0 — API Keys + Bulk/Batch + Milestones~~
**Completed:** 2026-04-19. Three new resources — `ApiKeysResource` (4 endpoints: list, create, generate, delete; full RSA keypair lifecycle verified against demo with throwaway keys and try/finally cleanup), `MilestonesResource` (list + get + list_all paginator; `limit` is required 1-500 per spec; RFC3339 coercion helper accepts `datetime | str`), `LiveDataResource` (4 endpoints: get, get_typed [legacy], batch up to 100 ids, game_stats). Plus 4 new methods on `MarketsResource`: `list_trades`/`list_trades_all` (reuses `historical.Trade`), `bulk_candlesticks` (comma-joined tickers), `bulk_orderbooks` (auth-required, explode:true tickers). 11 new Pydantic models (`ApiKey`, request/response envelopes for all 3 resources, `MarketCandlesticks` bundle, `PlayByPlay`/`PlayByPlayPeriod` for game stats). 82 new unit tests + 41 new integration tests (including real-lifecycle API key create/list/delete on demo). METHOD_ENDPOINT_MAP +13, BODY_MODEL_MAP +2 (`CreateApiKeyRequest`, `GenerateApiKeyRequest`), `_contract_map.py` +8 response/request models, EXCLUSIONS +2 paginator cursors, RESOURCE_MODULES +3, meta-coverage test now expects 14 resource classes (was 11). FULL-covered endpoints 44 → 57 (64%). **Live-demo finding:** `GET /milestones?category=Sports` returns `category: "sports"` lowercase in response body even though filter accepted title-case — server-side normalization inconsistency; test asserts case-insensitively.

### ~~v0.11.0 — Communications / RFQ + Subaccounts~~
**Completed:** 2026-04-18. Two new resource subsystems — `CommunicationsResource` + `AsyncCommunicationsResource` (11 endpoints: get_id, list_rfqs/create_rfq/get_rfq/delete_rfq, list_quotes/create_quote/get_quote/delete_quote, accept_quote/confirm_quote, plus list_all_rfqs + list_all_quotes paginator helpers) and `SubaccountsResource` + `AsyncSubaccountsResource` (6 endpoints: create, transfer, list_balances, list_transfers + list_all_transfers, update_netting, get_netting). 21 new Pydantic models (`RFQ`, `Quote`, `MveSelectedLeg` + envelopes/requests on Communications; `SubaccountBalance`, `SubaccountTransfer`, `SubaccountNettingConfig` + envelopes/requests on Subaccounts). Wired into `KalshiClient.communications` / `.subaccounts`. Registered 20 METHOD_ENDPOINT_MAP entries, 5 BODY_MODEL_MAP entries, 10 `_contract_map.py` response-side entries, 4 EXCLUSIONS. 103 new unit tests + 30 integration tests (26 passing, 4 correctly skipped; the demo-broken `get_netting` + the quote-party-two workflow gated behind the new `integration_real_api_only` marker). **Live-demo findings surfaced during integration runs:** (1) `GET /communications/quotes` requires `creator_user_id` OR `rfq_creator_user_id` filter even when `rfq_id` is provided (demo returns 400, not 403 — audit row corrected); (2) demo rejects malformed IDs with 400 `invalid_parameters` before 404 route lookup (regression tests assert `KalshiError` base class); (3) demo refuses self-quoting — `test_quote_lifecycle` skips cleanly so future server changes surface organically; (4) `POST /portfolio/subaccounts` needs `json={}` to force Content-Type (same fix as order_groups v0.10 reset/trigger). **Bonus: closed the P3 `_put()` 204 handling item** — was on the critical path for `accept_quote` / `confirm_quote` which return 204 per spec. `_put` now returns `None` on 204 like `_delete`. FULL-covered endpoints 31 → 44 (49%); meta-coverage test now expects 11 resource classes (was 9).

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
