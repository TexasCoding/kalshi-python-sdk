# Account

API tier limits — what your read/write rate-limit buckets look like.

Auth required.

## Quick reference

| Method | Endpoint |
|---|---|
| `limits()` | `GET /account/limits` |
| `endpoint_costs()` | `GET /account/endpoint_costs` |
| `volume_progress()` | `GET /account/api_usage_level/volume_progress` |
| `upgrade()` | `POST /account/api_usage_level/upgrade` |

## Read tier limits

```python
limits = client.account.limits()
print(limits.usage_tier)
print(limits.read.bucket_capacity, limits.read.refill_rate)
print(limits.write.bucket_capacity, limits.write.refill_rate)
```

`AccountApiLimits.read` and `.write` are `RateLimit` objects with
`bucket_capacity` and `refill_rate` fields (token-bucket parameters).
Use them to drive client-side throttling if you fan out many concurrent
calls. `AccountApiLimits.grants` (new in v4.0.0) lists the caller's active
usage-level grants — see [API usage-level grants](#api-usage-level-grants) below.

!!! note "Differs from the OpenAPI spec shape"
    The published spec describes `read_limit` and `write_limit` as integers;
    the production server returns the nested `RateLimit` objects shown above.
    The SDK normalizes to the live shape.

## Endpoint costs

New in v2.1.0. Lists API v2 endpoints whose configured token cost differs
from the default — useful for budgeting against your write tier.

```python
costs = client.account.endpoint_costs()
print(costs.default_cost)               # int, the baseline (typically 10)
for entry in costs.endpoint_costs:
    # EndpointTokenCost: method (str), path (str), cost (int)
    print(entry.method, entry.path, entry.cost)
```

Endpoints not present in `endpoint_costs` use `default_cost`. Batch
endpoints typically appear here with a per-item multiplier (e.g.
`POST /portfolio/orders/batched` costs ~10 tokens per order in the batch).

## Volume progress

New in v4.1.0. `volume_progress()` (`GET /account/api_usage_level/volume_progress`)
returns the latest cron-computed trading-volume snapshots toward the
volume-based API usage tiers for the predictions (`event_contract`) lane.

```python
progress = client.account.volume_progress()
for snapshot in progress.volume_progress:
    print(snapshot.computed_ts, snapshot.trailing_30d_volume)
    for goal in snapshot.goals:
        # earn = volume needed to earn the level; keep = volume to retain it.
        print(goal.level, goal.earn_volume_goal, goal.keep_volume_goal)
```

`AccountVolumeProgress.volume_progress` is a list of
`AccountApiUsageLevelVolumeProgress` snapshots. `computed_ts` is the Unix
second at which the snapshot was computed; `trailing_30d_volume` and each
goal's `earn_volume_goal` / `keep_volume_goal` are fixed-point contract counts
(`Decimal`).

## API usage-level grants

New in v4.0.0. `AccountApiLimits.grants` is a list of `ApiUsageLevelGrant`
(exported from the top-level `kalshi` package) describing the caller's active
usage-level grants across exchange lanes. Each grant has:

- `exchange_instance` — the exchange lane: `"event_contract"` or `"margined"`.
- `level` — the API usage level the grant confers (e.g. `"premier"`,
  `"paragon"`, `"prime"`).
- `source` — how it was created: `"volume"` (earned from trading volume) or
  `"manual"` (assigned by Kalshi).
- `expires_ts` — Unix-seconds expiry, or `None` for a permanent grant.

```python
limits = client.account.limits()
for grant in limits.grants:
    print(grant.exchange_instance, grant.level, grant.source, grant.expires_ts)
```

`upgrade()` requests a **permanent Advanced** API usage-level grant
(`POST /account/api_usage_level/upgrade`). It requires that at least one of your
last 100 Predictions orders was API-created; otherwise the server returns 403
(mapped to `KalshiAuthError`). It returns `None` on success (HTTP 201) — re-read
`limits()` to see the resulting grant:

```python
client.account.upgrade()
print(client.account.limits().grants)
```

## Reference

::: kalshi.resources.account.AccountResource
    options:
      heading_level: 3

::: kalshi.resources.account.AsyncAccountResource
    options:
      heading_level: 3
