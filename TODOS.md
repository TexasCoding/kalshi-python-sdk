# TODOS

## P1: Verify Kalshi price format (cents vs dollars)
**What:** Test actual API responses from the demo environment to verify price field formats. The OpenAPI spec field names use `_dollars` suffix (e.g., `yes_price_dollars`, `price_dollars`), which may mean the API returns dollar amounts, not integer cents.
**Why:** If the API returns dollar values (not cents), the DollarDecimal type conversion logic needs adjustment. This is a foundational assumption.
**Depends on:** Demo API access.
**Added:** 2026-04-12 via /plan-eng-review

## P1: Auth path percent-encoding canonicalization
**What:** Normalize percent-encoding in auth signing paths. Currently trailing slashes and query params are stripped, but percent-encoded characters (e.g., `%2F`) are not normalized.
**Why:** A percent-encoded path segment would produce a different signature than the decoded version. Could cause silent 401 errors on edge-case tickers.
**Depends on:** v0.1 shipped + demo API verification.
**Added:** 2026-04-12 via /plan-eng-review (partially addressed: trailing slash + query strip done)

## P1: Verify candlestick endpoint paths and response format
**What:** Test candlestick endpoints against the demo API. The OpenAPI spec shows a nested MarketCandlestick schema (yes_bid, yes_ask, price as nested BidAskDistribution objects) but the current SDK Candlestick model is flat OHLC. Also verify which candlestick endpoint paths are correct (series path vs direct market path).
**Why:** The current Candlestick model does not match the real API response format. Both live and historical candlestick methods are likely broken. This should be verified against the demo API alongside the P1 price format verification.
**Depends on:** Demo API access.
**Added:** 2026-04-12 via /plan-eng-review (Codex outside voice found the schema mismatch)

## P2: Unauthenticated client path for public endpoints
**What:** Allow SDK usage without RSA auth credentials for public endpoints (exchange status, events list, historical data, market data). Either `KalshiClient()` with no auth, or a separate `KalshiPublicClient`.
**Why:** Researchers and data consumers who never trade shouldn't need RSA keys to read market data. Currently KalshiClient.__init__ raises ValueError without credentials.
**Depends on:** v0.2 shipped.
**Added:** 2026-04-12 via /plan-eng-review (Codex outside voice identified the gap)

## P1: Endpoint-level contract tests for resource methods
**What:** Add contract tests that verify resource methods (request building, response reshaping) match the OpenAPI operation definitions. Currently the spec drift pipeline only checks model schemas, not the resource layer that reshapes data.
**Why:** The SDK's real breakage surface is in resource methods: `orderbook()` rewrites `orderbook_fp` data (resources/markets.py:59), `create()` hand-builds request JSON bypassing `CreateOrderRequest` (resources/orders.py:18), `get()` on events changes shape based on `with_nested_markets` (resources/events.py:49). Model-schema comparison can stay green while the SDK is broken.
**Pros:** Catches the most dangerous class of bugs (SDK works but returns wrong data).
**Cons:** Doubles the contract test complexity. Requires parsing spec operations, not just schemas.
**Depends on:** Issue #9 (spec drift pipeline) shipped first.
**Added:** 2026-04-13 via /plan-eng-review (Codex outside voice identified the gap)

## Completed

### ~~Async test coverage~~
**Completed:** v0.1.2 (2026-04-12). PR #20. Files: test_async_client.py, test_async_markets.py, test_async_orders.py.

### ~~KalshiClient constructor + from_env() tests~~
**Completed:** v0.1.2 (2026-04-12). File: test_client.py (315 lines).

### ~~Add py.typed marker for PEP 561 compliance~~
**Completed:** v0.1.0 (2026-04-12). File at `kalshi/py.typed`.
