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

## P2: Async test coverage
**What:** Add tests for AsyncTransport, AsyncKalshiClient, AsyncMarketsResource, AsyncOrdersResource. Mirror all sync tests with async equivalents.
**Why:** Testing specialist flagged 4 critical gaps: zero async test coverage. The async code is structurally identical to sync but untested.
**Depends on:** v0.1 shipped.
**Added:** 2026-04-12 via /review

## P2: KalshiClient constructor + from_env() tests
**What:** Add tests for client constructor branches (auth object, key_id+path, key_id+pem, ValueError), from_env(), demo flag, context manager.
**Why:** Testing specialist flagged these as untested public API surface.
**Depends on:** v0.1 shipped.
**Added:** 2026-04-12 via /review

## Completed

### ~~Add py.typed marker for PEP 561 compliance~~
**Completed:** v0.1.0 (2026-04-12). File at `kalshi/py.typed`.
