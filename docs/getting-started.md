# Getting Started

This page walks you from a blank environment to your first authenticated request
against Kalshi's demo API.

## Install

```bash
pip install kalshi-sdk
```

Requires Python 3.12 or newer.

## Create an API key

1. Sign in to your Kalshi account. Demo and production are **separate accounts** with
   **separate API keys** — pick one for now and create the account there:
    - Demo (recommended for development): [demo.kalshi.co](https://demo.kalshi.co)
    - Production: [kalshi.com](https://kalshi.com)
2. From the same environment you signed into, open your account settings and create
   an API key:
    - Demo: [demo.kalshi.co/account/profile](https://demo.kalshi.co/account/profile)
    - Production: [kalshi.com/account/profile](https://kalshi.com/account/profile)
3. Download the private key PEM file and store it somewhere safe, e.g.
   `~/.kalshi/private_key.pem`. Treat it like a password.

A demo key cannot authenticate against production and vice versa. The rest of this
guide assumes a demo key and `demo=True`.

You do **not** need an API key to read public market data — skip ahead to
["Hello, markets" (no auth)](#hello-markets-no-auth) if you just want to browse.

## Hello, world (authenticated)

```python
from kalshi import KalshiClient

with KalshiClient(
    key_id="your-key-id",
    private_key_path="~/.kalshi/private_key.pem",
    demo=True,  # use the sandbox while learning
) as client:
    page = client.markets.list(status="open", limit=5)
    for market in page:
        print(market.ticker, market.yes_bid, market.yes_ask)
```

The client is a context manager — the underlying `httpx.Client` is closed on
exit. If you can't use a `with` block, call `client.close()` yourself.

## Hello, markets (no auth)

Public endpoints work without credentials. The client is "unauthenticated" but
all read-only resource methods still function:

```python
from kalshi import KalshiClient

with KalshiClient(demo=True) as client:
    assert client.is_authenticated is False
    markets = client.markets.list(status="open", limit=5)
    for market in markets:
        print(market.ticker)
```

Calling a private endpoint (e.g. placing an order) on an unauthenticated client
raises [`AuthRequiredError`](errors.md).

## Async

The async client mirrors the sync client. `list_all()` returns an
`AsyncIterator` directly, so `async for` just works:

```python
import asyncio
from kalshi import AsyncKalshiClient

async def main() -> None:
    async with AsyncKalshiClient(
        key_id="your-key-id",
        private_key_path="~/.kalshi/private_key.pem",
        demo=True,
    ) as client:
        async for market in client.markets.list_all(status="open"):
            print(market.ticker, market.yes_bid)

asyncio.run(main())
```

## Place an order (demo)

```python
from kalshi import KalshiClient

with KalshiClient.from_env() as client:
    order = client.orders.create(
        ticker="EXAMPLE-25-T",
        side="yes",
        action="buy",
        count=10,
        yes_price="0.65",          # 65 cents — strings or Decimals, never float
        time_in_force="good_till_canceled",
        client_order_id="my-unique-id",  # idempotency key
    )
    print(order.order_id, order.status)
```

Prices are decimal dollars per the Kalshi spec. Internally the SDK uses
`Decimal` via the `DollarDecimal` type — never `float`.

## Where to next

- [Authentication](authentication.md) — all the ways to provide credentials.
- [API Reference](reference.md) — the full auto-generated reference.
