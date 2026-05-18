# Errors

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
KalshiError                          # base, .status_code: int | None
├── KalshiAuthError                  # 401 / 403
│   └── AuthRequiredError            # preflight on unauth'd client
├── KalshiNotFoundError              # 404
├── KalshiValidationError            # 400 (carries .details: dict[str, str])
├── KalshiRateLimitError             # 429 (carries .retry_after: float | None)
├── KalshiServerError                # 5xx
└── KalshiWebSocketError             # base for WS errors
    ├── KalshiConnectionError        # handshake / reconnect failure
    ├── KalshiSequenceGapError       # exposed for custom resync handlers
    ├── KalshiBackpressureError      # queue full with ERROR overflow
    └── KalshiSubscriptionError      # subscribe / unsubscribe rejected
```

The `KalshiError` base carries an optional `status_code: int | None`.
HTTP-derived exceptions populate it; WebSocket and `AuthRequiredError`
leave it `None`.

## HTTP status → exception

| Status | Exception | Notes |
|---|---|---|
| `400` | `KalshiValidationError` | `.details` is populated from `body["details"]` or `body["errors"]` when present and dict-shaped. |
| `401` / `403` | `KalshiAuthError` | Bad signature, expired key, missing scope. |
| `404` | `KalshiNotFoundError` | Unknown ticker, missing order, etc. |
| `429` | `KalshiRateLimitError` | `.retry_after` parsed from the `Retry-After` header if it's a non-negative finite numeric (HTTP-date form falls back to computed backoff). |
| `5xx` | `KalshiServerError` | All server-side failures. |
| anything else | `KalshiError` | Catch-all, with `status_code` set. |

`AuthRequiredError` is the one HTTP-shaped exception that fires *before* the
network — calling a private endpoint on an unauthenticated client raises it
preflight, without sending the request. `status_code` is `None`. Since it
subclasses `KalshiAuthError`, catching the parent covers both.

The mapping is performed by `_map_error` in
[`kalshi/_base_client.py`](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/_base_client.py).

## Validation errors

Two distinct things can go wrong with payloads:

- **Server-side request validation** (`400 Bad Request`) — surfaces as
  `KalshiValidationError`, with `details: dict[str, str]` populated from the
  server's response when available. Use it to report field-level problems back
  to the user.
- **Pydantic validation on the response** — if the server returns a body that
  doesn't match the SDK's typed model (a wire-format drift), Pydantic's own
  `ValidationError` bubbles up. It is **not** a subclass of `KalshiError` —
  treat it as a bug report against the SDK's model layer, not as a transient
  error.

Client-side validation on request bodies (Pydantic models with `extra="forbid"`)
also raises Pydantic's `ValidationError` directly, **before** the network. A
misspelled kwarg in a resource method raises `TypeError` first; phantom keys
passed via `request=Model(...)` fail at `Model(...)` construction.

## Transport-level wrapping

Non-HTTP failures are wrapped to a typed exception with the original as
`__cause__`:

- **Timeouts** on retryable methods (`GET`, `HEAD`, `OPTIONS`) retry; once
  retries are exhausted, the last `httpx.TimeoutException` is re-raised wrapped
  in `KalshiError`. Timeouts on `POST` / `DELETE` raise `KalshiError`
  immediately, no retry.
- **Connection failures** (DNS, TLS, RST) raise `KalshiError` immediately on
  any verb, no retry.

There is no `KalshiTimeoutError` class. Inspect `e.__cause__` if you need to
distinguish.

## Catching everything from the SDK

```python
from kalshi import KalshiError

try:
    do_things(client)
except KalshiError as e:
    log.exception("SDK call failed (status=%s)", e.status_code)
```

A bare `except KalshiError` covers every SDK-raised exception **except** the
Pydantic `ValidationError` you'd get from a malformed response (that one is a
bug, not a runtime error).

## WebSocket errors

WebSocket failures are a separate sub-hierarchy under
`KalshiWebSocketError`:

- **`KalshiConnectionError`** — raised when the initial connect fails, when
  the auth handshake is rejected, or when `ws_max_retries` is exhausted on a
  reconnect attempt. Also surfaces from `ConnectionManager.send()` / `recv()`
  if you call them without being connected.
- **`KalshiSubscriptionError`** — server rejected a `subscribe` /
  `unsubscribe` / `update_subscription` command. Carries an optional
  `error_code` field with the server's machine-readable code.
- **`KalshiBackpressureError`** — raised from `MessageQueue.put()` when the
  queue is full and the overflow strategy is `ERROR`. The receive loop treats
  this as **fatal**: it broadcasts sentinels to every active iterator and
  exits. See [WebSocket → Backpressure](websockets.md#backpressure).
- **`KalshiSequenceGapError`** — exposed for callers wiring their own resync
  logic on top of the SDK's primitives. The built-in receive loop **does not
  raise** this — it recovers from gaps silently (drops the message, clears
  local orderbook state, waits for the next snapshot).

A subscription's iterator continues to yield across reconnects — the SDK
re-issues the subscribe and patches the new server-side `sid` into the durable
client-side id. You won't see `KalshiConnectionError` from inside `async for`;
you'll see it from the `connect()` context manager if the socket can't be
re-established at all.

## See also

- [Retries & idempotency](retries.md) — what does and doesn't get retried, why
  POST/DELETE never retry, recommended patterns for safely retrying writes.

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
