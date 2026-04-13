# Architecture

**Analysis Date:** 2026-04-13

## Pattern Overview

**Overall:** Dual-transport facade with split sync/async resource hierarchy

**Key Characteristics:**
- Spec-first hybrid: hand-crafted client facades and models with OpenAPI generation pipeline support
- Single transport layer abstraction shared by both sync and async code (not sync-wrapping-async)
- Resource pattern: each API endpoint group has corresponding sync (`Resource`) and async (`AsyncResource`) implementations
- Type-safe price handling via custom `DollarDecimal` type for Kalshi's FixedPointDollars format
- Exponential backoff retry strategy with jitter and Retry-After header support

## Layers

**Client Facade:**
- Purpose: Entry point for users; manages dependency injection of auth, config, and transport
- Location: `kalshi/client.py` (sync), `kalshi/async_client.py` (async)
- Contains: Client classes with resource initialization, context manager support, from_env factory
- Depends on: Auth, Config, Transport, Resources
- Used by: End-user applications

**Transport Layer:**
- Purpose: HTTP request execution with authentication, retry, and error mapping
- Location: `kalshi/_base_client.py` (SyncTransport, AsyncTransport classes)
- Contains: Request building, signing, retry logic (exponential backoff + jitter), error mapping
- Depends on: Auth (for signing), Config (for retry/timeout settings), httpx
- Used by: Resource layer

**Resource Layer:**
- Purpose: Endpoint-specific business logic; wraps transport into typed API methods
- Location: `kalshi/resources/*.py` (six resource modules: markets, orders, events, exchange, historical, portfolio)
- Contains: Sync and async variants of each resource (e.g., `MarketsResource` + `AsyncMarketsResource`)
- Depends on: Transport, Models, Pagination
- Used by: Client facade

**Model Layer:**
- Purpose: Pydantic data classes; handle API response/request serialization with field mapping
- Location: `kalshi/models/*.py` (common, markets, orders, events, exchange, historical, portfolio)
- Contains: Response DTOs, request models, pagination wrapper (`Page[T]`)
- Depends on: Custom types (`DollarDecimal`)
- Used by: Resources for validation and serialization

**Infrastructure:**
- Purpose: Cross-cutting concerns (auth, config, error handling, custom types)
- Location: `kalshi/auth.py`, `kalshi/config.py`, `kalshi/errors.py`, `kalshi/types.py`
- Contains: RSA-PSS signing, timeout/retry config, exception hierarchy, decimal handling
- Depends on: cryptography, httpx, pydantic
- Used by: Transport, models, resources

## Data Flow

**Sync Request Flow:**

1. User calls method on sync resource (e.g., `client.markets.list()`)
2. Resource method builds query params via `_params()` helper (drops None values)
3. Resource calls `self._list()` or `self._get()` / `self._post()` / `self._delete()`
4. Transport.request() executes with retry loop:
   - Signs request: constructs auth headers via `auth.sign_request(method, path_only)`
   - Issues HTTP request via httpx.Client
   - On 429/502/503/504 with retryable method (GET/HEAD/OPTIONS): exponential backoff + retry
   - Maps errors to SDK exception hierarchy
5. Resource parses JSON response, validates via Pydantic models
6. Resource returns typed object (single model) or `Page[T]` (paginated)

**Async Request Flow:**

Identical to sync, except:
- AsyncTransport uses httpx.AsyncClient instead of httpx.Client
- Backoff uses `asyncio.sleep()` instead of `time.sleep()`
- Resources inherit from `AsyncResource`, methods are `async def`
- Paginated iteration returns `AsyncIterator[T]` instead of `Iterator[T]`

**Pagination:**

- List endpoints return `Page[T]`: container with `items: list[T]`, `cursor: str | None`
- `Page` is iterable over items; exposes `has_next` property and `cursor` metadata
- `list_all()` methods auto-paginate via internal loop: fetch page → yield items → update cursor → repeat until `has_next` is False
- Max pages limit is 1000 (prevents infinite loops)

**State Management:**

- Auth state: immutable after construction (RSA key loaded once at init)
- Config state: immutable dataclass (frozen=True)
- Transport state: pooled httpx client (reused across requests)
- Resource state: stateless (no caching between calls)
- No global state; per-client isolation via dependency injection

## Key Abstractions

**SyncTransport / AsyncTransport:**
- Purpose: HTTP execution with authentication and retry
- Examples: `kalshi/_base_client.py` (SyncTransport lines 79-175, AsyncTransport lines 178-272)
- Pattern: Identical request/retry/error-mapping logic duplicated for sync and async variants (not inheritance to avoid complexity)

**SyncResource / AsyncResource:**
- Purpose: Base class for all resources; shared helpers for GET/POST/DELETE and list pagination
- Examples: `kalshi/resources/_base.py` (SyncResource lines 21-77, AsyncResource lines 80-135)
- Pattern: Both classes implement `_get()`, `_post()`, `_delete()`, `_list()`, `_list_all()` with identical signatures (awaited in async variant)

**Page[T]:**
- Purpose: Generic pagination model; opaque to resources, transparent to users
- Examples: `kalshi/models/common.py`
- Pattern: Pydantic Generic[T]; iterable over items; `cursor` and `has_next` metadata exposed

**DollarDecimal:**
- Purpose: Pydantic type for Kalshi's FixedPointDollars (string prices in API responses)
- Examples: `kalshi/types.py` (lines 11-42)
- Pattern: Annotated[Decimal, BeforeValidator, PlainSerializer]; accepts str/int/float/Decimal at parse, outputs str at serialize

**KalshiAuth:**
- Purpose: RSA-PSS request signing (singleton signer per client)
- Examples: `kalshi/auth.py` (lines 28-104)
- Pattern: Immutable state (key_id + RSA private key); thread-safe signing via cryptography library

**Exception Hierarchy:**
- Purpose: Distinguish error types for caller handling
- Examples: `kalshi/errors.py`
- Pattern: Base `KalshiError` with status_code; specialized subclasses capture additional context (e.g., KalshiValidationError.details, KalshiRateLimitError.retry_after)

## Entry Points

**KalshiClient.__init__():**
- Location: `kalshi/client.py` lines 37-85
- Triggers: Manual instantiation; `from_env()` factory; context manager
- Responsibilities: Auth construction (key_id + key path/PEM, or pre-built KalshiAuth), Config construction (base_url, timeout, retries, or defaults), Transport construction, Resource instantiation

**KalshiClient.from_env():**
- Location: `kalshi/client.py` lines 87-100
- Triggers: Environment-based setup (KALSHI_KEY_ID, KALSHI_PRIVATE_KEY / KALSHI_PRIVATE_KEY_PATH, optional KALSHI_API_BASE_URL, KALSHI_DEMO)
- Responsibilities: Load auth from env, delegate to `__init__()`

**AsyncKalshiClient:**
- Location: `kalshi/async_client.py`
- Triggers: Same as KalshiClient but for async contexts
- Responsibilities: Identical to sync client, except uses AsyncTransport and AsyncResource classes

**Resource Methods (e.g., MarketsResource.list, OrdersResource.create):**
- Location: `kalshi/resources/*.py`
- Triggers: Direct call from user code (e.g., `client.markets.list()`)
- Responsibilities: Build query/body params, validate input, call transport, parse response, return typed object or Page[T]

## Error Handling

**Strategy:** Eager mapping of HTTP status codes to SDK exceptions at transport layer; resources assume success

**Patterns:**

1. **Transport-level mapping** (in `_base_client.py` `_map_error()` lines 35-70):
   - 400 → KalshiValidationError (includes field-level details if present)
   - 401/403 → KalshiAuthError
   - 404 → KalshiNotFoundError
   - 429 → KalshiRateLimitError (extracts Retry-After header)
   - 5xx → KalshiServerError
   - Other → base KalshiError

2. **Retry logic** (lines 104-171 for sync, 205-272 for async):
   - Only retryable methods (GET/HEAD/OPTIONS) on transient codes (429/502/503/504)
   - DELETE/POST never retried (idempotency risk)
   - Exponential backoff: `base_delay * 2^attempt + jitter`, capped at `retry_max_delay`
   - Retry-After header capped at `retry_max_delay` (prevents server from forcing sleep)
   - Max attempts controlled by `config.max_retries` (default 3)

3. **Caller responsibility**:
   - Catch SDK exceptions by type for specialized handling
   - Query exception attributes (status_code, details, retry_after) for context
   - No automatic retry on caller side (transport handles it)

## Cross-Cutting Concerns

**Logging:** 
- Framework: Python's standard `logging` module
- Approach: Logger named `"kalshi"` at transport layer; debug-level request/response details, warning-level retry events
- Location: `kalshi/_base_client.py` lines 28, 107-113, 134, 158-166, 208-213, 235-237

**Validation:**
- Framework: Pydantic v2
- Approach: Model validation at resource layer (after JSON parsing); field-level alias handling for API format differences
- Example: Market model uses `validation_alias=AliasChoices("yes_bid_dollars", "yes_bid")` to accept both API format and SDK short name

**Authentication:**
- Framework: RSA-PSS via cryptography library
- Approach: Sign at transport layer before every request; includes timestamp (ms) in signature
- Signing payload: `str(timestamp_ms) + METHOD + /trade-api/v2/endpoint` (path-only, no query params)
- Headers: KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE (base64), KALSHI-ACCESS-TIMESTAMP
- Location: `kalshi/auth.py` lines 93-104 (sign_request method)

---

*Architecture analysis: 2026-04-13*
