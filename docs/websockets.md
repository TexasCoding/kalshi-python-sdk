# WebSocket Streaming

The SDK ships an async WebSocket client (`kalshi.ws.client.KalshiWebSocket`)
covering all 11 Kalshi channels — `ticker`, `trade`, `orderbook_delta`,
`fill`, `market_positions`, `user_orders`, `order_group`, `market_lifecycle`,
`multivariate`, `multivariate_lifecycle`, and `communications` — with
sequence-gap detection, automatic reconnection, and configurable
backpressure.

A full streaming guide with subscription, resync, and backpressure examples is
forthcoming. Track progress at
[issue #14](https://github.com/TexasCoding/kalshi-python-sdk/issues/14).
