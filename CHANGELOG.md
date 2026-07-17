# Changelog

All notable changes to kalshi-sdk will be documented in this file.

## 7.1.0 — 2026-07-17

Syncs the upstream OpenAPI/AsyncAPI specs **3.24.0 → 3.25.0** (Closes #475).
Additive only — no breaking public-API changes.

### Added

- **`MarginMarket.schedule`** (perps) — required field on margin market responses.
  Typed as `MarginMarketSchedule | None` (null for markets that trade 24/7).
  Nested `MarginMarketSchedule` exposes `is_open: bool` and
  `next_close_ts` / `next_open_ts` (`int | None`, Unix epoch seconds; null
  while the corresponding phase is active). Exported from `kalshi.perps` and
  `kalshi.perps.models`.

### Spec notes

- Core OpenAPI gained `POST /portfolio/intra_exchange_instance_transfer`
  (same path/schema as the perps transfer). The endpoint is still marked
  **currently not available** upstream; the core client records it in
  `_UNIMPLEMENTED_ENDPOINTS`. Use
  `PerpsClient.transfers.transfer_instance()` for the margin product surface.

## 7.0.0 — 2026-07-10

Syncs the upstream OpenAPI/AsyncAPI specs **3.23.0 → 3.24.0** (Closes #467, #470).
One **breaking** rename on the subaccounts surface, a soft-deprecation, three new
endpoints, and additive drift fixes. Kalshi changed spec content without always
bumping `info.version`, so this also absorbs in-place edits made under the same string.

### Changed (breaking)

- **Position-transfer price is now fixed-point dollars, not integer cents.** The
  `price_cents` field/kwarg (integer cents, 0-100) on
  `ApplySubaccountPositionTransferRequest`, `SubaccountTransfer`, and
  `subaccounts.transfer_position()` (sync + async) is renamed **`price`** and
  typed `OrderPrice` / `DollarDecimal` (fixed-point dollars, `Decimal`). Pass
  `price=Decimal("0.50")` where you previously passed `price_cents=50`. The old
  client-side cap (`le=100` cents) is gone — `OrderPrice` guards only
  non-negativity and the `$0.0001` tick, leaving the upper bound to the server
  (matches `CreateOrderRequest`). Upstream renamed the wire field `price_cents`
  → `price` (`FixedPointDollars`) in 3.24.0.

### Deprecated

- **`exchange.announcements()`** (sync + async) now emits a `DeprecationWarning`.
  Kalshi removed `GET /exchange/announcements` and the `Announcement` schema from
  the spec in 3.24.0, so the live endpoint 404s. The method and the `Announcement`
  model are **retained** (soft-deprecated) pending confirmation the removal is
  permanent — upstream has transiently dropped endpoints as publishing glitches
  before (see #452). A future major release removes them once confirmed.

### Added

- **`communications.quotes.get_for_rfq(rfq_id, quote_id)`** (sync + async) —
  `GET /communications/rfqs/{rfq_id}/quotes/{quote_id}`, the RFQ-scoped
  get-a-quote (returns `GetQuoteResponse`, the same payload as the flat
  `quotes.get`).
- **`klear.margin.active_obligations()`** (sync + async) —
  `GET /margin/active_obligations`, all currently-active settlement obligations
  (`GetActiveMarginObligationsResponse`; the plural sibling of the single-obligation
  `active_obligation()`).
- **`klear.margin.settlement_estimate_by_asset_class()`** (sync + async) —
  `GET /margin/settlement_estimate_by_asset_class`, next-settlement estimates keyed
  by asset class (`GetSettlementEstimateByAssetClassResponse` +
  `AssetClassSettlementEstimate`).
- **`SubaccountNettingConfig.exchange_index`** (`int`, required) — exchange index
  of the subaccount.
- **`portfolio.balance()`** (sync + async) gains an optional **`exchange_index`**
  query param — target a specific exchange shard (defaults to 0 server-side).
- **`ObligationEntry.asset_class`** (perps SCM / Klear; `AssetClassLiteral` =
  `Literal["Crypto"]`, required) — asset class of the settlement obligation.

## 6.0.0 — 2026-07-04

Syncs the upstream OpenAPI/AsyncAPI specs **3.22.0 → 3.23.0** (#463). The
headline change is **breaking**: Kalshi removed the multivariate lookup-history
endpoint from the spec, so the SDK removes the corresponding method and model.
Every other change is additive and backward-compatible.

### Removed (breaking)

- **`lookup_history()`** on `client.multivariate_collections` (sync + async) and
  the **`LookupPoint`** model (no longer exported from `kalshi` /
  `kalshi.models`). Upstream removed the backing `GET
  /multivariate_event_collections/{collection_ticker}/lookup` operation
  (`GetMultivariateEventCollectionLookupHistory`) and the `LookupPoint` schema in
  3.23.0 — the endpoint now 404s. The `lookup_tickers()` sibling (the `PUT` on the
  same path) is unaffected.

### Added

- **`ApiKey.subaccount`**, **`CreateApiKeyRequest.subaccount`**,
  **`GenerateApiKeyRequest.subaccount`** (`int | None`) — when set, restricts the
  API key to a single subaccount. `api_keys.create()` / `generate()` (sync +
  async) accept a `subaccount` kwarg that threads into the body. The request
  models bound it to the spec's `0-63` range (`ge=0, le=63`) client-side; the
  response model stays permissive.
- **`ApplySubaccountTransferRequest.exchange_index`** (`int | None`) — exchange
  shard to apply the transfer on (spec `ExchangeIndex`; defaults to 0).
- **`SubaccountTransfer`** additive fields: `exchange_index` and `transfer_type`
  (`"cash"`/`"position"`, both required), plus the position-transfer-only
  `market_ticker` / `side` (`"yes"`/`"no"`) / `count` / `price_cents`.
- **`MarginPosition.is_portfolio`** and **`MarginRiskPosition.is_portfolio`**
  (`bool`, required) — true when the position is hedged within a portfolio.
- **`MarginOrder.order_reason`** (`"liquidation"`/`"take_profit_stop_loss"`,
  optional) — reason for a system-generated order.
- **`MarketLifecyclePayload.price_ranges`** (WS `market_lifecycle_v2`) — valid
  price bands emitted alongside `price_level_structure`.
- **`subaccounts.transfer_position(...)`** (sync + async) — new
  `POST /portfolio/subaccounts/positions/transfer` endpoint (spec 3.23.0): moves
  an open **position** (contracts) between subaccounts, distinct from the
  cash-only `transfer()`. Returns `ApplySubaccountPositionTransferResponse`
  (`position_transfer_id`). New models `ApplySubaccountPositionTransferRequest` /
  `ApplySubaccountPositionTransferResponse` are exported from `kalshi` /
  `kalshi.models`.
- **`subaccounts.create(exchange_index=...)`** — `POST /portfolio/subaccounts`
  gained an optional `CreateSubaccountRequest` body (spec 3.23.0); `create()`
  now accepts an optional `exchange_index` to target a specific exchange shard.
  New `CreateSubaccountRequest` model exported from `kalshi` / `kalshi.models`.

### Fixed

- **Defensive optional-ization of fields 3.23.0 removed/relaxed.** The drift
  suite is spec→SDK only, so a field the spec drops but the SDK still *requires*
  is a latent `ValidationError` if the server stops emitting it. Three such
  fields are now `... | None = None`:
  - `Market.fractional_trading_enabled` (removed from spec),
  - `MarketPosition.resting_orders_count` (removed from spec),
  - `MarginPosition.margin_used` (relaxed from required to optional).

## 5.0.1 — 2026-06-27

Spec-drift catch-up (#460). Kalshi added fields to the `ExchangeStatus` schema
in place — without bumping the OpenAPI `version` (still 3.22.0) — so the
nightly strict contract suite flagged additive drift the day after the 5.0.0
sync. All changes are additive and backward-compatible.

### Fixed

- **`ExchangeStatus` additive drift.** Added two optional fields that upstream
  introduced on `GET /exchange/status`:
  - `intra_exchange_transfers_active: bool | None` — whether intra-exchange
    transfers are currently permitted (omitted by older servers, hence optional).
  - `exchange_index_statuses: list[ExchangeIndexStatus]` — per-index (shard)
    status breakdown; defaults to `[]` when absent or null.

### Added

- **`ExchangeIndexStatus`** model (exported from `kalshi` and `kalshi.models`):
  per-exchange-index operational status with `exchange_index`, `exchange_active`,
  `trading_active`, and `intra_exchange_transfers_active`.

## 5.0.0 — 2026-06-26

Syncs the upstream OpenAPI spec **3.21.0 → 3.22.0** (#454, #458). The headline
change is **breaking**: Kalshi removed the V1 order-write endpoints from the
spec, so the SDK removes the V1 order methods and their models. Order writes now
go exclusively through the V2 `/portfolio/events/orders` family (the `*_v2`
methods, which have existed since 3.18.0). See `docs/migration.md` for the
V1 → V2 mapping.

### Removed (breaking)

- **V1 order-write methods** on `client.orders` (sync + async): `create`,
  `cancel`, `batch_create`, `batch_cancel`, `amend`, `decrease`. The underlying
  endpoints (`POST/DELETE /portfolio/orders`, `/portfolio/orders/batched`,
  `/portfolio/orders/{id}/amend`, `/portfolio/orders/{id}/decrease`) were
  removed from the spec in 3.22.0. Use the `*_v2` equivalents instead.
- **V1 order models** (no longer exported from `kalshi` / `kalshi.models`):
  `CreateOrderRequest`, `AmendOrderRequest`, `AmendOrderResponse`,
  `DecreaseOrderRequest`, `BatchCreateOrdersRequest`, `BatchCreateOrdersResponse`,
  `BatchCreateOrdersResponseEntry`, `BatchCancelOrdersRequest`,
  `BatchCancelOrdersResponse`, `BatchCancelOrdersResponseEntry`,
  `BatchCancelOrdersRequestOrder`, and the `ActionLiteral` (`buy`/`sell`) alias.
- **Dead quote filters** — `event_ticker` and `market_ticker` were removed from
  `GET /communications/quotes` upstream, so they are removed from
  `client.communications.quotes.list` / `list_all` and the
  `communications.list_quotes` / `list_all_quotes` facade methods.

### Added

- **RFQ-scoped quote actions** (spec 3.22.0) on `client.communications.quotes`
  (sync + async): `accept_for_rfq(rfq_id, quote_id, ...)`,
  `confirm_for_rfq(rfq_id, quote_id)`, `delete_for_rfq(rfq_id, quote_id)` —
  backing `PUT/DELETE /communications/rfqs/{rfq_id}/quotes/{quote_id}[/accept|/confirm]`.
- **`cancel_v2` `market_ticker` query param** — required when `exchange_index`
  is `-1` (auto-route by ticker).
- **`BatchCancelOrdersV2RequestOrder.market_ticker`** — same auto-route semantics
  for batch V2 cancels.
- **`SubaccountBalance.exchange_index`** — the exchange shard a balance is held on.
- **Perps SCM** (`kalshi.perps.klear`): new `MarketSettlementEstimate` model;
  `SettlementEstimate.positions` (per-market breakdown map); and
  `GetSettlementEstimateResponse.prev_settlement_prices` (market → last
  settlement price, centicents).

## 4.2.0 — 2026-06-19

Reconciles in-place upstream spec drift detected by the nightly run (#451):
the live OpenAPI/AsyncAPI specs gained fields after 4.1.0 vendored them, under
the same `3.21.0` version string. All changes are additive — new response
fields on existing models. Also widens the `cryptography` dependency ceiling.

### Added

- **`Event.settlement_sources`** — the official settlement sources for an event
  (`EventData.settlement_sources`, openapi 3.21.0). Typed
  `NullableList[SettlementSource]`, so a JSON `null` coerces to `[]` while the
  key-present contract holds (same nullable shape as `Series.settlement_sources`).
  Note: spec-**required**, so code that constructs `Event` directly (e.g. test
  mocks) must now include it.
- **WS `MarketLifecyclePayload` strike fields** — `strike_type`, `cap_strike`,
  and `custom_strike` on `market_lifecycle_v2` payloads (asyncapi). All optional;
  present only on `metadata_updated` frames. `strike_type` (`between` / `greater`
  / `less`) controls how `floor_strike` / `cap_strike` are interpreted;
  `custom_strike` carries structured strikes.

### Changed

- **`cryptography` dependency ceiling widened `<49` → `<50`** (#448) — permits
  cryptography 49.x. The SDK's RSA-PSS signing path uses only `hashes` /
  `serialization` / `padding` / `rsa`, none of which 49.0.0's removals affect.
- Re-vendored `specs/openapi.yaml` (added `EventData.settlement_sources`) and
  `specs/asyncapi.yaml` (added the lifecycle strike fields; refreshed WS
  error-code docs). `openapi.yaml` was held at its known-good 104-operation
  state: the upstream publish transiently dropped `CreateOrder` /
  `BatchCreateOrders` / `AmendOrder`, an upstream glitch that was not imported.

## 4.1.0 — 2026-06-14

Spec sync from upstream OpenAPI v3.20.0 → v3.21.0 (plus AsyncAPI/perps). All
changes are additive — new query params, response fields, and four new
endpoints. Also closes the nightly spec-drift CI gap (failures now open a
tracking issue).

### Added

- **`client.communications.block_trade_proposals`** — new sub-resource for the
  block-trade-proposals API (openapi 3.21.0): `list()` / `list_all()`
  (`GET /communications/block-trade-proposals`), `create()`
  (`POST /communications/block-trade-proposals`), and `accept()`
  (`POST /communications/block-trade-proposals/{id}/accept`). New models
  `BlockTradeProposal` / `GetBlockTradeProposalsResponse` /
  `ProposeBlockTradeRequest` / `ProposeBlockTradeResponse` /
  `AcceptBlockTradeProposalRequest` (exported from `kalshi`).
- **`AccountResource.volume_progress()`** — `GET /account/api_usage_level/volume_progress`
  returns trailing-30-day trading-volume progress toward volume-based API usage
  tiers. New models `AccountVolumeProgress` / `AccountApiUsageLevelVolumeProgress`
  / `AccountApiUsageLevelVolumeGoal`.
- **`events.list` / `list_all` gain a `tickers` filter** — comma-separated event
  tickers (`GET /events?tickers=...`).
- **`communications` quotes endpoints gain `min_ts` / `max_ts`** — filter quotes
  by last-updated Unix timestamp on `quotes.list` / `list_all` (and the
  deprecated `list_quotes` / `list_all_quotes` forwarders).
- **Perps `MarginMarket` mark-price fields** — `settlement_mark_price`,
  `liquidation_mark_price`, and `reference_price` (each a nested `TickerPrice`
  of `{price, ts_ms}`); **`MarginPosition.subaccount`** (the holding subaccount
  number); and **WS `ErrorPayload.market_tickers`** (multi-market error frames).
  Note: `MarginPosition.subaccount` is spec-**required**, so code that constructs
  `MarginPosition` directly (e.g. test mocks) must now include it.

### Changed

- Re-vendored `specs/openapi.yaml` (3.20.0 → 3.21.0), `specs/asyncapi.yaml`,
  `specs/perps_openapi.yaml`, and `specs/perps_scm_openapi.yaml`.
- **Upstream narrowed the `Settlement.market_result` enum** — `void` was removed
  (now `yes` / `no` / `scalar`). No SDK change: `Settlement.market_result` is a
  plain `str` with `extra="allow"`, so any value still parses; noted here for
  accuracy.
- **Nightly spec-drift CI now files a tracking issue on failure.** The scheduled
  `Spec Drift Detection` run previously failed silently between the weekly
  `Weekly Spec Sync` runs; it now opens (and dedups) a single `spec-drift` issue
  so upstream drift is tracked the day it appears.

### Fixed

- Hardened the `TestWsSpecDrift` contract-test fixture (the class-scoped fixture
  is now a `@staticmethod`) so the strict nightly run reports real WebSocket
  drift instead of erroring the whole class under `-W error::UserWarning`.

## 4.0.0 — 2026-06-09

Spec-drift reconciliation against the latest upstream OpenAPI (3.20.0) and AsyncAPI
specs (closes #443). Includes one **breaking** change: the Self-Clearing-Member
"Klear" API migrated from cookie-session login to Bearer-token auth. Everything
else is additive.

### Breaking

- **Klear (SCM) auth is now a Bearer token.** Upstream removed `POST /log_in` and
  switched the Klear API to `Authorization: Bearer <admin_user_id>:<access_token>`.
  `KlearClient` / `AsyncKlearClient` now require `admin_user_id` and `access_token`
  at construction (or via `from_env()`, which reads `KALSHI_KLEAR_ADMIN_USER_ID` /
  `KALSHI_KLEAR_ACCESS_TOKEN`). Removed: the `login()` method, the
  `is_authenticated` property, the `client.auth` resource, and the `LogInRequest` /
  `LogInResponse` models. `KlearAuth` is now a Bearer-credential holder
  (`KlearAuth(admin_user_id, access_token)`). Generate a token at
  <https://klearing.kalshi.com> (the "Security" page).

### Added

- **`cfbenchmarks_value` WebSocket channel** — stream CF Benchmarks reference index
  values (e.g. `BRTI`) with trailing 60-second and final-minute quarter-hour
  averages via `KalshiWebSocket.subscribe_cfbenchmarks_value(index_ids=[...])`. New
  models `CFBenchmarksValueMessage` / `CFBenchmarksValuePayload` /
  `CFBenchmarksAvgData` / `CFBenchmarksIndexListMessage` /
  `CFBenchmarksIndexListPayload` (exported from `kalshi.ws.models`).
- **`AccountResource.upgrade()`** — `POST /account/api_usage_level/upgrade` to
  request a permanent Advanced API usage-level grant.
- **`AccountApiLimits.grants`** — the per-exchange-lane usage-level grant list, plus
  a new `ApiUsageLevelGrant` model (`exchange_instance` / `level` / `source` /
  `expires_ts`), exported from `kalshi`.
- **`MarginAccountResource.api_limits()`** — `GET /account/limits/perps` for the
  Perps API tier limits (reuses `AccountApiLimits`).
- **Perps market notional/leverage fields** — `MarginMarket` gains
  `leverage_estimates` and `volume`/`volume_24h`/`open_interest` notional-value
  fields; `MarginMarketCandlestick` and the `ticker` WS payload gain notional-value
  fields, all tracking the spec.

### Changed

- Re-vendored `specs/openapi.yaml`, `specs/asyncapi.yaml`, `specs/perps_openapi.yaml`,
  `specs/perps_asyncapi.yaml`, and `specs/perps_scm_openapi.yaml`; the subaccount
  range documented in prose is now 1–63 (no validation change).

## 3.3.0 — 2026-06-06

Adds a complete **FIX protocol** subsystem (FIXT.1.1 / FIX50SP2) for both the
prediction and perps products. Additive release: no changes to the existing REST,
WebSocket, or Perps surfaces.

### Added

- **FIX engine (`kalshi.fix`)** — a hand-rolled, async-first FIX client for both
  products: `FixClient` (prediction) and `MarginFixClient` (margin, in
  `kalshi.perps.fix`), re-exported from the top-level `kalshi` package alongside
  `FixConfig`, `FixEnvironment`, and `FixSessionType`. Covers five session types —
  order entry (NR/RT), drop copy, market data, post-trade settlement (prediction),
  and RFQ (prediction), plus order-group management over the order-entry session —
  on a session state machine with
  RSA-PSS logon (reusing the REST key), heartbeat / test-request liveness,
  sequence tracking with gap-fill / resend on the retransmission sessions, and
  AWS-style full-jitter reconnect. (Epic #402.)
- **Typed FIX messages** — Pydantic v2 models for every Kalshi FIX message across
  order entry, order groups, market data, RFQ/quoting, drop copy, and market
  settlement, with `DollarDecimal` / `FixedPointCount` money types (no float
  drift) and a central inbound dispatch via `decode_app_message`.
- **`FixOrderBook`** — aggregated order-book reconstruction from market-data
  snapshots + incrementals; **`SettlementReassembler`** — paginated
  settlement-report reassembly.
- **`FixSession.on_decode_error`** hook + `decode_app_message_strict` — surface a
  registered-but-malformed inbound message instead of silently dropping it (#432).
- **FIX documentation** — new `docs/fix.md` guide, plus FIX coverage in the
  README, errors, authentication, configuration, environment-variables, and the
  API reference.
- **FIX dictionary drift test** — `specs/kalshi-fix-dictionary.xml` checked in
  with a model↔dictionary drift test, the FIX analogue of the REST contract-drift
  suite (#437).

### Fixed

- Documentation accuracy pass: `fcm.positions_all()` is now documented (the FCM
  page previously stated it did not exist); the `portfolio` reads document their
  `subaccount` parameter; the `markets.is_block_trade` version note is corrected
  to SDK v3.1.0; the `OrderPrice` and `MultiplierDecimal` types are documented;
  and the docs landing page's WebSocket channel count is corrected to 11.

## 3.2.0 — 2026-06-05

Adds full SDK support for the Kalshi **Perps (margin) API** — a separate
perpetual-futures exchange — as standalone clients alongside the existing
prediction-API surface. Additive release: no changes to `KalshiClient`.

### Added

- **`PerpsClient` / `AsyncPerpsClient`** — standalone clients for the perps
  exchange (`external-api.kalshi.com` / demo `external-api.demo.kalshi.co`,
  `/trade-api/v2`), with their own `PerpsConfig` and a separate `KALSHI_PERPS_*`
  credential namespace. They reuse the prediction-API RSA-PSS signer and HTTP
  transport unchanged. The constructors and `from_env()` also accept
  `ws_base_url` (set the WS endpoint independently from REST) and `password`
  (passphrase for an encrypted key), and read `KALSHI_PERPS_WS_BASE_URL` /
  `KALSHI_PERPS_PRIVATE_KEY_PASSPHRASE` from the environment; passing `config=`
  together with `demo`/`base_url`/`ws_base_url` is rejected. Resource families:
  `exchange` (status / enabled gate /
  risk parameters), `markets` (list / get / orderbook / candlesticks), `orders`
  (create / get / list / cancel / decrease / amend + FCM), `order_groups`,
  `portfolio` (positions / fills / trades), `margin` (balance / risk /
  notional risk limit / fee tiers), `funding` (rate estimate / historical /
  history), and `transfers` (intra-exchange-instance + margin subaccounts).
  Margin order side is `bid` / `ask`; prices are `DollarDecimal`
  (FixedPointDollars), counts `FixedPointCount`, and `number/double` ratios
  (leverage, funding rate, ROE, fee tiers) are `MultiplierDecimal` (exact
  `Decimal`, string-serialized) — consistent across the REST, WS, and exchange
  surfaces. Margin-account list responses tolerate a server-returned `null`.
- **`PerpsWebSocket`** — the perps margin WebSocket
  (`external-api-margin-ws.kalshi.com`, `/trade-api/ws/v2/margin`) with six typed
  channels (`subscribe_orderbook_delta`, `subscribe_ticker` — carrying
  `funding_rate` + `next_funding_time_ms`, `subscribe_trade`, `subscribe_fill`,
  `subscribe_user_orders`, `subscribe_order_group`). Reuses the event-contract
  WS connection / sequence-gap / backpressure machinery; perps WS timestamps are
  Unix epoch **milliseconds** (`*_ms` fields).
- **`KlearClient` / `AsyncKlearClient`** — the Self-Clearing-Member "Klear"
  settlement API (`api.klear.kalshi.com` / demo `demo-api.kalshi.co`,
  `/klear-api/v1`) with a third auth model: **cookie-session + MFA** via
  `login(email=..., password=..., code=...)`. Resource `margin` covers reports,
  active/historical obligations, settlement estimate, settlement + guaranty-fund
  balances, settlement-balance history, and settlement-balance withdrawal.
  Klear money fields are integer centicents; the single real-money write
  (`withdraw_settlement_balance`) validates a positive amount at construction.
  Credentials and the session cookie are never logged or shown in `repr()`.
- `docs/perps.md` (+ mkdocs nav), README "Perps (margin) trading" section, and
  runnable `examples/perps_create_order.py` / `perps_stream_ticker.py` /
  `perps_balance_risk.py`.

### Changed

- Prediction-API list endpoints `markets.candlesticks` / `bulk_candlesticks` /
  `bulk_orderbooks` now validate a typed response envelope: a **missing**
  spec-required array key raises `ValidationError` (surfacing spec drift instead
  of silently returning `[]`), while a **null** array coerces to `[]` (Kalshi's
  empty-as-null convention — the prior `data.get(...)` extraction would
  `TypeError` on a null array). The perps `markets.list` / `markets.candlesticks`
  / `funding.historical_rates` / `funding.history` responses use the same
  `NullableList` envelopes, so null-handling is consistent across both surfaces.
  The optional `order_groups.list` stays tolerant of a missing/null array.

### Fixed

- `KalshiWebSocket._stop()` now retrieves an already-finished receive-loop's
  exception, so a session torn down after a permanent close no longer logs
  asyncio's "Task exception was never retrieved" on garbage collection.

### Internal

- Vendored the three perps specs (`specs/perps_openapi.yaml`,
  `perps_asyncapi.yaml`, `perps_scm_openapi.yaml`); `scripts/sync_spec.py` and the
  weekly spec-sync workflow now fetch/diff/checksum them and fold their sha256
  into the drift fingerprint (preserving the `contents: read` + `issues: write`
  security model).
- Parameterized the contract-drift harness per spec: `TestPerps*Drift` /
  `TestPerpsScm*Drift` validate the perps REST + SCM surfaces against their own
  specs, alongside the existing prediction-API drift suites.
- README / `docs/index.md` banners note the perps surface (34 REST operations,
  6 WS channels, 10 SCM operations).

## 3.1.0 — 2026-06-04

OpenAPI + AsyncAPI spec sync from v3.19.0 → v3.20.0 (`#385`). Adds the
new `GET /events/fee_changes` endpoint plus three smaller additive
changes upstream re-published into 3.20.0 after the drift issue was
filed (the OpenAPI checksum in `#385` is therefore stale; the AsyncAPI
checksum still matches).

### Added

- `events.fee_changes()` / `fee_changes_all()` (sync + async) for
  `GET /events/fee_changes` — the new paginated event-level fee-override
  feed (`event_ticker`, `limit`, `cursor`). Returns `Page[EventFeeChange]`
  (and an auto-paginating iterator). `EventFeeChange` exposes
  `fee_type_override` / `fee_multiplier_override`, both present-but-`None`
  when an override is cleared.
- `is_block_trade` query param on `markets.list_trades` /
  `list_all_trades` (+ deprecated `list_trades_all`) and
  `historical.trades` / `trades_all`. Omit for all trades, `True` for
  only block trades, `False` for only non-block.
- `Trade.is_block_trade` (`bool`) — new spec-required, non-nullable
  response field; a missing key raises so a schema regression surfaces.
- WebSocket `event_fee_update` message on the existing
  `market_lifecycle_v2` channel (`EventFeeUpdateMessage` /
  `EventFeeUpdatePayload`). `subscribe_market_lifecycle()` now yields
  `MarketLifecycleMessage | EventFeeUpdateMessage`. Channel count is
  unchanged (still 11) — this is a second message type on an existing
  channel. **Behavioral note for existing subscribers:** discriminate on
  `.type` before reading payload fields — an `EventFeeUpdatePayload` has no
  `market_ticker`, so naive access raises `AttributeError`. See the
  migration callout in [`docs/websockets.md`](docs/websockets.md).

### Internal

- `specs/openapi.yaml` (sha256
  `b72a2aa138695d810f6ca85096bfe19e1b66ba5e9b2ed37753be284b5288d271`)
  and `specs/asyncapi.yaml` (sha256
  `2f72d0a3fd25fe331210ed300f03ad4c1fedcb561b3ab425046b2dca6f4683ec`)
  snapshots bumped; `kalshi/_generated/models.py` regenerated.
- Spec also relaxed `CreateOrderV2Request.client_order_id` and
  `EventData.product_metadata` from required to optional, and added
  `ApiKeyScope` / `FeeType` enums. No SDK-facade change: the V2 order
  keeps `client_order_id` required by design, `Event.product_metadata`
  already tolerated server omission, and API-key `scopes` stays `str`
  for forward-compat.
- README + `docs/index.md` banners bumped to "99 operations … OpenAPI
  v3.20.0".

## 3.0.1 — 2026-05-26

OpenAPI spec sync from v3.18.0 → v3.19.0 (`#383`). Single additive
request-side constraint on `GET /structured_targets`: the `ids` query
param gained `maxItems: 2000`. Mirrored at the SDK boundary so an
oversize filter fails fast with a clear `ValueError` instead of paying
a network round trip for a 400. No endpoint, channel, or response-model
changes; regenerated `kalshi/_generated/models.py` is byte-identical to
the v3.18.0 output.

### Changed

- `StructuredTargetsResource.list` / `list_all` and their async
  counterparts now raise `ValueError("ids accepts at most 2000 entries
  per spec ...")` when `ids` exceeds 2000 entries. The 2000 boundary
  is inclusive (matches spec `maxItems`). Mirrors the existing
  `live_data.batch` (`milestone_ids`, max 100) and
  `markets.bulk_*` (`tickers`, max 100) precedent.

### Internal

- `specs/openapi.yaml` snapshot bumped (sha256
  `5eaeca6bb64b2ff0aa4f63f9e13381da5a8f6d8f9b34328408499a0503a3085d`).
- README + `docs/index.md` banners bumped to "OpenAPI v3.19.0".

## 3.0.0 — 2026-05-22

Public-API rename release. Three breaking-rename issues (`#348`, `#349`, `#351`)
that were deferred from the v2.7.0 audit closure now land with **one-release
deprecation aliases**: both old and new spellings work in v3.0.0; old names
emit `DeprecationWarning` and will be removed in a future release (v3.1+).

This is the first release in the v3 line. The wire protocol is unchanged from
v2.7.0; v3 is purely a public Python API ergonomics break.

### Migration

See `docs/migrations/v2-to-v3.md` for full BEFORE/AFTER snippets and a one-page
search-and-replace cheat sheet.

### Breaking changes

All three changes ship with `@typing_extensions.deprecated` aliases on the old
names — existing v2.x callers continue to work, but get a `DeprecationWarning`
on every call until they migrate.

- **`CommunicationsResource` sub-namespaces** (`#348`). Flat noun-prefixed
  methods (`list_rfqs`, `get_rfq`, `create_rfq`, `delete_rfq`, `list_all_rfqs`,
  `list_quotes`, `get_quote`, `create_quote`, `delete_quote`, `accept_quote`,
  `confirm_quote`, `list_all_quotes`) are split into two sub-resources matching
  the OpenAPI v3.18.0 tag structure:

  ```python
  # v2.x (deprecated in v3.0.0)
  client.communications.list_rfqs(...)
  client.communications.create_rfq(...)
  client.communications.accept_quote(quote_id, accepted_side="yes")

  # v3.0.0+
  client.communications.rfqs.list(...)
  client.communications.rfqs.create(...)
  client.communications.quotes.accept(quote_id, accepted_side="yes")
  ```

  The misc `client.communications.get_id(...)` stays at the top level (no
  sub-noun). The new sub-resource classes `RFQsResource`, `QuotesResource`,
  `AsyncRFQsResource`, `AsyncQuotesResource` are exported from `kalshi/__init__.py`
  for type annotations.

- **`MarketsResource.list_trades_all` → `list_all_trades`** (`#349`).
  Standardizes on `list_all_<noun>` matching the other three resources
  (`CommunicationsResource.list_all_rfqs`, `SubaccountsResource.list_all_transfers`,
  etc.). `list_trades_all` remains as a deprecated alias.

  ```python
  # v2.x (deprecated in v3.0.0)
  for trade in client.markets.list_trades_all(ticker="..."):
      ...

  # v3.0.0+
  for trade in client.markets.list_all_trades(ticker="..."):
      ...
  ```

- **`OrdersResource.fills` / `fills_all` → `PortfolioResource.fills` /
  `fills_all`** (`#351`). The endpoint URL is `/portfolio/fills`; this aligns
  the SDK layout with the URL family (`portfolio.settlements`,
  `portfolio.deposits`, `portfolio.withdrawals`). The old `OrdersResource.fills`
  / `fills_all` remain as deprecated aliases.

  ```python
  # v2.x (deprecated in v3.0.0)
  page = client.orders.fills(ticker="...")

  # v3.0.0+
  page = client.portfolio.fills(ticker="...")
  ```

### Polish

- **`_fills_params` deduped** to `kalshi/resources/_base.py` (was duplicated in
  `orders.py` and `portfolio.py` during the relocation).

### Internal

- 78 new regression tests covering the deprecation-alias delegation and warning
  emission across sync + async pairs for every renamed method (12 communications
  forwarders × 2, plus markets + fills × 2 each).
- `tests/_contract_support.py` `METHOD_ENDPOINT_MAP` registers both old and new
  spellings for the duration of the alias window.

### Deprecation removal schedule

The v3.0.0 aliases will be removed no sooner than **v3.1.0**. Callers should
migrate before then. Each deprecated method has a `@typing_extensions.deprecated`
decorator that surfaces in type checkers and IDEs per PEP 702.

## 2.7.0 — 2026-05-22

Post-v2.6 independent multi-LLM reviewer audit closure. **47 issues filed
(`#311`–`#357`) by a 9-reviewer parallel pass** combining 7 internal specialist
agents (security/auth, HTTP transport, WebSocket, models/contracts, sync/async
parity, performance, resources/API) with **fresh-eyes external LLM reviews via
the Codex CLI (GPT-5) and Gemini CLI**. 44 issues closed in this release across
4 sequential waves (W0 docs, W1 HIGH integrity, W2 MEDIUM correctness, W3 LOW
polish/perf/deps); 17 PRs merged. 3 breaking-rename issues (`#348`, `#349`,
`#351`) deferred to **v3.0.0** milestone. Main is mypy `--strict` clean, ruff
clean, **2876 unit tests passing** (≈100 new regression tests added).

### Breaking changes

Five behavioral fences; all surface bugs that were silently wrong or invariants
the SDK now enforces. Per project policy (established by v2.0–v2.6),
bug-surfacing behavioral fences ship in minor releases; intentional public-API
removals or renames are reserved for major releases — that's why the three
breaking renames (`#348`, `#349`, `#351`) are deferred to v3.0.0.

- **`AmendOrderRequest.side` / `.action` narrowed to `Literal`** (`#312`).
  Mirrors the v2.5 `#270` narrowing on `CreateOrderRequest`. Previously any
  string passed validation and the server rejected with a 400; now invalid
  values raise `pydantic.ValidationError` at construction.
- **`KalshiConfig.extra_headers` immutable post-construction** (`#313`). The
  `#298` `KALSHI-ACCESS-*` fence ran once at construction; post-construction
  mutation of `extra_headers` could reopen the auth-header forge surface.
  `extra_headers` is now stored as `MappingProxyType` over a defensive copy
  — `config.extra_headers["k"] = "v"` raises `TypeError`. Construction-time
  fence unchanged.
- **`CommunicationsResource.list_rfqs` / `list_quotes` `status` kwarg
  narrowed to `Literal`** (`#324`). New `RfqStatusLiteral` / `QuoteStatusLiteral`
  match the spec's closed set; arbitrary `str` is rejected by mypy at the
  call site. Consistent with the existing `OrdersResource.list(status=...)`
  pattern.
- **`to_decimal()` rejects `NaN` / `Infinity`** (`#325`). The public helper
  promised safety in its docstring but accepted any `Decimal`. Now raises
  `ValueError` on non-finite inputs, matching the `_coerce_decimal` validator.
- **`DollarDecimal` request-side fields reject negative prices and
  sub-tick precision** (`#343`). `CreateOrderRequest`,
  `AmendOrderRequest`, `CreateOrderV2Request`, `AmendOrderV2Request` now
  reject negative `yes_price` / `no_price` and sub-$0.0001-tick precision
  at construction. Response-side `DollarDecimal` is unchanged (servers may
  emit any value).

### Critical (HIGH-severity money/auth/data-integrity fixes)

- **`KalshiClient.from_env` preserves caller ownership of `KalshiAuth`**
  (`#311`). The `from_env` classmethod (sync and async) overwrote `_auth_owned`
  from the input kwarg instead of recomputing from what `__init__` actually
  did. Two real bugs: (a) `from_env(key_id=..., private_key=...)` with no env
  vars set leaked the sign `ThreadPoolExecutor` because the SDK-built auth
  was flagged "not owned"; (b) `from_env(auth=my_auth)` with env vars set
  caused `client.close()` to close the caller's still-referenced auth,
  raising `RuntimeError("KalshiAuth has been closed")` on the next
  `sign_request`. The fix recomputes ownership from `__init__`'s invariant.
- **WS `_wait_for_response` wraps `TimeoutError` as `KalshiSubscriptionError`**
  (`#314`). `asyncio.wait_for` raises bare `TimeoutError` on timeout, which
  escaped `subscribe()` / `unsubscribe()` unhandled because only
  `ConnectionClosed` was caught. Now wrapped with `channel` / `client_id` /
  `op` context so consumers branching on SDK exceptions actually see the
  expected type.
- **WS zombie-subscription cleanup on gap-recovery failure** (`#315`).
  `broadcast_error` never popped the dead `Subscription`. A failed
  `resubscribe_one` in `_handle_seq_gap` (and the `KalshiBackpressureError`
  path) left a zombie sub whose closed queue persisted; the next reconnect's
  `resubscribe_all` resurrected it on the server — silent data loss + a
  server-quota leak. `broadcast_error` now pops `_subscriptions` and
  `_sid_to_client` so reconnects can't resurrect dead subs.

### High-impact correctness

- **`from_env` lazy `try_from_env()` evaluation** (`#316`). The classmethod
  eagerly evaluated `KalshiAuth.try_from_env()` even when the caller passed
  `auth=` / `key_id` / `private_key` / `private_key_path`. A malformed
  `KALSHI_PRIVATE_KEY` in the process env then raised on every CI worker
  that bypassed env. Now gated on `caller_supplied_auth`.
- **`sign_request` strips URL fragment** (`#317`). `path.split("?")[0]`
  stripped query strings but not `#fragment`. httpx drops fragments before
  sending, producing a guaranteed signature mismatch (401) on any path
  containing `#`. Now strips both.
- **`Retry-After` honored across 408 / 429 / 503 / 504** (`#322`). Previously
  only 429 parsed `Retry-After`. Per RFC 7231 §7.1.3 the header applies to
  all four. `_parse_retry_after` extracted; `retry_after` lifted to
  `KalshiError` base class so `KalshiServerError` and `KalshiTimeoutError`
  also surface the hint.
- **`Retry-After` path applies jitter** (`#321`). Synchronized clients
  hitting the same 429/503 window would stampede the rate limit at the
  exact server-suggested moment. Full Jitter is now added on top of the
  server floor, capped at `retry_max_delay`. Preserves RFC compliance
  (`Retry-After` is a "no sooner than" hint).
- **Response body size cap on success path** (`#323`). The `#203` 16 KB
  cap applied only to error responses; the success path was unbounded.
  New `_enforce_response_body_cap` enforces the same protection on
  non-streaming success bodies via a Content-Length pre-check plus a
  post-buffer guard.
- **V1 order request models gain `ge=0` parity** (`#326`). `subaccount`,
  `exchange_index`, `subaccount_number` on `CreateOrderRequest`,
  `AmendOrderRequest`, `BatchCancelOrderRequest`, and related V1 + group
  models now reject negative integers (matching V2 and the `#295` sweep).
- **`Page._columns` handles `None`-first nullable nested columns** (`#328`).
  Detection inspected only `cols[0]`; a `None`-first nullable nested
  `BaseModel` column skipped the `model_dump` pass and broke
  `to_dataframe` / `to_polars` for nullable-Struct schemas.
- **WS `OrderbookDeltaPayload.ts` typed as `AwareDatetime`** (`#331`).
  Missed by the v2.5 `#270` WS datetime sweep. Tightening across
  `orderbook_delta`, `user_orders`, and `communications` payloads.
- **WS backpressure error closes connection cleanly** (`#332`).
  `KalshiBackpressureError` in the recv loop previously broadcast sentinels
  and broke, but left the WS open and `_running=True`. The next
  `subscribe_*` restarted the recv loop on top of orphan server-side subs.
  Now closes the connection and clears `_running` / manager refs so the
  next session starts fresh.

### Performance

- **Orderbook materialization via `model_construct`** (`#327`).
  `_BookState.to_orderbook` previously re-validated every price level through
  Pydantic on each `apply_delta`. Data is SDK-canonical after the snapshot
  validation; switched to `model_construct` to skip the redundant pass.
- **Zero-delta orderbook updates preserve cache** (`#347`). A no-op delta
  (quantity unchanged) used to invalidate the memoized `Orderbook` view,
  defeating the `#244` cache. Now skipped when the price-level dict is
  unchanged.
- **Public `apply_snapshot` single-copy** (`#344`). The public path
  allocated `yes` / `no` dicts twice — once via identity in
  `_apply_snapshot_inplace`, then again via `dict(msg.msg.yes)` to copy
  defensively. The bypass path (recv hot loop, `#296`) keeps identity
  adoption; the public path now copies once.
- **V2 batch endpoints use bytes-fast-path** (`#329`). `batch_create_v2` /
  `batch_cancel_v2` paid the dict-walk serializer twice; the v2.4 `#223`
  fast-path was never extended. Now serialize via `model_dump_json` once
  and send the bytes.
- **RSA-PSS / MGF1 / SHA256 config cached** (`#345`). Previously
  allocated per signature. Hoisted to module-level constants — measurable
  on the auth hot path.
- **`SequenceTracker.track` sync fast-path** (`#330`). New public
  `track_sync` lets the recv hot loop skip the per-frame coroutine-object
  allocation; the async wrapper remains for callers that need to await on
  the gap path.
- **WS recv `asyncio.timeout` swap** (`#356`). Replaced `asyncio.wait_for`
  in the recv hot path with `async with asyncio.timeout(...)` (Python 3.11+)
  — fewer TimerHandle allocations per frame.
- **`method.upper()` hoisted out of retry loop** (`#342`). Computed once
  per request instead of once per retry attempt.

### Polish

- **`AsyncTransport.close()` cancellation-safe** (`#333`). Sets `_closed`
  after `aclose()` returns, not before — cancellation between the two no
  longer leaks the httpx pool. Mirrors the v2.6 `#301` sync fix.
- **`_delete_with_body(params=...)` symmetry** (`#340`). The body-only
  variant gains the `params` kwarg that `_delete_with_body_json` already
  accepted.
- **Pagination cycle detector catches non-adjacent loops** (`#352`). The
  prior detector only caught adjacent cursor repeats; an `A→B→A→B` loop
  from a load-balanced pod-state drift now raises before exhausting
  `max_pages`. Memory-bounded at 1024 seen cursors.
- **WS `_handle_orphan_subscribed` correlation** (`#354`). Server
  `unsubscribed` acks for sids the client never owned no longer clobber
  unrelated state.
- **WS `ConnectionManager.reconnect` exc_info on failure** (`#355`). Per-
  attempt failures now log with `exc_info=True` at DEBUG so root cause
  (auth / TLS / DNS) survives to max-retry.
- **WS `_stop()` teardown order** (`#357`). Closes the connection FIRST,
  then broadcasts sentinels — late in-flight frames no longer land on
  closed queues. `close()` wrapped in `try/finally` so sentinels always
  fire even if `close()` raises.
- **`KalshiConfig.extra_headers` doubled-pipeline removed** (`#341`).
  Previously attached to `httpx.Client(headers=...)` defaults AND merged
  per-request via `_ci_merge`. Now `_ci_merge` is the single source of
  truth; the `#298` precedence contract (config defaults < per-call
  extras < signed auth) is structurally enforced.
- **`orders.create()` overload tightening** (`#350`). The `**kwargs`
  overload statically required `action` and `count` since v2.5 `#242`;
  the type signature is now updated to match runtime so mypy catches
  omissions at the call site.
- **Documentation drift sweep** (`#318`, `#319`, `#320`, `#334`, `#336`,
  `#337`, `#338`, `#339`). Three live-data endpoint paths and the
  `batch()` return shape corrected; `positions_all()` "does not exist"
  claim dropped (it shipped in v2.5 `#269`); `structured_targets.get()`
  404 mapping corrected (raises `KalshiNotFoundError`, not `None`);
  sync/async docstring drift normalized across `orders`, `markets`,
  `portfolio`, `communications`; `CreateOrderV2Request` docstring
  corrected (`DollarDecimal`, not the nonexistent `FixedPointDollars`);
  `LiveDataResource.get_typed` clarified as the legacy URL form.
- **`KalshiAuth.from_pem` OpenSSH-format error** (`#335`). Detecting an
  `-----BEGIN OPENSSH PRIVATE KEY-----` header now raises a targeted
  `KalshiAuthError` with the exact `ssh-keygen -p -m PKCS8 -f <path>`
  conversion command instead of the generic PEM parse failure.

### Additive

- **`kalshi.OrderPrice`** — public type alias for the request-side
  bounded `DollarDecimal` used by order-request models (`#343`).
- **`kalshi.RfqStatusLiteral`, `kalshi.QuoteStatusLiteral`** — public
  Literal aliases for communications status filtering (`#324`).
- **`SequenceTracker.track_sync`** — public sync entry point for the WS
  recv hot path (`#330`).

### Dependencies

- **`pydantic>=2.4`** (`#346`). Bumped from `>=2.0` to ensure the
  `StrictInt` / `_coerce_decimal` invariants the SDK relies on get the
  2.4+ semantics. Pydantic 2.0–2.3 also shipped JSON-parser bugs.

## 2.6.0 — 2026-05-22

Post-v2.5 independent reviewer audit closure (`#273` follow-on). 7 issues
(`#295`–`#301`) identified by a fresh 7-agent parallel review of v2.5.0 across
security, HTTP transport, WebSocket reliability, models/types, REST resources,
performance, and docs/testing. Executed across 3 sequential waves (W0 docs,
W1 money/correctness, W2 polish) in disjoint git worktrees. 7 PRs merged;
main is mypy --strict clean, ruff clean, 2780+ unit tests passing.

### Breaking changes

Two behavioral fences; both surface bugs that were already wrong.

- **`int` request fields reject `bool`** (`#295`). Per-field `StrictInt`
  annotation on every money-routing / counting integer of every Request
  model: `subaccount`, `exchange_index`, `expiration_ts`, `reduce_by`,
  `reduce_to`, `contracts_limit`, `contracts`, `from_subaccount`,
  `to_subaccount`, `amount_cents`, `subaccount_number` across V1 + V2.
  `bool` is an `int` subclass, so a caller passing `True`/`False` used to
  silently route to subaccount 1 / transfer 1 cent / decrease by 1 contract
  with no error. Now raises `ValidationError` at construction. The existing
  `buy_max_cost` validator (`#243`) is unchanged. New `kalshi.StrictInt`
  alias is exported for downstream models.
- **`KALSHI-ACCESS-*` in `extra_headers` is rejected** (`#298`). Both
  `KalshiClient(..., config=KalshiConfig(extra_headers=...))` at
  construction time and per-request `extra_headers=` kwargs now raise
  `ValueError` if any key (case-insensitive) starts with `kalshi-access-`.
  Previously a caller-supplied `'kalshi-access-key'` (lowercase) co-existed
  with the SDK-signed `KALSHI-ACCESS-KEY` and httpx shipped both raw header
  lines — a forge surface even though the documented contract promises
  auth headers are SDK-managed.

### Critical (money-risk fixes)

- **`int` request fields reject `bool`** (`#295`, see Breaking).
- **Auth-header forge surface closed** (`#298`, see Breaking). Companion fix:
  `_post(json=...)` / `_put(json=...)` / `_delete_with_body(json=...)` and
  their async mirrors now pin `Content-Type: application/json` explicitly,
  preventing a caller-supplied `'content-type': 'text/plain'` in
  `extra_headers` from causing httpx to ship a JSON body labelled as
  plain text.
- **WebSocket session re-entry is rejected** (`#297`). `KalshiWebSocket._start()`
  used to silently rebuild every manager on nested or re-used `connect()`,
  orphaning the outer session's subscriptions and recv task with no error.
  Now raises `RuntimeError` with a clear message. `_stop()` clears the
  manager refs after teardown so the same instance can be cleanly reused
  for a fresh `connect()` once the prior session exits. A partial connect
  failure (auth/network) also resets state cleanly via a `BaseException`
  cleanup block, so a failed connect no longer permanently bricks the
  instance.

### High-impact correctness

- **`KalshiConfig.extra_headers` validated at construction** (`#298`). Closes
  the construction-time bypass that survived the per-request guard.
- **Case-insensitive header merge** (`#298`). New `_ci_merge` ensures a
  caller-supplied `'x-foo'` and SDK-set `'X-Foo'` collapse to one wire
  entry rather than co-existing.
- **Public `OrderbookManager.apply_snapshot()` keeps no-aliasing contract**
  (`#296`). Snapshot/delta input messages remain safe to reuse after a
  public `apply_snapshot()` call — the manager defensively copies the
  adopted dicts. The recv loop continues to skip the copy via
  `_apply_snapshot_inplace` for the hot-path perf win (#263).

### Performance

- **Orderbook snapshot adoption restored to identity** (`#296`). The
  `dict(msg.msg.yes)` / `dict(msg.msg.no)` wrappers in
  `_apply_snapshot_inplace` were silently nullifying the ~5x speedup
  CHANGELOG #263 advertises. For a 200-level book that's 400 needless
  re-hashes/reallocs per snapshot on the recv hot path. Wrappers dropped;
  identity adoption restored on the bypass path.

### Polish

- **`Sync/AsyncTransport.close()` explicitly idempotent** (`#301`). New
  `_closed` flag matches the `KalshiAuth` / `KalshiClient` pattern; second
  and subsequent `close()` calls are no-ops. Documents the threading scope
  honestly: sync is sequential-safe (worst case: one redundant
  `httpx.Client.close()`, itself idempotent), async is fully race-free
  under cooperative scheduling.
- **`docs/resources/orders.md`**: removed stale `# ActionLiteral, defaults to
  "buy"` inline comment that would have re-introduced the `#242` footgun
  for readers (`#299`).
- **`docs/configuration.md`**: reference table now lists `total_timeout`,
  `ws_ping_interval`, `ws_close_timeout`, and `allow_unknown_host`; URL
  validation prose updated for the v2.5 default-reject behavior (`#300`).

### Additive

- **`kalshi.StrictInt`** — new public type alias for downstream models that
  want the same `bool`-rejection guard (`#295`).
- **`kalshi/_constants.py`** (internal) — holds `AUTH_HEADER_PREFIX` to
  eliminate drift between `_base_client.py` and `config.py` (`#298`).

## 2.5.0 — 2026-05-21

Post-v2.4 multi-reviewer audit closure (`#273`). 34 issues across security,
HTTP transport, WebSocket reliability, models/types, REST resources,
performance, and docs/testing — identified by a 7-agent parallel review on
top of the v2.4 sweep and executed across 4 sequential waves (W0 docs, W1
money-risk, W2 medium, W3 polish) in disjoint git worktrees. 20 PRs merged;
main is mypy --strict clean, ruff clean, 2742 unit tests passing.

### Breaking changes

Two user-visible breakages, both fence-and-forget. Migration in
`docs/migration.md` v2.4 → v2.5 section.

- **`orders.create()` kwarg path requires `count` and `action` explicitly**
  (`#242`). Previously `client.orders.create(ticker=..., side="yes")` placed
  a 1-contract live buy because `action` defaulted to `"buy"` and `count` to
  `1`. Now raises `TypeError` before any HTTP request. The `request=...`
  overload is unaffected; `CreateOrderRequest.count` no longer has a default.
- **Six REST + three WS model fields widened from `str`/`float` to `Decimal`**
  (`#258`, `#259`). WS: `OrderGroupPayload.contracts_limit` (`str` →
  `FixedPointCount`), `TickerPayload.dollar_volume` and `dollar_open_interest`
  (`str` → `DollarDecimal`). REST: `Market.floor_strike`, `Market.cap_strike`,
  `Event.fee_multiplier_override`, `MarketLifecyclePayload.floor_strike`,
  `Series.fee_multiplier`, `SeriesFeeChange.fee_multiplier` (bare `Decimal`
  or `float` → `DollarDecimal` / `Decimal` via `_coerce_decimal`). Wire
  format unchanged; consumers must adopt `Decimal` arithmetic.

### Critical (money-risk fixes)

- **WS: validation failure on a sequenced frame no longer silently advances
  the seq watermark** (`#241`). Before: a malformed `orderbook_delta` /
  `order_group_update` frame was logged + skipped but seq tracking had
  already advanced, so the next legitimate frame matched expected-seq and
  gap detection never fired — local orderbook silently corrupted with no
  resync trigger. After: pre-validate + apply + dispatch is wrapped in a
  try/except that rolls back the watermark on any exception, so the next
  delta triggers a real gap-recovery resubscribe.
- **REST/WS split-environment combinations rejected at construction**
  (`#239`). Before: `KalshiClient(demo=True,
  base_url="https://api.elections.kalshi.com/...")` (or the env-var
  equivalent) silently produced a config where REST hit production but WS
  hit demo — a WS-driven strategy could trade real money against a demo
  book. After: `KalshiConfig.__post_init__` rejects mismatched REST/WS
  hosts and the constructors raise `ValueError` with both inputs named.
- **`CreateOrderRequest.buy_max_cost` validator rejects `bool`** (`#243`).
  Before: `buy_max_cost=True` slipped through as `1` (1¢ cap) because
  `bool` is an `int` subclass. After: explicit rejection, matching the
  `_coerce_decimal` invariant set by v2.4's `#225`.
- **`orders.create()` no longer silently defaults to 1-contract buy**
  (`#242`, see Breaking changes).
- **Transport retries network-level httpx errors on idempotent verbs**
  (`#240`). `ConnectError` / `NetworkError` / `RemoteProtocolError` /
  `ReadError` / `WriteError` now participate in the same `RETRYABLE_METHODS`
  + backoff + total-timeout loop the timeout branch already uses for
  GET/HEAD/OPTIONS. `ConnectError` on POST/DELETE is also safe (request
  never reached the wire, mirroring v2.4's `#204` PoolTimeout carve-out).
  Other transport errors on non-idempotent verbs still surface immediately
  so the caller can reconcile via `client_order_id`. New
  `KalshiNetworkError` raised when retries are exhausted.

### High-impact correctness

- **Errors `408` and `504` route to `KalshiTimeoutError`** (`#251`). Carries
  the "may or may not have committed" semantic from v2.4's `#226`; callers
  can branch on `except KalshiTimeoutError` and reconcile.
- **Suppressed error bodies preserve the typed exception class** (`#252`).
  A 429/401/409/422/504 whose body exceeds the 16KB `Content-Length` cap
  still routes to the right subclass instead of degrading to
  `KalshiError`. 429 Retry-After is still populated.
- **WS: resubscribe-window stash drained on every gap recovery** (`#254`).
  Frames captured between unsubscribe-ack and the new subscribe-ack are
  replayed through `_process_frame` for the new sid (filtered by sid;
  others dropped with a debug log). Was previously only drained on full
  reconnect, so per-gap stashes accumulated until the next disconnect.
- **WS: stale orderbook frames no longer mutate the local book** (`#255`).
  Snapshot/delta apply is gated on subscription-existence at the configured
  sid; frames arriving after teardown short-circuit before validation,
  fixing a race where the high-level `subscribe_book` iterator could read a
  stale book.
- **WS: `_OrderbookIterator` raises `KalshiOrderbookUnavailableError`
  instead of yielding an empty `Orderbook`** (`#257`). Before: if
  `mgr.get(ticker)` returned `None` mid-resync, the iterator yielded an
  empty book — indistinguishable from a real zero-liquidity market. After:
  typed error surfaces the race so the caller can reattach to a fresh
  iterator after the resync snapshot lands.
- **WS: `KalshiBackpressureError` carries structured `channel` / `sid` /
  `client_id` / `maxsize`** (`#256`). Matches the structured-error contract
  v2.4's `#213` established for `KalshiSequenceGapError` /
  `KalshiSubscriptionError`.
- **WS: orphan `subscribed` acks released** (`#268`). If a `subscribe` task
  is cancelled between send and ack, the server still completes the
  subscription; the dispatcher now detects the orphan ack (sid present, no
  client_id mapping) and emits `unsubscribe` so the sid doesn't leak.
- **WS: snapshot payload `yes`/`no` required** (`#268`). A malformed
  snapshot now raises `ValidationError` (which pairs cleanly with `#241`'s
  seq rollback) instead of silently materializing an empty book.
- **Auth: conflicting key inputs rejected explicitly** (`#249`).
  `KalshiClient(private_key_path=..., private_key=...)` and dual env-var
  (`KALSHI_PRIVATE_KEY` + `KALSHI_PRIVATE_KEY_PATH`) now raise instead of
  silently preferring one source.
- **Unknown `base_url` host fails closed by default** (`#250`). New
  `KalshiConfig.allow_unknown_host=False` rejects hosts outside
  `{api.elections.kalshi.com, demo-api.kalshi.co, localhost, 127.0.0.1,
  ::1}` so a typo like `kalsi.com` no longer delivers signed requests to
  an attacker. Opt-in via the field or `KALSHI_ALLOW_UNKNOWN_HOST=1`.
- **`Decimal('NaN')` / `Infinity` rejected at the boundary** (`#270`).
  `_coerce_decimal` calls `is_finite()` after coercion so a downstream
  arithmetic NaN never ships `"NaN"` to a real-money order endpoint.
- **Sign-executor close race fixed** (`#267`). `_get_sign_executor`
  rechecks `_closed` under the lock so a racing `close()` can't leave a
  freshly-instantiated `ThreadPoolExecutor` dangling.

### Performance

- **WS recv loop drops per-frame `asyncio.Task` + `asyncio.shield`**
  (`#245`). Cooperative pause via `Event` + 50 ms poll instead of
  allocating a `Task` / `Future` / contextvars copy per frame. Inline
  dispatch on the hot path.
- **`subscribe_book` iterator caches the materialized `Orderbook`**
  (`#244`). Memoized on `_BookState`, invalidated by the in-place apply
  helpers; eliminates the O(n log n) sort + 2N `OrderbookLevel`
  validations per delta that the high-level iterator was paying on top of
  v2.4's `#199` in-place fast path.
- **WS snapshot apply collapses to a single dict walk** (`#263`).
  `OrderbookSnapshotPayload.yes` / `.no` validate directly into
  `dict[Decimal, Decimal]` via a `BeforeValidator`; `_apply_snapshot_inplace`
  adopts the dict in identity (no rebuild). ~5× faster on a 200-level book.
- **`Page.to_dataframe` / `to_polars` built column-oriented** (`#264`).
  Replaces per-row `model_dump(mode="python")` with a single getattr-driven
  column build. Preserves the v2.4 Decimal contract; nested-model cells
  still dumped per-column so polars Struct inference works.
- **REST has a pluggable JSON loader** (`#260`). New
  `KalshiConfig.rest_json_loads` mirrors the existing `ws_json_loads`; set
  to `orjson.loads` for ~2–3× faster list-endpoint parsing.
- **Signing path skips regex on the common case** (`#261`).
  `_normalize_percent_encoding` short-circuits when no `%` appears.
- **Header merge hoisted out of the retry loop** (`#262`). Only
  `auth_headers` changes per attempt; the 3-way `config_extra +
  per_call_extra + body_headers` merge is now precomputed once per
  request, saving N-1 dict copies across retries.
- **`MessageQueue._size` counter dropped** (`#271`). `qsize()` derives from
  `len(self._buffer)` adjusted for the sentinel; two ints saved per put/get
  on the WS hot path.
- **`import asyncio` hoisted out of `AsyncTransport.request`** (`#271`).
  Stray per-request `sys.modules` lookup eliminated.

### Configuration knobs (additive)

- `KalshiConfig.rest_json_loads` (`#260`).
- `KalshiConfig.allow_unknown_host` + `KALSHI_ALLOW_UNKNOWN_HOST` env var
  (`#250`).
- `extra_headers=` plumbed through every public REST resource method —
  302 method signatures via codemod (`#253`). `KALSHI-ACCESS-*` signing
  headers always win, so callers cannot forge them via this surface.

### Typed-exception expansion

- New `KalshiNetworkError` (`#240`) — exhausted retries on a network-level
  httpx error.
- New `KalshiOrderbookUnavailableError` (`#257`) — `_OrderbookIterator`
  race where `mgr.get(ticker)` returned `None` mid-resync.
- `KalshiBackpressureError` gains `channel` / `sid` / `client_id` /
  `maxsize` keyword-only fields (`#256`).

### Models, types, request shape

- **WS `user_orders` + `communications` payloads use `pydantic.AwareDatetime`**
  (`#270`). Closes the gap left by v2.4's `#234` REST sweep — naive RFC3339
  strings now raise `ValidationError` on WS too.
- **V1 `CreateOrderRequest` enum-style fields narrowed to `Literal[...]`**
  (`#270`). Closes the V1/V2 strictness gap; users constructing the
  request directly fail at construction instead of server-side.
- **`MultiplierDecimal` alias + `_coerce_decimal` on multiplier fields**
  (`#259`, see Breaking changes).
- **Internal `UnixSecondsTimestamp` alias** (`#270`). Documents the
  seconds-vs-milliseconds wire-shape choice on `Balance.updated_ts`,
  `Deposit.created_ts` / `finalized_ts`, `Withdrawal.created_ts` /
  `finalized_ts`.
- **`Retry-After` past-date / negative form clamps to 0.0** (`#267`). Both
  delta-seconds and HTTP-date branches now agree (was: negative delta-
  seconds fell back to computed backoff while past HTTP-date retried
  immediately).

### REST resources

- **`portfolio.positions_all()` / `fcm.positions_all()`** (`#269`). Both
  endpoints are cursor-paginated; previously they shipped no `*_all()`
  iterator, breaking the SDK's pagination convention.
- **`multivariate.lookup_history` validates `lookback_seconds` enum
  locally** (`#269`). Spec restricts to `{10, 60, 300, 3600}`; passing
  anything else now raises `ValueError` before the round trip.
- **Three deprecated multivariate endpoints marked
  `@typing_extensions.deprecated`** (`#269`). `lookup_tickers`,
  `lookup_history`, `create_market` (sync + async) carry the spec's
  "should not be used for new integrations" message; emit
  `DeprecationWarning` on first call.
- **`event_ticker` accepts `list[str] | str`** on `OrdersResource.list` /
  `list_all` (`#269`). Joined via `_join_tickers(values, max_items=10)`
  matching the spec's `MultipleEventTickerQuery`; the kwarg previously
  typed `str` only.

### `from_env` ergonomics

- **`KalshiClient.from_env(**kwargs: Unpack[ClientInitKwargs])`** (`#266`).
  `from_env` now exposes a `typing.Unpack`-driven TypedDict so typos like
  `time_out=10` trip mypy strict at the call site; the internal
  `# type: ignore[arg-type]` is gone.

### Documentation

- `docs/migration.md` gains a `v2.4 → v2.5` section covering the two
  breaking changes above.
- `docs/migration.md` v2.3 → v2.4 section added (`#246`) covering the V1
  batch shape change, the new typed exceptions, passphrase-protected PEMs,
  HTTP/2, and per-request `extra_headers`.
- `docs/resources/orders.md` batch_create / batch_cancel examples
  rewritten for the v2.4 typed-response shape (`#247`).
- README pagination quickstart uses `Page.has_next` (was `has_more`, which
  never existed) (`#248`).
- Three docstrings retagged from `v3.0.0 BREAKING` to `v2.4.0` where the
  change actually shipped (`#265`).
- `pyproject.toml` gains `Framework :: AsyncIO`, `Operating System :: OS
  Independent`, and `Topic :: Office/Business :: Financial :: Investment`
  classifiers for PyPI discoverability (`#272`).
- Stale `Unreleased (post-v2.2.0)` bullet removed from ROADMAP (`#272`).

### Testing

- **34 regression tests added** across waves W1 / W2 / W3 (TDD per issue).
- **`tests/test_split_env.py`** — 12 tests covering the REST/WS host
  cross-check (`#239`).
- **`tests/test_http2.py`** (skipif `h2` missing) — asserts `http2=True`
  propagates to the underlying httpx pools on both sync + async clients
  (`#271`).
- **`tests/test_rest_json_loader.py`** — six tests covering the new
  `rest_json_loads` hook (`#260`).
- **`tests/test_extra_headers_plumbing.py`** — 245 reflective tests
  asserting every public resource method exposes the new `extra_headers`
  kwarg (`#253`).
- **Two new bench scripts**: `scripts/bench_orderbook_iterator.py` (drives
  `_OrderbookIterator.__anext__` end-to-end) and
  `scripts/bench_page_to_dataframe.py` (`#271`).
- **Hermetic test fixtures**: `tests/conftest.py` strips `KALSHI_*` env at
  import + enables `KALSHI_ALLOW_UNKNOWN_HOST=1` process-wide so existing
  tests using `https://test.kalshi.com` still work alongside the new
  default-fail.

### Breaking changes summary

1. **`#242`** — `orders.create()` requires `count` and `action`
   explicitly on the kwarg path (no silent 1-contract buy).
2. **`#258` + `#259`** — six REST model fields + three WS payload fields
   widened from `str` / `float` to `Decimal`. Wire format unchanged;
   consumers must adopt `Decimal` arithmetic.

See `docs/migration.md` v2.4 → v2.5 for code-level migration snippets.

## 2.4.0 — 2026-05-21

Comprehensive multi-reviewer audit (`#224`) — 33 issues across security, HTTP
transport, WebSocket reliability, models/types, resources, performance,
testing, and documentation. Identified by an 8-agent parallel review; executed
across 4 sequential waves of disjoint git worktrees. The most impactful items
by category:

### Critical (silent data loss / silent money corruption fixes)

- **WS orderbook resync after sequence gap** (`#189`). Before: a single dropped
  frame cleared the local book and never asked the server for a fresh
  snapshot — the consumer kept receiving deltas against a permanently-empty
  book. After: `_handle_seq_gap` drives a real unsubscribe+resubscribe with
  per-sid ticker tracking so all-markets subscriptions are also covered.
- **`Page.to_dataframe` / `Page.to_polars` Decimal preservation** (`#190`).
  Before: `DollarDecimal` / `FixedPointCount` serializers ran for
  `mode='python'` too, so DataFrame columns held `str` and `df['price'].sum()`
  returned concatenated strings instead of a numeric sum. After: serializers
  use `when_used='json'`; live `Decimal` flows through pandas/polars.

### High-impact correctness (HTTP + WS + Decimal + V1 orders)

- **DollarDecimal serialization is positional** (`#191`). `_decimal_to_str`
  uses `f'{v:f}'` so values like `Decimal('1E+10')` never reach the wire as
  scientific notation that Kalshi would reject.
- **Retry policy widened** (`#192`). `RETRYABLE_STATUS_CODES` now includes
  408, 425, and the Cloudflare 5xx range (520–524). POST/DELETE still never
  retry, preserving idempotency.
- **Total wall-clock retry budget** (`#193`). New `KalshiConfig.total_timeout`
  caps cumulative time spent inside a single request including retries.
  `None` (default) preserves the legacy unbounded behavior.
- **V1 batch order endpoints surface typed per-leg responses** (`#194`,
  **BREAKING**). `orders.batch_create` now returns
  `BatchCreateOrdersResponse` (was `list[Order]` that crashed on any failed
  leg). `orders.batch_cancel` now returns `BatchCancelOrdersResponse` (was
  `None`) exposing per-order `reduced_by_fp`. Migration: upgrade reads from
  `response[i]` to `response.orders[i].order` (and check `.error`).
- **WS generic `subscribe()` rejects unknown param keys** (`#195`). Was
  silently dropping typos like `params={'tickerz': [...]}` and subscribing
  the consumer to a much broader stream than intended.
- **WS server-side seq reset detection** (`#196`). `SequenceTracker.track`
  now distinguishes `seq == last` (drop) from `seq < last` (reset → gap
  recovery); was silently dispatching the reset window with no signal.
- **WS fast-fail on permanent close codes** (`#197`). `ConnectionClosed` with
  codes 1002/3/7-10 or 4xxx now raises `KalshiConnectionError` immediately
  instead of burning the 10-retry budget on doomed reconnect attempts.
- **WS payload type alignment with REST** (`#198`). `*_fp` count/size/volume
  fields on every WS payload model now type as `FixedPointCount`; RFC3339
  timestamps type as `datetime`. Eliminates silent str+int TypeErrors when
  consumer code mixes REST and WS data.
- **`order_group_updates` sequence gap recovery** (`#205`). Same resubscribe
  helper as orderbook gaps; was missed events with no signal.
- **WS unsubscribe drops orderbook state** (`#206`). Long-running
  subscribe/unsubscribe cycles no longer leak `_BookState` entries.
- **ERROR backpressure strategy raises through iterator** (`#207`). Consumer
  `async for` now raises `KalshiBackpressureError` instead of terminating
  silently (indistinguishable from a clean close).

### Performance

- **WS recv loop stops rebuilding+discarding orderbook snapshots** (`#199`).
  New `_apply_*_inplace` variants on `OrderbookManager` skip the O(n log n)
  sort + ~2N OrderbookLevel allocations on the per-frame hot path.
- **Pluggable JSON loader/dumper** (`#209`). `KalshiConfig.ws_json_loads` /
  `ws_json_dumps` allow opt-in to `orjson` / `ujson` for high-rate
  streaming (default: stdlib `json`).
- **WS reconnect uses AWS Full Jitter** (`#221` polish). Matches the REST
  policy; eliminates the thundering-herd window at the capped-delay end.
- **Batch order bodies serialized once** (`#223` polish). Resource layer
  routes batch_create/batch_cancel through new `_post_json` / `_delete_with_body_json`
  bytes helpers that use `model_dump_json` + `httpx content=`, skipping one
  full dict-walk per call.
- **`_list_all` cursor-loop guard is O(1)** (`#223` polish). Switched from
  unbounded `set[str]` to single `last_cursor` (only catches realistic
  server-replay shape).

### Security & robustness

- **Response-body buffering bounded** (`#203`). `_map_error` caps via
  `Content-Length` (16KB) and truncates the exception message to 1024
  chars. Prevents memory + log-volume blowup on hostile error payloads.
- **`base_url` validated to include `/trade-api/v2`** (`#202`). Misconfigs
  fail at construction instead of producing silent 401s from a corrupted
  signing path.
- **Passphrase-protected PEMs supported** (`#217`). `KalshiAuth.from_pem` /
  `from_key_path` / `from_env` accept `password=` (str/bytes/callable);
  `KALSHI_PRIVATE_KEY_PASSPHRASE` env var. Users no longer need to write
  plaintext keys to disk.
- **URL-encoded path segments** (`#211`). `_seg()` helper applied across
  every resource — user-supplied IDs with `/`, `?`, `..` etc. are encoded
  or rejected at the SDK boundary.
- **RecordingTransport scrubs response headers** (`#220` polish).
  Set-Cookie, Authorization, and `X-Kalshi-*-(id|key|account|user)` headers
  filtered by default (user-overridable).

### Typed-exception expansion

- New `KalshiConflictError` (409), `KalshiTimeoutError`, `KalshiPoolExhaustedError`
  (`#201`, `#204`). 422 routes to `KalshiValidationError`. `httpx.PoolTimeout`
  raises `KalshiPoolExhaustedError` and IS safe to retry on POST/DELETE
  (request never reached the wire) — `httpx.TimeoutException` raises
  `KalshiTimeoutError` and preserves the existing POST/DELETE never-retry
  policy (server may have committed).
- `KalshiSequenceGapError` + `KalshiSubscriptionError` carry structured
  `channel` / `sid` / `last_seq` / `next_seq` / `op` context (`#213`).
- `AuthRequiredError` default message mentions both
  `KALSHI_PRIVATE_KEY_PATH` and `KALSHI_PRIVATE_KEY` (`#215`).

### Configuration knobs (additive, all opt-in)

- `total_timeout` (`#193`)
- `ws_ping_interval`, `ws_close_timeout` (`#208`)
- `ws_json_loads`, `ws_json_dumps` (`#209`)
- `http2` install extra (`#220` polish; `pip install kalshi-sdk[http2]`)
- Per-request `extra_headers` plumbed through transport (`#220` polish)

### Documentation

- `docs/migration.md` now has continuous coverage v1 → v2.3 (was missing
  v2.1→v2.2 and v2.2→v2.3 sections; `#200`) plus a v2.3→v2.4 section
  documenting #194's breaking shape and the new typed exceptions.
- README + `docs/websockets.md` agree on channel count + use real SDK
  method names (`#218`).
- New `docs/websockets.md` Performance section: queue sizing, overflow
  strategy, orjson example, recv-loop threading (`#222` polish).
- `docs/configuration.md`, `docs/environment-variables.md`, cancel/delete
  docstrings, and stale audit/predecessor refs cleaned up (`#222` polish).
- `pydantic.AwareDatetime` adopted on REST response model datetime fields;
  new datetime-semantics note in `docs/concepts.md` (`#221` polish).

### Testing

- WS hardening: 27+ new tests across orderbook resync, seq reset, close
  codes, backpressure signal, unsubscribe cleanup (`#231`).
- Phantom-kwarg behavioral coverage parametrized across all 23 Request
  models (`#219`).
- Three new bench harnesses: `scripts/bench_ws_recv.py`,
  `scripts/bench_orderbook_delta.py`, `scripts/bench_request_hot_path.py`
  (`#223`).
- Integration `conftest.py` env-bridging moved from import-time mutation
  to a session-scoped fixture for clean test isolation (`#223`).

### Breaking changes summary

Only one user-visible breaking change: `orders.batch_create` and
`orders.batch_cancel` return typed response models instead of `list[Order]`
and `None` respectively (`#194`). The V2 family (`batch_create_v2` /
`batch_cancel_v2`) was already shaped this way; the V1 fix brings parity.
Migration in `docs/migration.md` v2.3→v2.4 section.

## 2.3.0 — 2026-05-20

WS reliability + auth polish batch on top of v2.2.0's spec-required tightening.
The big-ticket items: per-sid bounded stash that closes a silent message-loss
window during reconnect bursts (`#176`), cooperative shutdown via
`run_forever(stop_event=...)` (`#177`), async RSA-PSS sign offload onto a
dedicated 2-worker executor so signs don't queue behind `getaddrinfo` during
reconnect storms (`#178`), and a `run_forever()` foot-gun fix that now raises
`KalshiSubscriptionError` instead of silently returning when no subscription
has landed (`#175`). Plus 226 spec-required fields tightened to non-optional
with hard-fail drift gates (`#172` via `#180`), all 49→91 REST contract-map
entries (`#171` via `#181`), the first two `server_omits_despite_required`
exclusions for fields the live demo omits (`#183`), `MessageQueue` `maxlen`
defense-in-depth (`#173`), `_to_decimal_*` consolidation (`#174`), and a
pre-release docs audit sweep across the full mkdocs site (`#179`).

Soft-breaking at the response-parse boundary only (per `#172`): server
omission of a previously-optional spec-required field now raises
`pydantic.ValidationError` instead of silently producing `field=None`.
Wire format unchanged.

### Pre-release docs audit (#179)

Release-prep sweep across all doc surfaces — README, mkdocs site, ROADMAP,
per-resource pages, and public-API docstrings. Findings compiled from a
six-way parallel audit of disjoint file partitions, then triaged:

- **`ROADMAP.md`** — "Open trackers" section dropped; `#45`, `#53` are
  closed and `#106` was a PR (not an issue) whose remaining sub-items all
  shipped in this batch. "Next milestone" carry-overs that landed
  (`MessageQueue` `maxlen`, `_coerce_decimal`, WS UX foot-guns,
  CONTRACT_MAP completeness via `#181`) removed. Closes `#179`.
- **`docs/resources/multivariate.md`** — fixed wrong endpoint path on
  `lookup_history` (was `/lookup_history`, actual is `/lookup` with a
  `lookback_seconds` query param) and a broken example that called
  `hist.lookups` on a list return.
- **`docs/index.md`** — REST coverage updated from "85 endpoints" to "98
  operations" against current spec; sync/async parity claim explicitly
  notes WebSocket is async-only.
- **`docs/websockets.md`** — new "Resubscribe-window frame stashing"
  subsection documenting the `#176` mechanism, `stash_maxlen` bound, and
  overflow logging.
- **`docs/authentication.md`** — new "Async RSA-PSS sign offload"
  subsection documenting `KalshiAuth.sign_request_async()` (`#178`) plus
  the dedicated `ThreadPoolExecutor` lifecycle.
- **`docs/configuration.md`** — new "Lifecycle" section documenting
  `client.close()` semantics and cross-linking the sign-executor teardown.
- **`docs/resources/events.md`** — note documenting `Event.product_metadata`
  and `EventMetadata.market_details` server-omission handling from `#183`.
- **`README.md`** — WS quickstart uses the package-level import
  (`from kalshi.ws import KalshiWebSocket`) instead of the deeper
  `kalshi.ws.client`; channel list clarifies that 11 of the 13 channels
  have dedicated `subscribe_*` methods and the remaining two ride the
  generic `subscribe()` escape hatch.

### WS resubscribe-window frame stashing (#176)

Fixes silent message loss during reconnect bursts on high-volume channels.
Previously, between ``SubscriptionManager._sid_to_client.clear()`` and the
new sid mapping landing in ``_wait_for_response``, any data frame the
server sent on the freshly-assigned sid was non-matching from the wait's
perspective and **discarded** with a debug log. Under market-burst
reconnects on ``ticker`` / ``trade`` / ``fill``, the SDK could drop tens
of messages per reconnect.

``SubscriptionManager`` now stashes those non-matching data frames in a
per-sid bounded deque (``stash_maxlen=1000`` per sid by default) for the
duration of ``resubscribe_all``. After resubscribe completes,
``KalshiWebSocket._handle_reconnect`` drains the stash through
``_process_frame`` so the frames flow through the normal dispatch path
— seq tracker advances, orderbook manager applies, iterator consumers
receive them in arrival order.

The drain coordinates with #139's seq-gap tracking: replayed frames
go through ``seq_tracker.track`` exactly once, so the first live frame
after resubscribe sees the right watermark and doesn't trip a spurious
gap on what would otherwise look like a seq 0 → N jump.

Stash bound: per-sid deque uses ``collections.deque(maxlen=stash_maxlen)``.
On overflow, oldest evicts (deque semantics) and a single WARNING per
fill event is logged so callers notice congestion. Memory is bounded at
``stash_maxlen * len(active_subs) * avg_frame_size`` worst-case.

Frames whose sid did not get re-mapped during ``resubscribe_all`` (a
per-sub failure that #77's F-P-01 isolates) are dropped on drain with a
debug log — there's no consumer to deliver them to.

Drive-by: ``SubscriptionManager._wait_for_response`` swapped two deprecated
``asyncio.get_event_loop().time()`` calls for ``asyncio.get_running_loop().time()``
(the correct API inside an ``async def``).

### WS `run_forever(stop_event=...)` cooperative shutdown (#177)

`KalshiWebSocket.run_forever()` now accepts an optional
`stop_event: asyncio.Event | None = None` parameter. When set — typically
from a SIGINT handler via `add_signal_handler(SIGINT, stop.set)` —
`run_forever()` clears `_running`, closes the connection, and drains the
recv loop via its existing `not self._running` branch. The recv task is
NOT cancelled, so no `CancelledError` leaks out.

```python
import asyncio, signal

stop = asyncio.Event()
asyncio.get_running_loop().add_signal_handler(signal.SIGINT, stop.set)

async with ws.connect() as session:
    await session.subscribe_ticker(tickers=["EXAMPLE-25-T"])
    await session.run_forever(stop_event=stop)
```

No behavior change when `stop_event` is omitted — external cancellation
still propagates as before, and the #175 "missing subscription" guard
remains in place.

### WS `run_forever()` raises on missing subscription (#175)

`KalshiWebSocket.run_forever()` previously returned immediately when no
`subscribe_*` call had landed — `_recv_task` was `None` and the silent
no-op masked a real user mistake. Documented as a known foot-gun in
`#106` F-P-16; the callback-style example in `docs/websockets.md`
propagated the trap.

Now raises `KalshiSubscriptionError` at the call site with an
actionable message:

> `run_forever() requires at least one active subscription. Call
> subscribe_ticker(...) / subscribe_trade(...) / etc. (or the generic
> subscribe(channel, ...)) before run_forever() so the recv loop has
> something to drain. Registering an @ws.on(channel) callback does not
> subscribe — the server only sends frames for channels you explicitly
> subscribe to.`

Docs updated: the callback example now shows the correct
`subscribe_ticker(...) → run_forever()` pairing with a comment
explaining that the iterator return value is unused (callbacks fan out
alongside it).

Soft-breaking: code that relied on `run_forever()` returning silently
as a sleep-until-disconnect for a connection it never intended to use
for streaming now raises. There's no production usage of that shape;
the foot-gun was the bug.

### Nightly integration server-omission fixes (#183)

First two `server_omits_despite_required` cases caught by the post-#172
nightly integration job (run #26141405845 against demo commit `788789c`):

- **`Event.product_metadata`** — spec marks `required: true` but the live
  demo server omits the key entirely on most events (Mars trip, Liverpool
  vs Manchester United, "Bitcoin price on Jan 12" and others). Reverted to
  `dict[str, Any] | None = None` and registered the deviation in
  `EXCLUSIONS` with `kind="server_omits_despite_required"`. This is the
  first usage of the new exclusion kind shipped in #172.
- **`EventMetadata.market_details`** — spec marks `required: true` (`list`)
  but the live demo server sends JSON `null` for the value. Swapped
  `list[MarketMetadata]` → `NullableList[MarketMetadata]`. The spec
  contract (key present) is still enforced; callers always see a list.

Together these unblock 20 cascading integration-test failures across
`tests/integration/test_events.py`, `test_markets.py`, and `test_series.py`
(every test that calls `events.get()`).

`test_exclusion_map_is_current` learned about `server_omits_despite_required`
as the inverse of the other model exclusion kinds: the SDK field still has
to be present (so we can parse responses when the server *does* send it) but
must be optional. Stale-exclusion detection now flags either side flipping.

### WS / auth polish batch (#173 + #174 + #178)

- **#173 — `MessageQueue` defense-in-depth.** The WS `MessageQueue` underlying
  `collections.deque` now carries `maxlen=maxsize+1` as a hard memory ceiling
  enforced by deque itself, independent of the manual `_size` counter. If the
  counter ever drifts (a put path that forgets to increment, an exception
  between append and increment) the buffer cannot grow without bound. New
  regression test in `tests/ws/test_backpressure.py` injects counter drift and
  asserts the cap holds. No observable behavior change in the passing path.
- **#174 — types consolidation.** `_to_decimal_dollars` and `_to_decimal_fp`
  were byte-identical apart from their docstrings. Collapsed into a single
  `_coerce_decimal` helper shared by both `DollarDecimal` and `FixedPointCount`.
  Public aliases unchanged; only the internal helper is shared.
- **#178 — async RSA-PSS sign offload.** Added `KalshiAuth.sign_request_async()`
  that routes the ~1-10 ms RSA-PSS sign through a **dedicated**
  `ThreadPoolExecutor(max_workers=2)` lazy-initialised on first use.

  Async REST (`AsyncTransport.request`) and async WS connect
  (`ConnectionManager._build_auth_headers`) now use the async sign path; the
  sync `sign_request` API is unchanged for sync-transport callers.

  The executor is dedicated (not asyncio's shared default pool) so signs
  don't queue behind `loop.getaddrinfo` / file I/O / other `to_thread()`
  work on a busy event loop — relevant during WS reconnect storms where
  cold DNS resolution (5-50 ms) dominates the sign cost. Per the community
  feedback on #178: a falsifiable microbench under `scripts/bench_sign_offload.py`
  uses real `loop.time()` deltas (NOT the `asyncio.sleep(0)` ticker which is
  special-cased and doesn't measure wall-clock blocking). Measured: inline
  p99=2.95 ms vs. offloaded p99=0.68 ms on a 2048-bit key.

  `KalshiClient.close()` / `AsyncKalshiClient.close()` now shut down the
  sign executor too; the executor is daemon-style and idempotent to close.


### Contract-map completeness (#171)

Maps the remaining 42 REST sub-models, V2 orders family, and internal
containers into `CONTRACT_MAP` (49 entries → 91). Promotes
`test_contract_map_completeness` from `warnings.warn` to `pytest.fail` so
the next unmapped model fails CI loudly.

`_get_schema_fields` / `_get_required_fields` gain a dotted-path syntax
(`Parent.field.items`) so inline-object schemas the spec doesn't name at the
top level (`Batch*OrdersV2*` per-entry shapes) can still flow through the
drift pipeline.

Newly-surfaced drift caught by mapping these models:

- `BidAskDistribution` (OHLC): all four price fields tightened to required.
- `PriceDistribution`: gains 4 v3.18.0 spec fields (`mean_dollars`,
  `previous_dollars`, `min_dollars`, `max_dollars`), all optional per spec.
- `Candlestick`: 6 fields tightened to required.
- `MarketMetadata`: `image_url` + `color_code` tightened.
- `Schedule` / `WeeklySchedule`: tightened.
- `PositionsResponse`, `EventCandlesticks`, `ForecastPercentilesPoint`:
  tightened.
- `AssociatedEvent` (multivariate): `is_yes_only` + `active_quoters` tightened.
- `LookupPoint` (multivariate): `selected_markets` + `last_queried_ts` tightened.

`OrderbookLevel` is mapped to spec's `PriceLevelDollarsCountFp`, a positional
2-tuple `["<dollars_string>", "<fp_count_string>"]`. The SDK wraps it as a
named `{price, quantity}` object — no field-by-field comparison possible.
`_get_schema_fields` returns `{}` for the array-typed spec schema, so drift
checks skip it cleanly.

Fixture builders for `Candlestick`, `BidAskDistribution`, `PriceDistribution`
added to `tests/_model_fixtures.py` (3 new). Test fixtures parsing
`Candlestick` / `EventCandlesticks` / `MarketCandlesticks` now use those
builders.

### Required-but-optional drift closure (#172)

Required-but-optional drift closure (#172). Drops `None` defaults on 226
spec-required Pydantic model fields across 34 response models (21 REST, 13
WS). The SDK now matches the OpenAPI v3.18.0 / AsyncAPI v0.14 `required` set
on the wire. Promotes `test_required_drift` and `test_ws_required_drift`
from warning to hard CI failure, closing the regression class that allowed
required-but-typed-Optional fields to drift unnoticed.

### Breaking (response-parse side)

- **226 fields are no longer `Optional[T] | None` in response models** —
  see the full list per model in #172. Wire format is unchanged; the SDK
  now refuses to parse responses that omit a spec-required field, where
  previously the field defaulted to `None`. If the live server omits a
  spec-required field, `pydantic.ValidationError` is raised on parse.
- **`CreateOrderRequest.action` no longer defaults to `"buy"`** — callers
  constructing the request model directly must pass `action` explicitly.
  The `OrdersResource.create(action=None, ...)` kwarg path still defaults
  to `"buy"` for back-compat; only the model-construction surface changed.
- **Test fixtures constructing these models with partial dicts will
  raise `ValidationError`.** A new helper module `tests/_model_fixtures`
  provides complete spec-shaped builders (`market_dict`, `order_dict`,
  `fill_dict`, etc.) that accept `**overrides` for fields tests care about.

### Changed

- `test_required_drift` (REST) and `test_ws_required_drift` (WS) promoted
  from `warnings.warn` to `pytest.fail`. Future drift on these gates is
  CI-blocking.
- New `ExclusionKind` value `"server_omits_despite_required"` registered
  in `tests/_contract_support.py` for fields the spec marks required but
  the live server omits. Entries MUST cite a demo+prod observation.

### Migration

- Code that builds these models from server responses: no change. The
  server-side wire shape is what it always was — the SDK type just stopped
  lying about which fields are guaranteed.
- Code that builds these models in tests / mocks / fixtures: pass all
  spec-required fields, or use the `tests/_model_fixtures` builders. The
  builders are test-only (live under `tests/`, never shipped in the
  wheel) — production code does not import them.
- Callers who relied on `Optional` narrowing (`if order.outcome_side is
  not None: ...`) can drop the guard. `mypy --strict` will now flag the
  redundant check.

### Affected models

21 REST (136 fields): `Market`, `Order`, `Fill`, `MultivariateEventCollection`,
`Settlement`, `Trade`, `Event`, `Series`, `MarketPosition`, `EventPosition`,
`EventMetadata`, `Milestone`, `SportFilterDetails`, `IncentiveProgram`,
`ApiKey`, `SeriesFeeChange`, `MarketCandlesticks`, `ScopeList`,
`GetOrderGroupResponse`, `CreateOrderGroupResponse`, `CreateOrderRequest`.

13 WS payloads (90 fields): `UserOrdersPayload`, `FillPayload`,
`TickerPayload`, `TradePayload`, `MarketPositionsPayload`,
`QuoteExecutedPayload`, `QuoteCreatedPayload`, `QuoteAcceptedPayload`,
`MultivariatePayload`, `RfqCreatedPayload`, `RfqDeletedPayload`,
`MarketLifecyclePayload`, `OrderGroupPayload`.

## 2.2.0 — 2026-05-19

Response-side spec drift hardening stack (#157). Backfills the remaining
v3.18.0 OpenAPI / v0.14 AsyncAPI fields across REST and WebSocket response
models (65 new optional fields across 16 models), promotes additive
drift from warning to hard CI failure, and lands a high-signal bugfix
for the subaccount-number request constraint that was rejecting valid
server-assigned values.

### Added

- `Market` gains 11 spec fields, `Order` gains 8, `Fill` gains 4 (#159).
- `Event` gains 3, `EventMetadata` 2, `Settlement` 1, `Trade` 2,
  `IncentiveProgram` 1 (#160).
- `RFQ` gains 1, `Quote` 3, `OrderGroup` 1, `GetOrderGroupResponse` 1,
  `CreateOrderGroupResponse` 2 (#161).
- 33 fields across 11 WebSocket payload models (#162) — Unix-ms
  timestamps (`*_ts_ms`), `outcome_side` / `book_side` direction
  encoding, MVE linkage, and RFQ/Quote context echoes.
- `ErrorPayload` registered in `WS_CONTRACT_MAP` so WS contract coverage
  is complete.

### Changed

- Response-side additive spec drift now **hard-fails CI** (was a
  warning). Closes the regression path that allowed
  `Balance.balance_dollars` to ship missing in v2.1.0 across five
  rounds of review. Intentional deviations require an entry in
  `EXCLUSIONS` (`tests/_contract_support.py`) with a typed `kind` and
  `reason`.
- Unmapped SDK models (REST + WS) also now hard-fail — same regression
  surface.
- WS envelope and helper models now use `extra="allow"`, matching the
  WS payload policy from #143. Closes the matching ROADMAP item.
- Required-but-Optional drift stays as warning-only (~204 entries;
  separate policy decision).

### Fixed

- Subaccount-number request fields no longer cap at 32. Demo allocates
  ephemeral subaccount numbers above 32 (observed: 41), but the SDK was
  rejecting them client-side with a ``ValidationError`` because seven
  request-side model fields carried a ``le=32`` bound derived from spec
  prose. The actual OpenAPI schema defines no upper bound; only the
  description text mentions ``1-32``. Affected fields:
  ``ApplySubaccountTransferRequest.{from,to}_subaccount``,
  ``UpdateSubaccountNettingRequest.subaccount_number``,
  ``CreateOrderRequest.subaccount``,
  ``BatchCancelOrdersV2RequestOrder.subaccount``,
  ``CreateRFQRequest.subaccount``,
  ``CreateQuoteRequest.subaccount``.
  The ``ge=0`` lower bound is unchanged. Unblocks the
  ``test_transfer_between_subaccounts`` nightly integration test (#164).

## 2.1.0 — 2026-05-18

OpenAPI spec sync from v3.13.0 → v3.18.0. Adds the V2 event-market
orders family, deposits/withdrawals history, account endpoint-cost
introspection, and several optional query / body fields. Also fixes
a recurring false-alarm in the weekly spec-sync workflow.

### Added

- **V2 event-market orders** (`/portfolio/events/orders/*`). Legacy
  `/portfolio/orders` will be deprecated no earlier than May 6, 2026.
  - `orders.create_v2(request=CreateOrderV2Request(...))`
  - `orders.cancel_v2(order_id, subaccount=..., exchange_index=...)`
  - `orders.amend_v2(order_id, request=AmendOrderV2Request(...))`
  - `orders.decrease_v2(order_id, request=DecreaseOrderV2Request(...))`
  - `orders.batch_create_v2(request=BatchCreateOrdersV2Request(...))`
  - `orders.batch_cancel_v2(request=BatchCancelOrdersV2Request(...))`
- `portfolio.deposits()` / `portfolio.deposits_all()` — deposit history.
- `portfolio.withdrawals()` / `portfolio.withdrawals_all()` — withdrawal history.
- `account.endpoint_costs()` — lists endpoints whose token cost differs from the default.
- Optional `exchange_index` on `CreateOrderRequest`, `AmendOrderRequest`,
  `DecreaseOrderRequest`, `BatchCancelOrdersRequestOrder`, `CreateOrderGroupRequest`,
  and as a query kwarg on `orders.cancel` / `order_groups.delete`.
- Optional `user_filter` on `communications.list_rfqs` / `list_all_rfqs`;
  `user_filter` + `rfq_user_filter` on `communications.list_quotes` / `list_all_quotes`.
- Optional `incentive_description` on `incentive_programs.list` / `list_all`.
- Optional `post_only` on `CreateQuoteRequest`.
- `Balance.balance_dollars` (required, `DollarDecimal`) — the same value as
  `balance` (cents) rendered as a fixed-point dollar string. Required in
  the v3.18.0 spec for `GetBalanceResponse`.
- `Balance.balance_breakdown` (optional, `list[IndexedBalance]`) — splits
  the balance across exchange shards when present.
- New `IndexedBalance` model (`exchange_index`, `balance`) exposed from
  `kalshi` and `kalshi.models`.

### Changed

- ``Balance`` gained a required ``balance_dollars: DollarDecimal`` field
  (added by spec v3.18.0). Callers who construct ``Balance`` from API
  responses are unaffected — the server now guarantees the field. But
  callers who build ``Balance(...)`` instances directly in their own
  tests or mocks will hit ``ValidationError`` until they add it. This is
  a soft breaking change at the model-construction surface; the field is
  required because the spec marks it ``required``, not optional-in-practice.

  ```python
  # before v2.1.0
  Balance(balance=50000, portfolio_value=75000, updated_ts=ts)

  # v2.1.0+
  Balance(
      balance=50000,
      balance_dollars=Decimal("500.00"),  # new required field
      portfolio_value=75000,
      updated_ts=ts,
  )
  ```

### Migration note

- ``CreateOrderV2Request.client_order_id`` is **required**. V1's
  ``CreateOrderRequest`` made it optional, so callers migrating from
  ``orders.create()`` to ``orders.create_v2()`` must generate a unique
  client-order-id per call (UUID4 is the common choice). The server uses
  this field as the V2 idempotency key, so reusing a value will cause
  the server to return the original order rather than placing a new one.

### Fixed

- `specs/asyncapi.yaml` is now committed as a pinned snapshot, matching the
  long-standing intent on `specs/openapi.yaml`. The weekly spec-sync workflow
  no longer reports a bogus "AsyncAPI 0 → 13 channels" delta every Monday
  (the file was previously gitignored, so each cron diffed the fresh
  download against a non-existent old file).

## 2.0.0 — 2026-05-17

Audit-driven hardening release. 30 audit-findings landed across five
parallel waves (Wave 1 – Wave 5) plus follow-ups: a WebSocket recv-loop
overhaul, a spec-sync supply-chain rewrite, double-parse/double-validate
elimination on the WS hot path, and surface-level cleanup including
three deliberate breaking changes called out below.

### Breaking

- **`AccountApiLimits.read_limit` / `.write_limit` removed.** Replaced with
  `AccountApiLimits.read` / `.write`, both of type `RateLimit`
  (`bucket_capacity: int`, `refill_rate: int`). The published OpenAPI spec
  declares the limits as ints, but the live server returns nested token
  buckets — v2 matches the server. The old int fields never worked against
  the live API.

  ```python
  # v1
  limits = client.account.limits()
  limits.read_limit   # AttributeError after upgrade

  # v2
  limits.read.bucket_capacity   # int
  limits.read.refill_rate       # int
  ```

- **`Order.type` renamed to `Order.order_type`.** Wire format is unchanged
  (`validation_alias=AliasChoices("type", "order_type")` accepts both names
  on deserialization), but any user code reading `.type` on an `Order`
  instance must migrate to `.order_type`. Matches the project's existing
  builtin-shadow-avoidance convention (`milestone_type`, `target_type`,
  `incentive_type`). Spec v3.13.0 still defines `type` as required, so the
  field is preserved on the wire — only the Python attribute name changed
  (#91).

  ```python
  # v1
  order = client.portfolio.orders.get(order_id="...")
  print(order.type)        # AttributeError after upgrade

  # v2
  print(order.order_type)
  ```

- **Count/size/volume response fields retyped `DollarDecimal` → `FixedPointCount`
  (#90).** Fields with `_fp` wire aliases were annotated as the type that
  signals "dollar amount." Runtime behavior is unchanged (both validators
  resolve to `Decimal`), but the annotation now communicates the right
  semantics. `mypy --strict` users may need to update narrow assertions;
  `isinstance(x, Decimal)` remains valid. Affected: `Market.{yes_bid_size,
  yes_ask_size, no_bid_size, no_ask_size, volume, volume_24h, open_interest}`,
  `Candlestick.{volume, open_interest}`, `OrderbookLevel.quantity`,
  `Fill.count`, `Trade.count`, `MarketPosition.position`,
  `EventPosition.total_cost_shares`, `Settlement.{yes_count, no_count}`,
  `Series.volume`.

### Added

- **`max_pages: int | None` kwarg on every public `*_all()` method** — sync
  and async (19 + 19 method signatures). Bounded iteration without manual
  pagination. `None` (default) iterates until the server returns no cursor
  (#98).
- **`RateLimit` model** exposed via `kalshi.RateLimit` — represents the
  per-direction token-bucket structure on `AccountApiLimits.read` / `.write`.
- **`KalshiConfig.http2` and `KalshiConfig.limits`** — opt-in HTTP/2 and
  `httpx.Limits` (connection pool sizing, keep-alive) on the transport.
  Defaults preserve existing behavior (#141, F-R-15).
- **23 model classes re-exported from `kalshi.__all__`** — every name in
  `kalshi.models.__all__` is now also importable from the top-level
  `kalshi` package. New dynamic parity test enforces the invariant (#89).
- **`ConnectionManager.mark_streaming()`** public API — replaces the
  recv-loop's prior `_set_state` reach-through (#88).

### Changed

- **`*_all()` methods are now unbounded by default.** Previous internal
  1000-page cap silently truncated callers iterating beyond ~100k items.
  The cursor-repeat guard remains the runaway protection it always was.
  Callers wanting a cap pass `max_pages=N` explicitly (#98).
- **All response models uniformly use `extra="allow"` (#114).** Previously
  5 response models (`Page`, `Orderbook`, `OrderbookLevel`,
  `BidAskDistribution`, `PriceDistribution`) fell back to Pydantic's default
  `extra="ignore"`, silently dropping unknown fields. They now preserve
  them on `__pydantic_extra__`. Request bodies remain `extra="forbid"`.
  Drift guard test (`tests/test_model_extra_policy.py`) enforces the
  policy across every exported model.
- **WS callbacks no longer suppress queue delivery (#80).** Previously,
  registering a callback for a channel silently disabled the iterator
  queue for that channel — a user holding both an `@on()` callback AND an
  iterator on the same channel would never see the iterator fire. Now
  messages fan out to both. A WARNING is logged at `register_callback`
  time if an active subscription already exists, so upgraders see the
  signal. Callback-only users now accumulate up to `maxsize=1000` (existing
  `DROP_OLDEST` backpressure prevents unbounded growth).
- **`OrderbookManager` returns fresh snapshots instead of mutating in
  place (#85).** Consumers holding a reference to a previously-emitted
  `Orderbook` no longer see leaked mutations on the next delta.
- **`KalshiConfig` validates `base_url` and `ws_base_url`** at construction
  time. Non-`https`/`wss` to remote hosts is rejected; loopback HTTP/WS
  permitted for local mock servers. Unknown but secure hosts log a
  WARNING (proxies still work). Trailing slashes are normalized (#94).

### Fixed

- **`/account/limits` response now parses against the live server.** The
  published OpenAPI spec declares `read_limit`/`write_limit` as ints, but
  the live API returns nested `read`/`write` token-bucket objects.
  `AccountApiLimits` now matches the server.
- **`/search/tags_by_categories` no longer crashes** when a category (e.g.
  `Social`) returns `null` instead of an empty list. `tags_by_categories`
  values are now `NullableList[str]`, collapsing `null` → `[]`.
- **WS recv-loop reconnect/resubscribe correctness** — 5 race conditions
  fixed (per-sub isolation in resubscribe-all, `_subscribe_lock` covering
  the full reconnect+resubscribe sequence, `asyncio.shield` around the
  recv→dispatch critical section, `ConnectionClosed` surfacing as
  `KalshiConnectionError`, sentinel-before-cleanup ordering in
  `unsubscribe`) (#77).
- **WS recv-loop exception ladder narrowed** — `KalshiBackpressureError` /
  `KalshiSubscriptionError` break the loop and broadcast sentinels to all
  consumers; `json.JSONDecodeError` / `pydantic.ValidationError` / `KeyError`
  log+continue; unexpected exceptions broadcast sentinels then re-raise
  (#83).
- **WS server-initiated unsubscribe reaps `_sid_to_client`** mappings
  alongside the subscription, and resets `SequenceTracker._last_seq[sid]`
  via the now-wired `seq_tracker` kwarg (#81).
- **WS channel-level error envelopes surface via `on_error`** instead of
  being silently dropped, with a fallback log if no handler is registered
  (#82).
- **WS seq watermark rolls back on backpressure** — `_process_frame`
  captures the pre-`track` watermark and restores it if dispatch raises
  `KalshiBackpressureError`, so the dropped message stays visible as a
  future gap rather than being silently treated as already-seen (#78).
- **WS multi-ticker seq-gap clears every ticker** in the affected
  subscription instead of only `tickers[0]` (#79).
- **`Retry-After` parser rejects negative, NaN, and infinite values**
  (busy-loop / sleep-crash / cap-bypass) and honors `Retry-After: 0`
  end-to-end through the retry loop (was dropped by a falsy-check) (#96).
- **`Page.to_dataframe()` / `.to_polars()` nested-model serialization**
  pinned by tests; behavior is now under regression guard (#101).
- **WS double-parse + double-validate eliminated** — recv loop parses
  JSON once and hands the parsed dict (plus a `pre_validated` typed
  message for orderbook channels) to the dispatcher (#86).

### Security

- **Spec-sync workflow hardened against upstream compromise.** Reduced
  permissions from `contents: write + pull-requests: write` to
  `contents: read + issues: write`. Removed automatic PR creation and
  in-CI code-generation. Drift now opens a new `spec-drift`-labeled issue
  per distinct fingerprint (sha256 of upstream specs), deduped to prevent
  spam. SHA-pinned all third-party actions. Body rendered via Python
  template (no shell expansion of upstream content) (#92).
- **URL leakage scrubbed from `KalshiError.__str__`** — httpx exception
  strings include the full request URL with query parameters, which
  surfaced credentials in Sentry/log sinks. Surface method + path only
  (no host, no query); the underlying exception is on `__cause__`. Same
  fix in `KalshiConnectionError` for the WebSocket connect path (#84
  F-O-09).
- **Trade-data leakage scrubbed from WS dispatch log** — Pydantic's
  `ValidationError.__str__` echoes the full input including trade
  payload (price, count, user identifiers). Dropped `exc_info=True` on
  the failure log; surface type + exception class only (#84 F-O-05).
- **Claude action workflows SHA-pinned** + Dependabot enabled + nightly
  `pip-audit` workflow added (#93, #95).
- **Integration-nightly workflow shreds the PEM** on exit so a paused
  job can't leak the demo private key (#106 F-O-11).
- **PyPI release workflow uploads sigstore attestations** for trusted
  publisher verification (#106 F-O-12).
- **pytest bumped to `>=9,<10`** to clear CVE-2025-71176 (predictable
  `/tmp/pytest-of-{user}` directory on UNIX) (#123).

### Performance

- **`MessageQueue.qsize()` O(n) → O(1)** via a counter updated on
  put/get/`__anext__`/DROP_OLDEST eviction (#103).
- **REST retry backoff switched to AWS Full Jitter** —
  `uniform(0, min(cap, base * 2**attempt))`, cap applied before
  randomization (#104).
- **`RecordingTransport` O(N²) → amortized O(1) per request** — buffered
  in-memory, flushed on close instead of rewriting the recording on
  every request (#105).
- **`OrderbookManager.apply_delta` O(n) → O(1)** via a price-indexed
  dict, materializing sorted level lists lazily on snapshot emit (#87).
- **Transport caches `urlparse(base_url).path` once** instead of
  re-parsing per request (#106 F-R-04).

### Internal

- **`kalshi/__init__.py` re-export parity** — 23 model classes now
  re-exported from the top-level package with a dynamic parity test
  that prevents silent drift (#89).
- **`ExclusionKind = "client_only"`** for SDK-only kwargs with no spec
  counterpart (e.g. `max_pages`). Distinguishes from `paginator_handled`
  (spec params the SDK hides).
- **`tests/integration/helpers.py`** gained `wait_for_resource` /
  `await_resource` for demo's eventual-consistency lag on
  `POST → GET-by-id` (orders / order_groups). Fixes 11 integration
  failures that surfaced after configuring the demo secrets in CI.
- **`tests/integration/test_subaccounts.py`** ephemeral fixture polls
  `list_balances` for the new subaccount instead of asserting immediate
  visibility.
- **Test count delta: 1407 → 1808** (+401 across all waves).
- **Dependency-resolution drift fix**: pinned `ast-serialize<0.5` (a
  transitive of mypy 2.1) whose 0.5.0 release dropped `cp39-abi3`
  wheels, breaking CI on Python 3.12/3.13.

### Migration

See [`docs/migration.md`](docs/migration.md) for a focused v1.x → v2.0
migration guide.

## 1.1.0 — 2026-05-16

Post-1.0 enhancements and polish. 17 issues closed across four parallel waves of
work. No breaking changes to runtime behavior; two mypy-level type-system
tightenings are called out below.

### Added

- **Model-first request API.** Every POST/PUT/DELETE-with-body resource method
  now accepts a pre-built request model as an alternative to individual kwargs.
  Backward-compatible — the existing kwarg form continues to work unchanged
  (#56).

  ```python
  client.orders.amend(request=AmendOrderRequest(order_id=..., yes_price=...))
  client.orders.amend(order_id=..., yes_price=...)  # also works
  ```

  Each method has typed `@overload` stubs (32 methods × 2 = 64 stubs) so mypy
  catches misuse at type-check time, not runtime.

- **DataFrame integration.** `Page[T]` gained `.to_dataframe()` and
  `.to_polars()` methods with optional dependency extras (#12):

  ```bash
  pip install 'kalshi-sdk[pandas]'   # or [polars] or [all]
  ```

  ```python
  page = client.markets.list(limit=100)
  df = page.to_dataframe()
  ```

  Lazy imports; `Decimal` and `datetime` preserved as native types via
  `model_dump(mode="python")`.

- **Record / replay mock transport** (`kalshi.testing`) for offline integration
  testing (#13). `RecordingTransport` proxies real calls and saves
  request/response pairs as JSON; `ReplayTransport` serves the fixtures with
  no network. Sync and async transports both supported; signature/timestamp
  headers are excluded from fingerprinting so signatures can drift between
  record and replay.

  ```python
  with KalshiClient.from_env(transport=RecordingTransport("fixtures")) as c:
      c.exchange.status()  # records once

  with KalshiClient(transport=ReplayTransport("fixtures")) as c:
      c.exchange.status()  # offline replay
  ```

- **Typed `Literal` aliases for fixed-enum kwargs** (#50). 13 new aliases
  exported from `kalshi` and `kalshi.models`: `SideLiteral`, `ActionLiteral`,
  `TimeInForceLiteral`, `SelfTradePreventionTypeLiteral`, `OrderStatusLiteral`,
  `EventStatusLiteral`, `MarketStatusLiteral`, `MveFilterLiteral`,
  `MveHistoricalFilterLiteral`, `MultivariateCollectionStatusLiteral`,
  `IncentiveProgramStatusLiteral`, `IncentiveProgramTypeLiteral`,
  `SettlementStatusLiteral`. mypy now catches typos in resource kwargs at
  authoring time.

- **MkDocs documentation site** (#14, #57). Material theme + mkdocstrings;
  Getting Started, Authentication, WebSockets, Resources, Errors, Migration
  guides plus auto-generated API reference. GitHub Pages deploy workflow at
  `.github/workflows/docs.yml`.

- **Constructor-variant integration tests** (#54). Exercises every supported
  `KalshiClient` construction path against the demo API (`from_env`,
  `key_id + private_key_path`, in-memory PEM string, pre-built `KalshiAuth`,
  `demo=True`). Includes an async sibling test to catch signing-path drift.

- **Per-method auth guards on `markets.orderbook`** (#49). Spec walk confirmed
  this was the only public-resource GET endpoint missing `_require_auth()`;
  unauthenticated callers now get a clear `AuthRequiredError` instead of a
  confusing 401 from Kalshi.

### Changed

- **Sync/async dedup refactor** (#46). Extracted shared body-builder,
  query-param-builder, and response-parser helpers across 13 resource modules.
  Dispatcher logic and request-model construction now exist once per
  method-pair instead of twice. Sync/async signatures, `@overload` stubs, and
  the `async for item in client.markets.list_all():` ergonomic are all
  preserved.

- **Async `OrdersResource.batch_cancel` routed through shared
  `_delete_with_body` helper** (#47). Previously called the transport directly,
  bypassing the sync path's helper; any future retry / error-mapping change to
  the helper now applies to both transports symmetrically.

- **Sync `test_list_all` iteration idiom standardized** (#48). Sync tests now
  use the same manual-counter loop as their async siblings; cosmetic only.

### Fixed

- **Async `multivariate.lookup_tickers` 204 spec-drift guard** (#72). Sync had
  a clear `RuntimeError("spec drift: ...")` on an unexpected 204; async would
  surface a confusing `TypeError` from `model_validate(None)`. Extracted a
  shared `_parse_lookup_tickers_response` helper so both paths share the
  guard.

### Test infrastructure

- **Typed `ExclusionKind`** discriminator on contract drift exclusions (#51).
  Replaces the free-text `reason` substring matching in
  `test_exclusion_map_is_current` with explicit
  `Literal["body_param", "spec_deprecated", "paginator_handled",
  "wire_normalization", "kwarg_rename"]` classification. All 47 existing
  exclusions reclassified.

- **Nested-model body-drift detection** (#52). The drift test now recurses
  into nested `BaseModel` fields (e.g. `TickerPair` inside
  `CreateMarketInMultivariateEventCollectionRequest.selected_markets`).
  `TickerPair.extra="allow"` intentionally preserved because `LookupPoint`
  responses echo provider keys; the existing pin test documents the carve-out.

- **`kwarg_rename` `ExclusionKind`** split out of `wire_normalization` (#68).
  Python-naming-hygiene renames (`milestone_type`, `target_type`,
  `incentive_type` — spec field `type` shadows the builtin) are now
  classified separately from wire-format normalization.

### Infrastructure

- **Weekly OpenAPI + AsyncAPI spec sync CI** (#16). Cron + manual dispatch
  workflow snapshots both specs, regenerates models, runs ruff / mypy /
  pytest, opens a PR with version + endpoint diff if any changes detected.
  Third-party actions pinned to commit SHAs because the workflow holds
  `contents: write` + `pull-requests: write`. Concurrency-guarded against
  same-branch races.

- **Nightly integration CI** against the demo API (#55). Secret-gated, skips
  cleanly on forks, dedupes failure issues by stable title.

### mypy-only breaking changes

These tighten types without changing runtime behavior. Existing valid calls are
unaffected; the type system will now reject calls that would have failed at
runtime anyway (or that were always wrong but mypy couldn't see it).

- `Page[T]` TypeVar tightened from `TypeVar("T")` to
  `TypeVar("T", bound=BaseModel)`. Matches the bound already used inside
  `kalshi/resources/_base.py` and the actual usage pattern across the SDK
  (every concrete `Page[X]` parameterizes with a `BaseModel` subclass).
- Resource-method kwargs for the 13 enum fields above are now `Literal[...]`
  instead of `str | None`. Callers passing arbitrary strings (typos, in-flight
  variable values) now fail at mypy-check time.

### Coverage at 1.1.0

- 89/89 REST endpoints implemented (sync + async); auth-guard audit complete
  across public resources.
- 11 WebSocket channels with sequence-gap detection, configurable backpressure,
  and automatic reconnection.
- **1407 unit tests passing** (1455 collected, 48 skipped — up from 899 at
  1.0.0), mypy `--strict` clean (76 source files), ruff clean.
- Drift tests now detect query/path/body/WS-payload schema drift _and_ nested
  body-model drift.
- Optional extras: `pandas`, `polars`, `all`, `docs`.

## 1.0.0 — 2026-05-10

First stable release. No behavioral changes from 0.15.0 — this release marks
the public API surface as stable for semantic versioning.

### Added
- `LICENSE` file (MIT) — declared in `pyproject.toml` since 0.1.0 but not
  shipped as a file; now included at repo root and in both wheel
  (`dist-info/licenses/LICENSE`) and sdist artifacts (#42).
- `README.md` — install, sync + async quickstart, env-var auth, demo vs
  production, public/unauthenticated usage, order placement, WebSocket
  streaming, error hierarchy, retry policy, pagination (#41).
- `docs/RELEASING.md` — one-time PyPI trusted-publisher setup runbook plus
  cut-a-release procedure.
- `.github/workflows/release.yml` — tag-triggered release pipeline:
  tag/version drift check, `uv build`, `twine check`, PyPI publish via
  trusted publishing (OIDC, no token in repo secrets), GitHub Release
  with CHANGELOG-extracted body and artifacts attached (#15).
- `[project.urls]` extended from 3 → 6 keys (`Issues`, `Changelog`,
  `PyPI`); `Documentation` retargeted to README anchor (#44).

### Changed
- `Development Status` classifier bumped from `3 - Alpha` to
  `5 - Production/Stable` (#43).

### Coverage at 1.0.0
- 89/89 REST endpoints implemented (sync + async). 67 with live
  integration tests; 20 SDK+unit only; 2 auth-gated (demo cannot
  authenticate); 1 demo-broken (server-side).
- 12 WebSocket message types dispatched with spec-aligned envelope and
  payload types. 14 integration tests; 3 frame types live-verified.
- 899 unit tests, mypy `--strict` clean, ruff clean, contract drift
  tests on query/path/body/WS-payload schemas.

## 0.15.0 — 2026-04-19

### Fixed — WebSocket payload type drift

Closes the payload-type class of bug surfaced (but not resolved) during v0.14.0. v0.14.0 fixed the envelope-type drift (dispatcher routing) but left a parallel payload-type drift intact: SDK modeled `_dollars`-aliased fields as `int` and several `ts` fields as `int | None`, while demo sends dollar-decimal strings (`"0.0100"`) and RFC3339 date-time strings (`"2026-04-19T23:14:30.160405Z"`). Pydantic rejected real frames at `model_validate`, so the dispatcher continued to silently drop every `orderbook_delta` frame and every `user_order` frame. Live-captured evidence on demo, fix verified via provoke probes (1 orderbook_snapshot + 1 orderbook_delta + 2 user_order frames round-trip cleanly after the fix).

- **`OrderbookDeltaPayload`** — `price: int` → `DollarDecimal`; `delta: int` → `FixedPointCount` (Decimal-backed, spec `delta_fp` format); `ts: int | None` → `str | None` (RFC3339).
- **`OrderbookSnapshotPayload`** — `yes: list[list[int]]` / `no: list[list[int]]` → `list[tuple[str, str]]` (spec `yes_dollars_fp` / `no_dollars_fp` is `[price_in_dollars, count_fp]` string pairs with `minItems: 2, maxItems: 2`). Tuple type enforces the exact-2-element arity that list-of-list silently tolerated; a malformed 3-element row now fails at `model_validate` instead of crashing the downstream iterator.
- **`UserOrdersPayload`** — `yes_price: int | None` → `DollarDecimal | None`; `taker_fill_cost`, `maker_fill_cost`, `taker_fees`, `maker_fees` promoted from `str | None` to `DollarDecimal | None` (CLAUDE.md price convention).
- **`MarketPositionsPayload`** — `position_cost`, `realized_pnl`, `fees_paid`, `position_fee_cost` promoted from `str | None` to `DollarDecimal | None`.
- **`FillPayload.fee_cost`** — promoted from `str | None` to `DollarDecimal | None`.
- **`MarketLifecyclePayload.settlement_value`** — promoted from `str | None` to `DollarDecimal | None`.
- **`RfqCreatedPayload.target_cost`**, **`QuoteCreatedPayload.{yes_bid,no_bid}`**, **`QuoteAcceptedPayload.{yes_bid,no_bid}`** — promoted from `str | None` to `DollarDecimal | None`. Completes the CLAUDE.md price convention across every `_dollars`-aliased WS payload field — downstream consumers doing Decimal math no longer hit `TypeError: unsupported operand type(s) for +: 'str' and 'Decimal'`.
- **`TickerPayload`** — `yes_bid`, `yes_ask`, `no_bid`, `no_ask` from `int | None` to `DollarDecimal | None`.
- **`TradePayload`** — `yes_price`, `no_price` from `int | None` to `DollarDecimal | None`.
- **`FillPayload`** — `yes_price: int | None` → `DollarDecimal | None`.
- **`RfqCreatedPayload.created_ts`**, **`RfqDeletedPayload.deleted_ts`**, **`QuoteCreatedPayload.created_ts`**, **`QuoteExecutedPayload.executed_ts`** — `int | None` → `str | None` (spec says `string, format: date-time`). **Caveat: spec-aligned, no live capture.** The communications channel was quiet on demo during v0.15.0 work. If demo follows the v0.14.0 `user_orders` precedent (emits `created_ts_ms` as integer milliseconds instead of the spec'd ISO string), these fields will reject the frame. Monitor with the drift test — a future live capture can confirm or defer to `extra="allow"` pickup. Matches the v0.14.0 pattern for `market_position` / `multivariate_lookup` envelope types (spec-inferred, no live evidence).

### Changed — OrderbookManager works in dollars + contracts directly

`OrderbookManager.apply_snapshot` / `apply_delta` previously assumed cents integers on the wire and divided by 100 to produce dollar Decimals, and treated `quantity` as dollar-denominated. With the payload fix, both wire values are already decimal strings (`price_dollars` for price, `delta_fp` for count). Manager now uses the Decimal directly, no conversion. Quantity is now correctly a contract count (e.g. `Decimal("100")`), not a dollar amount.

### Added — drift-test coverage for payload-level types

- **`test_ws_payload_field_type_drift`** in `tests/test_contracts.py` — parametrized over `WS_CONTRACT_MAP`, hard-fails if an SDK field's Python type conflicts with the AsyncAPI spec schema type for three specific patterns: `_dollars`-aliased string field typed as `int`, `date-time` string field typed as `int`, or array-of-strings field typed as `list[list[int]]`. Would have blocked the v0.14.0 envelope-only PR; reduces the blast radius of this class of drift to one parametrized test case per model.
- Helpers `_unwrap_annotation`, `_sdk_type_kind`, `_spec_property_kind`, `_ws_field_type_violations` — type-kind comparison infrastructure reusable for future spec-alignment work.

### Verified

Live-captured on demo 2026-04-19: `orderbook_snapshot` (quiet market, empty rows) and `orderbook_delta` (`price=Decimal('0.0100')`, `delta='1.00'`, `ts='2026-04-19T23:14:30.160405Z'`) parse cleanly; `user_order` placement + cancel frames both parse (`yes_price=Decimal('0.0100')`). All 1378 unit tests green; mypy strict clean on `kalshi/`.

## 0.14.0 — 2026-04-19

### Fixed
- WebSocket dispatcher silently dropped `user_orders` / `market_positions` / `multivariate` frames because `MESSAGE_MODELS` keyed on the channel name (plural) instead of the envelope `type` const (singular per AsyncAPI spec). Confirmed live on demo for `user_orders` via a provoke probe — demo emits `"type":"user_order"` singular. Resolved by aligning SDK to spec across all three channels.

### Added
- `scripts/ws_capture.py` — one-shot demo WS frame dumper used for evidence gathering. Autoloads `.env`; refuses non-demo URLs; prints raw JSONL to stdout.
- `scripts/ws_provoke_user_order.py` — order-lifecycle probe that subscribes to `user_orders` raw WS, places a non-marketable limit order via REST, and captures the resulting frames.
- 11 new WebSocket integration tests covering every currently-dispatched message type end-to-end. Each skips cleanly on demo silence within its respective timeout window.
- Hard-assertion drift guard: `test_ws_envelope_type_drift` now fails on any new spec/SDK envelope-type mismatch not on the (currently-empty) `_DEMO_DIVERGENCE_ALLOWLIST`.

### Known Limitations
- Envelope-type drift is fixed (the dispatcher now routes `user_order` / `market_position` / `multivariate_lookup` frames to the correct Message class), but a separate payload-type drift remains. `OrderbookDeltaPayload.price` and `UserOrdersPayload.yes_price` are typed `int` — demo sends dollar-decimal strings (`"0.0200"`, `"0.0100"`). `ts` fields across payloads are typed `int | None` — demo sends ISO datetime strings. Pydantic rejects these frames at `model_validate`, so the dispatcher continues to silently drop `orderbook_delta` and `user_order` frames. Net user-visible behavior for those channels is unchanged until v0.15.0 fixes the payload types. Of the 14 WS integration tests shipped, only `test_ws_connect_and_auth` currently passes against live demo; 13 skip on timeout because the dispatcher drops every subscribed payload. Tracked as v0.15.0 in TODOS.md.

## [0.13.0] — 2026-04-19

### Added — REST coverage to 100%

Final push to close the North Star goal (every OpenAPI REST operation has SDK + unit + integration tests). Adds 10 endpoints across 5 new resources plus 2 extensions to existing ones.

**New resources (5):**

- **`AccountResource`** — `GET /account/limits` returns API tier limits (usage_tier, read_limit, write_limit) for the authenticated user. Wired as `client.account`.
- **`StructuredTargetsResource`** — `GET /structured_targets` (paginated list with ids/type/competition filters, page_size 1–2000) and `GET /structured_targets/{id}`. Structured targets are external entities (players, teams, tournaments) markets can anchor to; `details` is flexible JSON keyed by target type. Wired as `client.structured_targets`. `type` query param renamed to `target_type` (avoid Python built-in shadow).
- **`FcmResource`** — `GET /fcm/orders` and `GET /fcm/positions`, both filtered by required `subtrader_id`. FCM-only endpoints; response envelopes reuse existing `Order` and `PositionsResponse` shapes. Wired as `client.fcm`.
- **`SearchResource`** — `GET /search/tags_by_categories` (category → tag-list mapping) and `GET /search/filters_by_sport` (sport → filter/competition mapping + display ordering). Both unauthenticated. Wired as `client.search`.
- **`IncentiveProgramsResource`** — `GET /incentive_programs` (status/type/limit filters up to 10 000) with `IncentiveProgram` model (centi-cent `period_reward`, nullable `discount_factor_bps` and `target_size_fp`). Unique wire shape: this endpoint paginates on `next_cursor` (not `cursor` like every other Kalshi endpoint); resource hand-rolls Page wrapping to handle the difference. `type` query param renamed to `incentive_type`. Wired as `client.incentive_programs`.

**Extensions (2):**

- **`exchange.user_data_timestamp()`** — `GET /exchange/user_data_timestamp` reports the upper bound of lag between exchange state and user-scoped REST endpoints (GetBalance, GetOrders, GetFills, GetPositions). Combine with WebSocket feeds for a live view. New `UserDataTimestamp` model.
- **`portfolio.total_resting_order_value()`** — `GET /portfolio/summary/total_resting_order_value`. FCM-member only (spec: "intended for FCM members, rare"); non-FCM accounts receive 403 on both demo and prod. Integration test marked `@pytest.mark.integration_real_api_only` — skipped under the default run, opt-in via `KALSHI_ENABLE_REAL_API_ONLY=1`.

### Infrastructure

- **Coverage harness resource count: 14 → 19.** All new resources register in `RESOURCE_MODULES` and `SCENARIO_REGISTRY`.
- **Contract map entries: +7** (UserDataTimestamp, AccountApiLimits, StructuredTarget, SportFilterDetails, ScopeList, IncentiveProgram, TotalRestingOrderValue).
- **METHOD_ENDPOINT_MAP entries: +13** covering all new sync resource methods; async siblings auto-derived.
- **EXCLUSIONS entries: +16** (type-rename shadow avoidance on structured_targets/incentive_programs, paginator-handled cursors on new list_all methods).
- **Demo verification.** All 10 endpoints reach demo; 2 are auth-gated (total_resting_order_value + FCM endpoints with non-FCM account). Verified against Path B audit (2026-04-18).

### Counts

- 45 new unit tests across 7 new/extended test modules.
- 25 new integration tests (22 run on demo; 3 gated behind `integration_real_api_only`).
- Total suite: 827 → **~900 tests.**
- FULL-covered REST endpoints: 57 → **67** (75%+); the remaining gaps are all WebSocket (deferred to v0.14.0).

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

Followup polish (fourth review round):

- **`GetApiKeysResponse.api_keys` now uses `NullableList[ApiKey]`** — last remaining envelope-level list in this PR using plain `list[ApiKey]`. Brings the API Keys envelope in line with `GetMilestonesResponse`, `GetLiveDatasResponse`, and the Milestone/LiveData nested lists, so a server-sent `{"api_keys": null}` coerces to `[]` instead of raising a Pydantic `ValidationError`. Regression test added: `test_list_handles_null_api_keys`.
- **`CreateApiKeyRequest.public_key` docstring** — now specifies "PEM-encoded RSA public key" so callers know the expected format without having to round-trip to the server.

Followup polish (fifth review round):

- **`ApiKey.scopes` and `MarketCandlesticks.candlesticks` now use `NullableList`** — last two remaining bare `list[T]` fields on response models in this PR. Swept for consistency with the rest of the SDK. Server-sent `null` for either field now coerces to `[]` instead of raising Pydantic `ValidationError`. Two new regression tests: `test_list_handles_null_scopes` and `test_bulk_candlesticks_handles_null_candlesticks`.

Followup polish (sixth review round):

- **`GenerateApiKeyResponse.private_key` is now `pydantic.SecretStr`** — the PEM private key field is returned once and never retrievable again. Plain `str` would appear verbatim in any `repr()`, `str()`, or incidental log call of the response model. Wrapping with `SecretStr` masks it as `'**********'` in those contexts; callers retrieve the PEM via `response.private_key.get_secret_value()`. Docstring updated with usage note. Breaking for pre-release callers accessing `response.private_key` directly as a string (integration test + 3 unit tests updated in this PR).
- **`_orderbook_from_item` redundant `or []` removed** — `ob.get("yes", [])` already returned `[]` on missing key, making the third `or []` clause dead. Simplified to `ob.get("yes_dollars") or ob.get("yes") or []` for cleaner reading.
- **`_iso()` docstring clarifies string passthrough** — callers passing pre-stringified dates must ensure RFC3339 compliance themselves. Only `datetime` inputs get the UTC coercion guarantee.

Followup polish (seventh review round):

- **`MilestonesResource.get()` now uses `GetMilestoneResponse`** — the envelope model existed only for contract-map purposes; the resource bypassed it via `data.get("milestone", data)`. Now uses `GetMilestoneResponse.model_validate(data).milestone` for consistency with every other envelope-in-use pattern. A server response missing `"milestone"` now raises Pydantic `ValidationError` naming the field — clearer than the old fallback's silent whole-dict revalidation.
- **`_orderbook_from_item` now raises `KalshiError` instead of `ValueError`** — malformed server response is a protocol violation, not a user error. Matches the SDK-wide "catch `KalshiError` to handle SDK errors" contract. Regression test updated; three new direct unit tests for the helper cover missing-key, empty-string-ticker, and happy-path shapes.
- **`bulk_candlesticks` ticker count now splits + filters empty segments** — a pre-joined string like `"A,B,,"` previously counted as 4 (comma count + 1); now counts 2 real tickers. Tightens the 100-ticker cap against trailing/consecutive comma bypasses without waiting on the deferred `_join_tickers` validation work.
- **`MilestonesResource.list` RFC3339 docstring** — call-site now surfaces the `_iso()` string-passthrough limitation: pass `datetime` for guaranteed UTC, strings travel verbatim.

Followup polish (eighth review round):

- **[MED] Async `bulk_candlesticks` ticker-count bug** — the split+filter ticker-count fix from the seventh round only landed on the sync path; the async counterpart still used the naive `joined.count(",") + 1` formula. Trailing-comma strings like `"A,B,,"` would spuriously fail async calls with `ValueError` (counted as 4, not 2); `,`.join([""] * 99) + "A,B"` would wrongly pass (100 commas, 2 real tickers). Now sync and async share the same `sum(1 for t in joined.split(",") if t.strip())` counter. Three new async regression tests in `TestAsyncMarketsBulkCandlesticksValidation` cover over-100 list, over-100 string, and trailing-comma happy path.

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
