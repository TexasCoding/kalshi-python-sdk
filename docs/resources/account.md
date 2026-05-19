# Account

API tier limits — what your read/write rate-limit buckets look like.

Auth required.

## Quick reference

| Method | Endpoint |
|---|---|
| `limits()` | `GET /account/limits` |
| `endpoint_costs()` | `GET /account/endpoint_costs` |

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
calls.

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

## Reference

::: kalshi.resources.account.AccountResource
    options:
      heading_level: 3

::: kalshi.resources.account.AsyncAccountResource
    options:
      heading_level: 3
