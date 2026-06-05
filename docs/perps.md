# Perps (margin) trading

Kalshi's **Perps** (perpetual futures / margin) API is a separate exchange on its
own host. The SDK exposes it through standalone clients rather than a namespace on
`KalshiClient`, because the perps exchange uses a different host and Kalshi
recommends **separate API keys** for it.

| Surface | Client | Host (prod / demo) | Auth |
|---|---|---|---|
| Perps REST | `PerpsClient` / `AsyncPerpsClient` | `external-api.kalshi.com` / `external-api.demo.kalshi.co` (`/trade-api/v2`) | RSA-PSS (same signer as `KalshiClient`) |
| Perps WebSocket | `PerpsWebSocket` | `external-api-margin-ws.kalshi.com` / `external-api-margin-ws.demo.kalshi.co` (`/trade-api/ws/v2/margin`) | RSA-PSS apiKey |
| SCM "Klear" | `KlearClient` / `AsyncKlearClient` | `api.klear.kalshi.com` / `demo-api.kalshi.co` (`/klear-api/v1`) | cookie-session + MFA |

The RSA-PSS signer and the HTTP transport are **reused unchanged** from the
prediction API — only the host, config, and credentials differ.

## Client construction

```python
from kalshi import PerpsClient

# Explicit credentials:
with PerpsClient(
    key_id="your-perps-key-id",
    private_key_path="~/.kalshi/perps_key.pem",
    demo=True,
) as perps:
    print(perps.exchange.status())
```

`PerpsConfig.production()` / `PerpsConfig.demo()` build the canonical environments;
pass a `PerpsConfig` for full control (timeouts, retry policy, custom JSON loaders).
See [Authentication](authentication.md) for how RSA-PSS keys are generated and
[Configuration](configuration.md) for the config surface (shared with `KalshiConfig`).

### Environment variables (`from_env`)

Perps credentials live under a **separate** `KALSHI_PERPS_*` namespace so they
never collide with the prediction-API `KALSHI_*` vars:

| Variable | Purpose |
|---|---|
| `KALSHI_PERPS_KEY_ID` | perps API key id (omit for an unauthenticated client) |
| `KALSHI_PERPS_PRIVATE_KEY` / `KALSHI_PERPS_PRIVATE_KEY_PATH` | RSA private key (PEM string or file) |
| `KALSHI_PERPS_PRIVATE_KEY_PASSPHRASE` | optional passphrase for an encrypted PEM (a `password=` kwarg overrides it) |
| `KALSHI_PERPS_API_BASE_URL` | optional REST base-URL override |
| `KALSHI_PERPS_WS_BASE_URL` | optional WS base-URL override (keeps the WS feed off production when overriding REST) |
| `KALSHI_PERPS_DEMO` | `"true"` routes to the demo exchange |

```python
from kalshi import AsyncPerpsClient

async with AsyncPerpsClient.from_env(demo=True) as perps:
    ...
```

## Resource families

| Attribute | Endpoints |
|---|---|
| `exchange` | `status()`, `enabled()` (per-member access gate), `risk_parameters()` |
| `markets` | `list()`, `get()`, `orderbook()`, `candlesticks()` |
| `orders` | `create()`, `get()`, `list()` / `list_all()`, `cancel()`, `decrease()`, `amend()`, `list_fcm()` / `list_all_fcm()` |
| `order_groups` | `list()`, `get()`, `create()`, `delete()`, `reset()`, `trigger()`, `update_limit()` |
| `portfolio` | `positions()`, `fills()` / `fills_all()`, `trades()` / `trades_all()` |
| `margin` | `balance()`, `risk()`, `notional_risk_limit()`, `fee_tiers()` |
| `funding` | `rate_estimate()`, `historical_rates()`, `history()` |
| `transfers` | `transfer_instance()`, `create_subaccount()`, `transfer_subaccount()` |

The margin order side is `bid` / `ask` (not the prediction API's `yes` / `no`).
Orders create/cancel/decrease/amend are POSTs/DELETEs and are **never retried**.

## Value types & timestamps

- Prices are `DollarDecimal` — `FixedPointDollars` strings with up to 6 decimal
  places, parsed to `Decimal` (no float on the price path).
- Counts are `FixedPointCount` — 2-decimal fixed-point with an `_fp` wire suffix.
- `number/double` ratios (margin thresholds, funding rate) use `MultiplierDecimal`
  to avoid binary-float drift.
- **REST** timestamps are RFC3339 (`AwareDatetime`); some query/response fields are
  Unix-seconds `int`.
- **WebSocket** timestamps are Unix epoch **milliseconds** on `*_ms`-suffixed
  fields (`ts_ms`, `created_ts_ms`, `next_funding_time_ms`, …) — a real parsing
  difference from the event-contract WS.

## Funding mechanics

Funding is the perpetual-futures tether: periodic payments between longs and shorts
keep the perp's mark price near its index. The `funding` resource exposes the
current in-progress estimate, historical applied rates, and the authenticated
user's per-payment history:

```python
est = perps.funding.rate_estimate(ticker="BTC-PERP")
print(est.funding_rate, est.next_funding_time)        # in-progress estimate
rows = perps.funding.history(start_date="2026-01-01", end_date="2026-02-01")
```

`subscribe_ticker` on the WS also carries the live `funding_rate` and
`next_funding_time_ms`.

## Risk & balance introspection

```python
bal = perps.margin.balance(compute_available_balance=True)
for sub in bal.subaccount_balances:
    print(sub.subaccount, sub.account_equity, sub.maintenance_margin)

risk = perps.margin.risk()
print(risk.account_leverage, risk.total_maintenance_margin)
for pos in risk.positions:
    print(pos.market_ticker, pos.position_leverage, pos.estimated_liquidation_price)
```

## WebSocket streaming

```python
from kalshi import PerpsWebSocket
from kalshi.perps import PerpsConfig

ws = PerpsWebSocket(auth=perps._auth, config=PerpsConfig.demo())
async with ws.connect() as session:
    async for msg in await session.subscribe_ticker(tickers=["BTC-PERP"]):
        if msg.msg.funding_rate is not None:
            print(msg.msg.funding_rate.rate, msg.msg.funding_rate.next_funding_time_ms)
```

Six data channels — `orderbook_delta` (snapshot + delta, sequenced), `ticker`,
`trade`, `fill`, `user_orders`, `order_group_updates`. The connection, sequence-gap
detection, reconnect, and backpressure machinery are reused from the event-contract
WS stack (see [WebSocket](websockets.md)); the perps orderbook is `bid` / `ask`.
The equities-only channels (`market_positions`, `multivariate*`, `communications`,
`market_lifecycle_v2`) have no perps counterpart.

## Self-Clearing-Member "Klear" API

The Klear API (settlement balances, obligations, margin reports, withdrawals) is a
third surface with a **completely different auth model** — email + password (+ MFA)
via `POST /log_in`, which sets a session cookie replayed on every subsequent
request. It is exposed via `KlearClient` / `AsyncKlearClient`:

```python
from kalshi import KlearClient

with KlearClient(demo=True) as klear:
    resp = klear.login(email="...", password="...")
    if resp.required_mfa_method:                 # MFA challenge
        klear.login(email="...", password="...", code="123456")
    reports = klear.margin.margin_reports(start_date="2026-01-01", end_date="2026-02-01")
    bal = klear.margin.settlement_balance()
```

Money fields on the Klear margin schemas are integer **centicents** (`1 USD =
10,000 centicents`); only the withdrawal `amount` is a fixed-point dollar string.
`klear.margin.withdraw_settlement_balance(amount="500.00")` validates the amount as
positive at construction (the single real-money write) before any request is sent.
Credentials and the session cookie are never logged or shown in `repr()`.
