# Coding Conventions

**Analysis Date:** 2026-04-13

## Naming Patterns

**Files:**
- Module files: `lowercase_with_underscores.py` (e.g., `auth.py`, `_base_client.py`, `config.py`)
- Private module prefix: Single underscore for internal modules (e.g., `_base_client.py`, `_contract_map.py`)
- Class files match their primary class: `auth.py` exports `KalshiAuth`, `config.py` exports `KalshiConfig`

**Functions:**
- snake_case for all functions (e.g., `sign_request()`, `list_all()`, `from_env()`)
- Leading underscore for private/internal functions (e.g., `_params()`, `_map_error()`, `_compute_backoff()`)
- Classmethods use descriptive names: `from_key_path()`, `from_pem()`, `from_env()`, `production()`, `demo()`

**Variables:**
- snake_case for all variables and attributes (e.g., `base_url`, `timestamp_ms`, `max_retries`)
- Leading underscore for private instance attributes (e.g., `self._auth`, `self._config`, `self._transport`)
- Constants in UPPERCASE (e.g., `PRODUCTION_BASE_URL`, `DEMO_BASE_URL`, `RETRYABLE_STATUS_CODES`)

**Types:**
- PascalCase for all classes (e.g., `KalshiClient`, `AsyncKalshiClient`, `KalshiAuth`, `KalshiConfig`, `Market`, `Order`)
- Custom types use descriptive names: `DollarDecimal` (Annotated Pydantic type), `Page[T]` (generic pagination model)
- Exception classes end with `Error`: `KalshiError`, `KalshiAuthError`, `KalshiNotFoundError`, `KalshiValidationError`, `KalshiRateLimitError`, `KalshiServerError`

## Code Style

**Formatting:**
- Line length: 100 characters (Ruff configured with `line-length = 100`)
- Indentation: 4 spaces
- Tool: Ruff for linting and formatting

**Linting:**
- Ruff enabled with rules: `["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "RUF"]`
- Ignored rules:
  - `A002`: Allow shadowing builtins (Kalshi API uses field names like `type`)
  - `UP046`: Allow Pydantic v2 Generic[T] subclass syntax for generic models
- Run via: `uv run ruff check .` or `uv run ruff check . --fix`

**Type Checking:**
- mypy strict mode (all settings enabled)
- Must pass before commit: `uv run mypy kalshi/`
- CI rejects PRs if mypy fails
- Special requirement: Use `builtins.list[T]` in type annotations inside resource classes (not bare `list[T]`), due to shadowing by resource `.list()` methods

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first, enables PEP 563 string annotations)
2. Standard library imports (stdlib)
3. Third-party imports (pydantic, httpx, cryptography, etc.)
4. Local imports (kalshi.* modules)

**Example:**
```python
from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
from pydantic import AliasChoices, BaseModel, Field

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
```

**Path Aliases:**
- Not used; all imports are absolute from `kalshi.*` package root
- No @ or ~ shortcuts in configuration

## Error Handling

**Patterns:**
- Exceptions are custom subclasses of `KalshiError` base exception (defined in `kalshi/errors.py`)
- HTTP responses map to specific exception types via `_map_error()` function in `kalshi/_base_client.py`:
  - 400 → `KalshiValidationError` (may include field-level `details`)
  - 401/403 → `KalshiAuthError`
  - 404 → `KalshiNotFoundError`
  - 429 → `KalshiRateLimitError` (includes optional `retry_after` header value)
  - 5xx → `KalshiServerError`
  - Other → `KalshiError` (base)
- All exceptions store `status_code` as instance attribute
- Raised by transport layer in `SyncTransport.request()` and `AsyncTransport.request()`
- User code catches specific exceptions or base `KalshiError`

**Example:**
```python
from kalshi.errors import KalshiRateLimitError, KalshiNotFoundError

try:
    market = client.markets.get("FAKE")
except KalshiNotFoundError as e:
    print(f"Market not found: {e.status_code}")
except KalshiRateLimitError as e:
    if e.retry_after:
        time.sleep(e.retry_after)
```

## Logging

**Framework:** Python `logging` module (stdlib)

**Logger:** Single module-level logger per transport: `logger = logging.getLogger("kalshi")`

**Patterns:**
- Debug level: Request/response flow details (path, method, status)
- Warning level: Retry attempts, Retry-After header warnings
- No info/error logging at this layer (errors bubble up as exceptions)

**Example from `kalshi/_base_client.py`:**
```python
logger.debug("Request: %s %s", method.upper(), path)
logger.debug("Response: %s %s → %d", method.upper(), path, response.status_code)
logger.warning("Timeout on %s %s, retrying in %.1fs", method, path, delay)
```

Users control logging verbosity:
```python
import logging
logging.getLogger("kalshi").setLevel(logging.DEBUG)
```

## Comments

**When to Comment:**
- Algorithm explanations: e.g., RSA-PSS signature calculation, exponential backoff with jitter
- Known limitations: e.g., percent-encoding normalization in URL paths (see `auth.py:133-137`)
- API quirks and fallbacks: e.g., parsing orderbook with legacy fallback keys
- Multiline complex logic: e.g., query param stripping before signature, retry backoff computation

**JSDoc/TSDoc:**
- Use Google-style docstrings for public classes, methods, functions
- Triple-quoted: `"""Single-line summary.` or `"""Multi-line summary with details."""`
- Include Args, Returns, Raises sections for public methods
- Do NOT use type hints in docstrings (rely on function signature type annotations)

**Example:**
```python
def sign_request(
    self, method: str, path: str, timestamp_ms: int | None = None
) -> dict[str, str]:
    """Sign a request and return the auth headers.

    Args:
        method: HTTP method (GET, POST, DELETE, etc.)
        path: Full API path (e.g., /trade-api/v2/markets). Query params are stripped.
        timestamp_ms: Unix timestamp in milliseconds. Auto-generated if None.

    Returns:
        Dict with KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE, KALSHI-ACCESS-TIMESTAMP.
    """
```

## Function Design

**Size:** Aim for <50 lines for typical methods. Larger functions (like retry logic) acceptable if focused on single responsibility.

**Parameters:**
- Keyword-only arguments for public APIs (use `*` separator after positional args if any)
- Type hints required on all parameters (enforced by mypy strict)
- Default values encouraged for optional parameters

**Return Values:**
- Explicit return type annotations required (mypy strict enforces)
- Return `dict[str, Any]` for raw API responses, then parse into Pydantic models
- Return Pydantic `BaseModel` subclasses or `Page[T]` for structured data
- Return `None` for void operations (e.g., `cancel()` methods)
- Async methods return coroutines (awaitable), not values directly

**Example pattern:**
```python
def create(
    self,
    *,
    ticker: str,
    side: str,
    count: int = 1,
) -> Order:
    """Create an order."""
    body = {"ticker": ticker, "side": side, "count": count}
    data = self._post("/portfolio/orders", json=body)
    return Order.model_validate(data.get("order", data))
```

## Module Design

**Exports:**
- Each module exports its primary classes/functions via `__all__`
- `kalshi/__init__.py` re-exports public API: clients, models, auth, config, exceptions
- Internal modules prefixed with `_` are not re-exported

**Barrel Files:**
- `kalshi/models/__init__.py` exports all model classes
- `kalshi/resources/__init__.py` exports resource base classes
- No wildcard imports (`from X import *`); all imports explicit

**Example `__init__.py`:**
```python
from kalshi.auth import KalshiAuth
from kalshi.errors import KalshiError, KalshiAuthError, ...

__all__ = [
    "KalshiAuth",
    "KalshiError",
    "KalshiAuthError",
    ...
]
```

## Pydantic Model Design

**Config:**
- All models inherit from `pydantic.BaseModel`
- Use `validation_alias=AliasChoices(...)` to accept both API field names (with `_dollars` suffix) and SDK field names
- Use `serialization_alias` to output with API names when serializing

**Fields:**
- Price fields: Use `DollarDecimal` custom type (handles str/int/float/Decimal conversion)
- Optional fields: Default to `None` with explicit `| None` union type
- Constraints: Use Pydantic `Field()` for validation rules, constraints

**Example:**
```python
from kalshi.types import DollarDecimal
from pydantic import AliasChoices, BaseModel, Field

class Market(BaseModel):
    ticker: str
    yes_bid: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_bid_dollars", "yes_bid"),
    )
```

---

*Convention analysis: 2026-04-13*
