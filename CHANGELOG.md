# Changelog

All notable changes to kalshi-sdk will be documented in this file.

## [0.12.0] — 2026-04-19

### Fixed (post-review)

- **`include_latest_before_start` is now tri-state** — `candlesticks` and `bulk_candlesticks` (sync + async) previously mapped `False` to `None` (dropped), which meant callers explicitly opting out silently accepted whatever the server default happened to be. Now: `True → "true"`, `False → "false"`, `None → drop`. Same pattern `live_data` already uses; `_bool_param` promoted to `kalshi/resources/_base.py` as the shared helper. Two new wire-shape tests cover the `False` → `"false"` case (sync and async).
- **`_orderbook_from_item` raises on missing per-item ticker** — previously returned `Orderbook(ticker="")`, silently corrupting caller-side lookups when the server response omitted the field. Now raises `ValueError` with the offending item. Regression test added.
- **Upper-bound validation on bulk methods** — `bulk_candlesticks`, `bulk_orderbooks`, and `live_data.batch` now raise `ValueError` when passed > 100 entries (spec `maxItems`). Saves a wasted round-trip on a request the server would reject. Two new tests per resource. **Followup fix:** `bulk_candlesticks` originally only validated `list | tuple` inputs; a pre-joined comma-separated string with 150 tickers bypassed the guard. Validation now counts commas on the joined form and catches both input shapes uniformly. New test: `test_bulk_candlesticks_rejects_over_100_string`.
- **API key leak sweep moved to `tests/integration/conftest.py`** — a `scope="session", autouse=True` fixture inside `test_api_keys.py` only applies to tests collected from that module. Moved to the integration `conftest.py` so the sweep runs on every integration session regardless of which test files are selected. `API_KEY_LEAK_PREFIX` also lives in conftest now; test_api_keys.py imports it.
- **`_delete_with_retry` docstring** — said "3 attempts," but the loop iterates 4 times (`[0.0, 0.25, 0.5, 1.0]`). Docstring and module header now accurately say "4 attempts (immediate + 0.25s/0.5s/1.0s backoff)."
- **Minor** — `import time` moved to the top of `tests/integration/test_markets.py`; async `LiveDataResource.batch` / `get_typed` / `game_stats` now have docstrings matching their sync counterparts; added a comment explaining the `milestones.get()` `data.get("milestone", data)` fallback.

Followup polish (second review round):

- **`_orderbook_from_item` dict fallback is now key-presence, not truthiness** — the previous `item.get("orderbook_fp") or item.get("orderbook", {}) or {}` treated an empty-dict `"orderbook_fp": {}` as falsy and fell through to the legacy `"orderbook"` key, quietly blending two different server shapes. Now checks `"orderbook_fp" in item` first and only uses the legacy key when `orderbook_fp` is actually absent.
- **`LiveDataResource.get_typed` parameter rename** — `type` → `milestone_type` (sync + async). The former shadowed the Python built-in and bit in closures/lambdas. Value still populates the `{type}` path segment. **Breaking for pre-release callers** using the kwarg form (`live_data.get_typed(type=...)`); positional callers are unaffected. Drift test exclusions updated.
- **Async `AsyncMarketsResource.bulk_candlesticks` docstring** — sync had the spec-constraint + wire-format note; async was missing it. Added.
- **`_delete_with_retry` / `_async_delete_with_retry` last_exc sentinel** — `last_exc` was assigned only inside the `except` branch, technically unbound on an empty loop. Sentinel `RuntimeError("no delete attempts executed")` assigned pre-loop.

Followup polish (third review round):

- **`_orderbook_from_item` error wording** — `not ticker` catches both missing-key and empty-string cases. Error message now says "has empty or missing 'ticker' field" instead of "missing required 'ticker' field" to match both paths. Regression-test match string updated.
- **`MilestonesResource.list` / `list_all` `type` rename** — same built-in-shadow fix as `get_typed`: `type` → `milestone_type` (sync + async). Wire still sends `?type=...`. Drift-test EXCLUSIONS updated for both methods. Internal unit test `test_list_sends_filters` updated to use the new kwarg name.
- **`GetMilestonesResponse.milestones` now uses `NullableList[Milestone]`** — envelope-level list was a plain `list[Milestone]` while nested lists on `Milestone` itself used `NullableList`. Consistency fix: if Kalshi ever returns `{"milestones": null}` during an outage or empty result, parsing coerces to `[]` instead of raising Pydantic validation error.
- **`AsyncMarketsResource.bulk_orderbooks` docstring** — sync had the spec-constraint + wire-format note; async was missing it. Added.
- **`live_milestone` fixture exception collapse** — `except (KalshiNotFoundError, KalshiError)` had a dead first branch (`KalshiNotFoundError` is a subclass of `KalshiError`). Collapsed to `except KalshiError` with a comment explaining both paths are caught.

### Added

- **API Keys resource** — `ApiKeysResource` + `AsyncApiKeysResource` covering all 4 `/api_keys` endpoints for programmatic credential management:
  - `GET /api_keys` — list keys registered on the account
  - `POST /api_keys` — register a caller-minted RSA public key
  - `POST /api_keys/generate` — have Kalshi mint a fresh key pair; private key is returned ONCE and cannot be retrieved again
  - `DELETE /api_keys/{api_key}` — remove a key
- **Bulk / batch market endpoints** on `MarketsResource` — three multi-ticker read paths:
  - `list_trades` + `list_trades_all` — `GET /markets/trades` (paginated Trade listing across all markets; reuses the existing `historical.Trade` model since the schema is shared)
  - `bulk_candlesticks` — `GET /markets/candlesticks` (up to 100 tickers per call, comma-joined on wire per spec `type: string`)
  - `bulk_orderbooks` — `GET /markets/orderbooks` (auth-required; `tickers` serialized as repeated params per spec `style: form, explode: true`)
- **Milestones resource** — `MilestonesResource` + `AsyncMilestonesResource`:
  - `GET /milestones` — paginated listing with filters for category, competition, type, related_event_ticker, source_id, minimum_start_date (RFC3339), min_updated_ts (Unix seconds). `limit` is required (1-500) per spec
  - `GET /milestones/{milestone_id}` — single milestone lookup
  - `list_all` paginator helper
- **Live Data resource** — `LiveDataResource` + `AsyncLiveDataResource` covering 4 endpoints keyed by `milestone_id`:
  - `get` — `GET /live_data/milestone/{milestone_id}` (preferred shape)
  - `get_typed` — `GET /live_data/{type}/milestone/{milestone_id}` (legacy shape, retained for spec-completeness; docstring recommends `get`)
  - `batch` — `GET /live_data/batch` (up to 100 milestone_ids; wire format `?milestone_ids=a&milestone_ids=b` via httpx list-explosion)
  - `game_stats` — `GET /live_data/milestone/{milestone_id}/game_stats` (returns `pbp: None` for unsupported milestone types without a Sportradar ID)
- **11 new Pydantic models** — `ApiKey` + 5 API-key request/response envelopes; `Milestone` + 2 response envelopes; `LiveData`, `PlayByPlay`, `PlayByPlayPeriod`, and 3 live-data response envelopes; `MarketCandlesticks` (per-market bundle in the bulk candlesticks response). Request models use `extra="forbid"`; response models use `extra="allow"`. Milestone `details` and LiveData `details` are `dict[str, Any]` per spec `additionalProperties: true` (shape varies by milestone type).
- **82 new unit tests** — 25 for API Keys, 12 for Milestones, 16 for LiveData, 7 for bulk markets, 2 client-wiring additions. Plus real-lifecycle integration coverage: API Keys mints a throwaway RSA keypair in-test and runs `create → list → delete` on demo with try/finally cleanup; bulk methods + Milestones + LiveData all exercise against demo inventory.

### Changed

- **Test coverage** — FULL-covered endpoints 44 → 57 (64%). Meta-coverage test now expects 14 resource classes (was 11). Three new resources (`ApiKeysResource`, `MilestonesResource`, `LiveDataResource`) + 4 new methods on `MarketsResource` registered in `METHOD_ENDPOINT_MAP` (13 new entries), `BODY_MODEL_MAP` (2 new request-body entries for `CreateApiKeyRequest`/`GenerateApiKeyRequest`), `_contract_map.py` (8 new response-side entries), `coverage_harness.RESOURCE_MODULES` (3 new modules), and `test_coverage.py` import list.
- **EXCLUSIONS expanded** — 2 new `cursor` paginator entries for `MarketsResource.list_trades_all` and `MilestonesResource.list_all` (paginator-handled; not caller-facing).
- **Live-demo finding documented in the integration suite:** `GET /milestones?category=Sports` returns milestones with `category="sports"` (lowercase) in the response body even though the filter accepted the title-cased input and the spec example shows `"Sports"`. `test_list_with_category` asserts case-insensitively so future server-side case fixes don't regress.

## [0.11.0] — 2026-04-18

### Added

- **Communications / RFQ resource** — `CommunicationsResource` + `AsyncCommunicationsResource` covering all 11 endpoints of the RFQ + Quote subsystem (OTC market access):
  - `GET /communications/id` — caller's public communications ID
  - `GET /communications/rfqs`, `POST /communications/rfqs`, `GET /communications/rfqs/{rfq_id}`, `DELETE /communications/rfqs/{rfq_id}` — RFQ lifecycle (plus `list_all_rfqs` paginator)
  - `GET /communications/quotes`, `POST /communications/quotes`, `GET /communications/quotes/{quote_id}`, `DELETE /communications/quotes/{quote_id}` — Quote lifecycle (plus `list_all_quotes` paginator)
  - `PUT /communications/quotes/{quote_id}/accept`, `PUT /communications/quotes/{quote_id}/confirm` — two-party workflow
- **Subaccounts resource** — `SubaccountsResource` + `AsyncSubaccountsResource` covering all 6 endpoints for multi-account workflows:
  - `POST /portfolio/subaccounts` — spin up the next numbered subaccount (empty body; demo requires explicit `Content-Type: application/json`, SDK sends `json={}` to force it)
  - `POST /portfolio/subaccounts/transfer` — move cents between subaccounts with client-side idempotency ID
  - `GET /portfolio/subaccounts/balances`, `GET /portfolio/subaccounts/transfers` (+ `list_all_transfers`) — read state
  - `PUT /portfolio/subaccounts/netting`, `GET /portfolio/subaccounts/netting` — netting configuration
- **New Pydantic models** — 13 for Communications (`RFQ`, `Quote`, `MveSelectedLeg`, 5 response envelopes, 3 request models, 2 id wrappers) + 8 for Subaccounts (`SubaccountBalance`, `SubaccountTransfer`, `SubaccountNettingConfig`, 3 response envelopes, 2 request models). Request models use `extra="forbid"` so phantom keys fail at construction time; response models use `extra="allow"`.
- **`integration_real_api_only` pytest marker** — new marker for endpoints the demo server cannot service (auth-gated role requirements, demo-broken routes). The `pytest_collection_modifyitems` hook in `tests/integration/conftest.py` auto-skips these tests unless `KALSHI_ENABLE_REAL_API_ONLY=1` is set. Applied to 4 tests spanning Communications (`list_quotes_unfiltered`, `list_all_quotes`, `list_quotes_by_rfq`, `accept_and_confirm_quote`) + Subaccounts (`get_netting` — demo returns 500).
- **103 new tests** — 64 unit tests for Communications (`tests/test_communications.py`: model aliases, request wire-shape, happy/error paths per method, async, auth guards, client wiring) + 39 unit tests for Subaccounts (`tests/test_subaccounts.py`: same matrix). Plus 16 integration tests for Communications + 14 for Subaccounts against the demo server.

### Changed

- **Test coverage** — FULL-covered endpoints 31 → 44 (52%); partial coverage (SDK + unit, no integration) expanded across the v0.11.0 scope. Meta-coverage test now expects 11 resource classes (was 9). `CommunicationsResource` and `SubaccountsResource` both registered in `METHOD_ENDPOINT_MAP` (20 new entries), `BODY_MODEL_MAP` (5 new request-body entries), `_contract_map.py` (10 new response-side entries), and `coverage_harness.RESOURCE_MODULES`.
- **EXCLUSIONS expanded** — 3 new entries covering `CreateRFQRequest.contracts_fp` (integer form only, matching the `count_fp` precedent), `CreateRFQRequest.target_cost_centi_cents` (deprecated in spec), and the `cursor` paginator kwargs on the 3 new `list_all_*` methods (2 communications + 1 subaccounts).
- **Live-demo findings refined the v0.11.0 audit:**
  - `GET /communications/quotes` requires `creator_user_id` OR `rfq_creator_user_id` even when `rfq_id` is provided — demo returns `400 "Either creator_user_id or rfq_creator_user_id must be filled"`. Supersedes the audit's "403 unless filtered by rfq_id" note; all `list_quotes` variants are `integration_real_api_only`.
  - Demo rejects malformed IDs with `400 invalid_parameters` before the route-level 404 lookup, so the 404 regression tests assert the base `KalshiError` class to tolerate either shape.
  - Demo refuses self-quoting (RFQ creator responding to their own RFQ) with `400` — `test_quote_lifecycle` skips with a descriptive reason rather than failing, so a future demo-server change surfaces organically.

### Fixed

- **`_put()` now handles 204 No Content.** `SyncResource._put` / `AsyncResource._put` previously called `response.json()` unconditionally and raised `JSONDecodeError` on empty-body responses. Mirrors the `_delete()` pattern — returns `None` on 204. Required by the new `accept_quote` / `confirm_quote` endpoints, which return `204` on success per spec. Closes the P3 reliability item flagged on PR #33.

## [0.10.0] — 2026-04-18

### Added

- **Order Groups resource** — `OrderGroupsResource` + `AsyncOrderGroupsResource` covering 7 endpoints for rolling 15-second contracts-limit groups (OCO/if-then strategies):
  - `GET /portfolio/order_groups` — list groups on the account (plain `list[OrderGroup]`, no pagination)
  - `GET /portfolio/order_groups/{order_group_id}` — full group including member order IDs
  - `POST /portfolio/order_groups/create` — create a new group with `contracts_limit: int`
  - `DELETE /portfolio/order_groups/{order_group_id}` — cancel all member orders and delete the group
  - `PUT /portfolio/order_groups/{order_group_id}/reset` — reset the matched-contracts counter
  - `PUT /portfolio/order_groups/{order_group_id}/trigger` — cancel all member orders, block new ones until reset
  - `PUT /portfolio/order_groups/{order_group_id}/limit` — update the rolling-15s limit (no `subaccount` kwarg — spec explicitly omits the query param on this endpoint)
- **5 new Pydantic models** — `OrderGroup`, `GetOrderGroupResponse`, `CreateOrderGroupResponse` (responses with `extra="allow"`), `CreateOrderGroupRequest`, `UpdateOrderGroupLimitRequest` (request models with `extra="forbid"`). `GetOrderGroupResponse.orders` uses `NullableList[str]` to handle Kalshi's intermittent `null`-vs-array responses on spec-required list fields.
- **9 integration tests** against the demo server — 5 sync + 4 async, exercising create → get → update_limit → reset → trigger → delete flow with `ephemeral_group` try/finally cleanup fixture. Demo probing during the audit surfaced two real SDK bugs that were fixed before ship: (1) `reset`/`trigger` PUT requests were missing `Content-Type: application/json` because httpx omits the header when no body is passed; (2) async `create → get` needed a 0.5s sleep for demo eventual consistency (matches the existing `test_orders.py` pattern).
- **41 new unit tests** (`tests/test_order_groups.py`) — wire-shape coverage across all 7 methods sync + async, 5 response-model alias tests, 6 request-model serialization/validation tests, 7 auth-guard regression tests, 2 client-wiring tests. Unit tests explicitly assert `request.content == b"{}"` on `reset`/`trigger` to lock in the httpx `Content-Type` fix.
- **Path B demo-feasibility audit** — new reusable script `scripts/audit_demo_feasibility.py` that probes every spec endpoint not yet in `METHOD_ENDPOINT_MAP` against demo and classifies each as `demo-supported` / `demo-501` / `auth-gated` / `demo-broken`. The audit informed the corrected v0.10-v0.13 scope in TODOS.md (path corrections: `POST /create`, `PUT` for reset/trigger/limit; API Keys is 4 endpoints not 5; RFQ quotes list is auth-gated on demo; subaccounts/netting GET is demo-broken with a 500).

### Changed

- **Test coverage** — FULL-covered endpoints 24 → 31 (35%), not-implemented 53 → 46 (52%). Meta-coverage test now expects 9 resource classes (was 8). New `OrderGroupsResource` registered in `METHOD_ENDPOINT_MAP` (7 entries), `BODY_MODEL_MAP` (2 entries for request bodies), and the integration coverage harness.
- **EXCLUSIONS expanded** — 2 new entries for `contracts_limit_fp` on both order-group request models. The SDK commits to the integer `contracts_limit` wire form (same precedent as `count_fp` on order requests); the string FixedPointCount variant is deliberately absent from the SDK surface.
- **TODOS.md drift corrections** — v0.11 Communications/RFQ block now lists all 11 endpoints with per-endpoint demo classification; `POST /portfolio/subaccounts` documented as returning 201 on empty body (audit probe created subaccount #1 with \$0 on demo — integration tests will need a cleanup fixture); API Keys v0.12 count corrected from 5 to 4.

### Fixed

- **Version drift** — `pyproject.toml` bumped from 0.9.1 to 0.10.0 to track `kalshi/__init__.py`. The 0.9.1 release shipped with the same drift; this release fixes both together.

## [0.9.1] — 2026-04-18

### Added

- **`NullableList[T]`** — new reusable Pydantic type alias in `kalshi.types` for response-model list fields that the live API may return as JSON null. Applied across 24 list-default fields in response models (events, exchange, markets, multivariate, portfolio, series). Replaces a one-off `field_validator` pattern with a systematic opt-in: any new response field that could be null from the server uses `NullableList[X] = []` instead of `list[X] = []`.
- **Integration test coverage for Series + Multivariate Collections resources (v0.9.0 scope).** 11 previously-unregistered methods now have real tests against the Kalshi demo server:
  - `SeriesResource`: `list`, `get`, `fee_changes`, `event_candlesticks`, `forecast_percentile_history`
  - `MultivariateCollectionsResource`: `list`, `list_all`, `get`, `create_market`, `lookup_tickers`, `lookup_history`
  - `EventsResource`: `list_multivariate`, `list_all_multivariate`
- **Meta-coverage test** (`tests/integration/test_coverage.py`) now discovers all 8 resource classes (was 6) and fails on any public method that lacks an integration scenario. FULL-covered endpoints: 13 → 24.
- **`NullableList` regression tests** — 7 new unit tests in `tests/test_series_models.py` covering null coercion on Series (`tags`, `settlement_sources`, `additional_prohibitions`), `EventCandlesticks` (`market_tickers`, `market_candlesticks`), and `ForecastPercentilesPoint` (`percentile_points`).
- **Annotation-aware assertion oracle tests** — 6 new tests in `tests/integration/test_assertions.py` pinning `_annotation_contains` semantics across bare types, `Optional`, PEP 604 unions, `list[T]`, and `None` annotations. Plus 2 positive tests confirming float-annotated fields no longer misfire the DollarDecimal check.

### Changed

- **Semantic oracle** (`tests/integration/assertions.py`) is now annotation-aware. The oracle previously rejected *any* float value on a Pydantic model as "DollarDecimal parsing failed", which misfired on legitimately-typed fields like `Series.fee_multiplier: float` (spec type `number/double`). It now only flags floats where the field's type annotation actually resolves to `Decimal`, via a new `_annotation_contains()` helper that walks `__args__` through `Optional`, `Union`, `Annotated`, and generic aliases.
- **`tests/integration/test_multivariate.py`** — tightened except clauses on `test_create_market` and `test_lookup_tickers` (sync + async). Previously caught `KalshiServerError` as `pytest.skip`, which masked real SDK regressions (body serialization, PUT/POST auth) as demo flakiness. Now only swallows `KalshiValidationError` and `KalshiNotFoundError`; 5xx fails loud so the integration suite actually serves its north-star purpose of surfacing real SDK issues.

### Fixed

- **Stale `__version__`** in `kalshi/__init__.py` (was `0.7.0`, now `0.9.1`). `pyproject.toml` was bumped to `0.8.0` in the previous release without updating the package `__version__`. Both now track together.
- **`TODOS.md`** restructured around the north-star goal: 100% endpoint coverage (SDK + unit + integration test for every REST operation and WebSocket channel). New phased roadmap v0.9 → v0.13. `BACKLOG.md` added as the parking lot for valuable-but-off-path items.

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
