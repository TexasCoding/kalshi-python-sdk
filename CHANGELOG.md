# Changelog

All notable changes to kalshi-sdk will be documented in this file.

## [0.8.0] — 2026-04-18

### Breaking changes

- **`orders.create()` — removed phantom `type` kwarg.** The `type` field was never in the OpenAPI spec; Kalshi silently ignored it. Callers passing `type="limit"` (or `"market"` etc.) now get a `TypeError` at call time. Remove the kwarg from your call sites.
- **`orders.create()` — `buy_max_cost` type changed.** Now `int | None` representing **cents** (e.g., `buy_max_cost=500` for a $5.00 cap). Previously typed `DollarDecimal`. Spec says cents at `components.schemas.CreateOrderRequest`. Passing a `Decimal` or `float` raises `ValidationError` (via a `field_validator`). Passing a fractional string like `"5.5"` raises; integer strings like `"500"` coerce as before.
- **`orders.batch_cancel()` — signature change.** Previously: `batch_cancel(order_ids: list[str])`. Now: `batch_cancel(orders: list[BatchCancelOrdersRequestOrder] | list[str])`. Callers passing a plain list of order-id strings still work via the convenience path — each string is wrapped internally as a `BatchCancelOrdersRequestOrder`. Callers passing `order_ids=[...]` as a kwarg must rename to `orders=[...]`.
- **Wire body normalization — `count_fp` replaces `count`.** `orders.create()` and `orders.batch_create()` now emit `count_fp` (Decimal string) instead of `count` (int) on the wire, matching the convention already used by `orders.amend()`. Kalshi accepts both keys per spec; the SDK standardizes on `count_fp` for a single wire shape across methods. MITM proxy tests inspecting wire bytes need to update expectations.
- **`orders.batch_cancel()` wire field flip.** Previously SDK sent `body={"ids": [...]}` — the spec-deprecated field. Now sends `body={"orders": [{"order_id": "..."}, ...]}` — the spec-preferred field that also supports per-order subaccount routing.
- **Every POST/PUT/DELETE request body is now a Pydantic model with `extra="forbid"`.** `orders.create`, `orders.amend`, `orders.decrease`, `orders.batch_create`, `orders.batch_cancel`, `multivariate.create_market`, `multivariate.lookup_tickers` route body construction through `CreateOrderRequest`, `AmendOrderRequest`, `DecreaseOrderRequest`, `BatchCreateOrdersRequest`, `BatchCancelOrdersRequest`, `CreateMarketInMultivariateEventCollectionRequest`, `LookupTickersForMarketInMultivariateEventCollectionRequest` respectively. Existing method signatures are unchanged for all non-removed kwargs.
  - **Exception type note:** unknown kwargs on the resource METHOD raise Python's built-in `TypeError` (e.g., `orders.create(foo='bar')` → `TypeError: ... unexpected keyword argument 'foo'`). Unknown kwargs when constructing a REQUEST MODEL directly (e.g., `CreateOrderRequest(foo='bar')`) raise `pydantic.ValidationError`. The latter is NOT wrapped in the SDK's `KalshiValidationError` (which is reserved for HTTP 400 responses). If you catch `KalshiError` broadly in your wrapper code and also construct request models directly, add `pydantic.ValidationError` to your except clause.

### Added

- **7 new kwargs on `orders.create()`**: `time_in_force` (`"fill_or_kill"` / `"good_till_canceled"` / `"immediate_or_cancel"`), `post_only`, `reduce_only`, `self_trade_prevention_type`, `order_group_id`, `cancel_order_on_pause`, `subaccount`. All match spec `components.schemas.CreateOrderRequest` properties that were previously unreachable from the SDK. `subaccount` was already supported on `cancel`/`amend`/`decrease`/`list`/`fills` — this closes the inconsistency.
- **`buy_max_cost` now wired through `orders.create()`.** The field existed on the model since v0.1 but was never exposed on the method. Now accepted as an integer cents value.
- **Per-order `subaccount` routing on `orders.batch_cancel()`.** The preferred spec field (`orders: list[BatchCancelOrdersRequestOrder]`) carries optional `subaccount` per entry; the SDK now exposes this capability.
- **`TestRequestParamDrift` and `TestRequestBodyDrift`** in `tests/test_contracts.py`. Parametrized over `METHOD_ENDPOINT_MAP` entries (47 GET/DELETE + 7 POST/PUT/DELETE-with-body). Hard-fail on spec/SDK divergence not covered by the `EXCLUSIONS` allowlist. Complements the existing response-side `TestSpecDrift` (which warns rather than fails — intentional asymmetry: request drift is a user-facing capability gap).
- **`test_exclusion_map_is_current`** lint test — flags `EXCLUSIONS` entries whose claimed deviation no longer exists.
- **6 new Pydantic request models** exported from `kalshi.models` and `kalshi`: `AmendOrderRequest`, `DecreaseOrderRequest`, `BatchCreateOrdersRequest`, `BatchCancelOrdersRequest`, `BatchCancelOrdersRequestOrder`, `CreateMarketInMultivariateEventCollectionRequest`, `LookupTickersForMarketInMultivariateEventCollectionRequest`. Users can construct these directly for advanced use cases (e.g., passing `list[BatchCancelOrdersRequestOrder]` to `batch_cancel()` with per-order subaccount).

### Changed

- `CreateOrderRequest` — 7 field additions, 1 field removal (`type`), 1 type change (`buy_max_cost` → `int`). Added a `field_validator` that rejects `Decimal` and `float` inputs on `buy_max_cost` to prevent silent migration hazards.
- `MethodEndpointEntry` (test infrastructure) gains optional `request_body_schema: str | None = None`.
- `EXCLUSIONS` allowlist in `tests/_contract_support.py` — bootstrapped with 16 entries (5 model-side + 11 `cursor` paginator-handled). Task 3 appended 2 more (`AmendOrderRequest` cent-form). Task 7 scope expansion appended 1 more (`batch_cancel`'s `orders` body-param). Task 13 appended 6 more (`count` wire normalization on CreateOrderRequest + AmendOrderRequest, `reduce_by_fp`/`reduce_to_fp` deferred on DecreaseOrderRequest, deprecated `ids` on BatchCancelOrdersRequest). Total: 25.

## [0.7.0] - 2026-04-16

**Major release.** Resource method query/path parameter surface aligned to OpenAPI spec v3.13.0. 5 BREAKING changes (2 phantom kwargs removed, 3 renamed) and 32 new query params added across 6 resources.

### Added (32 new kwargs)

#### markets
- `MarketsResource.list` / `list_all`: `tickers` (`list[str] | str`, comma-joined per `TickersQuery` spec), `mve_filter`, `min_created_ts`, `max_created_ts`, `min_updated_ts`, `min_close_ts`, `max_close_ts`, `min_settled_ts`, `max_settled_ts`
- `MarketsResource.orderbook`: `depth`
- `MarketsResource.candlesticks`: `include_latest_before_start` (bool, "true or omit" rule)

#### historical
- `HistoricalResource.markets` / `markets_all`: `mve_filter`
- `HistoricalResource.fills` / `fills_all`: `max_ts`
- `HistoricalResource.orders` / `orders_all`: `max_ts`
- `HistoricalResource.trades` / `trades_all`: `min_ts`, `max_ts`

#### orders
- `OrdersResource.cancel`: `subaccount`
- `OrdersResource.list` / `list_all`: `event_ticker`, `min_ts`, `max_ts`, `subaccount`
- `OrdersResource.fills` / `fills_all`: `min_ts`, `max_ts`, `subaccount`

#### portfolio
- `PortfolioResource.balance`: `subaccount`
- `PortfolioResource.positions`: `count_filter` (filters by which numeric fields are non-zero — NOT a `settlement_status` replacement), `ticker`, `subaccount`
- `PortfolioResource.settlements` / `settlements_all`: `event_ticker`, `min_ts`, `max_ts`, `subaccount`

### Changed

- `OrdersResource.list` / `list_all` (sync + async) standardized to use `_params()` helper. **Behavior change:** empty-string values for `ticker=""`, `status=""`, AND `cursor=""` now reach the wire (previously dropped silently by truthiness check). If your code constructs the cursor via expressions like `page.cursor or ""`, you may now get a 400 from Kalshi where the previous version silently swallowed it; pass `cursor=None` (or omit) to drop the param.
- `_join_tickers()` helper lifted from `markets.py` to `_base.py` for cross-resource reuse. Now accepts list, tuple, or pre-joined string. Empty list/tuple/string returns `None` so `_params()` drops the key entirely (sending `?tickers=` has undefined server semantics). `OrdersResource.queue_positions` (sync + async) refactored to use the shared helper instead of duplicating the join logic inline.
- `_delete()` (sync + async) extended to accept optional `params=` kwarg (needed for `OrdersResource.cancel(subaccount=...)`). Backward compatible: defaults to `None`.

### BREAKING

#### REMOVE — phantom kwargs (not in spec)

- `MarketsResource.list` / `list_all`: `market_type` removed. Migration: drop the kwarg from caller code.
- `PortfolioResource.positions`: `settlement_status` removed. **NO direct replacement.** The kwarg was not a valid `/portfolio/positions` query param per spec lines 1055-1090 (only `/fcm/positions` accepts it). The spec param `count_filter` is unrelated semantically (filters by non-zero numeric fields, not by settlement state — verified spec lines 2206-2221). Migration: filter by settlement state client-side, OR use `/fcm/positions` if you are an FCM member.

#### RENAME — kwarg renamed to match spec

- `HistoricalResource.markets` / `markets_all`: `ticker` → `tickers`. Spec uses `TickersQuery` ($ref'd, type:string, comma-separated). Migration: `historical.markets(ticker="X")` → `historical.markets(tickers="X")` OR `historical.markets(tickers=["X", "Y"])`.

#### RENAME — positional arg renamed to match spec path template

- `SeriesResource.event_candlesticks(series_ticker, event_ticker, ...)` → `event_candlesticks(series_ticker, ticker, ...)`. Spec path: `/series/{series_ticker}/events/{ticker}/candlesticks` (verified `specs/openapi.yaml:1486`). Migration: positional callers (`X, Y, ...`) work unchanged. Kwarg callers (`event_ticker=...`) must switch to `ticker=...`.
- `SeriesResource.forecast_percentile_history(series_ticker, event_ticker, ...)` → `forecast_percentile_history(series_ticker, ticker, ...)`. Same migration as above.

### Tests

- 60+ new unit tests across `tests/test_orders.py`, `tests/test_async_orders.py`, `tests/test_markets.py`, `tests/test_async_markets.py`, `tests/test_historical.py`, `tests/test_portfolio.py`, `tests/test_series.py`.
- 5 BREAKING regression tests assert `TypeError` on the removed/renamed kwargs.
- 4 dedicated `tickers` comma-join serialization tests (markets + historical, sync + async).
- 2 dedicated `percentiles` `explode:true` serialization tests verify wire format `?percentiles=25&percentiles=50` (NOT comma-joined per spec line 1832).
- 4 regression tests for the `_params()` standardization on `orders.list` (empty-string `ticker` and `status` for both sync and async).
- 2 dedicated `markets.candlesticks(include_latest_before_start=True)` "true or omit" bool serialization tests.

## [0.6.1] - 2026-04-16

### Added
- Internal test infrastructure for upcoming v0.7.0 resource/spec alignment work: `tests/_contract_support.py` introduces `MethodEndpointEntry`, `METHOD_ENDPOINT_MAP` (53 sync methods across 8 resources), `_resolve_ref` with recursion cap, and `_resolve_path_params` helper that walks path-level and operation-level OpenAPI parameters with `$ref` and JSON Pointer escape (`~0`/`~1`) resolution.
- `docs/AUDIT-resource-params.md` cataloging 37 actionable rows of SDK↔spec drift: 2 phantom kwargs flagged for removal (`market_type` on `markets.list`, `settlement_status` on `portfolio.positions`), 3 breaking renames (`historical.markets.ticker` → `tickers`, series path `event_ticker` → `ticker` on 2 methods), and 32 missing params to add (subaccount, timestamp filters, `depth`, `mve_filter`, `count_filter`, etc.).
- 25 unit tests covering the new contract helpers, including reverse-completeness (every mapped path must resolve in `specs/openapi.yaml`) and tautological-pass guards.

### Changed
- No user-facing behavior changes. This is an infrastructure release preparing for v0.7.0.

## [0.5.0] - 2026-04-15

### Added
- `amend()` method on OrdersResource and AsyncOrdersResource for amending order price and/or quantity. Returns `AmendOrderResponse` with both pre and post-amendment order state.
- `decrease()` method on OrdersResource and AsyncOrdersResource for reducing order quantity by amount (`reduce_by`) or to amount (`reduce_to`)
- `queue_positions()` method for bulk queue position lookup across all resting orders, with optional `market_tickers` and `event_ticker` filters
- `queue_position()` method for single-order queue position lookup, returns `Decimal`
- `AmendOrderResponse` model containing `old_order` and `order` fields
- `OrderQueuePosition` model with `order_id`, `market_ticker`, and `queue_position` (FixedPointCount)
- Contract map entries for `AmendOrderResponse` and `OrderQueuePosition` for spec drift detection
- 29 new tests: sync/async happy paths, error paths, serialization verification, and auth guards for all 4 new methods
- Integration coverage harness registration for amend, decrease, queue_position, queue_positions

## [0.4.1] - 2026-04-15

### Added
- WS spec drift pipeline: contract tests verify all 15 WebSocket payload models against the AsyncAPI spec
- `AliasChoices` on all WS payload fields where AsyncAPI spec names differ from SDK names (26 fields across 8 model files)
- `WS_CONTRACT_MAP` with 15 entries in `_contract_map.py`, reusing the existing `ContractEntry` dataclass
- `TestWsSpecDrift` class with 5 tests: additive drift, required drift, schema coverage, contract map completeness, and envelope type drift
- Envelope type drift test that detects dispatch key mismatches between spec and SDK (found 3: `user_order` vs `user_orders`, `market_position` vs `market_positions`, `multivariate_lookup` vs `multivariate`)
- `extra = "allow"` on `OrderbookSnapshotPayload` and `OrderbookDeltaPayload` (the only two WS models missing it)
- P3 TODO for investigating WS dispatch type mismatch (spec vs SDK)

### Changed
- WS payload models now accept both spec-named fields (e.g., `yes_bid_dollars`) and SDK-named fields (e.g., `yes_bid`) via Pydantic `AliasChoices`

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
- **Breaking:** `KalshiClient()` and `AsyncKalshiClient()` no longer raise `ValueError` without credentials (they create unauthenticated clients)
- **Breaking:** `KalshiClient.from_env()` and `AsyncKalshiClient.from_env()` return unauthenticated clients when no env vars are set (previously raised `KalshiAuthError`)

### Migration
If you relied on `from_env()` raising as a startup check, use `KalshiAuth.from_env()` directly:
```python
# Before (raises at startup if no credentials):
client = KalshiClient.from_env()

# After (raises only when a private endpoint is called):
client = KalshiClient.from_env()
client.orders.list()  # AuthRequiredError here

# Migration — if you need fast-fail behavior:
from kalshi import KalshiAuth
auth = KalshiAuth.from_env()   # still raises if missing
client = KalshiClient(auth=auth)
```

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
