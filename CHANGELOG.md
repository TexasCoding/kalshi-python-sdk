# Changelog

All notable changes to kalshi-sdk will be documented in this file.

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
