# External Integrations

**Analysis Date:** 2026-04-13

## APIs & External Services

**Kalshi Prediction Markets API:**
- REST API - Primary integration for market data and order management
  - SDK/Client: `kalshi/client.py` (sync) and `kalshi/async_client.py` (async)
  - Base URL: `https://api.elections.kalshi.com/trade-api/v2`
  - Spec: `specs/openapi.yaml` (v3.13.0, 90+ endpoints)
  - Auth: RSA-PSS-SHA256 signatures (see Authentication below)

**Kalshi WebSocket API:**
- AsyncAPI - Real-time market data notifications
  - Spec: `specs/asyncapi.yaml` (v2.0.0, 11 WebSocket channels)
  - Base URL: WebSocket endpoint (typically wss://api.elections.kalshi.com)
  - Use case: Real-time market updates, subscription management
  - Note: SDK currently provides REST API client; WebSocket is available via raw httpx AsyncClient

## Resource Endpoints Covered

**Markets Resource (`kalshi/resources/markets.py`):**
- `GET /markets` - List markets (paginated)
- `GET /markets/{ticker}` - Get single market
- `GET /markets/{ticker}/orderbook` - Get orderbook snapshot
- `GET /markets/{ticker}/candlesticks` - Get OHLCV candlestick data
- Methods: `list()`, `get()`, `get_orderbook()`, `get_candlesticks()`

**Orders Resource (`kalshi/resources/orders.py`):**
- `POST /orders` - Create/place order
- `GET /orders/{order_id}` - Get order details
- `DELETE /orders/{order_id}` - Cancel order
- Methods: `create()`, `get()`, `cancel()`, `batch_cancel()`

**Portfolio Resource (`kalshi/resources/portfolio.py`):**
- `GET /portfolio/balances` - Account balance
- `GET /portfolio/orders` - Active orders
- `GET /portfolio/positions` - Holdings and positions
- `GET /portfolio/settlements` - Settlement records
- Methods: `get_balance()`, `list_orders()`, `list_positions()`, `list_settlements()`

**Historical Resource (`kalshi/resources/historical.py`):**
- `GET /historical/cutoff` - Cutoff timestamps for archived data
- `GET /historical/markets` - Archived markets
- `GET /historical/markets/{ticker}/candlesticks` - Historical candlesticks
- `GET /historical/orders` - Historical orders (canceled/executed)
- `GET /historical/fills` - Historical fills/trades
- Methods: `get_cutoff()`, `list_markets()`, `get_candlesticks()`, `list_orders()`, `list_fills()`

**Events Resource (`kalshi/resources/events.py`):**
- `GET /events` - List events
- `GET /events/{event_id}` - Get event details
- Methods: `list()`, `get()`

**Exchange Resource (`kalshi/resources/exchange.py`):**
- `GET /exchange` - Exchange status/metadata
- Methods: `get()`

## Data Storage

**Databases:**
- None - SDK is stateless, read-only (no local DB required)
- API state stored on Kalshi servers only

**File Storage:**
- Local filesystem only - Private RSA key stored as PEM files
  - Location: User-provided, commonly `~/.kalshi/key.pem`
  - Accessed via: `KalshiAuth.from_key_path()` or env var `KALSHI_PRIVATE_KEY_PATH`
  - No server-side object storage used

**Caching:**
- None - SDK does not implement client-side caching
- Retry logic provided for transient failures (429/502/503/504)

## Authentication & Identity

**Auth Provider:**
- Custom RSA-PSS-SHA256 signing (not OAuth/JWT)
  - Implementation: `kalshi/auth.py` - `KalshiAuth` class
  - Key generation: Uses Python cryptography library RSA key support
  - No external auth provider (Kalshi issues API keys directly)

**Key Requirements:**
- RSA private key (2048+ bits, PEM format)
- API Key ID (provided by Kalshi)
- Signature algorithm: RSA-PSS with SHA256 hash, MGF1(SHA256), salt_length=DIGEST_LENGTH

**Auth Headers Per Request:**
- `KALSHI-ACCESS-KEY` - API key ID
- `KALSHI-ACCESS-SIGNATURE` - base64-encoded RSA-PSS signature
- `KALSHI-ACCESS-TIMESTAMP` - Unix timestamp in milliseconds (string)

**Environment Configuration:**
- `KALSHI_KEY_ID` - Required, API key identifier
- `KALSHI_PRIVATE_KEY` - Optional, inline PEM string
- `KALSHI_PRIVATE_KEY_PATH` - Optional, path to PEM file (alternative to inline)
- One of PRIVATE_KEY or PRIVATE_KEY_PATH required, but not both

## Monitoring & Observability

**Error Tracking:**
- None built-in - SDK uses Python logging module
- Logger name: `"kalshi"` (see `kalshi/_base_client.py`)
- Applications can add handlers to logger for centralized tracking

**Logs:**
- Standard Python logging (configurable via `logging` module)
- Log level: DEBUG by default
- Contains: Request/response details, retry attempts, auth operations

**Error Handling:**
- Custom exception hierarchy in `kalshi/errors.py`:
  - `KalshiError` - Base exception
  - `KalshiValidationError` - 400 Bad Request (with `details` dict)
  - `KalshiAuthError` - 401/403 Auth failures
  - `KalshiNotFoundError` - 404 Not Found
  - `KalshiRateLimitError` - 429 Too Many Requests (includes `retry_after` header value)
  - `KalshiServerError` - 500+ Server errors

## CI/CD & Deployment

**Hosting:**
- Kalshi API is SaaS; SDK is stateless library
- No server infrastructure required for SDK itself
- SDK published to PyPI (planned/current)

**CI Pipeline:**
- GitHub Actions (inferred from `.github/` structure in repo)
- Test command: `uv run pytest tests/ -v`
- Lint: `uv run ruff check .`
- Type check: `uv run mypy kalshi/` (STRICT mode enforced in CI)
- Pre-commit hooks: mypy strict checking required before commits

## Environment Configuration

**Required env vars (at runtime):**
- `KALSHI_KEY_ID` - API key ID
- `KALSHI_PRIVATE_KEY` or `KALSHI_PRIVATE_KEY_PATH` - Private key (one required)

**Optional env vars:**
- `KALSHI_API_BASE_URL` - Override default production URL
- `KALSHI_DEMO` - Set to "true" to use demo API environment

**Secrets location:**
- `.env` files (user-managed, not committed)
- PEM key files (user-managed, commonly `~/.kalshi/`)
- Note: Never commit `.env` or `.pem` files to git

## Retry Policy

**Conditions:**
- HTTP status: 429 (Rate Limit), 502 (Bad Gateway), 503 (Service Unavailable), 504 (Gateway Timeout)
- Methods: Only GET, HEAD, OPTIONS (never POST/DELETE for safety)
- Configured in: `kalshi/config.py` via `KalshiConfig` fields

**Backoff Strategy:**
- Exponential backoff: `delay = base_delay * (2^attempt) + random(0, 0.5)`
- Default base_delay: 0.5 seconds
- Maximum delay: 30 seconds (capped)
- Retry-After header honored if present, but capped at retry_max_delay

**Configuration:**
- `max_retries` - Default 3 (configurable per client)
- `retry_base_delay` - Default 0.5 seconds
- `retry_max_delay` - Default 30 seconds
- Request timeout: Default 30 seconds (configurable)

## Webhooks & Callbacks

**Incoming:**
- None - SDK is pull-based (client queries API)
- Real-time updates available via WebSocket (AsyncAPI spec)

**Outgoing:**
- None - SDK does not send webhooks
- Users can implement polling or WebSocket subscription

---

*Integration audit: 2026-04-13*
