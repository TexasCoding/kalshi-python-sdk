# Perps (margin) trading

Kalshi's **Perps** (perpetual futures / margin) API is a separate exchange on its
own host. The SDK exposes it through standalone clients rather than a namespace on
`KalshiClient`, because the perps exchange uses a different host and Kalshi
recommends **separate API keys** for it.

| Surface | Client | Host (prod / demo) | Auth |
|---|---|---|---|
| Perps REST | `PerpsClient` / `AsyncPerpsClient` | `external-api.kalshi.com` / `external-api.demo.kalshi.co` (`/trade-api/v2`) | RSA-PSS (same signer as `KalshiClient`) |
| Perps WebSocket | `PerpsWebSocket` | `external-api-margin-ws.kalshi.com` / `external-api-margin-ws.demo.kalshi.co` (`/trade-api/ws/v2/margin`) | RSA-PSS apiKey |
| SCM "Klear" | `KlearClient` / `AsyncKlearClient` | `api.klear.kalshi.com` / `demo-api.kalshi.co` (`/klear-api/v1`) | Bearer `admin_user_id:access_token` |

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
| `orders` | `create()`, `get()`, `list()` / `list_all()`, `cancel()`, `decrease()`, `amend()` |
| `order_groups` | `list()`, `get()`, `create()`, `delete()`, `reset()`, `trigger()`, `update_limit()` |
| `portfolio` | `positions()`, `fills()` / `fills_all()`, `trades()` / `trades_all()` |
| `margin` | `balance()`, `risk()`, `notional_risk_limit()`, `fee_tiers()`, `api_limits()` |
| `funding` | `rate_estimate()`, `historical_rates()`, `history()` |
| `transfers` | `transfer_instance()`, `create_subaccount()`, `transfer_subaccount()` |
| `fcm` | `create_subtrader(subtrader_suffix=...)` — `POST /margin/fcm/subtraders` |

The margin order side is `bid` / `ask` (not the prediction API's `yes` / `no`).
Orders create/cancel/decrease/amend are POSTs/DELETEs and are **never retried**.

!!! warning "Deprecated in v7.2.0 — `list_fcm` / `list_all_fcm`"
    Kalshi removed `GET /margin/fcm/orders` from the perps OpenAPI. The SDK
    methods still exist (sync + async) but emit a `DeprecationWarning` and may
    404 against the live API. They will be removed in a future major release
    once the removal is confirmed permanent. Prediction-API FCM
    (`client.fcm.*` on `/fcm/*`) is unchanged.

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
- **Notional values** — `MarginMarket` (REST) and the margin ticker WS payload
  carry optional `volume_notional_value` / `volume_24h_notional_value` /
  `open_interest_notional_value` (`DollarDecimal | None`); `MarginMarketCandlestick`
  carries the same fields as **required** (inherent to a settled historical
  record). `MarginMarket.leverage_estimates` maps notional position sizes
  (`"1000"`, `"10000"`, …) to `MultiplierDecimal` leverage, or `None` when margin
  config / price data is unavailable.
- **Mark prices** (since the v3.21.0 spec sync) — `MarginMarket` carries three
  optional reference-price objects: `settlement_mark_price`,
  `liquidation_mark_price`, and `reference_price`, each a nested `TickerPrice`
  (`TickerPrice | None`). `TickerPrice` is a new model with `price`
  (`DollarDecimal`, a `FixedPointDollars` USD string) and `ts_ms` (the source
  timestamp in epoch **milliseconds**, `int`). All three are absent from the spec
  `required` list, so they are `None` when the upstream price is unavailable.
- **Exchange shard** (SDK v11.0.0) — `MarginMarket.exchange_index` (`int`) is
  required; order groups may only reference markets that share their
  `exchange_index`.
- **Trading schedule** (since the v3.25.0 spec sync / SDK v7.1.0) — `MarginMarket`
  carries a **required** `schedule` key typed `MarginMarketSchedule | None`.
  `None` means the market trades 24/7. When present, `MarginMarketSchedule` has
  `is_open: bool` plus `next_close_ts` / `next_open_ts` (`int | None`, Unix
  epoch **seconds**): `next_close_ts` is null while closed, `next_open_ts` is
  null while open.
- **Subaccounts** (since the v3.21.0 spec sync) — `MarginPosition` (the
  `portfolio.positions()` rows) carries a **required** `subaccount` (`int`)
  identifying which subaccount holds the position.
- **Portfolio hedging** (since the v3.23.0 spec sync) — `MarginPosition` and
  `MarginRiskPosition` carry a **required** `is_portfolio` (`bool`), `True` when
  the position is hedged within a portfolio so its margin is computed at the
  portfolio level. `MarginOrder` gained an optional `order_reason`
  (`"liquidation"` / `"take_profit_stop_loss"`) identifying system-generated
  orders.

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

`perps.margin.api_limits()` (`GET /account/limits/perps`) returns the Perps API
tier limits in the same shape as the prediction API's `client.account.limits()`
(an `AccountApiLimits` with `usage_tier`, `read`/`write` token buckets, and the
`grants` list of `ApiUsageLevelGrant`).

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
The prediction-only channels (`market_positions`, `multivariate*`, `communications`,
`market_lifecycle_v2`, `cfbenchmarks_value`) have no perps counterpart.

## Self-Clearing-Member "Klear" API

The Klear API (settlement balances, obligations, margin reports, withdrawals) is a
third surface with a **different auth model** — a pre-generated Bearer token passed
as `Authorization: Bearer <admin_user_id>:<access_token>` on every request. Generate
the token and find your admin user id at <https://klearing.kalshi.com> (the
"Security" page). It is exposed via `KlearClient` / `AsyncKlearClient`:

```python
from kalshi import KlearClient

with KlearClient(admin_user_id="...", access_token="...", demo=True) as klear:
    reports = klear.margin.margin_reports(start_date="2026-01-01", end_date="2026-02-01")
    bal = klear.margin.settlement_balance()
```

Credentials can also come from the environment via `KlearClient.from_env()` (reads
`KALSHI_KLEAR_ADMIN_USER_ID` / `KALSHI_KLEAR_ACCESS_TOKEN`).

`klear.margin.active_obligations()` returns all currently-active settlement
obligations. `klear.margin.settlement_estimate_by_asset_class()` returns
next-settlement estimates keyed by asset class. (The singular
`active_obligation()` / `settlement_estimate()` endpoints were removed upstream
in the v11.0.0 reconcile.)

When an `ObligationEntry` inline detail array is capped at 1000 rows, the
matching `*_truncated` flag is set; page the full set via:

```python
for row in klear.margin.settlement_details_all(ob.id):
    ...
for row in klear.margin.maintenance_margin_details_all(ob.id):
    ...
for row in klear.margin.funding_payments_all(ob.id):
    ...
```

Each `AssetClassSettlementEstimate` exposes optional
`omitted_subtrader_count` / `group_breakdowns` / `omitted_group_count`.
`MaintenanceMarginDetail` may include `margin_group_id`.

Subtrader groups — margined as one netted portfolio:

```python
groups = klear.margin.list_subtrader_groups()
created = klear.margin.create_subtrader_group(subtrader_ids=["st-a", "st-b"])
klear.margin.update_subtrader_group(created.group_id, subtrader_ids=["st-a", "st-c"])
klear.margin.delete_subtrader_group(created.group_id)
```

Money fields on the Klear margin schemas are integer **centicents** (`1 USD =
10,000 centicents`); only the withdrawal `amount` is a fixed-point dollar string.
`klear.margin.withdraw_settlement_balance(amount="500.00")` validates the amount as
positive at construction (the single real-money write) before any request is sent.
The Bearer `access_token` is never logged and is redacted in `repr()` (only the
non-secret `admin_user_id` is shown).

## Perps over FIX

The margin product is also reachable over the FIX protocol via `MarginFixClient`
(`from kalshi import MarginFixClient`), which reuses the shared FIX core with the
`KALSHI_PERPS_*` key and fixed-point-dollar pricing. Margin supports the
order-entry, drop-copy, and market-data sessions (no RFQ / post-trade). See
[FIX protocol](fix.md).
