# kalshi-sdk

A professional, spec-first Python SDK for the [Kalshi](https://kalshi.com) prediction markets API.

[![PyPI version](https://img.shields.io/pypi/v/kalshi-sdk.svg)](https://pypi.org/project/kalshi-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/kalshi-sdk.svg)](https://pypi.org/project/kalshi-sdk/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Type checked: mypy strict](https://img.shields.io/badge/mypy-strict-blue.svg)](https://mypy.readthedocs.io/)

- **Full coverage** of the Kalshi REST API (89 endpoints across 19 resources) and WebSocket API (12 message types).
- **Sync and async** clients sharing one transport — no thread-pool wrapping.
- **Typed end-to-end**: Pydantic v2 models, `mypy --strict` clean, ships `py.typed`.
- **Spec-aligned with drift guards**: hard-fail contract tests catch query, body, and WebSocket payload drift on every commit.
- **Safe defaults**: only idempotent verbs (`GET`/`HEAD`/`OPTIONS`) retry; `POST`/`DELETE` never retry to avoid duplicate orders or cancels.

## Install

```bash
pip install kalshi-sdk
```

Requires Python 3.12+.

## Quickstart — sync

```python
from kalshi import KalshiClient

with KalshiClient(
    key_id="your-key-id",
    private_key_path="~/.kalshi/private_key.pem",
) as client:
    page = client.markets.list(status="open", limit=10)
    for market in page:
        print(market.ticker, market.yes_bid, market.yes_ask)
```

## Quickstart — async

```python
import asyncio
from kalshi import AsyncKalshiClient

async def main() -> None:
    async with AsyncKalshiClient(
        key_id="your-key-id",
        private_key_path="~/.kalshi/private_key.pem",
    ) as client:
        # list_all() yields across pages — works directly with `async for`.
        async for market in client.markets.list_all(status="open"):
            print(market.ticker, market.yes_bid)

asyncio.run(main())
```

## Authentication

Kalshi uses RSA-PSS request signing. Generate a key pair in your Kalshi
[account settings](https://kalshi.com/account/profile) and download the PEM.

### From environment variables

```bash
export KALSHI_KEY_ID="..."
export KALSHI_PRIVATE_KEY_PATH="~/.kalshi/private_key.pem"
# or, inline:
export KALSHI_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----..."

# Optional:
export KALSHI_DEMO=true              # use the demo (sandbox) environment
export KALSHI_API_BASE_URL=...       # override base URL
```

```python
from kalshi import KalshiClient

client = KalshiClient.from_env()
```

`from_env()` returns an **unauthenticated** client if no credentials are set.
Public endpoints still work; private endpoints raise `AuthRequiredError`.

### Demo vs production

```python
KalshiClient(key_id="...", private_key_path="...", demo=True)   # sandbox
KalshiClient(key_id="...", private_key_path="...")              # production (default)
```

### Public / unauthenticated usage

You don't need credentials to read public market data:

```python
from kalshi import KalshiClient

with KalshiClient(demo=True) as client:
    assert client.is_authenticated is False
    markets = client.markets.list(status="open", limit=5)
```

## Placing orders

```python
from kalshi import KalshiClient

with KalshiClient.from_env() as client:
    order = client.orders.create(
        ticker="EXAMPLE-25-T",
        side="yes",
        action="buy",
        count=10,
        yes_price="0.65",          # 65 cents
        time_in_force="good_till_canceled",
        client_order_id="my-uuid", # idempotency key
    )
    print(order.order_id, order.status)
```

Prices are decimal dollars (e.g. `"0.65"`) per the Kalshi spec. Internally
the SDK uses `Decimal` via the `DollarDecimal` type — never `float`.

## WebSocket streaming

```python
import asyncio
from kalshi import KalshiAuth, KalshiConfig
from kalshi.ws.client import KalshiWebSocket

async def main() -> None:
    auth = KalshiAuth.from_key_path("your-key-id", "~/.kalshi/private_key.pem")
    config = KalshiConfig.demo()  # or KalshiConfig.production()

    ws = KalshiWebSocket(auth=auth, config=config)
    async with ws.connect() as session:
        stream = await session.subscribe_orderbook_delta(tickers=["EXAMPLE-25-T"])
        async for msg in stream:
            print(msg)

asyncio.run(main())
```

Available channels: `ticker`, `trade`, `orderbook_delta`, `fill`,
`market_positions`, `user_orders`, `order_group`, `market_lifecycle`,
`multivariate`, `multivariate_lifecycle`, `communications`.

## Error handling

All SDK errors inherit from `KalshiError`:

```python
from kalshi import (
    KalshiError,
    KalshiAuthError,        # 401 / 403
    AuthRequiredError,      # called private endpoint without credentials
    KalshiNotFoundError,    # 404
    KalshiValidationError,  # 400 (has .details: dict[str, str])
    KalshiRateLimitError,   # 429 (has .retry_after: float | None)
    KalshiServerError,      # 5xx
    # WebSocket-specific:
    KalshiWebSocketError,
    KalshiConnectionError,
    KalshiSequenceGapError,
    KalshiBackpressureError,
    KalshiSubscriptionError,
)

try:
    client.markets.get("DOES-NOT-EXIST")
except KalshiNotFoundError as e:
    print(e.status_code, str(e))
```

## Retry policy

- Retries on `429`, `502`, `503`, `504`, `500` (idempotent GET only).
- `POST` and `DELETE` are **never** retried — duplicate order / cancel risk.
- Exponential backoff with jitter, capped at `retry_max_delay`.
- `Retry-After` is honored but capped at `retry_max_delay` to prevent a
  server-controlled stall.

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

## Pagination

List endpoints return a `Page[T]` you can iterate, plus a `cursor` for manual
control. For "give me everything" use `list_all()`:

```python
# Manual cursor loop:
page = client.markets.list(status="open", limit=200)
while True:
    for market in page:
        ...
    if not page.has_more:
        break
    page = client.markets.list(status="open", limit=200, cursor=page.cursor)

# Or just:
for market in client.markets.list_all(status="open"):
    ...
```

## Resources

| | |
|---|---|
| **Kalshi REST OpenAPI spec** | https://docs.kalshi.com/openapi.yaml |
| **Kalshi WebSocket AsyncAPI spec** | https://docs.kalshi.com/asyncapi.yaml |
| **Production base URL** | `https://api.elections.kalshi.com/trade-api/v2` |
| **Demo base URL** | `https://demo-api.kalshi.co/trade-api/v2` |
| **Changelog** | [CHANGELOG.md](CHANGELOG.md) |
| **Issues** | https://github.com/TexasCoding/kalshi-python-sdk/issues |

## License

MIT — see [LICENSE](LICENSE).
