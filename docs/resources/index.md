# Resources

The SDK exposes one resource class per Kalshi API surface area: `markets`,
`events`, `orders`, `portfolio`, `exchange`, `series`, `multivariate`,
`historical`, and more. Each resource is reachable as an attribute on
`KalshiClient` / `AsyncKalshiClient`, e.g. `client.markets.list(...)`.

Per-resource usage guides — with end-to-end examples for the common workflows
on each surface — are forthcoming. Track progress at
[issue #14](https://github.com/TexasCoding/kalshi-python-sdk/issues/14).

In the meantime, the [API Reference](../reference.md) page auto-generates the
complete signature and docstring for every public method.
