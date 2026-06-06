# Authentication

Kalshi uses RSA-PSS request signing. You'll need:

- A **key ID** (string, identifies the key on Kalshi's side).
- A **private key** — RSA, PEM-encoded, PKCS#8. May be unencrypted or
  encrypted; encrypted keys require a passphrase (see below).

Generate the pair in your [Kalshi account settings](https://kalshi.com/account/profile)
and download the PEM file. The signing scheme used internally is
RSA-PSS / SHA256 / MGF1(SHA256) / salt = digest length / base64 — you don't need
to implement any of that yourself; the SDK does it for you.

You can also mint keys programmatically once authenticated; see
[API keys](resources/api-keys.md).

## Option 1 — Key file path (most common)

```python
from kalshi import KalshiClient

with KalshiClient(
    key_id="your-key-id",
    private_key_path="~/.kalshi/private_key.pem",
) as client:
    ...
```

`~` is expanded for you. Pass a `pathlib.Path` or a string. The constructor is
keyword-only; an empty `key_id` raises `ValueError` immediately.

## Option 2 — Environment variables

The `from_env()` constructors read credentials and configuration from the
environment:

```bash
export KALSHI_KEY_ID="..."
export KALSHI_PRIVATE_KEY_PATH="~/.kalshi/private_key.pem"

# Optional knobs:
export KALSHI_DEMO=true                # use the sandbox environment
export KALSHI_API_BASE_URL="..."       # override the base URL entirely
```

```python
from kalshi import KalshiClient

with KalshiClient.from_env() as client:
    ...
```

If `KALSHI_KEY_ID` / `KALSHI_PRIVATE_KEY_PATH` are unset, `from_env()` returns
an **unauthenticated** client. Public endpoints still work. See
[Environment variables](environment-variables.md) for the full table and
precedence rules.

## Option 3 — In-memory PEM (env var)

If you store the private key in a secret manager (Vault, AWS Secrets Manager,
GCP Secret Manager, …), set `KALSHI_PRIVATE_KEY` to the PEM contents:

```bash
export KALSHI_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
MIIEv...
-----END PRIVATE KEY-----"
```

Then `KalshiClient.from_env()` will load the key directly without touching the
filesystem. `KALSHI_PRIVATE_KEY` takes precedence over `KALSHI_PRIVATE_KEY_PATH`
when both are set.

## Option 4 — In-memory PEM (constructor)

You can also pass the PEM string straight to the constructor:

```python
from kalshi import KalshiClient

pem = secret_manager.get("kalshi/private_key")  # str returning the PEM body

with KalshiClient(key_id="...", private_key=pem) as client:
    ...
```

The constructor accepts both `private_key_path=` and `private_key=`; supply
exactly one.

## Demo vs. production

```python
from kalshi import KalshiClient

# Sandbox — for development. Hits https://demo-api.kalshi.co/trade-api/v2.
KalshiClient(key_id="...", private_key_path="...", demo=True)

# Production — the default. Hits https://api.elections.kalshi.com/trade-api/v2.
KalshiClient(key_id="...", private_key_path="...")
```

You can also flip via the `KALSHI_DEMO=true` env var when using `from_env()`.

!!! warning "Demo and production keys are different"
    Kalshi issues separate keys for the demo and production environments. Make
    sure the `demo` flag matches the key you're using, or every request will
    401.

## Async

Identical, with `AsyncKalshiClient`:

```python
import asyncio
from kalshi import AsyncKalshiClient

async def main() -> None:
    async with AsyncKalshiClient.from_env() as client:
        page = await client.markets.list(status="open", limit=5)
        for market in page:
            print(market.ticker)

asyncio.run(main())
```

## Public / unauthenticated usage

You don't need credentials for most public market data:

```python
from kalshi import KalshiClient

with KalshiClient(demo=True) as client:
    assert client.is_authenticated is False
    markets = client.markets.list(status="open", limit=5)
```

A handful of "public-looking" endpoints still require auth at the server
(`markets.orderbook`, `markets.bulk_orderbooks`,
`series.forecast_percentile_history`, `exchange.user_data_timestamp`).
Calling those on an unauthenticated client raises
[`AuthRequiredError`](errors.md) preflight — no network round-trip.

If you instead call a private endpoint with the wrong scope or expired
credentials, the server returns 401/403 and the transport maps it to
[`KalshiAuthError`](errors.md). `AuthRequiredError` is a subclass of
`KalshiAuthError`, so catching the parent covers both.

## Direct `KalshiAuth` usage

For the [WebSocket](websockets.md) client and other lower-level use cases you
may want to construct `KalshiAuth` directly:

```python
from kalshi import KalshiAuth

# From a key file
auth = KalshiAuth.from_key_path("your-key-id", "~/.kalshi/private_key.pem")

# From a PEM string already in memory
auth = KalshiAuth.from_pem("your-key-id", pem_string)

# From the environment — raises if vars are missing
auth = KalshiAuth.from_env()

# From the environment — returns None on missing creds, but still raises
# KalshiAuthError if vars are set but malformed
maybe_auth = KalshiAuth.try_from_env()
```

### Key format constraints

`from_pem` and `from_key_path` are strict about format. If your key fails to
load, check:

- **Must be RSA.** EC, Ed25519, DSA keys are rejected.
- **Must be PKCS#8** (`-----BEGIN PRIVATE KEY-----`). Legacy PKCS#1
  (`-----BEGIN RSA PRIVATE KEY-----`) is supported by the underlying
  `cryptography` library on a best-effort basis.
- **Passphrase-protected keys are supported via `password=`** — see below. If
  you load an encrypted PEM without supplying a password, `KalshiAuth` raises
  `KalshiAuthError` with a hint pointing at the `password=` parameter and the
  `KALSHI_PRIVATE_KEY_PASSPHRASE` env var.

### Passphrase-protected keys

Encrypted PEMs are a recommended practice for trading keys: you keep the key
at-rest encrypted on disk or in a secret manager. The SDK accepts a
`password=` keyword on every loader so you don't have to write a plaintext key
to disk:

```python
from kalshi import KalshiAuth, KalshiClient

# Inline literal (don't hard-code in real code — pull from a secret manager).
auth = KalshiAuth.from_key_path(
    "your-key-id",
    "~/.kalshi/encrypted_key.pem",
    password="hunter2",
)

# Deferred fetch: pass a zero-arg callable. The SDK invokes it during load,
# so the secret never sits in the calling frame longer than necessary.
auth = KalshiAuth.from_pem(
    "your-key-id",
    pem_string,
    password=lambda: secret_manager.get("kalshi/passphrase"),
)

# Bytes are accepted too.
auth = KalshiAuth.from_pem("your-key-id", pem, password=b"hunter2")
```

For env-driven flows, set `KALSHI_PRIVATE_KEY_PASSPHRASE` alongside
`KALSHI_PRIVATE_KEY` / `KALSHI_PRIVATE_KEY_PATH`:

```bash
export KALSHI_KEY_ID="..."
export KALSHI_PRIVATE_KEY_PATH="~/.kalshi/encrypted_key.pem"
export KALSHI_PRIVATE_KEY_PASSPHRASE="hunter2"
```

```python
from kalshi import KalshiClient

with KalshiClient.from_env() as client:
    ...
```

`KalshiClient.from_env()` has no `password=` kwarg — it reads the passphrase
only from `KALSHI_PRIVATE_KEY_PASSPHRASE`. For programmatic passphrase control,
build a `KalshiAuth` (above) and pass it as `auth=`. (The perps
`PerpsClient.from_env()` *does* accept a `password=` kwarg.)

Wherever a `password=` argument is accepted (the `KalshiAuth.from_*`
constructors and `PerpsClient`), it always wins over an environment passphrase
when both are supplied. A wrong passphrase
raises `KalshiAuthError` ("Invalid PEM private key…"); a missing passphrase
for an encrypted PEM raises `KalshiAuthError` pointing at the `password=`
parameter.

If you'd rather store the key unencrypted, you can still strip the passphrase
with `openssl pkey`:

```bash
openssl pkey -in encrypted.pem -out unencrypted.pem
```
### Manual signing

`KalshiAuth.sign_request(method, path, timestamp_ms=None)` is part of the
public API for callers building custom transports. The path is the URL path
only — query string stripped, trailing slash stripped (except for the literal
`/`), with percent-encoded sequences normalized to uppercase hex per RFC 3986.

```python
from kalshi import KalshiAuth

auth = KalshiAuth.from_env()
headers = auth.sign_request("GET", "/trade-api/v2/exchange/status")
# headers = {"KALSHI-ACCESS-KEY": ..., "KALSHI-ACCESS-SIGNATURE": ...,
#            "KALSHI-ACCESS-TIMESTAMP": ...}
```

### Async RSA-PSS sign offload

`KalshiAuth.sign_request_async(method, path, timestamp_ms=None)` is the
coroutine version of `sign_request()`. It offloads the RSA-PSS signing
(typically 1–10 ms on a 2048-bit key) onto a **dedicated**
`ThreadPoolExecutor(max_workers=2)` lazy-initialised on first use, so signs
don't queue behind `loop.getaddrinfo` / file I/O / other `to_thread()` work
on a busy event loop:

```python
headers = await auth.sign_request_async("GET", "/trade-api/v2/exchange/status")
```

The async REST transport (`AsyncTransport.request`) and async WebSocket
connect (`ConnectionManager._build_auth_headers`) both use this path
automatically — relevant during reconnect storms where cold DNS resolution
(5–50 ms) would otherwise dominate the sign cost. The sync `sign_request`
API is unchanged for sync-transport callers.

`KalshiAuth.close()` shuts the executor down; `KalshiClient.close()` and
`AsyncKalshiClient.close()` chain into it, so you only need to call it
directly if you construct `KalshiAuth` standalone (e.g. for the WebSocket
with no REST client alongside).

## FIX authentication

The [FIX subsystem](fix.md) reuses this same RSA-PSS key — the logon signature
rides the FIX `RawData` field. `FixClient` reads the same `KALSHI_*` variables (or
`from_auth(auth)` reuses an existing `KalshiAuth`); the margin `MarginFixClient`
uses the separate `KALSHI_PERPS_*` key. No FIX-specific credentials are needed.

See the [API reference](reference.md) for the full surface.
