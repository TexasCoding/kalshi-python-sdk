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

## P3: Integration test — series and multivariate event endpoints
**What:** Add SDK resource methods and integration tests for `/series`, `/series/{series_ticker}`, `/events/multivariate`, and `/series/{series_ticker}/events/{ticker}/candlesticks`. These endpoints exist in the OpenAPI spec (77 total endpoints) but the SDK only covers 24.
**Why:** The SDK covers 24 of 77 API endpoints. Series data and multivariate events are commonly used by researchers and traders building screeners.
**Depends on:** New resource classes need to be added to the SDK first.
**Added:** 2026-04-14

## ~~P3: Integration test — order amendments and decrease~~
**Completed:** v0.5.0 (2026-04-15). Added `amend()`, `decrease()`, `queue_positions()`, and `queue_position()` to OrdersResource and AsyncOrdersResource. AmendOrderResponse and OrderQueuePosition models. 29 new tests (sync/async happy paths, error paths, serialization, auth guards). Contract map entries for spec drift coverage. Also added queue position endpoints (GET /portfolio/orders/queue_positions, GET /portfolio/orders/{order_id}/queue_position) as natural companion to amend.

## P3: Integration test — handle transient 500 errors from demo API
**What:** `TestOrdersSync::test_list_all` intermittently fails with `KalshiServerError: HTTP 500` when paginating orders on the demo server. Investigate whether this is a known demo server issue or a bug in cursor handling. Consider adding a retry wrapper or `pytest.mark.flaky` for demo-specific transient failures.
**Why:** Transient 500s on demo cause false test failures, making CI unreliable. The SDK's retry logic already handles 500s for GET requests, but `list_all()` re-raises after exhausting retries. Either the retry count is too low for demo, or the demo server has a known instability on the orders list endpoint with cursors.
**Depends on:** Integration test suite stable (done).
**Added:** 2026-04-14

## P3: Verify public resource endpoint auth requirements
**What:** Check the OpenAPI spec for which GET endpoints in public resources (MarketsResource, EventsResource, ExchangeResource, HistoricalResource) actually require auth headers. If any public resource method routes to an auth-requiring endpoint, add a per-method `_require_auth()` guard to that specific method.
**Why:** The unauthenticated client guards private resources (orders, portfolio) at the resource level, but some public resource endpoints might require auth (e.g., if Kalshi adds a `/markets/{ticker}/my-position` endpoint). Without guards on those specific methods, users get a confusing 401 from Kalshi instead of a clear `AuthRequiredError`.
**Depends on:** Unauthenticated client path shipped.
**Added:** 2026-04-14 via /plan-eng-review (Codex outside voice identified the gap)

## Completed

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
