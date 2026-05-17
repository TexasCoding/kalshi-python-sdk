# Error Handling

All SDK exceptions inherit from `KalshiError`. HTTP responses are mapped to
typed exceptions in the transport layer before any resource code sees them,
so you can `try/except` against the specific failure mode instead of
inspecting status codes.

```python
from kalshi import KalshiClient, KalshiNotFoundError, KalshiRateLimitError

try:
    market = client.markets.get("DOES-NOT-EXIST")
except KalshiNotFoundError as e:
    print(e.status_code, str(e))
except KalshiRateLimitError as e:
    print("backoff hint:", e.retry_after)
```

## Hierarchy

```
KalshiError
├── KalshiAuthError              # 401 / 403
│   └── AuthRequiredError        # private endpoint called on unauth'd client
├── KalshiNotFoundError          # 404
├── KalshiValidationError        # 400 (carries .details: dict[str, str])
├── KalshiRateLimitError         # 429 (carries .retry_after: float | None)
├── KalshiServerError            # 5xx
└── KalshiWebSocketError
    ├── KalshiConnectionError    # handshake / reconnect failure
    ├── KalshiSequenceGapError   # unresolved sequence gap on a stream
    ├── KalshiBackpressureError  # queue full with ERROR overflow strategy
    └── KalshiSubscriptionError  # subscribe / unsubscribe rejected
```

The `KalshiError` base carries an optional `status_code: int | None`.
HTTP-derived exceptions populate it; WebSocket and `AuthRequiredError`
leave it `None`.

## HTTP status → exception

The mapping is done by `_map_error` in
[`kalshi/_base_client.py`](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/_base_client.py).
It runs against the response status code, with the message pulled from
`body["message"]`, then `body["error"]`, then the raw response text:

| Status | Exception | Notes |
|---|---|---|
| `400` | `KalshiValidationError` | `details` is populated from `body["details"]` or `body["errors"]` when present and dict-shaped. |
| `401` / `403` | `KalshiAuthError` | Bad signature, expired key, missing scope. |
| `404` | `KalshiNotFoundError` | Unknown ticker, missing order, etc. |
| `429` | `KalshiRateLimitError` | `retry_after` parsed from the `Retry-After` header if it's a numeric value (HTTP-date form falls back to computed backoff). |
| `5xx` | `KalshiServerError` | All server-side failures. |
| anything else | `KalshiError` | Catch-all, with `status_code` set. |

`AuthRequiredError` is the one exception that fires *before* the network —
calling a private endpoint on an unauthenticated client raises it
immediately, without sending the request.

## Retry behavior

Retries are conservative by design: the wrong retry on the wrong verb is
how duplicate orders happen.

- **Retried** on `429`, `500`, `502`, `503`, `504` — and **only** for
  `GET`, `HEAD`, `OPTIONS`. `POST` and `DELETE` are never retried, even on
  transient 5xx, to avoid duplicate-order / duplicate-cancel risk.
- **Backoff** is exponential with jitter: `retry_base_delay * 2**attempt
  + random.uniform(0, 0.5)`, capped at `retry_max_delay` (default 30s).
- **`Retry-After`** is honored on 429 but also capped at `retry_max_delay`
  — a hostile or misconfigured server cannot stall the client with
  arbitrary sleep values.
- **Timeouts** on retryable methods retry with the same backoff. Timeouts
  on `POST` / `DELETE` raise immediately.

Tune via `KalshiConfig`:

```python
from kalshi import KalshiClient, KalshiConfig

config = KalshiConfig(
    timeout=10.0,
    max_retries=5,
    retry_base_delay=0.5,
    retry_max_delay=15.0,
)
client = KalshiClient(key_id="...", private_key_path="...", config=config)
```

If `max_retries` runs out, the last typed exception is re-raised. Application
code never sees a bare `httpx` exception — non-HTTP failures (DNS, TLS,
connection-reset) are wrapped in `KalshiError` with the original exception
as `__cause__`.

## WebSocket errors

WebSocket failures are a separate sub-hierarchy under
`KalshiWebSocketError`:

- **`KalshiConnectionError`** — raised when the initial connect fails, when
  the auth handshake is rejected, or when `ws_max_retries` is exhausted on
  a reconnect attempt. Also surfaces from `ConnectionManager.send()` /
  `recv()` if you call them without being connected.
- **`KalshiSubscriptionError`** — server rejected a `subscribe` /
  `unsubscribe` / `update_subscription` command. Carries an optional
  `error_code` field with the server's machine-readable code.
- **`KalshiBackpressureError`** — raised from `MessageQueue.put()` when
  the queue is full and the overflow strategy is `ERROR`. See
  [WebSocket Streaming → Backpressure](websockets.md#backpressure).
- **`KalshiSequenceGapError`** — defined for callers that wire their own
  resync logic on top of the SDK's primitives. The built-in receive loop
  recovers from gaps silently (drops the message, clears local state,
  waits for the next snapshot) rather than raising.

A subscription's iterator continues to yield across reconnects — the SDK
re-issues the subscribe and patches the new server-side `sid` into the
durable client-side id. You won't see `KalshiConnectionError` from inside
`async for`; you'll see it from the `connect()` context manager if the
socket can't be re-established at all.

## Validation errors

Two distinct things can go wrong with payloads, and they raise different
exceptions:

- **Server-side request validation** (`400 Bad Request`) — surfaces as
  `KalshiValidationError`, with `details: dict[str, str]` populated from
  the server's response when available. Use it to report field-level
  problems back to the user.
- **Pydantic validation on the response** — if the server returns a body
  that doesn't match the SDK's typed model (a wire-format drift, or a
  new field in an unexpected shape), Pydantic's own `ValidationError`
  bubbles up. It is *not* a subclass of `KalshiError` — treat it as a
  bug report against the SDK's model layer, not as a transient error.

Client-side validation on request bodies (Pydantic models with
`extra="forbid"`) also raises Pydantic's `ValidationError` directly,
before the network. A misspelled kwarg in a resource method raises
`TypeError` first; phantom keys passed via `request=Model(...)` fail at
`Model(...)` construction.

## Exception reference

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
