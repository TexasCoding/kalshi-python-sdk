# Testing Patterns

**Analysis Date:** 2026-04-13

## Test Framework

**Runner:**
- pytest 8.x
- pytest-asyncio 0.24.x (handles async test discovery and execution)
- asyncio_mode: "auto" (auto-detect async tests via `@pytest.mark.asyncio`)
- Config: `pyproject.toml` under `[tool.pytest.ini_options]`

**Assertion Library:**
- pytest's built-in `assert` statements (no external assertion library)

**HTTP Mocking:**
- respx 0.21.x (httpx mock library, replaces unittest.mock for HTTP calls)

**Run Commands:**
```bash
uv run pytest tests/ -v              # Run all tests with verbose output
uv run pytest tests/ -k test_name    # Run specific test by name
uv run pytest tests/ --tb=short      # Show short traceback format
uv run pytest tests/ -x              # Stop on first failure
uv run pytest tests/ --lf            # Run last failed tests
```

## Test File Organization

**Location:**
- Tests co-located in `tests/` directory (separate from source, not mixed in `kalshi/`)
- Test file naming: `test_*.py` (pytest discovery pattern)

**Structure:**
```
tests/
├── conftest.py              # Shared fixtures (auth, config, RSA keys)
├── test_auth.py             # Tests for kalshi.auth (RSA signing)
├── test_client.py           # Tests for KalshiClient, SyncTransport, error mapping
├── test_async_client.py     # Tests for AsyncKalshiClient, AsyncTransport
├── test_markets.py          # Tests for MarketsResource (sync)
├── test_async_markets.py    # Tests for AsyncMarketsResource
├── test_orders.py           # Tests for OrdersResource (sync)
├── test_async_orders.py     # Tests for AsyncOrdersResource
├── test_pagination.py       # Tests for Page[T] model and list_all iteration
├── test_models.py           # Tests for Pydantic models, DollarDecimal, aliases
├── test_events.py           # Tests for EventsResource
├── test_portfolio.py        # Tests for PortfolioResource
├── test_exchange.py         # Tests for ExchangeResource
├── test_historical.py       # Tests for HistoricalResource
├── test_contracts.py        # Tests for contract mapping utilities
└── __init__.py              # Empty marker file
```

## Test Structure

**Suite Organization:**
```python
# tests/test_auth.py - Class-based test organization

class TestSignRequest:
    """Tests for KalshiAuth.sign_request()."""
    
    def test_returns_three_headers(self, test_auth: KalshiAuth) -> None:
        headers = test_auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=1000)
        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers

class TestFromKeyPath:
    """Tests for KalshiAuth.from_key_path()."""
    
    def test_loads_valid_pem_file(self, pem_bytes: bytes) -> None:
        # Setup, action, assertion
        ...
```

**Patterns:**
- Test classes group related test methods: `TestSignRequest`, `TestFromKeyPath`, `TestMarketsList`, `TestErrorMapping`
- Test method names are descriptive: `test_returns_three_headers()`, `test_strips_query_params()`, `test_not_found()`
- Test method signature uses type-hinted fixtures: `def test_name(self, fixture_name: FixtureType) -> None:`
- Single assertion per test when possible; multiple assertions acceptable if testing one behavior (e.g., structure of a dict)

## Fixtures

**Shared Fixtures (conftest.py):**
```python
@pytest.fixture
def rsa_private_key() -> rsa.RSAPrivateKey:
    """Generate a test RSA private key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)

@pytest.fixture
def pem_bytes(rsa_private_key: rsa.RSAPrivateKey) -> bytes:
    """PEM-encoded private key bytes."""
    return rsa_private_key.private_bytes(...)

@pytest.fixture
def test_auth(rsa_private_key: rsa.RSAPrivateKey) -> KalshiAuth:
    """A KalshiAuth instance with a test key."""
    return KalshiAuth(key_id="test-key-id", private_key=rsa_private_key)

@pytest.fixture
def test_config() -> KalshiConfig:
    """A test config pointing at a fake base URL."""
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=2,
    )
```

**Module-Specific Fixtures (in test files):**
```python
# tests/test_markets.py

@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,  # Disable retries for deterministic tests
    )

@pytest.fixture
def markets(test_auth: KalshiAuth, config: KalshiConfig) -> MarketsResource:
    return MarketsResource(SyncTransport(test_auth, config))
```

**Fixture Usage:**
- Built on pytest's dependency injection
- Fixtures automatically called based on function parameter names
- Fixtures can depend on other fixtures (e.g., `markets` depends on `test_auth` and `config`)
- Fresh instances per test (scope="function" is default)

## Mocking

**Framework:** respx (modern httpx mock library)

**Patterns:**

**Basic mock (decorator style):**
```python
@respx.mock
def test_returns_page_of_markets(self, markets: MarketsResource) -> None:
    respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
        return_value=httpx.Response(
            200,
            json={
                "markets": [
                    {"ticker": "MKT-A", "yes_bid_dollars": "0.45"},
                    {"ticker": "MKT-B", "yes_bid_dollars": "0.60"},
                ],
                "cursor": "page2",
            },
        )
    )
    page = markets.list()
    assert len(page) == 2
    assert page.has_next is True
```

**Multiple responses (side_effect):**
```python
@respx.mock
def test_auto_paginates(self, markets: MarketsResource) -> None:
    respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"markets": [{"ticker": "A"}, {"ticker": "B"}], "cursor": "page2"},
            ),
            httpx.Response(
                200,
                json={"markets": [{"ticker": "C"}], "cursor": None},
            ),
        ]
    )
    tickers = [m.ticker for m in markets.list_all()]
    assert tickers == ["A", "B", "C"]
```

**Asserting on request (route.calls):**
```python
@respx.mock
def test_with_status_filter(self, markets: MarketsResource) -> None:
    route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
        return_value=httpx.Response(200, json={"markets": [], "cursor": None})
    )
    markets.list(status="open")
    assert route.calls[0].request.url.params["status"] == "open"
```

**Async pattern (with @pytest.mark.asyncio):**
```python
@respx.mock
@pytest.mark.asyncio
async def test_get_retries_on_502(self, transport: AsyncTransport) -> None:
    route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
        side_effect=[
            httpx.Response(502, text="Bad Gateway"),
            httpx.Response(200, json={"markets": []}),
        ]
    )
    resp = await transport.request("GET", "/markets")
    assert resp.status_code == 200
    assert route.call_count == 2
```

**What to Mock:**
- External HTTP calls (mocked via respx)
- File I/O in auth tests (use tempfile)
- Do NOT mock internal SDK classes in unit tests (test real composition)

**What NOT to Mock:**
- RSA signing (test the real crypto)
- Model validation (test real Pydantic parsing)
- Retry logic (test real exponential backoff)
- Error mapping (test real exception construction)

## Fixtures and Factories

**Test Data:**

**Helper functions for creating test objects:**
```python
# tests/test_pagination.py

def _market(ticker: str) -> Market:
    return Market(ticker=ticker)

class TestPage:
    def test_iterate_items(self) -> None:
        page: Page[Market] = Page(items=[_market("A"), _market("B")])
        tickers = [m.ticker for m in page]
        assert tickers == ["A", "B"]
```

**Inline fixture creation:**
```python
# tests/test_models.py

class TestDollarsAliasFields:
    def test_market_accepts_dollars_suffix(self) -> None:
        m = Market.model_validate({
            "ticker": "T",
            "yes_bid_dollars": "0.4500",
            "yes_ask_dollars": "0.5500",
        })
        assert m.yes_bid == Decimal("0.4500")
```

## Coverage

**Requirements:** Not enforced via CI (no coverage threshold configured)

**Testing approach:**
- Aim for comprehensive coverage of public APIs and error paths
- 149 tests covering: auth, transport, retry, error mapping, pagination, all resources, models, client constructors, async code paths
- Each public method receives at least: happy path test, error path test, edge case test

## Test Types

**Unit Tests:**
- Scope: Single module or class in isolation (with mocked dependencies)
- Examples: `test_auth.py` tests `KalshiAuth` signing; `test_models.py` tests Pydantic field parsing
- Approach: Use respx to mock HTTP, assert on output

**Integration Tests:**
- Scope: Full request/response cycle through transport (not actual API)
- Examples: `test_client.py` tests retry logic with mocked HTTP responses; `test_markets.py` tests resource methods
- Approach: Mock HTTP responses, test error mapping, pagination, data parsing

**API Contract Tests:**
- Implicit: Model tests verify field name aliases accept both API names and SDK names
- Example: `test_models.py::TestDollarsAliasFields` verifies `Market.model_validate({yes_bid_dollars: ...})` works

**No E2E tests:** Codebase does not include tests against live API (would require real credentials)

## Common Patterns

**Async Testing:**

Test async resources with `@pytest.mark.asyncio` and `async def`:
```python
@respx.mock
@pytest.mark.asyncio
async def test_list_returns_page(self, markets: AsyncMarketsResource) -> None:
    respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
        return_value=httpx.Response(
            200,
            json={"markets": [{"ticker": "A"}], "cursor": None},
        )
    )
    page = await markets.list()
    assert len(page) == 1
```

Async iterators return `AsyncIterator` directly, so `async for` works:
```python
@respx.mock
@pytest.mark.asyncio
async def test_list_all_auto_paginates(self, markets: AsyncMarketsResource) -> None:
    # Set up mock responses
    tickers = []
    async for market in markets.list_all():
        tickers.append(market.ticker)
    assert tickers == ["A", "B", "C"]
```

**Error Testing:**

Test that specific error types are raised:
```python
@respx.mock
def test_404_raises_not_found(self, markets: MarketsResource) -> None:
    respx.get("https://test.kalshi.com/trade-api/v2/markets/FAKE").mock(
        return_value=httpx.Response(404, json={"message": "market not found"})
    )
    with pytest.raises(KalshiNotFoundError):
        markets.get("FAKE")
```

Test exception attributes:
```python
def test_validation_error_includes_details(self) -> None:
    resp = httpx.Response(
        400, json={"message": "failed", "details": {"ticker": "required"}}
    )
    err = _map_error(resp)
    assert isinstance(err, KalshiValidationError)
    assert err.details == {"ticker": "required"}
    assert err.status_code == 400
```

**Decimal/Precision Testing:**

Test float-to-Decimal conversion avoids precision issues:
```python
def test_float_precision(self) -> None:
    """0.65 as float has representation issues. to_decimal avoids them."""
    result = to_decimal(0.65)
    # Decimal(0.65) would give 0.6499999...
    # Decimal(str(0.65)) gives exactly 0.65
    assert str(result) == "0.65"
```

---

*Testing analysis: 2026-04-13*
