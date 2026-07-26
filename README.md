# kalshi-sdk

<p align="center">
  <img src="docs/assets/kalshi-sdk-hero.jpg" alt="Kalshi Python SDK — Trade the Future · Full REST + WebSocket · Sync + Async" width="780">
</p>

A professional, spec-first Python SDK for the [Kalshi](https://kalshi.com) prediction markets API.

[![PyPI version](https://img.shields.io/pypi/v/kalshi-sdk.svg)](https://pypi.org/project/kalshi-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/kalshi-sdk.svg)](https://pypi.org/project/kalshi-sdk/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Type checked: mypy strict](https://img.shields.io/badge/mypy-strict-blue.svg)](https://mypy.readthedocs.io/)

- **Full coverage** of the Kalshi REST API (104 operations across 19 resources, OpenAPI v3.26.0) and WebSocket API (12 typed `subscribe_*` channels + 2 escape-hatch).
- **Perps (margin) API**: standalone `PerpsClient` / `AsyncPerpsClient` + `PerpsWebSocket` for the perpetual-futures exchange (34 REST operations, 6 WS channels), plus a `KlearClient` for the Self-Clearing-Member "Klear" settlement API (11 operations). See [Perps (margin) trading](#perps-margin-trading).
- **FIX protocol**: an async-first FIX engine (FIXT.1.1 / FIX50SP2) for both products — order-entry, drop-copy, market-data, post-trade (prediction), and RFQ (prediction) sessions (plus order-group management over the order-entry session) with typed message models, sequence recovery, and order-book / settlement reassembly. `from kalshi import FixClient` / `MarginFixClient`. See [FIX protocol](#fix-protocol-low-latency-trading).
- **V2 event-market orders**: `create_v2` / `amend_v2` / `decrease_v2` / `cancel_v2` plus batched variants on `/portfolio/events/orders/*` — the only order-write surface.
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

Orders are written through the V2 event-market family on
`/portfolio/events/orders/*` — event-scoped semantics with single-book
`bid`/`ask` sides and fixed-point dollar prices.

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
        price=Decimal("0.50"),              # 50 cents
        time_in_force="good_till_canceled",
        self_trade_prevention_type="taker_at_cross",
    ))
    print(resp.order_id, resp.remaining_count, resp.fill_count)
```

Prices and counts are `Decimal` — never `float`. Internally the SDK uses the
`DollarDecimal` type for prices (FixedPointDollars on the wire). `side` is the
book side (`"bid"` / `"ask"`), not `"yes"` / `"no"`, and `client_order_id` is
required on `CreateOrderV2Request` (the server uses it for idempotency).

The V2 surface is **model-only** — there is no kwarg overload. Every write
takes a fully-constructed request model whose `model_config = {"extra":
"forbid"}` rejects phantom keys at construction time. Cancel takes the order id
directly:

```python
client.orders.cancel_v2(resp.order_id)
```

See [V2 orders docs](https://texascoding.github.io/kalshi-python-sdk/resources/orders/#v2-event-market-orders) for `amend_v2` / `decrease_v2` / `batch_create_v2` / `batch_cancel_v2`.

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

Available channels (12 typed + 2 escape-hatch). Twelve have dedicated
`subscribe_*` methods — `subscribe_ticker`, `subscribe_trade`,
`subscribe_orderbook_delta`, `subscribe_fill`, `subscribe_market_positions`,
`subscribe_user_orders`, `subscribe_order_group`,
`subscribe_market_lifecycle`, `subscribe_multivariate`,
`subscribe_multivariate_lifecycle`, `subscribe_communications`,
`subscribe_cfbenchmarks_value`. The
AsyncAPI-declared `control_frames` and `root` channels are reachable
through the generic `subscribe(channel, ...)` escape hatch. See
[docs/websockets.md](docs/websockets.md#the-12-channels) for the full
channel table.

## Perps (margin) trading

Kalshi's **Perps** (perpetual futures / margin) API is a separate exchange on its
own host. The SDK exposes it through standalone `PerpsClient` / `AsyncPerpsClient`
(and `PerpsWebSocket`), reusing the same RSA-PSS auth as `KalshiClient` but with
**separate API keys** issued for the perps exchange — prod base URL
`https://external-api.kalshi.com/trade-api/v2`, demo
`https://external-api.demo.kalshi.co/trade-api/v2`.

```python
from kalshi import PerpsClient

# Reads KALSHI_PERPS_KEY_ID + KALSHI_PERPS_PRIVATE_KEY[_PATH] (separate from KALSHI_*).
with PerpsClient.from_env(demo=True) as perps:
    print(perps.exchange.status())            # is the margin exchange trading?
    for m in perps.markets.list(status="active"):
        print(m.ticker, m.bid, m.ask)
    print(perps.margin.balance())             # per-subaccount balance breakdown
```

```python
import asyncio
from kalshi import AsyncPerpsClient

async def main() -> None:
    async with AsyncPerpsClient.from_env(demo=True) as perps:
        async for order in perps.orders.list_all():
            print(order.order_id, order.price, order.remaining_count)

asyncio.run(main())
```

Resource families on the perps client: `exchange`, `markets`, `orders`,
`order_groups`, `portfolio`, `margin` (balance/risk/fees), `funding`, `transfers`.
Real-time streaming via `PerpsWebSocket` — `subscribe_ticker` (carries
`funding_rate` + `next_funding_time_ms`), `subscribe_orderbook_delta`,
`subscribe_trade`, `subscribe_fill`, `subscribe_user_orders`,
`subscribe_order_group`.

Prices are `DollarDecimal` (FixedPointDollars, up to 6 decimals); counts are
`FixedPointCount` (2 decimals, `_fp` wire suffix). REST timestamps are RFC3339;
**WebSocket timestamps are Unix epoch milliseconds** (`*_ms` fields). The
Self-Clearing-Member "Klear" settlement API (margin reports, settlement balances,
obligations, withdrawals) is a third surface exposed via `KlearClient`, which uses
**Bearer token** auth (`KlearClient(admin_user_id=..., access_token=...)`)
rather than RSA-PSS. Full guide: [docs/perps.md](docs/perps.md).

## FIX protocol (low-latency trading)

For persistent, low-latency sessions the SDK includes a hand-rolled, **async-first**
FIX engine (FIXT.1.1 / FIX50SP2) for both products: order-entry, drop-copy,
market-data, post-trade (prediction), and RFQ (prediction) sessions — plus
order-group management over the order-entry session — with typed message models,
automatic logon/heartbeat/sequence recovery, and order-book / settlement
reassembly. It reuses the same RSA-PSS key as the REST client (`KALSHI_*` for
prediction, `KALSHI_PERPS_*` for margin).

```python
import asyncio
from decimal import Decimal
from kalshi import FixClient, FixEnvironment
from kalshi.fix import NewOrderSingle, ExecutionReport, Side, decode_app_message

async def main() -> None:
    async def on_message(raw) -> None:
        msg = decode_app_message(raw)
        if isinstance(msg, ExecutionReport):
            print(msg.cl_ord_id, msg.exec_type, msg.ord_status)

    client = FixClient.from_env(environment=FixEnvironment.DEMO)
    async with client.order_entry(on_message=on_message) as session:
        await session.send(NewOrderSingle(
            cl_ord_id="order-1", symbol="KXNBAGAME-26MAY25NYKCLE-NYK",
            side=Side.BUY_YES, order_qty=Decimal("10"), price=Decimal("0.55"),
        ))
        await asyncio.sleep(2)

asyncio.run(main())
```

Prediction uses `FixClient`; margin uses `MarginFixClient`. Full guide:
[docs/fix.md](docs/fix.md).

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
