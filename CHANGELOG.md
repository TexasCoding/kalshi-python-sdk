# Changelog

All notable changes to kalshi-sdk will be documented in this file.

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
