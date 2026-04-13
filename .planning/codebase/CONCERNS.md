# Codebase Concerns

**Analysis Date:** 2026-04-13

## Tech Debt

### Spec-SDK Field Optionality Mismatch (API Contract Risk)

**Issue:** Multiple hand-written models intentionally define fields as optional (nullable, `= None`) even though the OpenAPI spec marks them as required. This is a conscious design choice for SDK robustness but creates a contract drift between what Kalshi returns and what the SDK accepts.

**Files:**
- `kalshi/models/portfolio.py` (Balance, MarketPosition, EventPosition, Settlement)
- `kalshi/models/historical.py` (Trade)
- `kalshi/models/events.py` (Event, EventMetadata)

**Examples:**
- Settlement: spec requires `fee_cost`, `market_result`, `yes_count_fp`, `no_count_fp` — SDK fields are all optional
- Trade: spec requires `ticker`, `taker_side`, `yes_price_dollars`, `no_price_dollars` — SDK fields are all optional
- MarketPosition: spec requires `total_traded_dollars`, `position_fp`, `market_exposure_dollars` — SDK fields are all optional

**Impact:**
- Prevents runtime validation from catching missing fields
- Code expecting these fields must check for None
- Risk of silent bugs if API returns incomplete responses

**Fix approach:**
1. Audit spec vs SDK for each model; identify truly optional fields
2. Make required fields non-optional in models; add default factories for safe nulls if needed
3. Document intentional differences with `notes` in `_contract_map.py`
4. Add validation tests that parse incomplete API responses

---

### Unmapped Sub-Models in Contract Tests (Model Coverage Gap)

**Issue:** 8 SDK models exist without entries in the contract map. These are nested/composite models but not formally tracked for drift against spec.

**Files:**
- `kalshi/_contract_map.py` (missing entries)
- `kalshi/models/markets.py` (BidAskDistribution, Candlestick, OrderbookLevel, PriceDistribution)
- `kalshi/models/events.py` (MarketMetadata, SettlementSource)
- `kalshi/models/exchange.py` (DailySchedule, MaintenanceWindow, Schedule, WeeklySchedule)
- `kalshi/models/portfolio.py` (PositionsResponse)

**Impact:**
- No automated detection of field additions/removals in nested models
- Easy to miss OpenAPI spec updates to composite fields
- Silent incompatibilities if spec adds required fields to candlestick, orderbook level, etc.

**Fix approach:**
1. Add all 8 sub-models to CONTRACT_MAP with appropriate spec schema names
2. Run contract tests to identify any hidden drift
3. Document why specific models are intentionally excluded (if any)

---

### Raw API Response Unpacking Assumes Consistent Structure (Fragile)

**Issue:** Multiple resource methods unpack API responses with fallback logic to handle legacy vs. current field names. This pattern is error-prone if API schema changes unexpectedly.

**Files:**
- `kalshi/resources/markets.py` lines 56, 63-66 (get, orderbook)
- `kalshi/resources/orders.py` lines 48, 53 (create, get)

**Example (markets.py:56):**
```python
market = data.get("market", data)  # Falls back to entire response if "market" key missing
return Market.model_validate(market)
```

**Example (markets.py:63-66):**
```python
ob = data.get("orderbook_fp") or data.get("orderbook", data)  # Multi-level fallback
yes_raw = ob.get("yes_dollars") or ob.get("yes", []) or []     # Chain of defaults
```

**Impact:**
- Silent failures if API structure changes
- Difficult to debug when Kalshi spec drifts
- No clear error message if both keys are missing

**Fix approach:**
1. Wrap in helper method with explicit error handling: `_extract_field(data, ["market", "data"], "market")`
2. Log warnings when falling back to legacy format
3. Add integration tests against real API spec structure
4. Consider using discriminated unions if API supports versioning

---

## Security Considerations

### Percent-Encoded Characters in Auth Signing Path (Potential Issue)

**Issue:** The auth signing path does NOT normalize percent-encoded characters (e.g., `%2D` stays as `%2D`). The code assumes Kalshi tickers are alphanumeric + hyphens and won't contain encodable characters. If Kalshi introduces tickers with special characters, the signature will fail.

**Files:**
- `kalshi/auth.py` lines 130-137 (comments acknowledge the risk)

**Risk:**
- Kalshi tickers like `BTC-USD` could theoretically become `BTC%2DUSD` in a URL
- Signature verification would fail because SDK doesn't normalize before signing
- No automated test covers this case

**Current mitigation:** Code comment references GitHub issue #2; tickers are currently safe

**Recommendations:**
1. Add test covering percent-encoded ticker path: `test_percent_encoded_path`
2. Coordinate with Kalshi: confirm tickers will never require encoding
3. If encoding becomes possible, implement conditional normalization:
   ```python
   # Only unquote if spec requires it
   clean_path = urllib.parse.unquote(clean_path)
   ```

---

## Fragile Areas

### orderbook() Method Hand-Parses Nested JSON (Complex, Untested Path)

**Issue:** `markets.orderbook()` manually constructs OrderbookLevel objects from raw price/quantity pairs instead of using model validation. This parsing is fragile to API changes.

**Files:**
- `kalshi/resources/markets.py` lines 59-79

**Code:**
```python
yes_levels = [
    OrderbookLevel(price=pair[0], quantity=pair[1])
    for pair in yes_raw
    if len(pair) >= 2  # Silent filter if pair too short
]
```

**Why fragile:**
- Manual list unpacking with no validation of element types
- `if len(pair) >= 2` silently drops malformed data (should error)
- If API adds/removes orderbook fields, no model validation catches it
- Orderbook model has no contract map entry, so spec drift is invisible

**Test coverage:** Basic happy-path test exists, but no error cases:
- Empty orderbook
- Null/None price values
- Non-numeric price/quantity
- Extra fields in pair tuples

**Safe modification:**
1. Use Pydantic model for parsing: `OrderbookLevel.model_validate({"price": ..., "quantity": ...})`
2. Let Pydantic validate field types
3. Add error handling for malformed data
4. Add contract map entry for OrderbookLevel to catch spec drift

---

### Response JSON Parsing Assumes Valid JSON (No Fallback)

**Issue:** All response handling assumes `response.json()` succeeds. If API returns non-JSON 2xx response (rare but possible), SDK raises uncaught exception.

**Files:**
- `kalshi/resources/_base.py` lines 29, 36, 43, 88, 95, 102
- `kalshi/_base_client.py` line 39 (error mapping only; success path not protected)

**Code (resources/_base.py:29):**
```python
def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = self._transport.request("GET", path, params=params)
    result: dict[str, Any] = response.json()  # Raises if response is not JSON
    return result
```

**Impact:**
- Unexpected 2xx response with text/html or empty body → JSONDecodeError (unhandled)
- Error message doesn't indicate which endpoint failed
- No graceful degradation for protocol issues

**Fix approach:**
1. Add try/except wrapping response.json():
   ```python
   try:
       result = response.json()
   except json.JSONDecodeError as e:
       raise KalshiError(f"Invalid JSON response from {path}: {e}") from e
   ```
2. Log response body for debugging
3. Treat 204 No Content and similar before calling .json()

---

### Retry Logic Reaches "Should Not Reach" Code Path (Logic Error Possible)

**Issue:** The retry loop has a fallback at line 170-172 (`if last_error: raise last_error`), but the loop structure makes this unreachable under normal conditions. This suggests the loop logic may be incomplete or misunderstood.

**Files:**
- `kalshi/_base_client.py` lines 104-172 (SyncTransport.request)
- `kalshi/_base_client.py` lines 205-272 (AsyncTransport.request)

**Code (lines 169-172):**
```python
# Should not reach here, but just in case
if last_error:
    raise last_error
raise KalshiError("Max retries exhausted")
```

**Why fragile:**
- The comment "Should not reach here" indicates uncertainty about loop termination
- If `max_retries=0`, the loop runs once; if response fails, line 150 raises error (good)
- But the fallback at line 172 is always unreachable because:
  - Line 150: `if not should_retry: raise error` exits on first non-retryable error
  - Line 170: Only reached if loop completes (all retries exhausted), which is `last_error is not None`
  - So line 172 is dead code

**Impact:**
- Misleading code; readers may assume the fallback is used
- Could mask future bugs if loop structure changes

**Fix approach:**
1. Remove lines 170-172 (dead code)
2. Ensure the loop always either raises or returns before completion
3. Add assertion: `assert False, "Retry loop must exit or raise"`

---

### Missing Cleanup on Auth Error in Client Constructors (Resource Leak)

**Issue:** If auth initialization fails after transport creation, the transport's HTTP client pool is never closed. This is unlikely but possible in edge cases.

**Files:**
- `kalshi/client.py` lines 50-85
- `kalshi/async_client.py` lines 43-78

**Code (client.py:50-85):**
```python
if auth is not None:
    self._auth = auth
elif key_id and private_key_path:
    self._auth = KalshiAuth.from_key_path(key_id, private_key_path)  # Can raise
elif key_id and private_key:
    self._auth = KalshiAuth.from_pem(key_id, private_key)  # Can raise
else:
    raise ValueError(...)

# ... config setup (can raise) ...

self._transport = SyncTransport(self._auth, self._config)  # Auth checked before, but...
```

**Impact:**
- No actual leak (transport created after auth), but pattern is fragile
- If config creation fails, no cleanup needed; if transport creation fails, no cleanup needed
- Future refactoring could reorder this and introduce a leak

**Fix approach:**
1. Keep auth validation early (before transport creation)
2. Add try/finally if transport creation could raise:
   ```python
   try:
       self._transport = SyncTransport(self._auth, self._config)
   except Exception:
       # No cleanup needed (nothing created yet)
       raise
   ```
3. Or use factory pattern to build client in isolated scope

---

## Test Coverage Gaps

### Orderbook Manual Parsing Not Fully Tested

**Files:**
- `kalshi/resources/markets.py` lines 59-79 (orderbook method)
- `tests/test_markets.py` (test coverage)

**Missing test cases:**
- Malformed orderbook response (extra/missing fields)
- Empty orderbook (empty yes/no lists)
- Non-numeric price values
- Null/None price or quantity
- Orderbook API returning `orderbook` key instead of `orderbook_fp`

**Priority:** Medium (feature works but lacks edge case coverage)

---

### Percent-Encoded Ticker Signature Test Missing

**Files:**
- `kalshi/auth.py` lines 130-137
- `tests/test_auth.py` (missing percent-encoding test)

**Missing test:**
```python
def test_sign_with_percent_encoded_path():
    auth = KalshiAuth("test-key", generate_rsa_key())
    # Verify that %2D (encoded hyphen) is NOT normalized in signature
    headers1 = auth.sign_request("GET", "/trade-api/v2/markets/BTC-USD")
    headers2 = auth.sign_request("GET", "/trade-api/v2/markets/BTC%2DUSD")
    # Should differ (if they don't, normalization happened invisibly)
    assert headers1["KALSHI-ACCESS-SIGNATURE"] != headers2["KALSHI-ACCESS-SIGNATURE"]
```

**Priority:** Low (tickers currently safe, but good to document assumption)

---

### No Test for Non-JSON 2xx Response

**Files:**
- `kalshi/resources/_base.py` (no error handling for invalid JSON)
- `tests/test_client.py` (no test for this case)

**Missing test:**
```python
def test_json_decode_error_on_2xx_response():
    with respx.mock:
        route = respx.get("https://api.elections.kalshi.com/trade-api/v2/test")
        route.mock(return_value=httpx.Response(200, text="<html>Not JSON</html>"))
        
        client = KalshiClient(auth=test_auth, config=test_config)
        with pytest.raises(KalshiError, match="Invalid JSON"):
            client.markets.list()
```

**Priority:** Medium (better error messages needed)

---

## Scaling Limits

### Pagination Hard-Capped at 1000 Pages

**Issue:** The `_list_all()` method terminates after 1000 pages, regardless of cursor. This is a safety limit but could silently drop results.

**Files:**
- `kalshi/resources/_base.py` lines 61-77 (SyncResource._list_all)
- `kalshi/resources/_base.py` lines 119-135 (AsyncResource._list_all)

**Code:**
```python
def _list_all(..., max_pages: int = 1000) -> Iterator[T]:
    for _ in range(max_pages):
        page = self._list(...)
        yield from page.items
        if not page.has_next:
            break
        current_params["cursor"] = page.cursor
```

**Impact:**
- If a user has >100k settlements (1000 pages × 100 items/page), last ones are silently dropped
- No warning or exception; iteration just stops
- User can't easily paginate beyond 1000 pages

**Current capacity:** Assuming default limit=100 per page, 1000 pages = 100,000 items

**Scaling path:**
1. Remove hard cap or increase to 10,000 pages
2. Add optional `max_pages` parameter to public API methods
3. Warn if cursor still exists after reaching max_pages
4. Consider streaming chunked reads for very large datasets

---

## Dependencies at Risk

### Passphrase-Protected Private Keys Not Supported (User Friction)

**Issue:** The SDK explicitly rejects passphrase-protected RSA private keys, requiring users to remove passphrases manually.

**Files:**
- `kalshi/auth.py` lines 60-65

**Code:**
```python
try:
    private_key = serialization.load_pem_private_key(pem_data, password=None)
except TypeError as e:
    raise KalshiAuthError(
        "Passphrase-protected private keys are not supported. "
        "Remove the passphrase with: openssl pkey -in key.pem -out key_nopass.pem"
    ) from e
```

**Impact:**
- Users with passphrase-protected keys must manually convert them
- Error message is clear but requires extra step
- No support for password prompting or env var passphrase

**Alternative approach:**
1. Accept optional `private_key_password` parameter
2. Prompt user for password if needed (interactive mode)
3. Read passphrase from `KALSHI_PRIVATE_KEY_PASSWORD` env var
4. Document security implications (storing password in env/memory)

---

## Missing Critical Features

### No Automatic Spec Sync or Type Generation (Manual Maintenance)

**Issue:** While `_generated/models.py` exists (datamodel-codegen output), it's not integrated into the build. Hand-written models in `kalshi/models/` must be manually kept in sync with the OpenAPI spec.

**Files:**
- `kalshi/_generated/models.py` (autogenerated, 2227 lines, not used)
- `kalshi/_contract_map.py` (manual mapping required)
- Infrastructure: scripts exist but not in CI/CD

**Impact:**
- If Kalshi adds new endpoints/fields, SDK must be manually updated
- Risk of falling out of sync with spec
- Maintenance burden as API grows (currently 90+ endpoints per CLAUDE.md)

**Current solution:** Test warnings detect drift, but don't auto-fix

**Fix approach:**
1. Integrate `scripts/sync_spec.py` into CI (download latest spec)
2. Run `datamodel-codegen` to regenerate models
3. Use contract tests to identify actual drift needing hand-crafted fixes
4. Auto-generate boilerplate resource classes for new endpoints

---

### No Request/Response Logging at SDK Level (Debugging Hard)

**Issue:** Logging is debug-level only (lines 107-113, 134 in _base_client.py). Production errors have minimal context for users to debug.

**Files:**
- `kalshi/_base_client.py` lines 107-113, 134, 158-166 (all debug level)

**Impact:**
- When a request fails, users see only exception message and status code
- No way to see full request/response without code changes
- Debugging API issues requires intercepting httpx logs (verbose)

**Fix approach:**
1. Add optional `log_level` to KalshiConfig (default: INFO for errors, DEBUG for success)
2. Log full request body on 4xx/5xx (redact auth headers)
3. Log response body on error (first 1KB)
4. Provide structured logging via stdlib logger for easy filtering

---

### No Connection Pooling Tuning (Resource Efficiency)

**Issue:** The httpx Client/AsyncClient are initialized with default connection pooling. No SDK config for pool size, keepalive, or timeouts beyond request timeout.

**Files:**
- `kalshi/_base_client.py` lines 85-89 (SyncTransport.__init__)
- `kalshi/_base_client.py` lines 184-188 (AsyncTransport.__init__)

**Code:**
```python
self._client = httpx.Client(
    base_url=config.base_url,
    timeout=config.timeout,
    headers=config.extra_headers,
    # No limits, pool_connections, pool_maxsize, etc.
)
```

**Impact:**
- Default pool size may be too small for high-concurrency bots (default: 10)
- Long-lived connections may not be reaped efficiently
- No tuning for production deployments

**Fix approach:**
1. Add pool tuning to KalshiConfig:
   ```python
   pool_connections: int = 10
   pool_maxsize: int = 10
   keepalive_expiry: float = 15.0
   ```
2. Pass to httpx.Client(limits=httpx.Limits(...))
3. Document recommended values for typical trading bots

---

