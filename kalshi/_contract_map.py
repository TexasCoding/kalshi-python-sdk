"""Contract map: hand-written SDK models → OpenAPI schema components.

The map links each hand-written model to its OpenAPI schema name.
Field aliases are auto-extracted from Pydantic model_fields at test time
(via validation_alias / serialization_alias), NOT duplicated here.

Only the sdk_model → spec_schema mapping and intentional exclusions live here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractEntry:
    """Maps one hand-written model to its OpenAPI schema."""

    sdk_model: str  # e.g., "kalshi.models.markets.Market"
    spec_schema: str  # e.g., "Market" (OpenAPI component name)
    ignored_fields: frozenset[str] = frozenset()
    notes: str = ""


# One entry per hand-written model that maps to a spec schema.
# Add entries as new resources are built.
CONTRACT_MAP: list[ContractEntry] = [
    ContractEntry(
        sdk_model="kalshi.models.markets.Market",
        spec_schema="Market",
        notes="DollarDecimal fields use short names with _dollars/_fp aliases",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.Order",
        spec_schema="Order",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.Fill",
        spec_schema="Fill",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.CreateOrderRequest",
        spec_schema="CreateOrderRequest",
        notes="Uses serialization_alias (outbound), not validation_alias (inbound)",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.AmendOrderResponse",
        spec_schema="AmendOrderResponse",
        notes="Response wrapper with old_order + order, both are Order instances",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.OrderQueuePosition",
        spec_schema="OrderQueuePosition",
    ),
    ContractEntry(
        sdk_model="kalshi.models.events.Event",
        spec_schema="EventData",
        notes="Spec uses 'EventData', not 'Event'",
    ),
    ContractEntry(
        sdk_model="kalshi.models.events.EventFeeChange",
        spec_schema="EventFeeChange",
    ),
    ContractEntry(
        sdk_model="kalshi.models.exchange.ExchangeStatus",
        spec_schema="ExchangeStatus",
    ),
    ContractEntry(
        sdk_model="kalshi.models.portfolio.Balance",
        spec_schema="GetBalanceResponse",
        notes="Spec wraps balance in GetBalanceResponse, not a standalone Balance schema",
    ),
    ContractEntry(
        sdk_model="kalshi.models.portfolio.MarketPosition",
        spec_schema="MarketPosition",
    ),
    ContractEntry(
        sdk_model="kalshi.models.portfolio.EventPosition",
        spec_schema="EventPosition",
    ),
    ContractEntry(
        sdk_model="kalshi.models.portfolio.Settlement",
        spec_schema="Settlement",
    ),
    ContractEntry(
        sdk_model="kalshi.models.historical.Trade",
        spec_schema="Trade",
    ),
    # Sub-models (no aliases, but track for field presence drift)
    ContractEntry(
        sdk_model="kalshi.models.markets.Orderbook",
        spec_schema="MarketOrderbookFp",
        notes="Spec uses 'MarketOrderbookFp', SDK uses 'Orderbook'",
    ),
    ContractEntry(
        sdk_model="kalshi.models.exchange.Announcement",
        spec_schema="Announcement",
    ),
    ContractEntry(
        sdk_model="kalshi.models.historical.HistoricalCutoff",
        spec_schema="GetHistoricalCutoffResponse",
        notes="Spec wraps in GetHistoricalCutoffResponse, not standalone",
    ),
    ContractEntry(
        sdk_model="kalshi.models.events.EventMetadata",
        spec_schema="GetEventMetadataResponse",
        notes="Spec wraps in GetEventMetadataResponse, not standalone",
    ),
    ContractEntry(
        sdk_model="kalshi.models.series.Series",
        spec_schema="Series",
        notes="volume uses DollarDecimal with _fp alias",
    ),
    ContractEntry(
        sdk_model="kalshi.models.series.SeriesFeeChange",
        spec_schema="SeriesFeeChange",
    ),
    ContractEntry(
        sdk_model="kalshi.models.multivariate.MultivariateEventCollection",
        spec_schema="MultivariateEventCollection",
    ),
    ContractEntry(
        sdk_model="kalshi.models.multivariate.TickerPair",
        spec_schema="TickerPair",
    ),
    ContractEntry(
        sdk_model="kalshi.models.communications.RFQ",
        spec_schema="RFQ",
        notes="contracts/target_cost use short names with _fp/_dollars aliases",
    ),
    ContractEntry(
        sdk_model="kalshi.models.communications.Quote",
        spec_schema="Quote",
        notes="bid/contracts fields use short names with _dollars/_fp aliases",
    ),
    ContractEntry(
        sdk_model="kalshi.models.communications.CreateRFQRequest",
        spec_schema="CreateRFQRequest",
        notes="Uses serialization_alias (outbound) for target_cost → target_cost_dollars",
    ),
    ContractEntry(
        sdk_model="kalshi.models.communications.CreateQuoteRequest",
        spec_schema="CreateQuoteRequest",
        notes="Spec wire uses yes_bid/no_bid without _dollars suffix (unlike other requests)",
    ),
    ContractEntry(
        sdk_model="kalshi.models.communications.AcceptQuoteRequest",
        spec_schema="AcceptQuoteRequest",
    ),
    ContractEntry(
        sdk_model="kalshi.models.subaccounts.SubaccountBalance",
        spec_schema="SubaccountBalance",
        notes="balance uses DollarDecimal; updated_ts is Unix int",
    ),
    ContractEntry(
        sdk_model="kalshi.models.subaccounts.SubaccountTransfer",
        spec_schema="SubaccountTransfer",
    ),
    ContractEntry(
        sdk_model="kalshi.models.subaccounts.SubaccountNettingConfig",
        spec_schema="SubaccountNettingConfig",
    ),
    ContractEntry(
        sdk_model="kalshi.models.subaccounts.ApplySubaccountTransferRequest",
        spec_schema="ApplySubaccountTransferRequest",
    ),
    ContractEntry(
        sdk_model="kalshi.models.subaccounts.UpdateSubaccountNettingRequest",
        spec_schema="UpdateSubaccountNettingRequest",
    ),
    ContractEntry(
        sdk_model="kalshi.models.api_keys.ApiKey",
        spec_schema="ApiKey",
    ),
    ContractEntry(
        sdk_model="kalshi.models.api_keys.CreateApiKeyRequest",
        spec_schema="CreateApiKeyRequest",
    ),
    ContractEntry(
        sdk_model="kalshi.models.api_keys.CreateApiKeyResponse",
        spec_schema="CreateApiKeyResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.models.api_keys.GenerateApiKeyRequest",
        spec_schema="GenerateApiKeyRequest",
    ),
    ContractEntry(
        sdk_model="kalshi.models.api_keys.GenerateApiKeyResponse",
        spec_schema="GenerateApiKeyResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.models.milestones.Milestone",
        spec_schema="Milestone",
        notes="details is dict[str, Any] per spec additionalProperties:true",
    ),
    ContractEntry(
        sdk_model="kalshi.models.live_data.LiveData",
        spec_schema="LiveData",
        notes="details is dict[str, Any] per spec additionalProperties:true",
    ),
    ContractEntry(
        sdk_model="kalshi.models.markets.MarketCandlesticks",
        spec_schema="MarketCandlesticksResponse",
        notes=(
            "Per-market candlestick bundle in bulk response; spec name "
            "MarketCandlesticksResponse, SDK name MarketCandlesticks"
        ),
    ),
    ContractEntry(
        sdk_model="kalshi.models.exchange.UserDataTimestamp",
        spec_schema="GetUserDataTimestampResponse",
        notes="Spec wraps single as_of_time in GetUserDataTimestampResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.models.account.AccountApiLimits",
        spec_schema="GetAccountApiLimitsResponse",
        notes=(
            "SPEC DRIFT: spec declares int 'read_limit'/'write_limit' but the "
            "live server returns nested 'read'/'write' token-bucket objects. "
            "SDK model follows the server."
        ),
    ),
    ContractEntry(
        sdk_model="kalshi.models.structured_targets.StructuredTarget",
        spec_schema="StructuredTarget",
        notes="All fields optional per spec; details is dict[str, Any]",
    ),
    ContractEntry(
        sdk_model="kalshi.models.search.SportFilterDetails",
        spec_schema="SportFilterDetails",
    ),
    ContractEntry(
        sdk_model="kalshi.models.search.ScopeList",
        spec_schema="ScopeList",
    ),
    ContractEntry(
        sdk_model="kalshi.models.incentive_programs.IncentiveProgram",
        spec_schema="IncentiveProgram",
        notes="period_reward is int centi-cents; target_size_fp DollarDecimal",
    ),
    ContractEntry(
        sdk_model="kalshi.models.portfolio.TotalRestingOrderValue",
        spec_schema="GetPortfolioRestingOrderTotalValueResponse",
        notes="Single int total_resting_order_value in cents",
    ),
    ContractEntry(
        sdk_model="kalshi.models.order_groups.OrderGroup",
        spec_schema="OrderGroup",
        notes="contracts_limit uses FixedPointCount with _fp alias",
    ),
    ContractEntry(
        sdk_model="kalshi.models.order_groups.GetOrderGroupResponse",
        spec_schema="GetOrderGroupResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.models.order_groups.CreateOrderGroupResponse",
        spec_schema="CreateOrderGroupResponse",
    ),
    # -- markets sub-models (#171) ---------------------------------------
    ContractEntry(
        sdk_model="kalshi.models.markets.BidAskDistribution",
        spec_schema="BidAskDistribution",
        notes="OHLC sub-model on Candlestick.yes_bid / .yes_ask",
    ),
    ContractEntry(
        sdk_model="kalshi.models.markets.PriceDistribution",
        spec_schema="PriceDistribution",
        notes="OHLC sub-model on Candlestick.price",
    ),
    ContractEntry(
        sdk_model="kalshi.models.markets.Candlestick",
        spec_schema="MarketCandlestick",
        notes="Spec uses 'MarketCandlestick'; SDK calls it 'Candlestick'",
    ),
    ContractEntry(
        sdk_model="kalshi.models.markets.OrderbookLevel",
        spec_schema="PriceLevelDollarsCountFp",
        notes=(
            "Spec encodes price levels as a positional 2-tuple "
            "['<dollars_string>', '<fp_count_string>']; the SDK exposes it "
            "as a named object with `price` / `quantity`. No field-by-field "
            "comparison is meaningful — _get_schema_fields returns {} for "
            "this array-typed schema."
        ),
    ),
    # -- orders V2 family (#171) -----------------------------------------
    ContractEntry(
        sdk_model="kalshi.models.orders.AmendOrderRequest",
        spec_schema="AmendOrderRequest",
        notes="Request body for /portfolio/orders/{order_id}/amend",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.DecreaseOrderRequest",
        spec_schema="DecreaseOrderRequest",
        notes="Request body for /portfolio/orders/{order_id}/decrease",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCreateOrdersRequest",
        spec_schema="BatchCreateOrdersRequest",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCancelOrdersRequest",
        spec_schema="BatchCancelOrdersRequest",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCancelOrdersRequestOrder",
        spec_schema="BatchCancelOrdersRequest.orders.items",
        notes="Inline object schema (no named component)",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.CreateOrderV2Request",
        spec_schema="CreateOrderV2Request",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.CreateOrderV2Response",
        spec_schema="CreateOrderV2Response",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.AmendOrderV2Request",
        spec_schema="AmendOrderV2Request",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.AmendOrderV2Response",
        spec_schema="AmendOrderV2Response",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.DecreaseOrderV2Request",
        spec_schema="DecreaseOrderV2Request",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.DecreaseOrderV2Response",
        spec_schema="DecreaseOrderV2Response",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.CancelOrderV2Response",
        spec_schema="CancelOrderV2Response",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCreateOrdersV2Request",
        spec_schema="BatchCreateOrdersV2Request",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCreateOrdersV2Response",
        spec_schema="BatchCreateOrdersV2Response",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCreateOrdersV2ResponseEntry",
        spec_schema="BatchCreateOrdersV2Response.orders.items",
        notes="Inline object schema (no named component)",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCancelOrdersV2Request",
        spec_schema="BatchCancelOrdersV2Request",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCancelOrdersV2RequestOrder",
        spec_schema="BatchCancelOrdersV2Request.orders.items",
        notes="Inline object schema (no named component)",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCancelOrdersV2Response",
        spec_schema="BatchCancelOrdersV2Response",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCancelOrdersV2ResponseEntry",
        spec_schema="BatchCancelOrdersV2Response.orders.items",
        notes="Inline object schema (no named component)",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCreateOrdersResponse",
        spec_schema="BatchCreateOrdersResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCreateOrdersResponseEntry",
        spec_schema="BatchCreateOrdersResponse.orders.items",
        notes="Inline object schema (no named component)",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCancelOrdersResponse",
        spec_schema="BatchCancelOrdersResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.models.orders.BatchCancelOrdersResponseEntry",
        spec_schema="BatchCancelOrdersResponse.orders.items",
        notes="Inline object schema (no named component)",
    ),
    # -- events sub-models (#171) ----------------------------------------
    ContractEntry(
        sdk_model="kalshi.models.events.MarketMetadata",
        spec_schema="MarketMetadata",
    ),
    ContractEntry(
        sdk_model="kalshi.models.events.SettlementSource",
        spec_schema="SettlementSource",
    ),
    # -- exchange sub-models (#171) --------------------------------------
    ContractEntry(
        sdk_model="kalshi.models.exchange.Schedule",
        spec_schema="Schedule",
    ),
    ContractEntry(
        sdk_model="kalshi.models.exchange.DailySchedule",
        spec_schema="DailySchedule",
    ),
    ContractEntry(
        sdk_model="kalshi.models.exchange.WeeklySchedule",
        spec_schema="WeeklySchedule",
    ),
    ContractEntry(
        sdk_model="kalshi.models.exchange.MaintenanceWindow",
        spec_schema="MaintenanceWindow",
    ),
    # -- portfolio sub-models (#171) -------------------------------------
    ContractEntry(
        sdk_model="kalshi.models.portfolio.IndexedBalance",
        spec_schema="IndexedBalance",
        notes="Per-shard balance entry on Balance.balance_breakdown",
    ),
    ContractEntry(
        sdk_model="kalshi.models.portfolio.PositionsResponse",
        spec_schema="GetPositionsResponse",
        notes="Spec uses 'GetPositionsResponse'; SDK exposes as 'PositionsResponse'",
    ),
    ContractEntry(
        sdk_model="kalshi.models.portfolio.Deposit",
        spec_schema="Deposit",
    ),
    ContractEntry(
        sdk_model="kalshi.models.portfolio.Withdrawal",
        spec_schema="Withdrawal",
    ),
    # -- series sub-models (#171) ----------------------------------------
    ContractEntry(
        sdk_model="kalshi.models.series.EventCandlesticks",
        spec_schema="GetEventCandlesticksResponse",
        notes="Spec wraps event candlesticks in GetEventCandlesticksResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.models.series.PercentilePoint",
        spec_schema="PercentilePoint",
    ),
    ContractEntry(
        sdk_model="kalshi.models.series.ForecastPercentilesPoint",
        spec_schema="ForecastPercentilesPoint",
    ),
    # -- multivariate sub-models (#171) ----------------------------------
    ContractEntry(
        sdk_model="kalshi.models.multivariate.AssociatedEvent",
        spec_schema="AssociatedEvent",
    ),
    ContractEntry(
        sdk_model="kalshi.models.multivariate.CreateMarketInMultivariateEventCollectionRequest",
        spec_schema="CreateMarketInMultivariateEventCollectionRequest",
    ),
    ContractEntry(
        sdk_model="kalshi.models.multivariate.CreateMarketResponse",
        spec_schema="CreateMarketInMultivariateEventCollectionResponse",
        notes="Long-form CreateMarketInMultivariateEventCollectionResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.models.multivariate.LookupTickersForMarketInMultivariateEventCollectionRequest",
        spec_schema="LookupTickersForMarketInMultivariateEventCollectionRequest",
    ),
    ContractEntry(
        sdk_model="kalshi.models.multivariate.LookupTickersResponse",
        spec_schema="LookupTickersForMarketInMultivariateEventCollectionResponse",
        notes="Spec name is the long-form ...Response; SDK shortens",
    ),
    ContractEntry(
        sdk_model="kalshi.models.multivariate.LookupPoint",
        spec_schema="LookupPoint",
    ),
]

# WS payload models → AsyncAPI schema components.
# Same ContractEntry type as REST, but tested via _get_ws_msg_fields()
# which navigates into the AsyncAPI msg.properties nesting.
#
# NOTE: WS models use AliasChoices(spec_name, sdk_name) so the contract
# test pipeline can auto-discover spec-to-SDK field mappings. The aliases
# serve the TEST PIPELINE, not runtime parsing. The real Kalshi WS API
# sends the SDK field names (e.g., "yes_bid": 56), not the spec field
# names (e.g., "yes_bid_dollars": "0.5600"). If Kalshi changes their wire
# format to match the spec, the int-typed fields would reject dollar
# strings — the spec drift pipeline is designed to detect that change.
WS_CONTRACT_MAP: list[ContractEntry] = [
    ContractEntry(
        sdk_model="kalshi.ws.models.ticker.TickerPayload",
        spec_schema="tickerPayload",
        notes="Spec has price_dollars and time fields not in SDK (expected additive drift)",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.fill.FillPayload",
        spec_schema="fillPayload",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.orderbook_delta.OrderbookSnapshotPayload",
        spec_schema="orderbookSnapshotPayload",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.orderbook_delta.OrderbookDeltaPayload",
        spec_schema="orderbookDeltaPayload",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.trade.TradePayload",
        spec_schema="tradePayload",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.user_orders.UserOrdersPayload",
        spec_schema="userOrderPayload",
        notes="Aligned to spec v0.14.0 (2026-04-19): envelope type is "
        "singular 'user_order' on the wire; channel name stays plural "
        "'user_orders'. Live-captured on demo.",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.market_lifecycle.MarketLifecyclePayload",
        spec_schema="marketLifecycleV2Payload",
        notes="SDK conflates lifecycle + event fields. "
        "Spec has additional_metadata, price_level_structure not in SDK.",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.event_fee.EventFeeUpdatePayload",
        spec_schema="eventFeeUpdatePayload",
        notes="New v3.20.0 message (#385); rides the market_lifecycle_v2 channel.",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.market_positions.MarketPositionsPayload",
        spec_schema="marketPositionPayload",
        notes="Aligned to spec v0.14.0 (2026-04-19): envelope type is "
        "singular 'market_position' on the wire; channel name stays plural "
        "'market_positions'. Pattern matches the directly-confirmed "
        "user_order drift. No direct demo capture (demo account idle for "
        "positions during capture window).",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.multivariate.MultivariatePayload",
        spec_schema="multivariateLookupPayload",
        notes="Aligned to spec v0.14.0 (2026-04-19): envelope type is "
        "'multivariate_lookup' on the wire; channel name stays 'multivariate'. "
        "MultivariateLifecycleMessage (type 'multivariate_market_lifecycle') "
        "is unaffected -- separate spec-aligned sibling. No direct demo "
        "capture (no active collections emitting).",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.order_group.OrderGroupPayload",
        spec_schema="orderGroupUpdatesPayload",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.communications.RfqCreatedPayload",
        spec_schema="rfqCreatedPayload",
        notes="Spec has mve_collection_ticker, mve_selected_legs not in SDK",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.communications.RfqDeletedPayload",
        spec_schema="rfqDeletedPayload",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.communications.QuoteCreatedPayload",
        spec_schema="quoteCreatedPayload",
        notes="Spec has extra _fp/_dollars fields + event_ticker not in SDK",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.communications.QuoteAcceptedPayload",
        spec_schema="quoteAcceptedPayload",
        notes="Spec has extra _fp/_dollars fields + event_ticker not in SDK",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.communications.QuoteExecutedPayload",
        spec_schema="quoteExecutedPayload",
    ),
    ContractEntry(
        sdk_model="kalshi.ws.models.base.ErrorPayload",
        spec_schema="errorResponsePayload",
        notes=(
            "WS error-frame payload surfaced via KalshiSubscriptionError. "
            "Spec name is `errorResponsePayload`; SDK class is `ErrorPayload`."
        ),
    ),
    # Intentionally excluded:
    # - eventLifecyclePayload: SDK reuses MarketLifecyclePayload for both channels
    # - multivariateMarketLifecyclePayload: allOf with marketLifecycleV2Payload, covered by base
    # - Control envelopes (SubscriptionInfo, OkMessage): structural, low drift risk
]


# ── Perps (margin) API response-side contract maps ──────────────────────────
# Map perps SDK response models to their schema names in the perps specs. These
# are consumed by ``TestPerpsSpecDrift`` / ``TestPerpsScmSpecDrift`` and resolved
# against ``specs/perps_openapi.yaml`` / ``specs/perps_scm_openapi.yaml`` rather
# than the prediction-API spec. The foundation issue (#388) ships them empty;
# the per-resource perps issues append their entries.
#
# NOTE: ``TestSpecDrift.test_contract_map_completeness`` only scans the
# prediction-API ``kalshi.models.*`` modules, so perps models under
# ``kalshi.perps.models.*`` are not subject to that completeness gate — these
# maps are additive coverage, populated as response models land.
PERPS_CONTRACT_MAP: list[ContractEntry] = [
    # ── perps exchange (#389) ───────────────────────────────────────────
    ContractEntry(
        sdk_model="kalshi.perps.models.exchange.ExchangeStatus",
        spec_schema="ExchangeStatus",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.exchange.MarginEnabledResponse",
        spec_schema="MarginEnabledResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.exchange.GetMarginRiskParametersResponse",
        spec_schema="GetMarginRiskParametersResponse",
    ),
    # ── perps markets (#390) ──
    ContractEntry(
        sdk_model="kalshi.perps.models.markets.MarginMarket",
        spec_schema="MarginMarket",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.markets.MarginMarketCandlestick",
        spec_schema="MarginMarketCandlestick",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.markets.BidAskDistributionHistorical",
        spec_schema="BidAskDistributionHistorical",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.markets.PriceDistributionHistorical",
        spec_schema="PriceDistributionHistorical",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.markets.GetMarginMarketsResponse",
        spec_schema="GetMarginMarketsResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.markets.GetMarginMarketCandlesticksResponse",
        spec_schema="GetMarginMarketCandlesticksResponse",
    ),
    # ── perps orders (#391) ──
    ContractEntry(
        sdk_model="kalshi.perps.models.orders.CreateMarginOrderResponse",
        spec_schema="CreateMarginOrderResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.orders.MarginOrder",
        spec_schema="MarginOrder",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.orders.GetMarginOrderResponse",
        spec_schema="GetMarginOrderResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.orders.GetMarginOrdersResponse",
        spec_schema="GetMarginOrdersResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.orders.CancelMarginOrderResponse",
        spec_schema="CancelMarginOrderResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.orders.DecreaseMarginOrderResponse",
        spec_schema="DecreaseMarginOrderResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.orders.AmendMarginOrderResponse",
        spec_schema="AmendMarginOrderResponse",
    ),
    # ── perps order_groups (#392) ──
    ContractEntry(
        sdk_model="kalshi.perps.models.order_groups.OrderGroup",
        spec_schema="OrderGroup",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.order_groups.GetOrderGroupResponse",
        spec_schema="GetOrderGroupResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.order_groups.CreateOrderGroupResponse",
        spec_schema="CreateOrderGroupResponse",
    ),
    # ── perps portfolio (#393) ──
    ContractEntry(
        sdk_model="kalshi.perps.models.portfolio.MarginPosition",
        spec_schema="MarginPosition",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.portfolio.GetMarginPositionsResponse",
        spec_schema="GetMarginPositionsResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.portfolio.MarginFill",
        spec_schema="MarginFill",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.portfolio.MarginTrade",
        spec_schema="MarginTrade",
    ),
    # NOTE: GetMarginFillsResponse / GetMarginTradesResponse are intentionally
    # NOT response-drift-mapped — their `cursor` is spec-`required` but the SDK
    # keeps it Optional for safe terminal-page parsing (the leaf MarginFill /
    # MarginTrade above carry the field coverage). Mirrors how the prediction-API
    # Page envelopes are excluded from CONTRACT_MAP.
    # ── perps margin_account (#394) ──
    ContractEntry(
        sdk_model="kalshi.perps.models.margin_account.MarginSubaccountBalance",
        spec_schema="MarginSubaccountBalance",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.margin_account.GetMarginBalanceResponse",
        spec_schema="GetMarginBalanceResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.margin_account.MarginRiskPosition",
        spec_schema="MarginRiskPosition",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.margin_account.GetMarginRiskResponse",
        spec_schema="GetMarginRiskResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.margin_account.NotionalRiskLimitResponse",
        spec_schema="NotionalRiskLimitResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.margin_account.GetMarginFeeTiersResponse",
        spec_schema="GetMarginFeeTiersResponse",
    ),
    # ── perps funding (#395) ──
    ContractEntry(
        sdk_model="kalshi.perps.models.funding.MarginFundingRate",
        spec_schema="MarginFundingRate",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.funding.MarginFundingHistoryEntry",
        spec_schema="MarginFundingHistoryEntry",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.funding.MarginFundingRateEstimate",
        spec_schema="GetMarginFundingRateEstimateResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.funding.GetMarginHistoricalFundingRatesResponse",
        spec_schema="GetMarginHistoricalFundingRatesResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.funding.GetMarginFundingHistoryResponse",
        spec_schema="GetMarginFundingHistoryResponse",
    ),
    # ── perps transfers (#396) ──
    ContractEntry(
        sdk_model="kalshi.perps.models.transfers.IntraExchangeInstanceTransferResponse",
        spec_schema="IntraExchangeInstanceTransferResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.models.transfers.CreateSubaccountResponse",
        spec_schema="CreateSubaccountResponse",
    ),
]

PERPS_SCM_CONTRACT_MAP: list[ContractEntry] = [
    # ── perps SCM/Klear (#400) ──────────────────────────────────────────
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.MarginReport",
        spec_schema="MarginReport",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.GetMarginReportsResponse",
        spec_schema="GetMarginReportsResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.ObligationReceiveInfo",
        spec_schema="ObligationReceiveInfo",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.SettlementDetail",
        spec_schema="SettlementDetail",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.MaintenanceMarginDetail",
        spec_schema="MaintenanceMarginDetail",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.ObligationEntry",
        spec_schema="ObligationEntry",
        notes="Folds spec allOf[ObligationInfo, inline] into one model",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.GetActiveMarginObligationResponse",
        spec_schema="GetActiveMarginObligationResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.SettlementEstimate",
        spec_schema="SettlementEstimate",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.GetSettlementEstimateResponse",
        spec_schema="GetSettlementEstimateResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.GetSettlementBalanceResponse",
        spec_schema="GetSettlementBalanceResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.GetGuarantyFundBalanceResponse",
        spec_schema="GetGuarantyFundBalanceResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.WithdrawSettlementBalanceResponse",
        spec_schema="WithdrawSettlementBalanceResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.GetSettlementBalanceWithdrawalResponse",
        spec_schema="GetSettlementBalanceWithdrawalResponse",
    ),
    ContractEntry(
        sdk_model="kalshi.perps.klear.models.margin.SettlementBalanceHistoryEntry",
        spec_schema="SettlementBalanceHistoryEntry",
    ),
]
