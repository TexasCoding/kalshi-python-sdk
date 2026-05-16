# Authentication

Kalshi uses RSA-PSS request signing. You'll need:

- A **key ID** (string, identifies the key on Kalshi's side).
- A **private key** — RSA, PEM-encoded.

Generate the pair in your [Kalshi account settings](https://kalshi.com/account/profile)
and download the PEM file. The signing scheme used internally is
RSA-PSS / SHA256 / MGF1(SHA256) / salt = digest length / base64 — you don't need
to implement any of that yourself; the SDK does it for you.

## Option 1 — Key file path (most common)

```python
from kalshi import KalshiClient

with KalshiClient(
    key_id="your-key-id",
    private_key_path="~/.kalshi/private_key.pem",
) as client:
    ...
```

`~` is expanded for you. Pass a `pathlib.Path` or a string.

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
an **unauthenticated** client. Public endpoints still work; private endpoints
raise `AuthRequiredError`.

## Option 3 — In-memory PEM

If you store the private key in a secret manager (Vault, AWS Secrets Manager,
GCP Secret Manager, …), set `KALSHI_PRIVATE_KEY` to the PEM contents:

```bash
export KALSHI_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
MIIEv...
-----END PRIVATE KEY-----"
```

Then `KalshiClient.from_env()` will load the key directly without touching the
filesystem.

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

You don't need credentials for public market data:

```python
from kalshi import KalshiClient

with KalshiClient(demo=True) as client:
    assert client.is_authenticated is False
    markets = client.markets.list(status="open", limit=5)
```

Any private endpoint call on an unauthenticated client raises
`AuthRequiredError` (a subclass of `KalshiAuthError`) immediately, before
hitting the network.

## Direct `KalshiAuth` usage

For the [WebSocket](websockets.md) client and other lower-level use cases you
may want to construct `KalshiAuth` directly:

```python
from kalshi import KalshiAuth

# From a key file
auth = KalshiAuth.from_key_path("your-key-id", "~/.kalshi/private_key.pem")

# From the environment (returns None if unset; use from_env() to raise instead)
maybe_auth = KalshiAuth.try_from_env()
```

See the [API reference](reference.md) for the full surface.
