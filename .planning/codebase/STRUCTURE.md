# Codebase Structure

**Analysis Date:** 2026-04-13

## Directory Layout

```
kalshi-python-sdk/
├── kalshi/                          # Main SDK package
│   ├── __init__.py                 # Public API exports + __version__
│   ├── client.py                   # KalshiClient (sync facade)
│   ├── async_client.py             # AsyncKalshiClient (async facade)
│   ├── _base_client.py             # SyncTransport + AsyncTransport
│   ├── auth.py                     # KalshiAuth (RSA-PSS signing)
│   ├── config.py                   # KalshiConfig (settings + defaults)
│   ├── errors.py                   # Exception hierarchy (6 classes)
│   ├── types.py                    # DollarDecimal, to_decimal()
│   ├── _contract_map.py            # (internal) Contract symbol mapping
│   ├── models/                     # Pydantic models (request/response DTOs)
│   │   ├── __init__.py            # Exports common, markets, orders, etc.
│   │   ├── common.py              # Page[T] generic pagination
│   │   ├── markets.py             # Market, Orderbook, OrderbookLevel, Candlestick
│   │   ├── orders.py              # Order, Fill, CreateOrderRequest
│   │   ├── events.py              # Event, EventMetadata
│   │   ├── exchange.py            # ExchangeStatus, Announcement, Schedule
│   │   ├── historical.py          # Trade, HistoricalCutoff
│   │   └── portfolio.py           # Balance, Settlement, PositionsResponse
│   ├── resources/                  # Endpoint-specific business logic
│   │   ├── __init__.py            # Exports all resources
│   │   ├── _base.py               # SyncResource + AsyncResource base
│   │   ├── markets.py             # MarketsResource + AsyncMarketsResource
│   │   ├── orders.py              # OrdersResource + AsyncOrdersResource
│   │   ├── events.py              # EventsResource + AsyncEventsResource
│   │   ├── exchange.py            # ExchangeResource + AsyncExchangeResource
│   │   ├── historical.py          # HistoricalResource + AsyncHistoricalResource
│   │   └── portfolio.py           # PortfolioResource + AsyncPortfolioResource
│   └── _generated/                # (generated from OpenAPI spec)
│       ├── __init__.py
│       └── models.py              # (reserved for future codegen)
├── tests/                          # Pytest test suite (149 tests)
│   ├── conftest.py                # Shared fixtures (test RSA keys, auth, config)
│   ├── test_auth.py               # Auth signing, key loading, env vars
│   ├── test_client.py             # Transport, retry, error mapping (sync)
│   ├── test_async_client.py       # Transport, retry, error mapping (async)
│   ├── test_markets.py            # Markets resource (sync)
│   ├── test_async_markets.py      # Markets resource (async)
│   ├── test_orders.py             # Orders resource (sync)
│   ├── test_async_orders.py       # Orders resource (async)
│   ├── test_events.py             # Events resource
│   ├── test_async_events.py       # Events resource (async)
│   ├── test_exchange.py           # Exchange resource
│   ├── test_async_exchange.py     # Exchange resource (async)
│   ├── test_historical.py         # Historical resource
│   ├── test_async_historical.py   # Historical resource (async)
│   ├── test_portfolio.py          # Portfolio resource
│   ├── test_async_portfolio.py    # Portfolio resource (async)
│   ├── test_models.py             # Decimal handling, model serialization
│   ├── test_pagination.py         # Page[T] model
│   ├── test_contracts.py          # Contract symbol mapping
│   └── __init__.py                # Marks tests as package
├── scripts/                        # Build/generation scripts
│   └── sync-openapi.sh            # OpenAPI spec sync (Kalshi → local cache)
├── specs/                          # API specifications
│   └── openapi-v3.13.0.yaml       # OpenAPI spec (cached from docs.kalshi.com)
├── pyproject.toml                 # Project metadata, dependencies, tool configs
├── uv.lock                        # Lockfile (uv package manager)
├── CLAUDE.md                      # Project instructions (SDK architecture, conventions)
├── CHANGELOG.md                   # Release history and notes
├── TODOS.md                       # Planned work (pagination utils, contract endpoints)
└── README.md                      # (empty, to be filled)
```

## Directory Purposes

**kalshi/**
- Purpose: Main package; contains all SDK code
- Contains: Client facades, models, resources, auth, config, error handling, custom types
- Key files: `__init__.py` (public API), `client.py`, `async_client.py`, `_base_client.py`

**kalshi/models/**
- Purpose: Pydantic data models for request/response serialization
- Contains: DTOs organized by API endpoint group (markets, orders, events, exchange, historical, portfolio)
- Key files: `common.py` (Page[T]), `markets.py` (Market, Orderbook, Candlestick), `orders.py` (Order, CreateOrderRequest, Fill)

**kalshi/resources/**
- Purpose: Endpoint-specific API methods; business logic layer between transport and models
- Contains: Sync + async variants for each resource group (6 resources × 2 variants = 12 classes)
- Key files: `_base.py` (SyncResource, AsyncResource base), `markets.py`, `orders.py`

**tests/**
- Purpose: Pytest test suite with 149 tests covering all public code paths
- Contains: Unit tests with respx (httpx mocking), fixtures for RSA keys/auth/config
- Patterns: respx.mock decorator, test classes per resource/feature, async_marker for async tests

**scripts/**
- Purpose: Automation for OpenAPI spec management
- Contains: Bash script to fetch latest OpenAPI spec from Kalshi docs

**specs/**
- Purpose: Cached API specifications
- Contains: OpenAPI v3.13.0 (237KB, 90+ endpoints)

## Key File Locations

**Entry Points:**
- `kalshi/__init__.py`: Public API exports (KalshiClient, AsyncKalshiClient, models, exceptions, auth config)
- `kalshi/client.py`: Synchronous client class (line 20: KalshiClient.__init__)
- `kalshi/async_client.py`: Asynchronous client class (line 20: AsyncKalshiClient.__init__)

**Configuration:**
- `kalshi/config.py`: KalshiConfig dataclass (base URL, timeout, retry settings)
- `kalshi/auth.py`: KalshiAuth class (RSA-PSS signing, key loading)

**Core Logic:**
- `kalshi/_base_client.py`: SyncTransport (lines 79-175) and AsyncTransport (lines 178-272) with retry/error mapping
- `kalshi/resources/_base.py`: SyncResource (lines 21-77) and AsyncResource (lines 80-135) base classes
- `kalshi/resources/markets.py`: MarketsResource (sync, lines 13-94) and AsyncMarketsResource (async, lines 97+)
- `kalshi/resources/orders.py`: OrdersResource (sync) and AsyncOrdersResource (async) for trading operations

**Type System:**
- `kalshi/types.py`: DollarDecimal custom type for Kalshi's FixedPointDollars format (Decimal str prices)
- `kalshi/errors.py`: Exception hierarchy (KalshiError base + 5 subclasses)

**Models:**
- `kalshi/models/markets.py`: Market (line 13), Orderbook (line 120+), Candlestick, OrderbookLevel
- `kalshi/models/orders.py`: Order, Fill, CreateOrderRequest
- `kalshi/models/common.py`: Page[T] generic pagination model

**Testing:**
- `tests/conftest.py`: Shared fixtures (test RSA keys, auth, config)
- `tests/test_markets.py`: Markets resource tests (sync)
- `tests/test_async_markets.py`: Markets resource tests (async)
- `tests/test_client.py`: Client initialization, transport, retry logic
- `tests/test_auth.py`: Auth signing, key loading validation

## Naming Conventions

**Files:**
- `*.py`: Python source files
- `client.py`: Sync client facade
- `async_client.py`: Async client facade
- `_base_client.py`: Internal base (single underscore prefix for non-public modules)
- `_base.py`: Internal base classes (single underscore prefix)
- `_contract_map.py`: Internal helper (single underscore)
- `_generated/`: Package for future OpenAPI-generated code (single underscore prefix)
- `conftest.py`: Pytest configuration and shared fixtures (tests/ root)
- `test_*.py`: Test modules (tests/ directory)

**Directories:**
- `kalshi/`: Main package (lowercase, no hyphens)
- `kalshi/models/`: Domain models
- `kalshi/resources/`: Resource classes
- `tests/`: Test root
- `scripts/`: Automation/tooling
- `specs/`: External specifications (API docs)

**Classes:**
- `KalshiClient`: PascalCase public class
- `AsyncKalshiClient`: PascalCase public class
- `KalshiAuth`: PascalCase public class
- `KalshiConfig`: PascalCase public class
- `KalshiError`: PascalCase exception base
- `KalshiValidationError`: PascalCase exception subclass
- `SyncResource`: PascalCase internal base
- `AsyncResource`: PascalCase internal base
- `MarketsResource`: PascalCase, follows resource_name + "Resource"
- `AsyncMarketsResource`: PascalCase, async variant with "Async" prefix

**Functions/Methods:**
- `list()`, `get()`, `create()`, `cancel()`: snake_case, verb-noun
- `from_key_path()`, `from_pem()`, `from_env()`: Factory methods, snake_case with "from_" prefix
- `_params()`, `_get()`, `_post()`, `_delete()`, `_list()`, `_list_all()`: Internal helpers (leading underscore)
- `sign_request()`: snake_case method
- `close()`: Context manager cleanup

**Variables/Attributes:**
- `config`, `auth`, `transport`: snake_case
- `base_url`, `timeout`, `max_retries`: snake_case with underscores
- `key_id`, `private_key`: snake_case
- `response`, `data`, `error`: snake_case

**Types:**
- `DollarDecimal`: PascalCase custom type
- `Page[T]`: PascalCase generic model
- `KalshiError`: PascalCase exception

**Constants:**
- `PRODUCTION_BASE_URL`: UPPERCASE with underscores (config.py)
- `DEMO_BASE_URL`: UPPERCASE with underscores (config.py)
- `DEFAULT_TIMEOUT`: UPPERCASE (config.py)
- `RETRYABLE_STATUS_CODES`: UPPERCASE (in _base_client.py, set literal)
- `RETRYABLE_METHODS`: UPPERCASE (in _base_client.py, set literal)

## Where to Add New Code

**New Resource (e.g., settlements):**

1. Create `kalshi/models/settlements.py` with Pydantic models:
   ```python
   from pydantic import BaseModel, Field, AliasChoices
   from kalshi.types import DollarDecimal
   
   class Settlement(BaseModel):
       id: str
       market_ticker: str
       amount: DollarDecimal = Field(
           validation_alias=AliasChoices("amount_dollars", "amount")
       )
   ```

2. Create `kalshi/resources/settlements.py` with both sync and async resource:
   ```python
   from kalshi.resources._base import SyncResource, AsyncResource, _params
   from kalshi.models.settlements import Settlement
   from kalshi.models.common import Page
   
   class SettlementsResource(SyncResource):
       def list(self, *, limit: int | None = None) -> Page[Settlement]:
           params = _params(limit=limit)
           return self._list("/settlements", Settlement, "settlements", params=params)
   
   class AsyncSettlementsResource(AsyncResource):
       async def list(self, *, limit: int | None = None) -> Page[Settlement]:
           params = _params(limit=limit)
           return await self._list("/settlements", Settlement, "settlements", params=params)
   ```

3. Export from `kalshi/models/__init__.py`:
   ```python
   from kalshi.models.settlements import Settlement
   ```

4. Export from `kalshi/__init__.py`:
   ```python
   from kalshi.models import Settlement
   __all__ = [..., "Settlement"]
   ```

5. Add to `KalshiClient.__init__()` in `kalshi/client.py`:
   ```python
   self.settlements = SettlementsResource(self._transport)
   ```

6. Add to `AsyncKalshiClient.__init__()` in `kalshi/async_client.py`:
   ```python
   self.settlements = AsyncSettlementsResource(self._transport)
   ```

7. Add tests in `tests/test_settlements.py`:
   ```python
   import pytest
   import respx
   import httpx
   from kalshi.resources.settlements import SettlementsResource
   from kalshi._base_client import SyncTransport
   from kalshi.auth import KalshiAuth
   from kalshi.config import KalshiConfig
   
   @pytest.fixture
   def settlements(test_auth: KalshiAuth, config: KalshiConfig) -> SettlementsResource:
       return SettlementsResource(SyncTransport(test_auth, config))
   
   class TestSettlementsList:
       @respx.mock
       def test_returns_page_of_settlements(self, settlements: SettlementsResource) -> None:
           respx.get("https://test.kalshi.com/trade-api/v2/settlements").mock(
               return_value=httpx.Response(200, json={"settlements": [...], "cursor": None})
           )
           page = settlements.list()
           assert len(page) > 0
   ```

**New Utility Function:**
- Location: `kalshi/types.py` (if type-related) or new `kalshi/utils.py` (if general)
- Import in `kalshi/__init__.py` if part of public API, else internal use only
- Example: `to_decimal()` helper in types.py for user convenience

**New Error Type:**
- Location: `kalshi/errors.py`
- Pattern: Inherit from `KalshiError`, add specialized attributes if needed
- Example: `class KalshiAccountError(KalshiError):` for account-specific errors

## Special Directories

**kalshi/_generated/:**
- Purpose: Reserved for OpenAPI-generated models and resources
- Current state: Empty placeholder (models.py file exists but unused)
- Generation plan: Future OpenAPI codegen pipeline (mentioned in TODOS.md)
- Committed: Yes (placeholder files checked in)
- Impact on imports: Not currently active; manual models in kalshi/models/ take precedence

**kalshi/__pycache__/, tests/__pycache__/, etc.:**
- Purpose: Python bytecode cache
- Committed: No (in .gitignore)

**.mypy_cache/, .ruff_cache/, .pytest_cache/:**
- Purpose: Tool caches (type checking, linting, testing)
- Committed: No (in .gitignore)

**.venv/:**
- Purpose: Virtual environment (uv-managed)
- Committed: No (in .gitignore)

**uv.lock:**
- Purpose: Lockfile for uv package manager (equivalent to requirements.txt lock)
- Committed: Yes (for reproducible builds)

---

*Structure analysis: 2026-04-13*
