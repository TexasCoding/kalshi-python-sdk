# Kalshi REST API — Endpoint Audit

**Source of truth:** `specs/openapi.yaml` (title: *Kalshi Trade API Manual Endpoints*, version **3.13.0**, OpenAPI 3.0.0).
**Base URL:** `https://api.elections.kalshi.com/trade-api/v2` (paths below are relative to this prefix).
**SDK coverage source:** `tests/_contract_support.py` (`METHOD_ENDPOINT_MAP`, `EXCLUSIONS`).
**All data below sourced from local files** — no live WebFetch was required; the checked-in spec files are authoritative for this audit.

---

## 1. Full endpoint list (REST)

### Tag: `historical` (7)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/historical/cutoff` | GetHistoricalCutoff | Get Historical Cutoff Timestamps |
| GET | `/historical/markets` | GetHistoricalMarkets | Get Historical Markets |
| GET | `/historical/markets/{ticker}` | GetHistoricalMarket | Get Historical Market |
| GET | `/historical/markets/{ticker}/candlesticks` | GetMarketCandlesticksHistorical | Get Historical Market Candlesticks |
| GET | `/historical/fills` | GetFillsHistorical | Get Historical Fills |
| GET | `/historical/orders` | GetHistoricalOrders | Get Historical Orders |
| GET | `/historical/trades` | GetTradesHistorical | Get Historical Trades |

### Tag: `exchange` (5)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/exchange/status` | GetExchangeStatus | Get Exchange Status |
| GET | `/exchange/announcements` | GetExchangeAnnouncements | Get Exchange Announcements |
| GET | `/series/fee_changes` | GetSeriesFeeChanges | Get Series Fee Changes *(tagged `exchange` despite `/series/` path)* |
| GET | `/exchange/schedule` | GetExchangeSchedule | Get Exchange Schedule |
| GET | `/exchange/user_data_timestamp` | GetUserDataTimestamp | Get User Data Timestamp |

### Tag: `orders` (11)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/portfolio/orders` | GetOrders | Get Orders |
| POST | `/portfolio/orders` | CreateOrder | Create Order |
| GET | `/portfolio/orders/{order_id}` | GetOrder | Get Order |
| DELETE | `/portfolio/orders/{order_id}` | CancelOrder | Cancel Order |
| POST | `/portfolio/orders/batched` | BatchCreateOrders | Batch Create Orders |
| DELETE | `/portfolio/orders/batched` | BatchCancelOrders | Batch Cancel Orders |
| POST | `/portfolio/orders/{order_id}/amend` | AmendOrder | Amend Order |
| POST | `/portfolio/orders/{order_id}/decrease` | DecreaseOrder | Decrease Order |
| GET | `/portfolio/orders/queue_positions` | GetOrderQueuePositions | Get Queue Positions for Orders |
| GET | `/portfolio/orders/{order_id}/queue_position` | GetOrderQueuePosition | Get Order Queue Position |

*(10 rows; `/portfolio/fills` is tagged `portfolio`, see below.)*

### Tag: `order-groups` (7)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/portfolio/order_groups` | GetOrderGroups | Get Order Groups |
| POST | `/portfolio/order_groups/create` | CreateOrderGroup | Create Order Group |
| GET | `/portfolio/order_groups/{order_group_id}` | GetOrderGroup | Get Order Group |
| DELETE | `/portfolio/order_groups/{order_group_id}` | DeleteOrderGroup | Delete Order Group |
| PUT | `/portfolio/order_groups/{order_group_id}/reset` | ResetOrderGroup | Reset Order Group |
| PUT | `/portfolio/order_groups/{order_group_id}/trigger` | TriggerOrderGroup | Trigger Order Group |
| PUT | `/portfolio/order_groups/{order_group_id}/limit` | UpdateOrderGroupLimit | Update Order Group Limit |

### Tag: `portfolio` (10)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/portfolio/balance` | GetBalance | Get Balance |
| POST | `/portfolio/subaccounts` | CreateSubaccount | Create Subaccount |
| POST | `/portfolio/subaccounts/transfer` | ApplySubaccountTransfer | Transfer Between Subaccounts |
| GET | `/portfolio/subaccounts/balances` | GetSubaccountBalances | Get All Subaccount Balances |
| GET | `/portfolio/subaccounts/transfers` | GetSubaccountTransfers | Get Subaccount Transfers |
| PUT | `/portfolio/subaccounts/netting` | UpdateSubaccountNetting | Update Subaccount Netting |
| GET | `/portfolio/subaccounts/netting` | GetSubaccountNetting | Get Subaccount Netting |
| GET | `/portfolio/positions` | GetPositions | Get Positions |
| GET | `/portfolio/settlements` | GetSettlements | Get Settlements |
| GET | `/portfolio/summary/total_resting_order_value` | GetPortfolioRestingOrderTotalValue | Get Total Resting Order Value |
| GET | `/portfolio/fills` | GetFills | Get Fills |

*(11 rows.)*

### Tag: `api-keys` (4)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/api_keys` | GetApiKeys | Get API Keys |
| POST | `/api_keys` | CreateApiKey | Create API Key |
| POST | `/api_keys/generate` | GenerateApiKey | Generate API Key |
| DELETE | `/api_keys/{api_key}` | DeleteApiKey | Delete API Key |

### Tag: `search` (2)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/search/tags_by_categories` | GetTagsForSeriesCategories | Get Tags for Series Categories |
| GET | `/search/filters_by_sport` | GetFiltersForSports | Get Filters for Sports |

### Tag: `account` (1)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/account/limits` | GetAccountApiLimits | Get Account API Limits |

### Tag: `market` (8)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/markets` | GetMarkets | Get Markets |
| GET | `/markets/{ticker}` | GetMarket | Get Market |
| GET | `/markets/{ticker}/orderbook` | GetMarketOrderbook | Get Market Orderbook |
| GET | `/markets/orderbooks` | GetMarketOrderbooks | Get Multiple Market Orderbooks |
| GET | `/markets/trades` | GetTrades | Get Trades |
| GET | `/markets/candlesticks` | BatchGetMarketCandlesticks | Batch Get Market Candlesticks |
| GET | `/series/{series_ticker}/markets/{ticker}/candlesticks` | GetMarketCandlesticks | Get Market Candlesticks |
| GET | `/series/{series_ticker}` | GetSeries | Get Series *(tagged `market`)* |
| GET | `/series` | GetSeriesList | Get Series List *(tagged `market`)* |

*(9 rows.)*

### Tag: `events` (5)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/events` | GetEvents | Get Events |
| GET | `/events/multivariate` | GetMultivariateEvents | Get Multivariate Events |
| GET | `/events/{event_ticker}` | GetEvent | Get Event |
| GET | `/events/{event_ticker}/metadata` | GetEventMetadata | Get Event Metadata |
| GET | `/series/{series_ticker}/events/{ticker}/candlesticks` | GetMarketCandlesticksByEvent | Get Event Candlesticks |
| GET | `/series/{series_ticker}/events/{ticker}/forecast_percentile_history` | GetEventForecastPercentilesHistory | Get Event Forecast Percentile History |

*(6 rows.)*

### Tag: `live-data` (4)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/live_data/milestone/{milestone_id}` | GetLiveDataByMilestone | Get Live Data |
| GET | `/live_data/{type}/milestone/{milestone_id}` | GetLiveData | Get Live Data (with type) |
| GET | `/live_data/batch` | GetLiveDatas | Get Multiple Live Data |
| GET | `/live_data/milestone/{milestone_id}/game_stats` | GetGameStats | Get Game Stats |

### Tag: `incentive-programs` (1)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/incentive_programs` | GetIncentivePrograms | Get Incentives |

### Tag: `fcm` (2)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/fcm/orders` | GetFCMOrders | Get FCM Orders |
| GET | `/fcm/positions` | GetFCMPositions | Get FCM Positions |

### Tag: `structured-targets` (2)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/structured_targets` | GetStructuredTargets | Get Structured Targets |
| GET | `/structured_targets/{structured_target_id}` | GetStructuredTarget | Get Structured Target |

### Tag: `milestone` (2)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/milestones` | GetMilestones | Get Milestones |
| GET | `/milestones/{milestone_id}` | GetMilestone | Get Milestone |

### Tag: `communications` (11)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/communications/id` | GetCommunicationsID | Get Communications ID |
| GET | `/communications/rfqs` | GetRFQs | Get RFQs |
| POST | `/communications/rfqs` | CreateRFQ | Create RFQ |
| GET | `/communications/rfqs/{rfq_id}` | GetRFQ | Get RFQ |
| DELETE | `/communications/rfqs/{rfq_id}` | DeleteRFQ | Delete RFQ |
| GET | `/communications/quotes` | GetQuotes | Get Quotes |
| POST | `/communications/quotes` | CreateQuote | Create Quote |
| GET | `/communications/quotes/{quote_id}` | GetQuote | Get Quote |
| DELETE | `/communications/quotes/{quote_id}` | DeleteQuote | Delete Quote |
| PUT | `/communications/quotes/{quote_id}/accept` | AcceptQuote | Accept Quote |
| PUT | `/communications/quotes/{quote_id}/confirm` | ConfirmQuote | Confirm Quote |

### Tag: `multivariate` (5)

| Method | Path | operationId | Summary |
|---|---|---|---|
| GET | `/multivariate_event_collections` | GetMultivariateEventCollections | Get Multivariate Event Collections |
| GET | `/multivariate_event_collections/{collection_ticker}` | GetMultivariateEventCollection | Get Multivariate Event Collection |
| POST | `/multivariate_event_collections/{collection_ticker}` | CreateMarketInMultivariateEventCollection | Create Market In Multivariate Event Collection |
| PUT | `/multivariate_event_collections/{collection_ticker}/lookup` | LookupTickersForMarketInMultivariateEventCollection | Lookup Tickers For Market In Multivariate Event Collection |
| GET | `/multivariate_event_collections/{collection_ticker}/lookup` | GetMultivariateEventCollectionLookupHistory | Get Multivariate Event Collection Lookup History |

---

## 2. WebSocket channels

**Source:** `specs/asyncapi.yaml` (title: *Kalshi Market Data WebSocket API*, version **2.0.0**, AsyncAPI 3.0.0).
**URL:** `wss://api.elections.kalshi.com/trade-api/ws/v2`.

### Connection channels

| Address | Title | Purpose |
|---|---|---|
| `/` | WebSocket Connection | Authenticated WebSocket handshake (tagged `control-frames` / `commands`) |
| `/` | Connection Keep-Alive | Ping/Pong keep-alive frames |

### Data channels (public + private)

| Address | Title | Purpose |
|---|---|---|
| `orderbook_delta` | Orderbook Updates | Real-time incremental orderbook deltas |
| `ticker` | Market Ticker | Market ticker updates (price, volume, open interest) |
| `trade` | Public Trades | Public trade stream |
| `fill` | User Fills | **Authenticated** — fills for the authenticated user's orders |
| `market_positions` | Market Positions | **Authenticated** — user's open positions |
| `market_lifecycle_v2` | Market & Event Lifecycle | Market/event status transitions (open, closed, settled) |
| `multivariate_market_lifecycle` | Multivariate Market & Event Lifecycle | Lifecycle for multivariate markets |
| `multivariate` | Multivariate Lookups | Multivariate lookup updates |
| `communications` | Communications | **Authenticated** — RFQ/Quote flow notifications |
| `order_group_updates` | Order Group Updates | **Authenticated** — order group state changes |
| `user_orders` | User Orders | **Authenticated** — user's order lifecycle updates |

### Command / response operations

Client-to-server commands: `Send Ping`, `Send Pong`, `Subscribe to Channels`, `Unsubscribe from Channels`, `List Subscriptions`, `Update Subscription - Add Markets`, `Update Subscription - Delete Markets`, `Update Subscription - Single SID`.

Server-to-client responses: `Receive Ping`, `Receive Pong`, `Subscription Confirmed`, `Unsubscription Confirmed`, `Update Confirmed`, `List Subscriptions Response`.

---

## 3. Coverage metadata

### Totals

| Metric | Count |
|---|---|
| Distinct paths in spec | 77 |
| Total operations in spec (unique `(method, path)`) | **89** |
| `MethodEndpointEntry` rows in `METHOD_ENDPOINT_MAP` | 108 |
| Distinct `(method, path)` tuples in `METHOD_ENDPOINT_MAP` | **89** |

> The 108→89 reduction is expected: `list` + `list_all` variants share the same endpoint, as do `fills` + `fills_all`, `markets` + `markets_all`, etc.

### Spec endpoints NOT in `METHOD_ENDPOINT_MAP` (gaps)

**None.** Diff of `set(spec_operations) - set(map_endpoints)` is empty. Every `(METHOD, path)` in the spec is registered in `METHOD_ENDPOINT_MAP`.

### `METHOD_ENDPOINT_MAP` entries NOT in spec (extras)

**None.** Diff of `set(map_endpoints) - set(spec_operations)` is empty.

### `EXCLUSIONS` — intentional deviations

`EXCLUSIONS` has **48 entries**. They split into two classes:

- **34 method-level** entries (keyed on a `METHOD_ENDPOINT_MAP` `sdk_method` FQN) — paginator ergonomics + Python built-in shadow-avoidance.
- **14 model-level** entries (keyed on a request-body model FQN, not a map entry) — wire-format normalizations on POST/PUT body models.

#### Method-level exclusions that shadow `METHOD_ENDPOINT_MAP` entries

| SDK method FQN | Param | Reason |
|---|---|---|
| `kalshi.resources.markets.MarketsResource.list_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.markets.MarketsResource.list_trades_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.events.EventsResource.list_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.events.EventsResource.list_all_multivariate` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.historical.HistoricalResource.markets_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.historical.HistoricalResource.fills_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.historical.HistoricalResource.orders_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.historical.HistoricalResource.trades_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.orders.OrdersResource.list_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.orders.OrdersResource.fills_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.orders.OrdersResource.batch_cancel` | `orders` | body param (BatchCancelOrdersRequest.orders); not query/path |
| `kalshi.resources.portfolio.PortfolioResource.settlements_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.multivariate.MultivariateCollectionsResource.list_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.communications.CommunicationsResource.list_all_rfqs` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.communications.CommunicationsResource.list_all_quotes` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.subaccounts.SubaccountsResource.list_all_transfers` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.milestones.MilestonesResource.list_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.structured_targets.StructuredTargetsResource.list_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.fcm.FcmResource.orders_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.incentive_programs.IncentiveProgramsResource.list_all` | `cursor` | paginator-handled; not a caller-facing kwarg on list_all |
| `kalshi.resources.live_data.LiveDataResource.get_typed` | `type` | SDK kwarg named milestone_type (not type) to avoid built-in shadow |
| `kalshi.resources.live_data.LiveDataResource.get_typed` | `milestone_type` | SDK renamed from spec's `{type}` path segment to avoid shadowing the Python built-in |
| `kalshi.resources.milestones.MilestonesResource.list` | `type` | SDK kwarg named milestone_type (not type) to avoid built-in shadow |
| `kalshi.resources.milestones.MilestonesResource.list` | `milestone_type` | SDK renamed from spec's `type` query param to avoid shadowing built-in |
| `kalshi.resources.milestones.MilestonesResource.list_all` | `type` | SDK kwarg named milestone_type (not type) to avoid built-in shadow |
| `kalshi.resources.milestones.MilestonesResource.list_all` | `milestone_type` | SDK renamed from spec's `type` query param to avoid shadowing built-in |
| `kalshi.resources.structured_targets.StructuredTargetsResource.list` | `type` | SDK kwarg named target_type (not type) to avoid built-in shadow |
| `kalshi.resources.structured_targets.StructuredTargetsResource.list` | `target_type` | SDK renamed from spec's `type` query param to avoid shadowing built-in |
| `kalshi.resources.structured_targets.StructuredTargetsResource.list_all` | `type` | SDK kwarg named target_type (not type) to avoid built-in shadow |
| `kalshi.resources.structured_targets.StructuredTargetsResource.list_all` | `target_type` | SDK renamed from spec's `type` query param to avoid shadowing built-in |
| `kalshi.resources.incentive_programs.IncentiveProgramsResource.list` | `type` | SDK kwarg named incentive_type (not type) to avoid built-in shadow |
| `kalshi.resources.incentive_programs.IncentiveProgramsResource.list` | `incentive_type` | SDK renamed from spec's `type` query param to avoid shadowing built-in |
| `kalshi.resources.incentive_programs.IncentiveProgramsResource.list_all` | `type` | SDK kwarg named incentive_type (not type) to avoid built-in shadow |
| `kalshi.resources.incentive_programs.IncentiveProgramsResource.list_all` | `incentive_type` | SDK renamed from spec's `type` query param to avoid shadowing built-in |

#### Model-level exclusions (request-body field overrides)

| Model FQN | Field | Reason |
|---|---|---|
| `kalshi.models.orders.CreateOrderRequest` | `yes_price` | cent form redundant with yes_price_dollars; SDK sends dollars |
| `kalshi.models.orders.CreateOrderRequest` | `no_price` | cent form redundant with no_price_dollars; SDK sends dollars |
| `kalshi.models.orders.CreateOrderRequest` | `sell_position_floor` | deprecated in spec (only accepts 0); superseded by reduce_only |
| `kalshi.models.orders.CreateOrderRequest` | `count` | SDK emits count_fp (serialization_alias); Kalshi accepts either |
| `kalshi.models.orders.AmendOrderRequest` | `yes_price` | cent form redundant with yes_price_dollars |
| `kalshi.models.orders.AmendOrderRequest` | `no_price` | cent form redundant with no_price_dollars |
| `kalshi.models.orders.AmendOrderRequest` | `count` | SDK emits count_fp (serialization_alias); Kalshi accepts either |
| `kalshi.models.orders.DecreaseOrderRequest` | `reduce_by_fp` | FixedPointCount variant; SDK emits integer form only; _fp deferred |
| `kalshi.models.orders.DecreaseOrderRequest` | `reduce_to_fp` | FixedPointCount variant; SDK emits integer form only; _fp deferred |
| `kalshi.models.orders.BatchCancelOrdersRequest` | `ids` | deprecated spec field; SDK v0.8.0 migrated to preferred `orders` |
| `kalshi.models.order_groups.CreateOrderGroupRequest` | `contracts_limit_fp` | FixedPointCount variant; SDK emits integer only (v0.10.0) |
| `kalshi.models.order_groups.UpdateOrderGroupLimitRequest` | `contracts_limit_fp` | FixedPointCount variant; SDK emits integer only (v0.10.0) |
| `kalshi.models.communications.CreateRFQRequest` | `contracts_fp` | FixedPointCount variant; SDK emits integer only (v0.11.0) |
| `kalshi.models.communications.CreateRFQRequest` | `target_cost_centi_cents` | deprecated in spec; superseded by target_cost_dollars |

---

## Summary

- **Endpoint coverage is 100%.** All 89 spec operations are registered in `METHOD_ENDPOINT_MAP`. There are no missing endpoints and no phantom endpoints.
- **All deviations are field/kwarg-level**, not endpoint-level — captured in the 48-entry `EXCLUSIONS` allowlist with documented reasons.
- **No REST surface gap exists** at the spec-operation granularity. Any further audit (missing query params, schema drift on response models, etc.) operates below this layer.
