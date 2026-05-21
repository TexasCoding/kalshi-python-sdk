# Configuration

Every client option lives on `KalshiConfig` — a frozen dataclass passed to
`KalshiClient(..., config=...)` or built implicitly by the convenience
constructors (`KalshiConfig.demo()`, `KalshiConfig.production()`).

## Quick reference

```python
from kalshi import KalshiClient, KalshiConfig
import httpx

config = KalshiConfig(
    base_url="https://api.elections.kalshi.com/trade-api/v2",
    timeout=30.0,
    max_retries=3,
    retry_base_delay=0.5,
    retry_max_delay=30.0,
    extra_headers={"User-Agent": "my-bot/1.2"},
    ws_base_url="wss://api.elections.kalshi.com/trade-api/ws/v2",
    ws_max_retries=10,
    http2=False,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
)

with KalshiClient(key_id="...", private_key_path="...", config=config) as client:
    ...
```

## Fields

| Field | Default | Meaning |
|---|---|---|
| `base_url` | `https://api.elections.kalshi.com/trade-api/v2` | REST base URL. Trailing slash is auto-stripped. |
| `timeout` | `30.0` | `httpx` timeout (seconds). Single scalar — applies to connect, read, write, and pool together. |
| `max_retries` | `3` | Maximum retry attempts on retryable methods. |
| `retry_base_delay` | `0.5` | Base for exponential backoff (seconds). |
| `retry_max_delay` | `30.0` | Cap on any single retry sleep — also caps `Retry-After`. |
| `extra_headers` | `{}` | Extra HTTP headers added to every request. Useful for custom User-Agent. |
| `ws_base_url` | `wss://api.elections.kalshi.com/trade-api/ws/v2` | WebSocket base URL. |
| `ws_max_retries` | `10` | Maximum reconnect attempts before the WS gives up. |
| `http2` | `False` | Enable HTTP/2 (requires `httpx[http2]` install extra). |
| `rest_json_loads` | `None` | Optional callable for parsing REST response bodies (e.g. `orjson.loads`). When set, receives `response.content` bytes; falls back to stdlib `json` otherwise. Useful for list-heavy endpoints (`markets.list_all`, `trades.list_all`). |
| `ws_json_loads` | `None` | Optional callable for parsing WS frames (e.g. `orjson.loads`). |
| `ws_json_dumps` | `None` | Optional callable for serializing outbound WS commands. |
| `limits` | `None` | Connection-pool limits passed to `httpx`. When `None`, the underlying `httpx.Client` uses its own pool defaults. Pass an `httpx.Limits(...)` to tune. See [Performance](websockets.md#performance) for WS sizing guidance. |
| `total_timeout` | `None` | Wall-clock cap (seconds) across the whole request including all retries. `None` = unbounded; cap with the per-attempt `timeout` only. See [Retries & idempotency](retries.md). |
| `ws_ping_interval` | `20.0` | Seconds between WebSocket keepalive pings (forwarded to the `websockets` library). |
| `ws_close_timeout` | `5.0` | Seconds to wait for a clean WebSocket close handshake before forcing the socket shut. |
| `allow_unknown_host` | `False` | When `False`, reject `base_url` / `ws_base_url` whose host is not in the Kalshi allowlist (`api.elections.kalshi.com`, `demo-api.kalshi.co`) or a loopback host. Opt out via the field or `KALSHI_ALLOW_UNKNOWN_HOST=1` when targeting a mock server, proxy, or alternate region. (Added in v2.5.0, #250.) |

See [Retries & idempotency](retries.md) for what `max_retries`,
`retry_base_delay`, `retry_max_delay` do at runtime.

## Convenience constructors

```python
config = KalshiConfig.demo()          # demo URLs + defaults
config = KalshiConfig.production()    # prod URLs + defaults
config = KalshiConfig.demo(timeout=10.0, max_retries=5)
```

Both accept any keyword override the full constructor accepts (except the URLs,
which they set themselves).

The `KalshiClient(demo=True, ...)` convenience flag is equivalent to passing
`config=KalshiConfig.demo()` — but you can layer on a full custom `config` if
you also need other tuning.

## URL validation

`KalshiConfig` enforces a small security policy on its URLs:

- `base_url` must be `https://` for remote hosts; `http://` is only allowed
  against `localhost`, `127.0.0.1`, or `::1` (for local fixtures / proxies).
- `ws_base_url` must be `wss://` for remote hosts; `ws://` is only allowed
  against the same loopback set.
- Trailing slashes are auto-stripped from both.
- Unknown hosts are rejected by default; opt in via `allow_unknown_host`
  (see the [Fields](#fields) table) or `KALSHI_ALLOW_UNKNOWN_HOST=1`. Kalshi's
  known hosts are `api.elections.kalshi.com` and `demo-api.kalshi.co`.

This catches plaintext config slip-ups before any request is sent.

## Custom User-Agent

```python
KalshiConfig(extra_headers={"User-Agent": "acme-trader/2.1 (+ops@acme.co)"})
```

`extra_headers` is set at the `httpx.Client` level and is **overridden** by the
SDK's per-request `KALSHI-ACCESS-*` headers, so it cannot be used to forge or
replace auth headers. It can only override client-level defaults that the SDK
doesn't re-set on every request — `User-Agent` is the realistic use case.

## HTTP/2

```python
KalshiConfig(http2=True)
```

Requires the `h2` package — install via `pip install 'kalshi-sdk[http2]'` (or
`pip install 'kalshi-sdk[all]'`). `KalshiConfig` validates this at construction
time and raises `ValueError` immediately if `h2` is missing, rather than
deferring the failure to the first request. Once enabled, the same setting
flows into the WebSocket client too (WebSocket runs on top of an HTTP/1.1
upgrade today; this only affects REST).

## Connection-pool limits

```python
import httpx

KalshiConfig(limits=httpx.Limits(max_connections=200, max_keepalive_connections=50))
```

Useful when you're driving a large fan-out workload (many async tasks).
Otherwise leave the defaults.

## Custom transport

`KalshiClient(..., transport=...)` plumbs an `httpx.BaseTransport` straight to
the underlying `httpx.Client`. Use it for:

- **Testing** — see [`kalshi.testing.ReplayTransport`](testing.md).
- **HTTP mocking in tests** — `respx.MockTransport()`.
- **Outbound proxies** — `httpx.HTTPTransport(proxy="http://corp-proxy:8080")`.

```python
import respx
from kalshi import KalshiClient

with respx.mock(base_url="https://api.elections.kalshi.com") as router:
    router.get("/trade-api/v2/exchange/status").respond(200, json={"exchange_active": True})
    with KalshiClient(transport=router) as client:
        assert client.exchange.status().exchange_active
```

The async client accepts an `httpx.AsyncBaseTransport` the same way.

## Pre-built `KalshiAuth`

If you've already constructed a `KalshiAuth` (e.g. for the WebSocket), reuse it:

```python
from kalshi import KalshiAuth, KalshiClient

auth = KalshiAuth.from_key_path("kid", "~/.kalshi/key.pem")
with KalshiClient(auth=auth) as client:
    ...
```

`auth=` and the credential kwargs (`key_id` / `private_key_path` /
`private_key`) are mutually exclusive — supply one or the other.

## Lifecycle

`KalshiClient` (and `AsyncKalshiClient`) is a context manager; the `with`
block tears down the underlying `httpx` client and a small dedicated
`ThreadPoolExecutor` used for offloading RSA-PSS signing on the async path
(see [Authentication](authentication.md#async-rsa-pss-sign-offload)). If
you keep a client as a long-lived attribute, call `client.close()`
explicitly when shutting down to release both pools deterministically.

```python
client = KalshiClient.from_env()
try:
    ...
finally:
    client.close()
```

`AsyncKalshiClient` follows the same shape — prefer `async with` so the
async `close()` chains the executor teardown on exit:

```python
async with AsyncKalshiClient.from_env() as client:
    ...
```

## Reference

::: kalshi.config.KalshiConfig
