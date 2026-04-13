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
        sdk_model="kalshi.models.events.Event",
        spec_schema="EventData",
        notes="Spec uses 'EventData', not 'Event'",
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
    # Intentionally excluded from contract map:
    # - Candlestick, BidAskDistribution, PriceDistribution, OrderbookLevel:
    #   Nested/composite models, no direct 1:1 spec schema match
    # - DailySchedule, WeeklySchedule, MaintenanceWindow, Schedule:
    #   Simple sub-schemas validated through parent model tests
    # - PositionsResponse: SDK-internal container shape
    # - MarketMetadata, SettlementSource: Simple sub-schemas
    # - Page[T]: SDK-internal pagination wrapper
]
