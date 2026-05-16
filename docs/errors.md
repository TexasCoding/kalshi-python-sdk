# Error Handling

All SDK errors inherit from `KalshiError`. HTTP errors are mapped from response
status to a typed exception by the transport layer; WebSocket errors are
raised by the streaming client.

A walkthrough with retry and recovery patterns is forthcoming. Track progress
at [issue #14](https://github.com/TexasCoding/kalshi-python-sdk/issues/14).

## Exception hierarchy

::: kalshi.errors.KalshiError

::: kalshi.errors.KalshiAuthError

::: kalshi.errors.AuthRequiredError

::: kalshi.errors.KalshiNotFoundError

::: kalshi.errors.KalshiValidationError

::: kalshi.errors.KalshiRateLimitError

::: kalshi.errors.KalshiServerError

::: kalshi.errors.KalshiWebSocketError

::: kalshi.errors.KalshiConnectionError

::: kalshi.errors.KalshiSequenceGapError

::: kalshi.errors.KalshiBackpressureError

::: kalshi.errors.KalshiSubscriptionError
