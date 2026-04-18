# TODOS




## P3: Investigate WS dispatch type mismatch (spec vs SDK)
**What:** The SDK dispatches WS messages on `type = "user_orders"` (plural) and `type = "market_positions"` (plural), but the AsyncAPI spec defines `type const = "user_order"` (singular) and `type const = "market_position"` (singular). Investigate whether the real API sends plural or singular by capturing live WS frames and comparing to the spec's `type` const values.
**Why:** If the real API sends singular (matching spec), the SDK silently drops these messages as "unknown type." If the real API sends plural (matching SDK), the spec is wrong. Either way, the mismatch should be resolved.
**Pros:** Prevents silent message drops if Kalshi aligns their API to their spec.
**Cons:** May be a spec-only bug with no runtime impact. Requires live WS session to verify.
**Depends on:** WS integration tests (done). WS spec drift pipeline (in progress).
**Added:** 2026-04-15 via /plan-eng-review (Codex outside voice identified the gap)

## P3: Integration test — CI pipeline with scheduled runs
**What:** Add a GitHub Actions workflow that runs `pytest tests/integration/ -v` on a schedule (nightly or weekly). Store KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH as GitHub Actions secrets. Report failures via PR comment or Slack notification.
**Why:** Integration tests only catch drift if they run regularly. Currently they only run when a developer manually runs them locally with credentials configured.
**Depends on:** Integration test suite stable (done). GitHub Actions secrets configured.
**Added:** 2026-04-14

## P3: Integration test — from_env() and constructor variant coverage
**What:** Add integration tests that verify KalshiClient can be constructed via all supported paths: `from_env()`, `key_id + private_key_path`, `key_id + private_key` (PEM string), `auth=KalshiAuth(...)`, and `demo=True` flag. Currently only `from_env()` is tested by the integration suite.
**Why:** Users construct the client in different ways. A signing bug that only manifests with `from_key_path()` vs `from_pem()` would go undetected.
**Depends on:** Integration test suite shipped (done).
**Added:** 2026-04-14

## ~~P3: Integration test — series and multivariate event endpoints~~
**Completed:** v0.6.0 (2026-04-16). Added SeriesResource (5 methods: list, get, fee_changes, event_candlesticks, forecast_percentile_history) and MultivariateCollectionsResource (5 methods: list, get, create_market, lookup_tickers, lookup_history). Added list_multivariate/list_all_multivariate to EventsResource. Fixed EventsResource.list() param drift (added with_milestones, min_close_ts, min_updated_ts). 11 new endpoints, 50+ new tests, 4 contract map entries. Auth guards on forecast_percentile_history, create_market, lookup_tickers.

## ~~P3: Integration test — order amendments and decrease~~
**Completed:** v0.5.0 (2026-04-15). Added `amend()`, `decrease()`, `queue_positions()`, and `queue_position()` to OrdersResource and AsyncOrdersResource. AmendOrderResponse and OrderQueuePosition models. 29 new tests (sync/async happy paths, error paths, serialization, auth guards). Contract map entries for spec drift coverage. Also added queue position endpoints (GET /portfolio/orders/queue_positions, GET /portfolio/orders/{order_id}/queue_position) as natural companion to amend.

## P3: Integration test — handle transient 500 errors from demo API
**What:** `TestOrdersSync::test_list_all` intermittently fails with `KalshiServerError: HTTP 500` when paginating orders on the demo server. Investigate whether this is a known demo server issue or a bug in cursor handling. Consider adding a retry wrapper or `pytest.mark.flaky` for demo-specific transient failures.
**Why:** Transient 500s on demo cause false test failures, making CI unreliable. The SDK's retry logic already handles 500s for GET requests, but `list_all()` re-raises after exhausting retries. Either the retry count is too low for demo, or the demo server has a known instability on the orders list endpoint with cursors.
**Depends on:** Integration test suite stable (done).
**Added:** 2026-04-14

## ~~P3: Piece 2 — automated contract test for request-param drift~~
**Completed:** v0.8.0 (2026-04-18). `TestRequestParamDrift` (query+path, 94 parametrized cases across 47 endpoints × sync+async) and `TestRequestBodyDrift` (body, 7 parametrized cases) in `tests/test_contracts.py`. Hard-fail on any drift; `EXCLUSIONS` allowlist in `tests/_contract_support.py` with reason strings. `test_exclusion_map_is_current` lint guards against stale allowlist entries. 25 bootstrap exclusions covering deprecated fields, paginator-handled cursor, count_fp wire normalization, deferred _fp variants on DecreaseOrderRequest, deprecated ids on BatchCancelOrdersRequest, and body-vs-query-param distinctions.

## ~~P3: Audit inline body dicts~~
**Completed:** v0.8.0 (2026-04-18). All POST/PUT/DELETE bodies routed through Pydantic models. CreateOrderRequest extended with 7 fields (time_in_force, post_only, reduce_only, self_trade_prevention_type, order_group_id, cancel_order_on_pause, subaccount) + buy_max_cost wired through. AmendOrderRequest, DecreaseOrderRequest, BatchCreateOrdersRequest, BatchCancelOrdersRequest (+ BatchCancelOrdersRequestOrder), and two multivariate request models added. Phantom `type` field on orders.create removed; buy_max_cost type fixed to int cents (spec-compliant); count wire key normalized to count_fp; batch_cancel migrated from deprecated `ids` wire field to preferred `orders` field with per-order subaccount support.

## P3: Reduce sync/async duplication tax (v0.8+)
**What:** Every resource file has near-identical sync and async classes (~95% duplication of method bodies). Each new kwarg must be added in two places; mismatch is a real risk. Possible approaches: (a) shared params-builder helpers, (b) sync-wrapping-async architecture, (c) code-gen from a single source. Out of scope for v0.7.0 because the audit alone added ~32 kwargs × 2 = ~64 method signatures touched.
**Why:** Maintenance tax keeps growing as the SDK adds resources. v0.7.0 doubled the kwarg surface; future additions get more painful.
**Pros:** Single source of truth. Half the maintenance.
**Cons:** Potentially big architectural change. Risk of breaking the `async for` ergonomics that `list_all` enables.
**Depends on:** v0.7.0 shipped (done).
**Added:** 2026-04-16 via /plan-eng-review round 2 (flagged but not bundled).

## P3: Verify public resource endpoint auth requirements
**What:** Check the OpenAPI spec for which GET endpoints in public resources (MarketsResource, EventsResource, ExchangeResource, HistoricalResource) actually require auth headers. If any public resource method routes to an auth-requiring endpoint, add a per-method `_require_auth()` guard to that specific method.
**Why:** The unauthenticated client guards private resources (orders, portfolio) at the resource level, but some public resource endpoints might require auth (e.g., if Kalshi adds a `/markets/{ticker}/my-position` endpoint). Without guards on those specific methods, users get a confusing 401 from Kalshi instead of a clear `AuthRequiredError`.
**Depends on:** Unauthenticated client path shipped.
**Added:** 2026-04-14 via /plan-eng-review (Codex outside voice identified the gap)

## P3: Enum typing sweep — adopt Literal across enum kwargs (v0.9)
**What:** Replace `str | None` with `Literal[...]` for fixed-enum kwargs: `time_in_force`, `self_trade_prevention_type`, `side`, `action`, `status` filters on list methods. Single-sweep release.
**Why:** v0.7.0 and v0.8.0 both deferred `Literal` adoption to avoid scoping-in a typing sweep during feature work. A dedicated sweep lets mypy catch invalid enum values at user-code authoring time.
**Depends on:** v0.8.0 shipped (done).
**Added:** 2026-04-18 via /plan-eng-review (scope decision deferred from v0.8.0).

## P3: Model-first request API overload (v0.9)
**What:** Add optional model-first signatures alongside existing kwarg-based signatures: `orders.amend(request: AmendOrderRequest)`, etc. Runtime dispatch on argument type. Existing kwarg-based callers unaffected.
**Why:** Advanced users (programmatic order construction, serialization layers) benefit from passing a fully-formed request model. Current API forces them to unpack into kwargs and re-pack.
**Depends on:** v0.8.0 shipped (done). Request models all exist.
**Added:** 2026-04-18 via /plan-eng-review.

## P3: Nested request-body schema $ref recursion (only if needed)
**What:** Extend `_resolve_request_body_schema` in `tests/_contract_support.py` to recurse into nested `$ref` pointers inside body schemas. Today all 7 POST/PUT/DELETE body schemas have flat properties — verified at v0.8.0. Only implement when a nested ref lands in the spec.
**Why:** Drift detection breaks silently if nested property refs are introduced without resolver support.
**Depends on:** v0.8.0 shipped (done). Activation trigger: first spec update that introduces a nested `$ref` in a POST/PUT/DELETE body schema.
**Added:** 2026-04-18 via /plan-eng-review.

## P3: Typed `Exclusion.kind` enum instead of free-text reason matching (v0.9)
**What:** Replace string-heuristic classification in `test_exclusion_map_is_current` (substring match on `"body param"`, `"not query/path"`, etc.) with a typed `kind: Literal["body_param", "spec_deprecated", "paginator_handled", "wire_normalization"]` field on `Exclusion`. Update all 25 existing entries to set `kind` explicitly.
**Why:** Current staleness checker in `tests/test_contracts.py` branches on free-text `reason` substrings. A future exclusion with slightly different wording (e.g. `"request body field"` instead of `"body param"`) would silently misclassify. A typed enum makes intent explicit and prevents classification drift.
**Pros:** Unambiguous; IDE autocomplete; mypy catches typos.
**Cons:** Requires updating 25 existing entries. Low risk but touches most of `_contract_support.py`.
**Depends on:** v0.8.0 shipped (done).
**Added:** 2026-04-18 via PR #31 claude[bot] review (finding n2).

## P3: Async/sync `_delete_with_body` parity (v0.9)
**What:** Sync `OrdersResource.batch_cancel` goes through `self._delete_with_body(...)`; async `AsyncOrdersResource.batch_cancel` calls `self._transport.request("DELETE", ...)` directly. If `_delete_with_body` ever gains error-mapping or retry behavior, the async path silently diverges. Add an `async_delete_with_body` helper (or equivalent on the async transport) and route async batch_cancel through it.
**Why:** The project's stated sync/async parity via dual transport abstraction has a one-method gap. Fine today (`_delete_with_body` is a thin shim), but tempting to drop extra logic into the sync helper without remembering the async path bypasses it.
**Depends on:** v0.8.0 shipped (done).
**Added:** 2026-04-18 via PR #31 claude[bot] review (finding m4).

## P3: TestRequestBodyDrift should cover nested Pydantic models (v0.9)
**What:** `_model_aliases()` in `tests/test_contracts.py` iterates one level deep only. Nested models like `TickerPair` (inside `CreateMarketInMultivariateEventCollectionRequest.selected_markets`) have no `BODY_MODEL_MAP` entry and are not checked for drift. `TickerPair` has `extra="allow"` so phantom fields flow to the wire silently.
**Why:** False confidence in drift coverage. Not a production bug today (TickerPair fields are correct) but a future schema change to the nested type would silently bypass the drift test.
**Pros:** Closes a genuine gap in the scanner; surfaces any drift on nested models.
**Cons:** Requires deciding whether TickerPair should gain `extra="forbid"` (could be breaking for callers who pass extra keys). Design decision + test expansion.
**Depends on:** v0.8.0 shipped (done).
**Added:** 2026-04-18 via /review adversarial pass (Finding INFORMATIONAL-3).

## Completed

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
