# kalshi-sdk

<p align="center">
  <img src="docs/assets/kalshi-sdk-hero.jpg" alt="Kalshi Python SDK — Trade the Future · Full REST + WebSocket · Sync + Async" width="780">
</p>

A professional, spec-first Python SDK for the [Kalshi](https://kalshi.com) prediction markets API.

[![PyPI version](https://img.shields.io/pypi/v/kalshi-sdk.svg)](https://pypi.org/project/kalshi-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/kalshi-sdk.svg)](https://pypi.org/project/kalshi-sdk/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Type checked: mypy strict](https://img.shields.io/badge/mypy-strict-blue.svg)](https://mypy.readthedocs.io/)

- **Full coverage** of the Kalshi REST API (98 operations across 19 resources, OpenAPI v3.19.0) and WebSocket API (11 typed `subscribe_*` channels + 2 escape-hatch).
- **V2 event-market orders**: `create_v2` / `amend_v2` / `decrease_v2` / `cancel_v2` plus batched variants on `/portfolio/events/orders/*`. Legacy `/portfolio/orders` keeps working — deprecated no earlier than May 6, 2026.
- **Funding & cost introspection**: `portfolio.deposits()`, `portfolio.withdrawals()`, `account.endpoint_costs()`.
- **Sync and async** clients sharing one transport — no thread-pool wrapping.
- **Typed end-to-end**: Pydantic v2 models, `mypy --strict` clean, ships `py.typed`. `Literal` types on fixed-enum kwargs.
- **Spec-aligned with drift guards**: hard-fail contract tests catch query, body, and WebSocket payload drift on every commit.
- **Safe defaults**: only idempotent verbs (`GET`/`HEAD`/`OPTIONS`) retry; `POST`/`DELETE` never retry to avoid duplicate orders or cancels.
- **DataFrame-ready**: optional `pandas` / `polars` extras for analysis workflows.
- **Offline-testable**: record/replay mock transport (`kalshi.testing`) for SDK consumers building integration tests.

📖 Full documentation: <https://texascoding.github.io/kalshi-python-sdk/>

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

Every POST/PUT/DELETE-with-body method also accepts a pre-built request model
as an alternative to individual kwargs (useful for programmatic order
construction):

```python
from kalshi import CreateOrderRequest

client.orders.create(request=CreateOrderRequest(
    ticker="EXAMPLE-25-T", side="yes", action="buy",
    count=10, yes_price="0.65",
))
```

### V2 event-market orders

Spec v3.18.0 introduced the V2 family on `/portfolio/events/orders/*` —
event-scoped semantics with single-book `bid`/`ask` sides and fixed-point
dollar prices. Legacy `/portfolio/orders` keeps working and will be
deprecated no earlier than May 6, 2026.

```python
import uuid
from decimal import Decimal
from kalshi import KalshiClient, CreateOrderV2Request

with KalshiClient.from_env() as client:
    resp = client.orders.create_v2(request=CreateOrderV2Request(
        ticker="EVENT-MKT",
        client_order_id=str(uuid.uuid4()),  # required + server idempotency key
        side="bid",                         # BookSideLiteral: "bid" | "ask"
        count=Decimal("10"),
        price=Decimal("0.50"),
        time_in_force="good_till_canceled",
        self_trade_prevention_type="taker_at_cross",
    ))
    print(resp.order_id, resp.remaining_count, resp.fill_count)
```

The V2 surface is model-only (no kwarg overload); pass a fully-constructed
request model. See [V2 orders docs](https://texascoding.github.io/kalshi-python-sdk/resources/orders/#v2-event-market-orders) for amend/decrease/batch variants.

## WebSocket streaming

```python
import asyncio
from kalshi import KalshiAuth, KalshiConfig
from kalshi.ws import KalshiWebSocket

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

Available channels (11 typed + 2 escape-hatch). Eleven have dedicated
`subscribe_*` methods — `subscribe_ticker`, `subscribe_trade`,
`subscribe_orderbook_delta`, `subscribe_fill`, `subscribe_market_positions`,
`subscribe_user_orders`, `subscribe_order_group`,
`subscribe_market_lifecycle`, `subscribe_multivariate`,
`subscribe_multivariate_lifecycle`, `subscribe_communications`. The
AsyncAPI-declared `control_frames` and `root` channels are reachable
through the generic `subscribe(channel, ...)` escape hatch. See
[docs/websockets.md](docs/websockets.md#the-11-channels) for the full
channel table.

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
    # Connection pool / HTTP-2 tuning (opt-in; defaults preserve v1 behavior)
    http2=False,
    limits=None,  # httpx.Limits(max_connections=..., keepalive_expiry=...)
    extra_headers={"X-My-Tag": "foo"},
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
    if not page.has_next:
        break
    page = client.markets.list(status="open", limit=200, cursor=page.cursor)

# Or just:
for market in client.markets.list_all(status="open"):
    ...

# Need a hard cap on pages (e.g. preview / quick sample)?
for market in client.markets.list_all(status="open", max_pages=5):
    ...
```

`*_all()` iterates until the server returns no cursor by default. Pass
`max_pages=N` for an explicit bound; passing `0` raises `ValueError`.

`Page[T]` also converts to a DataFrame when the optional extras are installed:

```bash
pip install 'kalshi-sdk[pandas]'   # or [polars] or [all]
```

```python
df = client.markets.list(status="open", limit=100).to_dataframe()
# Decimal and datetime preserved as native types in object columns.
```

## Testing against the SDK (no live API)

For SDK consumers who want offline integration tests, `kalshi.testing` ships
record-and-replay transports:

```python
from kalshi import KalshiClient
from kalshi.testing import RecordingTransport, ReplayTransport

# Record once against the real demo API:
with KalshiClient.from_env(transport=RecordingTransport("fixtures")) as c:
    c.exchange.status()

# Replay in tests — no network:
with KalshiClient(transport=ReplayTransport("fixtures")) as c:
    c.exchange.status()  # served from fixtures/GET_*.json
```

Fixtures are JSON; the fingerprint ignores `KALSHI-ACCESS-SIGNATURE` and
`KALSHI-ACCESS-TIMESTAMP` so signature drift between record and replay does not
break matching. **Always `.gitignore` the fixture directory when recording
against an authenticated account** — fixtures contain the full response body
(balances, positions, PII).

## Resources

| | |
|---|---|
| **Documentation site** | https://texascoding.github.io/kalshi-python-sdk/ |
| **Kalshi REST OpenAPI spec** | https://docs.kalshi.com/openapi.yaml |
| **Kalshi WebSocket AsyncAPI spec** | https://docs.kalshi.com/asyncapi.yaml |
| **Production base URL** | `https://api.elections.kalshi.com/trade-api/v2` |
| **Demo base URL** | `https://demo-api.kalshi.co/trade-api/v2` |
| **Changelog** | [CHANGELOG.md](CHANGELOG.md) |
| **Issues** | https://github.com/TexasCoding/kalshi-python-sdk/issues |

## License

MIT — see [LICENSE](LICENSE).
