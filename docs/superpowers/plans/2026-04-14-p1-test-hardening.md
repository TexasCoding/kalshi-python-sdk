# P1 Test Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all three P1 items in TODOS.md: semantic field assertions for integration tests, error path coverage, and auth percent-encoding canonicalization.

**Architecture:** Three independent deliverables that ship as atomic commits. A shared `assert_model_fields()` helper validates runtime field types/ranges/presence on any Pydantic model and gets wired into all existing integration tests. A new `test_errors.py` verifies the SDK exception hierarchy against real API error responses. A `_normalize_percent_encoding()` function in auth.py normalizes signing paths to uppercase hex digits.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, cryptography (RSA), httpx

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `tests/integration/assertions.py` | Semantic oracle: `assert_model_fields()` helper |
| Create | `tests/integration/test_errors.py` | Error path integration tests (404, 400, 401, 429) |
| Modify | `tests/integration/test_markets.py` | Add `assert_model_fields()` calls |
| Modify | `tests/integration/test_events.py` | Add `assert_model_fields()` calls |
| Modify | `tests/integration/test_exchange.py` | Add `assert_model_fields()` calls |
| Modify | `tests/integration/test_historical.py` | Add `assert_model_fields()` calls |
| Modify | `tests/integration/test_orders.py` | Add `assert_model_fields()` calls |
| Modify | `tests/integration/test_portfolio.py` | Add `assert_model_fields()` calls |
| Modify | `kalshi/auth.py` | Add `_normalize_percent_encoding()`, apply in `sign_request()` |
| Modify | `tests/test_auth.py` | Add canonicalization test vectors, update existing test |

---

### Task 1: Create the Semantic Oracle Helper

**Files:**
- Create: `tests/integration/assertions.py`

- [ ] **Step 1: Write the `assert_model_fields()` function**

Create `tests/integration/assertions.py`:

```python
"""Semantic oracle — validates runtime field values on any Pydantic model.

Checks:
1. No float values where Decimal is expected (catches DollarDecimal parse failures)
2. Price fields in [0, 1] range for binary market fields
3. Timestamp fields are datetime instances (not raw strings/ints)
4. Required fields are non-None
5. Recurses into nested BaseModel fields and list[BaseModel] fields
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


# Exhaustive set of field names that must be in [0, 1] when non-None.
# Covers Market, OrderbookLevel, BidAskDistribution, PriceDistribution,
# Order, Fill, and Trade models.
PRICE_RANGE_FIELDS: frozenset[str] = frozenset({
    # Market model
    "yes_bid",
    "yes_ask",
    "no_bid",
    "no_ask",
    "last_price",
    "previous_yes_bid",
    "previous_yes_ask",
    "previous_price",
    # OrderbookLevel
    "price",
    # BidAskDistribution / PriceDistribution (candlestick OHLC)
    "open",
    "high",
    "low",
    "close",
    # Order / Fill / Trade
    "yes_price",
    "no_price",
})


def assert_model_fields(model: BaseModel, *, _path: str = "") -> None:
    """Validate runtime field values on a Pydantic model instance.

    Args:
        model: Any Pydantic BaseModel instance from the SDK.
        _path: Internal, for nested error messages. Do not pass externally.

    Raises:
        AssertionError with a descriptive message on the first violation found.
    """
    prefix = f"{_path}." if _path else ""
    model_name = type(model).__name__

    for field_name, field_info in model.model_fields.items():
        full_name = f"{prefix}{model_name}.{field_name}"
        val = getattr(model, field_name, None)

        if val is None:
            # Check required-field presence
            if field_info.is_required():
                raise AssertionError(
                    f"{full_name} is None but field is required"
                )
            continue

        # 1. No floats where Decimal is expected
        if isinstance(val, float):
            raise AssertionError(
                f"{full_name} is float ({val!r}), expected Decimal. "
                f"DollarDecimal parsing may have failed."
            )

        # 2. Price range validation for inclusion-set fields
        if field_name in PRICE_RANGE_FIELDS and isinstance(val, Decimal):
            if not (Decimal("0") <= val <= Decimal("1")):
                raise AssertionError(
                    f"{full_name} = {val} is outside [0, 1] range for a price field"
                )

        # 3. Timestamp type enforcement
        #    If the field annotation resolves to datetime (or datetime | None),
        #    verify the runtime value is actually a datetime instance.
        if isinstance(val, str):
            # Check if this field is supposed to be a datetime
            annotation = field_info.annotation
            if annotation is datetime or (
                hasattr(annotation, "__args__")
                and datetime in getattr(annotation, "__args__", ())
            ):
                raise AssertionError(
                    f"{full_name} is a raw string ({val!r}), expected datetime. "
                    f"Timestamp parsing may have failed."
                )

        # 4. Recurse into nested BaseModel fields
        if isinstance(val, BaseModel):
            assert_model_fields(val, _path=f"{prefix}{model_name}")

        # 5. Recurse into list[BaseModel] fields
        if isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, BaseModel):
                    assert_model_fields(
                        item, _path=f"{prefix}{model_name}.{field_name}[{i}]"
                    )
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && python -c "from tests.integration.assertions import assert_model_fields; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add tests/integration/assertions.py
git commit -m "test: add semantic oracle helper for integration test field validation"
```

---

### Task 2: Write Unit Tests for the Oracle Itself

**Files:**
- Create: `tests/integration/test_assertions.py`

- [ ] **Step 1: Write tests that verify the oracle catches violations**

Create `tests/integration/test_assertions.py`:

```python
"""Unit tests for the semantic oracle (assert_model_fields).

These don't hit the network — they verify the oracle catches field violations
on synthetic model instances.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import BaseModel, Field

from tests.integration.assertions import assert_model_fields


class FakePrice(BaseModel):
    """Minimal model with a price-range field."""
    price: Decimal


class FakeMarket(BaseModel):
    """Minimal model mimicking Market fields."""
    ticker: str
    yes_bid: Decimal | None = None
    created_time: datetime | None = None
    volume: Decimal | None = None
    nested: FakePrice | None = None
    levels: list[FakePrice] = []


class TestDecimalEnforcement:
    def test_passes_with_decimal(self) -> None:
        m = FakeMarket(ticker="T", yes_bid=Decimal("0.50"))
        assert_model_fields(m)  # should not raise

    def test_fails_with_float(self) -> None:
        m = FakeMarket.__pydantic_validator__.validate_python(
            {"ticker": "T", "volume": "not_replaced"}
        )
        # Manually set a float to simulate a parse failure
        object.__setattr__(m, "volume", 0.5)
        with pytest.raises(AssertionError, match="float.*expected Decimal"):
            assert_model_fields(m)


class TestPriceRange:
    def test_passes_in_range(self) -> None:
        m = FakeMarket(ticker="T", yes_bid=Decimal("0.65"))
        assert_model_fields(m)

    def test_fails_above_one(self) -> None:
        m = FakeMarket(ticker="T", yes_bid=Decimal("1.50"))
        with pytest.raises(AssertionError, match="outside.*range"):
            assert_model_fields(m)

    def test_volume_not_range_checked(self) -> None:
        """volume is in the exclusion set — values > 1 are fine."""
        m = FakeMarket(ticker="T", volume=Decimal("9999"))
        assert_model_fields(m)  # should not raise


class TestTimestampEnforcement:
    def test_passes_with_datetime(self) -> None:
        m = FakeMarket(ticker="T", created_time=datetime(2026, 1, 1))
        assert_model_fields(m)

    def test_fails_with_raw_string(self) -> None:
        m = FakeMarket.__pydantic_validator__.validate_python(
            {"ticker": "T"}
        )
        object.__setattr__(m, "created_time", "2026-01-01T00:00:00Z")
        with pytest.raises(AssertionError, match="raw string.*expected datetime"):
            assert_model_fields(m)


class TestRequiredFields:
    def test_fails_when_required_is_none(self) -> None:
        m = FakeMarket.__pydantic_validator__.validate_python(
            {"ticker": "T"}
        )
        object.__setattr__(m, "ticker", None)
        with pytest.raises(AssertionError, match="None but field is required"):
            assert_model_fields(m)


class TestNestedRecursion:
    def test_recurses_into_nested_model(self) -> None:
        m = FakeMarket(ticker="T", nested=FakePrice(price=Decimal("1.50")))
        with pytest.raises(AssertionError, match="price.*outside.*range"):
            assert_model_fields(m)

    def test_recurses_into_list_of_models(self) -> None:
        m = FakeMarket(
            ticker="T",
            levels=[
                FakePrice(price=Decimal("0.50")),
                FakePrice(price=Decimal("2.00")),
            ],
        )
        with pytest.raises(AssertionError, match="price.*outside.*range"):
            assert_model_fields(m)

    def test_passes_valid_nested(self) -> None:
        m = FakeMarket(
            ticker="T",
            nested=FakePrice(price=Decimal("0.75")),
            levels=[FakePrice(price=Decimal("0.25"))],
        )
        assert_model_fields(m)
```

- [ ] **Step 2: Run the oracle unit tests**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run pytest tests/integration/test_assertions.py -v`

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_assertions.py
git commit -m "test: add unit tests for semantic oracle helper"
```

---

### Task 3: Wire Oracle into Existing Integration Tests

**Files:**
- Modify: `tests/integration/test_markets.py`
- Modify: `tests/integration/test_events.py`
- Modify: `tests/integration/test_exchange.py`
- Modify: `tests/integration/test_historical.py`
- Modify: `tests/integration/test_orders.py`
- Modify: `tests/integration/test_portfolio.py`

- [ ] **Step 1: Add `assert_model_fields()` to `test_markets.py`**

Add import at top of `tests/integration/test_markets.py`:

```python
from tests.integration.assertions import assert_model_fields
```

Add `assert_model_fields(market)` after each `assert isinstance(market, Market)` in sync tests:

In `test_list` (after the `if page.items:` block, on the market variable):
```python
            assert_model_fields(market)
```

In `test_get` (after `assert market.ticker == demo_market_ticker`):
```python
        assert_model_fields(market)
```

In `test_list_all` (inside the loop, after `assert isinstance(market, Market)`):
```python
            assert_model_fields(market)
```

In `test_orderbook` (after `assert ob.ticker == demo_market_ticker`):
```python
        assert_model_fields(ob)
```

In `test_candlesticks` (inside the loop, after `assert isinstance(candle, Candlestick)`):
```python
            assert_model_fields(candle)
```

Add the same `assert_model_fields()` calls in the corresponding async test methods. For `TestMarketsAsync.test_list`, after the `assert isinstance(page, Page)`:
```python
        if page.items:
            assert_model_fields(page.items[0])
```

For `TestMarketsAsync.test_get`:
```python
        assert_model_fields(market)
```

For `TestMarketsAsync.test_orderbook`:
```python
        assert_model_fields(ob)
```

- [ ] **Step 2: Add `assert_model_fields()` to `test_events.py`**

Add import at top:
```python
from tests.integration.assertions import assert_model_fields
```

In `TestEventsSync.test_list` (after `assert page.items[0].event_ticker`):
```python
            assert_model_fields(page.items[0])
```

In `TestEventsSync.test_get` (after `assert event.event_ticker == demo_event_ticker`):
```python
        assert_model_fields(event)
```

In `TestEventsSync.test_list_all` (after `assert isinstance(event, Event)`):
```python
            assert_model_fields(event)
```

In `TestEventsSync.test_metadata` (after `assert isinstance(meta, EventMetadata)`):
```python
        assert_model_fields(meta)
```

Add matching calls in async tests.

- [ ] **Step 3: Add `assert_model_fields()` to `test_exchange.py`**

Add import at top:
```python
from tests.integration.assertions import assert_model_fields
```

In `TestExchangeSync.test_status` (after `assert isinstance(result.trading_active, bool)`):
```python
        assert_model_fields(result)
```

In `TestExchangeSync.test_schedule` (after `assert isinstance(result, Schedule)`):
```python
        assert_model_fields(result)
```

In `TestExchangeSync.test_announcements` (inside the loop, after `assert isinstance(item, Announcement)`):
```python
            assert_model_fields(item)
```

Add matching calls in async tests.

- [ ] **Step 4: Add `assert_model_fields()` to `test_historical.py`**

Add import at top:
```python
from tests.integration.assertions import assert_model_fields
```

Add `assert_model_fields()` after every `assert isinstance(item, Model)` in sync tests:
- `test_cutoff`: `assert_model_fields(result)` after isinstance check
- `test_markets`: `assert_model_fields(item)` inside the loop
- `test_markets_all`: `assert_model_fields(market)` inside the loop
- `test_market`: `assert_model_fields(result)` after ticker check
- `test_candlesticks`: `assert_model_fields(candle)` inside the loop
- `test_fills`: `assert_model_fields(item)` inside the loop
- `test_fills_all`: `assert_model_fields(fill)` inside the loop
- `test_orders`: `assert_model_fields(item)` inside the loop
- `test_orders_all`: `assert_model_fields(order)` inside the loop
- `test_trades`: `assert_model_fields(item)` inside the loop
- `test_trades_all`: `assert_model_fields(trade)` inside the loop

Add matching calls in async tests (at least one per method to verify models parse correctly).

- [ ] **Step 5: Add `assert_model_fields()` to `test_orders.py`**

Add import at top:
```python
from tests.integration.assertions import assert_model_fields
```

In `TestOrdersSync.test_list` (inside the loop, after `assert isinstance(item, Order)`):
```python
            assert_model_fields(item)
```

In `TestOrdersSync.test_list_all` (after `assert isinstance(order, Order)`):
```python
            assert_model_fields(order)
```

In `TestOrdersSync.test_fills` (inside the loop, after `assert isinstance(item, Fill)`):
```python
            assert_model_fields(item)
```

In `TestOrdersSync.test_fills_all` (after `assert isinstance(fill, Fill)`):
```python
            assert_model_fields(fill)
```

In `TestOrdersSync.test_create_get_cancel` (after `assert order.order_id`):
```python
        assert_model_fields(order)
```

And after `assert retrieved.order_id == order.order_id`:
```python
            assert_model_fields(retrieved)
```

In `TestOrdersSync.test_batch_create_cancel` (inside the loop, after `assert isinstance(o, Order)`):
```python
            assert_model_fields(o)
```

Add matching calls in async test methods.

- [ ] **Step 6: Add `assert_model_fields()` to `test_portfolio.py`**

Add import at top:
```python
from tests.integration.assertions import assert_model_fields
```

In `TestPortfolioSync.test_balance` (after `assert isinstance(result.balance, int)`):
```python
        assert_model_fields(result)
```

In `TestPortfolioSync.test_positions` (after the list isinstance checks):
```python
        assert_model_fields(result)
```

In `TestPortfolioSync.test_settlements` (inside the loop, after `assert isinstance(item, Settlement)`):
```python
            assert_model_fields(item)
```

In `TestPortfolioSync.test_settlements_all` (after `assert isinstance(settlement, Settlement)`):
```python
            assert_model_fields(settlement)
```

Add matching calls in async tests.

- [ ] **Step 7: Run mypy on integration tests**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run mypy tests/integration/assertions.py tests/integration/test_assertions.py`

Expected: Success, no errors.

- [ ] **Step 8: Run unit tests to make sure nothing is broken**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run pytest tests/ -v --ignore=tests/integration -x`

Expected: All existing unit tests PASS.

- [ ] **Step 9: Commit**

```bash
git add tests/integration/test_markets.py tests/integration/test_events.py tests/integration/test_exchange.py tests/integration/test_historical.py tests/integration/test_orders.py tests/integration/test_portfolio.py
git commit -m "test: wire semantic oracle into all integration tests"
```

---

### Task 4: Error Path Integration Tests

**Files:**
- Create: `tests/integration/test_errors.py`

Note: Error tests don't register with the coverage harness because the harness tracks resource-method pairs (e.g., "MarketsResource" -> ["list", "get"]). Error path tests are cross-cutting — they test the shared `_map_error()` function in `_base_client.py`, not specific resource methods.

- [ ] **Step 1: Create `test_errors.py` with all error path tests**

Create `tests/integration/test_errors.py`:

```python
"""Integration tests for SDK error handling against real API responses.

Verifies that the error hierarchy in kalshi/errors.py correctly maps
HTTP error codes from the demo API to the right exception classes.

Tests are sync-only because error mapping lives in _map_error() which
is shared between SyncTransport and AsyncTransport.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import KalshiConfig
from kalshi.errors import (
    KalshiAuthError,
    KalshiNotFoundError,
    KalshiValidationError,
)


@pytest.mark.integration
class TestErrorPaths:
    """Verify SDK exception hierarchy against real API error responses."""

    def test_invalid_ticker_returns_not_found(
        self, sync_client: KalshiClient
    ) -> None:
        """GET /markets/{ticker} with a nonexistent ticker should raise KalshiNotFoundError."""
        with pytest.raises(KalshiNotFoundError) as exc_info:
            sync_client.markets.get("NONEXISTENT_TICKER_XYZ_99")

        exc = exc_info.value
        assert exc.status_code == 404
        assert str(exc)  # message is non-empty

    def test_malformed_params_returns_validation_error(
        self, sync_client: KalshiClient
    ) -> None:
        """Malformed request params should raise KalshiValidationError (400)."""
        # Use an obviously invalid limit value
        with pytest.raises(KalshiValidationError) as exc_info:
            sync_client.markets.list(limit=-1)

        exc = exc_info.value
        assert exc.status_code == 400
        assert str(exc)  # message is non-empty

    def test_bad_auth_returns_auth_error(self) -> None:
        """A client with invalid credentials should raise KalshiAuthError (401/403).

        Uses a throwaway client with a valid RSA key but wrong key_id,
        so signing succeeds but the server rejects the credentials.
        """
        dummy_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
        auth = KalshiAuth(
            key_id="invalid-key-id-for-test", private_key=dummy_key
        )
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2"
        )
        client = KalshiClient(auth=auth, config=config)

        try:
            with pytest.raises(KalshiAuthError) as exc_info:
                client.markets.list(limit=1)

            exc = exc_info.value
            assert exc.status_code in (401, 403)
            assert str(exc)  # message is non-empty
        finally:
            client.close()

    def test_not_found_error_has_status_code_attribute(
        self, sync_client: KalshiClient
    ) -> None:
        """Verify the exception object carries structured data, not just a message."""
        with pytest.raises(KalshiNotFoundError) as exc_info:
            sync_client.markets.get("ANOTHER_FAKE_TICKER_ABC_00")

        exc = exc_info.value
        # KalshiError base class stores status_code
        assert hasattr(exc, "status_code")
        assert isinstance(exc.status_code, int)

    def test_validation_error_details_attribute(
        self, sync_client: KalshiClient
    ) -> None:
        """KalshiValidationError should have a details attribute (may be None or dict)."""
        with pytest.raises(KalshiValidationError) as exc_info:
            sync_client.markets.list(limit=-1)

        exc = exc_info.value
        assert hasattr(exc, "details")
        # details is either None or a dict — both are valid
        assert exc.details is None or isinstance(exc.details, dict)
```

- [ ] **Step 2: Run the error path tests (requires demo API credentials)**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run pytest tests/integration/test_errors.py -v -m integration`

Expected: All tests PASS. If credentials are not set, tests should be skipped.

Note: If `test_malformed_params_returns_validation_error` fails because the API doesn't return 400 for `limit=-1`, try an alternative trigger. For example, pass an invalid `status` parameter: `sync_client.markets.list(status="INVALID_STATUS_XYZ")`. The test should be updated to use whichever trigger reliably produces a 400 response.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_errors.py
git commit -m "test: add error path integration tests for 404, 400, and 401"
```

---

### Task 5: Auth Percent-Encoding Canonicalization

**Files:**
- Modify: `kalshi/auth.py`
- Modify: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests for percent-encoding canonicalization**

Add the following to `tests/test_auth.py`, inside the `TestSignRequest` class, after the existing `test_encoded_and_decoded_paths_differ` method:

```python
    @pytest.mark.parametrize(
        "input_path,expected_canonical",
        [
            # Already uppercase — no change
            ("/trade-api/v2/markets/ABC%2FDEF", "/trade-api/v2/markets/ABC%2FDEF"),
            # Lowercase hex -> uppercase
            ("/trade-api/v2/markets/ABC%2fDEF", "/trade-api/v2/markets/ABC%2FDEF"),
            # Encoded space
            ("/trade-api/v2/markets/test%20name", "/trade-api/v2/markets/test%20name"),
            # Mixed case multiple
            ("/trade-api/v2/markets/%2F%2f%2F", "/trade-api/v2/markets/%2F%2F%2F"),
            # Lowercase + query (query stripped, then hex uppercased)
            ("/trade-api/v2/markets/ABC%2fDEF?q=1", "/trade-api/v2/markets/ABC%2FDEF"),
            # Lowercase + trailing slash
            ("/trade-api/v2/markets/ABC%2fDEF/", "/trade-api/v2/markets/ABC%2FDEF"),
            # No encoding needed
            ("/trade-api/v2/markets/simple", "/trade-api/v2/markets/simple"),
        ],
        ids=[
            "uppercase_passthrough",
            "lowercase_to_uppercase",
            "encoded_space",
            "mixed_case_multiple",
            "lowercase_plus_query",
            "lowercase_plus_trailing_slash",
            "no_encoding",
        ],
    )
    def test_percent_encoding_canonicalization(
        self,
        rsa_private_key: rsa.RSAPrivateKey,
        test_auth: KalshiAuth,
        input_path: str,
        expected_canonical: str,
    ) -> None:
        """Signing should normalize percent-encoding to uppercase hex."""
        ts = 1000
        headers = test_auth.sign_request("GET", input_path, timestamp_ms=ts)
        sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])

        expected_msg = f"{ts}GET{expected_canonical}".encode()
        # If the signing used the canonical path, verification will succeed.
        # If not, this will raise InvalidSignature.
        rsa_private_key.public_key().verify(
            sig,
            expected_msg,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )

    def test_case_variants_produce_same_signature(
        self, test_auth: KalshiAuth
    ) -> None:
        """Paths differing only in percent-encoding case should produce identical signatures."""
        h1 = test_auth.sign_request(
            "GET", "/trade-api/v2/events/TICKER%2dNAME", timestamp_ms=1000
        )
        h2 = test_auth.sign_request(
            "GET", "/trade-api/v2/events/TICKER%2DNAME", timestamp_ms=1000
        )
        assert h1["KALSHI-ACCESS-SIGNATURE"] == h2["KALSHI-ACCESS-SIGNATURE"]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run pytest tests/test_auth.py::TestSignRequest::test_percent_encoding_canonicalization -v`

Expected: FAIL — the `lowercase_to_uppercase` and other lowercase cases will fail because `sign_request()` doesn't normalize yet.

Also run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run pytest tests/test_auth.py::TestSignRequest::test_case_variants_produce_same_signature -v`

Expected: FAIL — the two paths produce different signatures currently.

- [ ] **Step 3: Implement `_normalize_percent_encoding()` in `kalshi/auth.py`**

Add `import re` to the imports at the top of `kalshi/auth.py` (after `from pathlib import Path`):

```python
import re
```

Add the helper function before the `KalshiAuth` class definition:

```python
def _normalize_percent_encoding(path: str) -> str:
    """Normalize percent-encoded characters to uppercase hex digits.

    RFC 3986 section 2.1: percent-encoded octets should use uppercase
    hex digits for consistency. This ensures signing payloads are
    identical regardless of how the URL was constructed.

    Examples:
        /markets/ABC%2fDEF -> /markets/ABC%2FDEF
        /markets/ABC%2FDEF -> /markets/ABC%2FDEF (no change)
    """
    return re.sub(
        r"%([0-9a-fA-F]{2})",
        lambda m: "%" + m.group(1).upper(),
        path,
    )
```

In the `sign_request()` method, after the trailing-slash stripping block and before the `ts_str = str(timestamp_ms)` line, replace the NOTE comment block with:

```python
        # Normalize percent-encoding to uppercase hex (RFC 3986 section 2.1)
        clean_path = _normalize_percent_encoding(clean_path)
```

Remove the old NOTE comment about percent-encoded characters (lines 133-136 in the original file).

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run pytest tests/test_auth.py -v`

Expected: All tests PASS, including the new canonicalization tests.

- [ ] **Step 5: Update the existing `test_percent_encoded_path_signed_as_is` test**

The existing test at `tests/test_auth.py:106` documents that percent-encoded paths are "signed as-is." After our change, they are still signed as-is (we don't decode them), but lowercase hex is now normalized to uppercase. Update the test name and docstring to reflect the new behavior:

Rename: `test_percent_encoded_path_signed_as_is` -> `test_percent_encoded_path_preserved_but_normalized`

Update the docstring:
```python
    def test_percent_encoded_path_preserved_but_normalized(
        self, rsa_private_key: rsa.RSAPrivateKey, test_auth: KalshiAuth
    ) -> None:
        """Percent-encoded paths are signed without decoding, but hex digits
        are normalized to uppercase per RFC 3986 section 2.1."""
```

The existing test body still works because `%2D` is already uppercase.

Also update `test_encoded_and_decoded_paths_differ`:
```python
    def test_encoded_and_decoded_paths_differ(self, test_auth: KalshiAuth) -> None:
        """Encoded and decoded paths produce different signatures.
        %2D is the encoding of '-', but the signing payload preserves the
        encoding rather than decoding it."""
```

- [ ] **Step 6: Run the full auth test suite**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run pytest tests/test_auth.py -v`

Expected: All tests PASS.

- [ ] **Step 7: Run mypy on the changed files**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run mypy kalshi/auth.py`

Expected: Success, no errors.

- [ ] **Step 8: Commit**

```bash
git add kalshi/auth.py tests/test_auth.py
git commit -m "fix: normalize percent-encoding in auth signing to uppercase hex (RFC 3986)"
```

---

### Task 6: Run Full Test Suite and Update TODOS.md

**Files:**
- Modify: `TODOS.md`

- [ ] **Step 1: Run all unit tests**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run pytest tests/ -v --ignore=tests/integration -x`

Expected: All existing unit tests PASS, plus the new `test_assertions.py` tests.

- [ ] **Step 2: Run mypy on all modified scopes**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run mypy kalshi/ tests/integration/assertions.py tests/integration/test_assertions.py tests/integration/test_errors.py`

Expected: Success, no errors.

- [ ] **Step 3: Run integration tests (if credentials available)**

Run: `cd /Users/jeffreywest/Code/Python/kalshi-python-sdk && uv run pytest tests/integration/ -v -m integration`

Expected: All tests PASS including the new `assert_model_fields()` calls and error path tests. If any `assert_model_fields()` call fails against real API data, that's a genuine bug found by the oracle — fix the model or document the finding.

- [ ] **Step 4: Update TODOS.md — mark P1 items as completed**

Move the three P1 items to the `## Completed` section at the bottom of `TODOS.md`:

```markdown
### ~~Auth path percent-encoding canonicalization~~
**Completed:** 2026-04-14. Added `_normalize_percent_encoding()` in `kalshi/auth.py` to normalize percent-encoded hex digits to uppercase per RFC 3986 section 2.1. Test vector corpus with 7 cases added to `tests/test_auth.py`.

### ~~Integration test — deeper field assertions on model responses~~
**Completed:** 2026-04-14. Created `tests/integration/assertions.py` with `assert_model_fields()` semantic oracle. Validates Decimal types, price ranges [0,1], datetime parsing, required-field presence, and recurses into nested models. Wired into all 6 integration test files.

### ~~Integration test — error path coverage~~
**Completed:** 2026-04-14. Created `tests/integration/test_errors.py` with tests for 404 (KalshiNotFoundError), 400 (KalshiValidationError), and 401 (KalshiAuthError) error paths against the demo API. Sync-only (error mapping is transport-shared).
```

- [ ] **Step 5: Commit**

```bash
git add TODOS.md
git commit -m "docs: mark 3 P1 items as completed in TODOS.md"
```
