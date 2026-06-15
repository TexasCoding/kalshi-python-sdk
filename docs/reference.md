# API Reference

Auto-generated from docstrings on the public surface of the `kalshi` package.

For narrative coverage of any of these, follow the section links — every
class here also has a dedicated user-facing page elsewhere in the docs.

## Clients

::: kalshi.client.KalshiClient

::: kalshi.async_client.AsyncKalshiClient

## Configuration

::: kalshi.config.KalshiConfig

## Authentication

::: kalshi.auth.KalshiAuth

## Errors

See [Errors](errors.md) — that page is the canonical autodoc reference for
every exception class.

## Pagination

::: kalshi.models.common.Page

## Custom types

::: kalshi.types

## Request models

::: kalshi.models.orders.CreateOrderRequest

::: kalshi.models.orders.AmendOrderRequest

::: kalshi.models.orders.DecreaseOrderRequest

::: kalshi.models.orders.BatchCreateOrdersRequest

::: kalshi.models.orders.BatchCancelOrdersRequest

::: kalshi.models.orders.BatchCancelOrdersRequestOrder

::: kalshi.models.api_keys.CreateApiKeyRequest

::: kalshi.models.api_keys.GenerateApiKeyRequest

::: kalshi.models.communications.CreateRFQRequest

::: kalshi.models.communications.CreateQuoteRequest

::: kalshi.models.communications.AcceptQuoteRequest

::: kalshi.models.communications.ProposeBlockTradeRequest

::: kalshi.models.communications.AcceptBlockTradeProposalRequest

::: kalshi.models.multivariate.CreateMarketInMultivariateEventCollectionRequest

::: kalshi.models.multivariate.LookupTickersForMarketInMultivariateEventCollectionRequest

::: kalshi.models.order_groups.CreateOrderGroupRequest

::: kalshi.models.order_groups.UpdateOrderGroupLimitRequest

::: kalshi.models.subaccounts.ApplySubaccountTransferRequest

::: kalshi.models.subaccounts.UpdateSubaccountNettingRequest

## Response models

### Markets, events, series

::: kalshi.models.markets

::: kalshi.models.events

::: kalshi.models.series

### Trading

::: kalshi.models.orders.Order

::: kalshi.models.orders.Fill

::: kalshi.models.orders.AmendOrderResponse

::: kalshi.models.orders.OrderQueuePosition

::: kalshi.models.portfolio

### Account, subaccounts, API keys, FCM

::: kalshi.models.account

::: kalshi.models.subaccounts

::: kalshi.models.api_keys

### Exchange, historical, search

::: kalshi.models.exchange

::: kalshi.models.historical

### RFQ / Quote, multivariate, live data, milestones, structured targets, incentive programs, order groups

::: kalshi.models.communications

::: kalshi.models.multivariate

::: kalshi.models.live_data

::: kalshi.models.milestones

::: kalshi.models.structured_targets

::: kalshi.models.incentive_programs

::: kalshi.models.order_groups

## WebSocket

See [WebSocket](websockets.md) for the narrative version.

::: kalshi.ws.client.KalshiWebSocket

::: kalshi.ws.connection.ConnectionState

::: kalshi.ws.backpressure.OverflowStrategy

::: kalshi.ws.backpressure.MessageQueue

::: kalshi.ws.models

## FIX protocol

See [FIX protocol](fix.md) for the narrative version.

::: kalshi.fix.client.FixClient

::: kalshi.perps.fix.MarginFixClient

::: kalshi.fix.config.FixConfig

::: kalshi.fix.session.FixSession

::: kalshi.fix.orderbook.FixOrderBook

::: kalshi.fix.settlement.SettlementReassembler

::: kalshi.fix.messages

::: kalshi.fix.enums

## Testing helpers

See [Testing](testing.md) for the narrative version.

::: kalshi.testing
