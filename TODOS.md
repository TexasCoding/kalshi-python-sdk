# TODOS


## P2: Unauthenticated client path for public endpoints
**What:** Allow SDK usage without RSA auth credentials for public endpoints (exchange status, events list, historical data, market data). Either `KalshiClient()` with no auth, or a separate `KalshiPublicClient`.
**Why:** Researchers and data consumers who never trade shouldn't need RSA keys to read market data. Currently KalshiClient.__init__ raises ValueError without credentials.
**Depends on:** v0.2 shipped.
**Added:** 2026-04-12 via /plan-eng-review (Codex outside voice identified the gap)

## P2: Extend spec drift pipeline to cover WebSocket models
**What:** Add AsyncAPI spec validation for WS message models in the contract test suite (`tests/test_contracts.py`). Currently only REST models are verified against the OpenAPI spec.
**Why:** Without it, Kalshi can change their WS message format and the SDK won't detect it until runtime. The WS models in `kalshi/ws/models/` ship outside the verification system.
**Pros:** Catches WS schema drift automatically. Same pattern as existing REST contract tests.
**Cons:** Requires AsyncAPI YAML parsing (different format than OpenAPI).
**Depends on:** v0.3 shipped (WS models must exist first). Issue #9 spec drift pipeline.
**Added:** 2026-04-13 via /plan-eng-review (Codex outside voice identified the gap)


## P2: Integration test — WebSocket live connection
**What:** Add integration tests that connect to `wss://demo-api.kalshi.co/trade-api/ws/v2`, subscribe to a channel (e.g., ticker for an active market), receive at least one message, and verify the message parses into the expected WS model. Test connect, subscribe, receive, unsubscribe, disconnect lifecycle.
**Why:** The WS client has 196 mock-based tests but zero tests against the real WebSocket server. Auth signing for WS, message framing, subscription handshake, and real-time data parsing are all unverified. The prior learnings (`ws-sid-server-generated`, `ws-snapshot-via-websocket`) suggest real-server behavior may differ from mocks.
**Depends on:** REST integration tests stable (done). WS client shipped (v0.3.0, done).
**Added:** 2026-04-14

## P2: Integration test — order lifecycle with fills verification
**What:** Place an order that actually fills (use a marketable price or match against an existing resting order), then verify fills() returns the fill with correct price, count, and timestamps. Currently order tests only place non-marketable orders that rest and get cancelled.
**Why:** The create → fill → verify-fill flow is the most important user path for traders. Current tests verify create/cancel but never verify the fill data path because orders are deliberately priced to not fill.
**Depends on:** Demo account with sufficient balance. May require placing opposing orders to guarantee a fill.
**Added:** 2026-04-14

## P2: Integration test — pagination correctness
**What:** Verify cursor-based pagination actually returns different results across pages. Current list_all tests iterate 2-3 items then break. Add a test that fetches page 1 with limit=2, uses the cursor to fetch page 2, and asserts the items are different (no overlap, no duplication).
**Why:** The _list_all implementation in _base.py passes cursors between requests but this has never been verified against the real API. A bug in cursor handling would silently return duplicate data or skip items.
**Depends on:** An endpoint with enough data for 2+ pages (markets or events should have enough).
**Added:** 2026-04-14

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

## P3: Integration test — order amendments and decrease
**What:** Add SDK resource methods and integration tests for `POST /portfolio/orders/{order_id}/amend` and `POST /portfolio/orders/{order_id}/decrease`. These order modification endpoints exist in the spec but aren't in the SDK.
**Why:** Amending orders (changing price) and decreasing quantity are core trading operations. Traders who can't amend must cancel and recreate, which loses queue priority.
**Depends on:** New resource methods need to be added to OrdersResource.
**Added:** 2026-04-14

## Completed

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
