# Environment variables

`KalshiClient.from_env()` and `KalshiAuth.from_env()` / `try_from_env()` read
these:

| Variable | Default | Effect |
|---|---|---|
| `KALSHI_KEY_ID` | unset | Key ID. If unset, `from_env()` returns an unauthenticated client. |
| `KALSHI_PRIVATE_KEY` | unset | PEM string. Takes precedence over `KALSHI_PRIVATE_KEY_PATH`. |
| `KALSHI_PRIVATE_KEY_PATH` | unset | Path to PEM file. `~` is expanded. |
| `KALSHI_DEMO` | `false` | Truthy values (`true`, `1`, `yes`, `on`, case-insensitive) flip the client to the demo URLs. |
| `KALSHI_API_BASE_URL` | unset | Overrides `base_url` entirely. Wins over `KALSHI_DEMO`. |

## Precedence

1. **Credentials**: `KALSHI_PRIVATE_KEY` (in-memory PEM) beats
   `KALSHI_PRIVATE_KEY_PATH` (file).
2. **Base URL**: an explicit `KALSHI_API_BASE_URL` wins over the demo/production
   pair selected by `KALSHI_DEMO`.
3. **Constructor overrides**: anything passed positionally / by kwarg to
   `KalshiClient(...)` wins over the corresponding env var. `from_env(**kwargs)`
   merges in user kwargs after reading the env.

## `from_env()` vs `try_from_env()`

- `KalshiAuth.from_env()` raises `KalshiAuthError` if `KALSHI_KEY_ID` is missing.
- `KalshiAuth.try_from_env()` returns `None` if credentials are absent — but
  **still raises** if the env vars are present but malformed (invalid PEM,
  unreadable file, encrypted key, …). It is "are creds available?" not "swallow
  every error".

`KalshiClient.from_env()` uses `try_from_env()` under the hood — missing creds
fall through to an unauthenticated client.

## Retry / timeout knobs

There are **no environment variables** for `timeout`, `max_retries`,
`retry_base_delay`, `retry_max_delay`, `ws_max_retries`, `http2`, or `limits`.
Pass a `KalshiConfig` explicitly:

```python
import os
from kalshi import KalshiClient, KalshiConfig

config = (
    KalshiConfig.demo() if os.getenv("KALSHI_DEMO", "").lower() == "true"
    else KalshiConfig.production()
)
config = dataclasses.replace(config, timeout=10.0, max_retries=5)
with KalshiClient.from_env(config=config) as client:
    ...
```
