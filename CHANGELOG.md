# Changelog

All notable changes to kalshi-sdk will be documented in this file.

## [0.4.0] - 2026-04-14

### Added
- Unauthenticated client access for public endpoints: `KalshiClient(demo=True)` works without RSA credentials
- `KalshiAuth.try_from_env()` classmethod that returns `None` instead of raising when credentials are missing
- `AuthRequiredError` exception (extends `KalshiAuthError`) raised when unauthenticated clients call private endpoints
- `is_authenticated` property on `SyncTransport` and `AsyncTransport`
- Auth guards on all private resource methods (orders, portfolio, historical fills/orders) and `.ws` property
- Empty-string `key_id` validation in client constructors (raises `ValueError` instead of silently degrading)
- Warning log when `KALSHI_KEY_ID` is set but no private key is configured

### Changed
- `KalshiClient()` and `AsyncKalshiClient()` no longer raise `ValueError` without credentials (they create unauthenticated clients)
- `KalshiClient.from_env()` and `AsyncKalshiClient.from_env()` return unauthenticated clients when no env vars are set (previously raised `KalshiAuthError`)

## [0.3.0] - 2026-04-14

### Added
- Full WebSocket client supporting all 11 Kalshi channels: orderbook_delta, ticker, trade, fill, market_positions, user_orders, order_group_updates, market_lifecycle_v2, multivariate, multivariate_market_lifecycle, communications
- `KalshiWebSocket` client with async context manager: `async with client.ws.connect() as session`
- Per-channel typed subscribe methods (`subscribe_ticker()`, `subscribe_fill()`, etc.) for mypy strict compatibility
- Generic `subscribe(channel, **params)` for dynamic use cases
- Callback API via `@session.on("channel")` decorator, mutually exclusive per channel with async iterators
- `ws.orderbook("TICKER")` convenience yields full `Orderbook` state on every delta update
- `ConnectionManager` with 6-state machine (DISCONNECTED, CONNECTING, CONNECTED, STREAMING, RECONNECTING, CLOSED)
- Auto-reconnect with exponential backoff + jitter, configurable via `ws_max_retries` (default 10)
- RSA-PSS auth during WebSocket handshake (reuses existing `KalshiAuth`)
- `SubscriptionManager` with durable client-side subscription IDs that survive reconnection (server sids are remapped transparently)
- `update_subscription()` for adding/removing tickers from live subscriptions without re-subscribing
- `SequenceTracker` for gap detection on channels that support `seq` (orderbook_delta, order_group_updates)
- Sequence gap triggers automatic resync (re-subscribe with fresh snapshot)
- `OrderbookManager` maintains local in-memory orderbook from WS snapshots + deltas
- `MessageQueue` with configurable overflow strategies: `DROP_OLDEST` (default for ticker/trade) and `ERROR` (default for orderbook_delta)
- `FixedPointCount` Pydantic type for `_fp` suffix fields (contract counts, volumes)
- 5 new WebSocket exception classes: `KalshiWebSocketError`, `KalshiConnectionError`, `KalshiSequenceGapError`, `KalshiBackpressureError`, `KalshiSubscriptionError`
- `ws_base_url` and `ws_max_retries` fields on `KalshiConfig`
- Typed Pydantic models for all 11 channel message payloads (24 model classes total)
- Fake WebSocket test server for integration testing (simulates subscribe, broadcast, disconnect, auth rejection)
- 306 new tests (149 existing + 306 new = 455 total)

### Changed
- **BREAKING:** `Order.count`, `initial_count`, `remaining_count`, `fill_count` changed from `int` to `FixedPointCount` (Decimal). Accepts both `int` and `_fp` string formats.
- **BREAKING:** `CreateOrderRequest.count` changed from `int = 1` to `FixedPointCount = Decimal("1")`
- `websockets>=14,<17` added as a dependency

## [Unreleased]

### Added
- OpenAPI spec drift detection pipeline: contract tests compare hand-written SDK models against the Kalshi OpenAPI spec
- `kalshi/_contract_map.py`: explicit manifest mapping 15 SDK models to OpenAPI schema components
- `tests/test_contracts.py`: 32 contract tests (additive drift, required drift, schema coverage, map completeness)
- `scripts/sync_spec.py`: downloads latest OpenAPI + AsyncAPI specs with retry/backoff
- `scripts/generate.py`: local dev tool to generate reference Pydantic models via datamodel-code-generator
- `.github/workflows/spec-drift.yml`: CI workflow (PRs use pinned spec, nightly downloads fresh)
- Pinned `specs/openapi.yaml` snapshot for deterministic PR builds
- New dev dependencies: `datamodel-code-generator`, `pyyaml`
- P1 TODO: endpoint-level contract tests for resource method validation

## [0.2.0] - 2026-04-12

### Added
- Exchange resource: `client.exchange.status()`, `schedule()`, `announcements()` for checking exchange operational state
- Portfolio resource: `client.portfolio.balance()`, `positions()`, `settlements()`, `settlements_all()` for account and position management
- Events resource: `client.events.list()`, `list_all()`, `get()`, `metadata()` for browsing event containers
- Historical resource: `client.historical.cutoff()`, `markets()`, `market()`, `candlesticks()`, `fills()`, `orders()`, `trades()` plus `_all()` auto-paginators for backtesting data
- `fills_all()` auto-paginator on OrdersResource and AsyncOrdersResource
- `_params()` helper for DRY query parameter building across all resources
- New models: `Event`, `EventMetadata`, `ExchangeStatus`, `Schedule`, `Announcement`, `Balance`, `MarketPosition`, `EventPosition`, `PositionsResponse`, `Settlement`, `HistoricalCutoff`, `Trade`, `BidAskDistribution`, `PriceDistribution`
- `PositionsResponse.has_next` property for pagination consistency
- New Market fields: `market_type`, `yes_sub_title`, `no_sub_title`, `settlement_value`, `yes_bid_size`, `yes_ask_size`, `no_bid_size`, `no_ask_size`, `created_time`, `updated_time`, `latest_expiration_time`, `fractional_trading_enabled`, `settlement_timer_seconds`
- New Fill fields: `fill_id`, `market_ticker`, `fee_cost` (with `_dollars` alias)
- 72 new tests (149 to 221 total) covering all new resources, async parity, and model validation

### Changed
- **BREAKING:** `MarketsResource.list()` and `get()` now hit `/markets` endpoint (was `/events`). Response keys changed from `events`/`event` to `markets`/`market`
- **BREAKING:** `Market.volume`, `Market.volume_24h`, `Market.open_interest` changed from `int` to `DollarDecimal` (API returns FixedPointCount `_fp` strings)
- **BREAKING:** `Fill.count` changed from `int` to `DollarDecimal` (API returns `count_fp` as FixedPointCount)
- **BREAKING:** `Candlestick` model redesigned with nested `BidAskDistribution`/`PriceDistribution` objects matching the real API schema (was flat OHLC fields)
- `CreateOrderRequest` now uses `extra="forbid"` to reject unknown fields (catches typos)
- `Settlement.fee_cost` and `Fill.fee_cost` now accept `fee_cost_dollars` alias

## [0.1.2] - 2026-04-12

### Added
- Full async test coverage: 45 new tests mirroring every sync test for AsyncTransport, AsyncKalshiClient, AsyncMarketsResource, and AsyncOrdersResource
- Tests cover async retry logic (502, 429), POST/DELETE not retried, constructor branches, `from_env()`, context manager, auto-pagination, orderbook, candlesticks, batch operations, and fills

## [0.1.1] - 2026-04-12

### Fixed
- Price fields now correctly map to Kalshi API `_dollars` suffix names (e.g., `yes_bid_dollars`) via Pydantic `AliasChoices`, fixing silent `None` values on all price fields when parsing real API responses
- CreateOrderRequest now sends `yes_price_dollars`/`no_price_dollars` keys instead of `yes_price`/`no_price` (the API expects FixedPointDollars strings, not integer cents)
- Orderbook parsing now reads from `orderbook_fp.yes_dollars`/`no_dollars` (the current API response format)
- Candlestick OHLC fields now accept `open_dollars`/`close_dollars`/etc. from the API
- OrderbookLevel.quantity changed from `int` to `DollarDecimal` to support fractional contracts (FixedPointCount strings)

### Added
- 24 new tests: price format regression tests, auth percent-encoding behavior tests, KalshiClient constructor and `from_env()` coverage (80 → 104 tests)
- New Market fields: `previous_yes_bid`, `previous_yes_ask`, `previous_price`, `notional_value`
- Auth percent-encoding limitation documented in code and tests (issue #2)

### Changed
- `DollarDecimal` docstring updated to reflect FixedPointDollars format (strings with up to 6 decimal places)
- CLAUDE.md updated with price format documentation and alias conventions

## [0.1.0] - 2026-04-12

### Added
- `KalshiClient` and `AsyncKalshiClient` with sync and async support for the Kalshi prediction markets API
- RSA-PSS authentication (`KalshiAuth`) with key file, PEM string, and environment variable loading
- Markets resource: list, list_all (auto-pagination), get, orderbook, candlesticks
- Orders resource: create, get, cancel, list, batch_create, batch_cancel, fills
- `Page[T]` generic pagination model with cursor support and lazy auto-pagination iterators
- `DollarDecimal` custom Pydantic v2 type for safe bidirectional price conversion (no float intermediaries)
- Exception hierarchy: `KalshiAuthError`, `KalshiNotFoundError`, `KalshiValidationError`, `KalshiRateLimitError`, `KalshiServerError`
- Automatic retry with exponential backoff + jitter for GET requests on 429/502/503/504
- Retry-After header support with configurable max delay cap
- `KalshiConfig` with production and demo environment helpers
- stdlib logging via `logging.getLogger("kalshi")` for request/response debugging
- PEP 561 `py.typed` marker for downstream type checking
- 80 tests covering auth, transport, retry, error mapping, pagination, markets, orders, and models
- GitHub Actions CI: lint (ruff) + type check (mypy strict) + test on Python 3.12 and 3.13
- Claude Code project configuration with scoped permissions
