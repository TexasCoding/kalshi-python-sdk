# Migrating from v3.x to v4.0.0

v4.0.0 has **one breaking change**: the Self-Clearing-Member "Klear" API
(`KlearClient` / `AsyncKlearClient`) switched from cookie-session login to a
pre-generated **Bearer token**, because upstream removed `POST /log_in`.

If you do not use the Klear API, **v4.0.0 requires no code changes** — everything
else is additive. The prediction and perps trade-api surfaces (RSA-PSS auth, all
REST resources, the WebSocket and FIX clients) are unchanged.

## TL;DR — Klear cheat sheet

| Find (v3.x) | Replace (v4.0.0) |
|---|---|
| `KlearClient(demo=True)` + `client.login(email=..., password=...)` (or `code=...` for MFA) | `KlearClient(admin_user_id=..., access_token=..., demo=True)` |
| `await client.login(...)` / `client.is_authenticated` | (removed — credentials are supplied at construction) |
| `from kalshi import LogInRequest, LogInResponse` | (removed) |
| `client.auth.log_in(...)` | (removed) |

Generate the Bearer token and find your admin user id at
<https://klearing.kalshi.com> (the "Security" page). Treat the token as a secret.

## 1. Klear (SCM) Bearer authentication (breaking)

Upstream removed `POST /log_in` and the cookie-session flow. The Klear API now
authenticates with a static header on every request:

```
Authorization: Bearer <admin_user_id>:<access_token>
```

`KlearClient` / `AsyncKlearClient` now **require** `admin_user_id` and
`access_token` (keyword-only) at construction. `KlearAuth` is now a Bearer
credential holder rather than a session-state tracker.

### Before (v3.x)

```python
from kalshi import KlearClient

with KlearClient(demo=True) as klear:
    resp = klear.login(email="me@example.com", password="...")
    if resp.required_mfa_method:                  # MFA challenge
        klear.login(email="me@example.com", password="...", code="123456")
    assert klear.is_authenticated
    reports = klear.margin.margin_reports(start_date="2026-01-01", end_date="2026-02-01")
```

### After (v4.0.0)

```python
from kalshi import KlearClient

# Credentials at construction:
with KlearClient(
    admin_user_id="your-admin-user-id",
    access_token="your-bearer-token",
    demo=True,
) as klear:
    reports = klear.margin.margin_reports(start_date="2026-01-01", end_date="2026-02-01")

# Or from the environment (KALSHI_KLEAR_ADMIN_USER_ID / KALSHI_KLEAR_ACCESS_TOKEN):
with KlearClient.from_env(demo=True) as klear:
    bal = klear.margin.settlement_balance()
```

### Removed

- `KlearClient.login()` / `AsyncKlearClient.login()`
- `KlearClient.is_authenticated` property
- the `client.auth` resource (`AuthResource` / `AsyncAuthResource`)
- the `LogInRequest` / `LogInResponse` models (and their `kalshi` / `kalshi.perps`
  re-exports)

### Changed

- `KlearAuth()` (no-arg session holder) → `KlearAuth(admin_user_id, access_token)`,
  a Bearer-credential holder. The `access_token` is redacted from `repr()`.
- New environment variables: `KALSHI_KLEAR_ADMIN_USER_ID`, `KALSHI_KLEAR_ACCESS_TOKEN`
  (read by `KlearClient.from_env()`). The old credentials were never read from the
  environment.

## 2. Additive changes (no migration needed)

These are new surfaces — existing code keeps working:

- **`cfbenchmarks_value` WebSocket channel** — stream CF Benchmarks reference index
  values (e.g. `BRTI`, `ETHUSD_RTI`) via
  `KalshiWebSocket.subscribe_cfbenchmarks_value(index_ids=[...])`. New models
  (`CFBenchmarksValueMessage`, `CFBenchmarksValuePayload`, `CFBenchmarksAvgData`,
  `CFBenchmarksIndexListMessage`, `CFBenchmarksIndexListPayload`) are exported from
  `kalshi.ws.models`. See [WebSocket](../websockets.md#cf-benchmarks-index-values).
- **`AccountResource.upgrade()`** — `POST /account/api_usage_level/upgrade` requests
  a permanent Advanced API usage-level grant. See
  [Account](../resources/account.md#api-usage-level-grants).
- **`AccountApiLimits.grants`** — a new field listing active usage-level grants,
  plus a new exported `ApiUsageLevelGrant` model.
- **`MarginAccountResource.api_limits()`** — `GET /account/limits/perps` for the
  Perps API tier limits (reuses `AccountApiLimits`).
- **Perps market notional/leverage fields** — `MarginMarket` gains
  `leverage_estimates` and `*_notional_value` fields; `MarginMarketCandlestick`
  and the margin ticker WS payload gain notional-value fields.

The subaccount range documented in prose is now 1–63 (no validation change).
