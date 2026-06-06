# Environment variables

`KalshiClient.from_env()` and `KalshiAuth.from_env()` / `try_from_env()` read
these:

| Variable | Default | Effect |
|---|---|---|
| `KALSHI_KEY_ID` | unset | Key ID. If unset, `from_env()` returns an unauthenticated client. |
| `KALSHI_PRIVATE_KEY` | unset | PEM string. **Conflicts** with `KALSHI_PRIVATE_KEY_PATH` — set exactly one. |
| `KALSHI_PRIVATE_KEY_PATH` | unset | Path to PEM file. `~` is expanded. Conflicts with `KALSHI_PRIVATE_KEY`. |
| `KALSHI_PRIVATE_KEY_PASSPHRASE` | unset | Passphrase for an encrypted PEM (read by `from_env()` / `try_from_env()`, and by `FixClient.from_env()`). |
| `KALSHI_DEMO` | `false` | The exact string `true` (case-insensitive) selects the demo URLs. Other values (`1`, `yes`, `on`) are **not** recognized. |
| `KALSHI_API_BASE_URL` | unset | Overrides `base_url` entirely. Wins over `KALSHI_DEMO`. |
| `KALSHI_ALLOW_UNKNOWN_HOST` | unset | Set to `1` to allow `base_url`/`ws_base_url` hosts outside `{api.elections.kalshi.com, demo-api.kalshi.co, localhost}`. Default-fail prevents typos like `kalsi.com` from silently signing to an attacker (#250). |

## Precedence

1. **Credentials**: setting both `KALSHI_PRIVATE_KEY` (in-memory PEM) and
   `KALSHI_PRIVATE_KEY_PATH` raises `KalshiAuthError`. Previously the inline
   PEM silently won; under #249 the ambiguity is rejected up-front so
   key-rotation mishaps surface as a clean error instead of a 401/403 mystery.
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
    KalshiConfig.demo(timeout=10.0, max_retries=5) if os.getenv("KALSHI_DEMO", "").lower() == "true"
    else KalshiConfig.production(timeout=10.0, max_retries=5)
)
with KalshiClient.from_env(config=config) as client:
    ...
```

## Perps environment variables

`PerpsClient.from_env()` / `AsyncPerpsClient.from_env()` read a **separate**
`KALSHI_PERPS_*` namespace — perps requires a key issued for the perps exchange:

| Variable | Default | Effect |
|---|---|---|
| `KALSHI_PERPS_KEY_ID` | unset | Perps key ID. Omit for an unauthenticated client. |
| `KALSHI_PERPS_PRIVATE_KEY` | unset | PEM string. Conflicts with `KALSHI_PERPS_PRIVATE_KEY_PATH`. |
| `KALSHI_PERPS_PRIVATE_KEY_PATH` | unset | Path to a PEM file. |
| `KALSHI_PERPS_PRIVATE_KEY_PASSPHRASE` | unset | Passphrase for an encrypted perps PEM. A `password=` kwarg to the client overrides it. |
| `KALSHI_PERPS_DEMO` | `false` | `true` (case-insensitive) selects the demo REST + WS endpoints. |
| `KALSHI_PERPS_API_BASE_URL` | unset | Overrides the perps REST `base_url`. |
| `KALSHI_PERPS_WS_BASE_URL` | unset | Overrides the perps `ws_base_url`, so a REST override doesn't leave the WS feed on production. |
| `KALSHI_PERPS_ALLOW_UNKNOWN_HOST` | unset | Set to `1` to allow non-Kalshi perps hosts (mock servers / proxies). |

## Klear (SCM) environment variables

`KlearClient` / `AsyncKlearClient` use cookie-session auth (no RSA keys), so they
read only environment selectors:

| Variable | Default | Effect |
|---|---|---|
| `KALSHI_KLEAR_DEMO` | `false` | `true` (case-insensitive) selects the demo Klear endpoint. |
| `KALSHI_KLEAR_API_BASE_URL` | unset | Overrides the Klear `base_url`. |
| `KALSHI_KLEAR_ALLOW_UNKNOWN_HOST` | unset | Set to `1` to allow non-Kalshi Klear hosts. |

## FIX

The [FIX subsystem](fix.md) reuses the credential variables above:
`FixClient.from_env()` reads the prediction `KALSHI_KEY_ID` /
`KALSHI_PRIVATE_KEY[_PATH]` / `KALSHI_PRIVATE_KEY_PASSPHRASE`, and
`MarginFixClient.from_env()` reads the perps `KALSHI_PERPS_*` set. FIX host/port is
resolved by `FixConfig` (not an env var); use a `host=`/`port=` override plus
`allow_unknown_host=True` or `KALSHI_FIX_ALLOW_UNKNOWN_HOST=1` only for a mock or
local TLS proxy.
