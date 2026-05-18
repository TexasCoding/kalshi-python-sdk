# Account

API tier limits — what your read/write rate-limit buckets look like.

Auth required.

## Quick reference

| Method | Endpoint |
|---|---|
| `limits()` | `GET /account/limits` |

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

## Reference

::: kalshi.resources.account.AccountResource
    options:
      heading_level: 3

::: kalshi.resources.account.AsyncAccountResource
    options:
      heading_level: 3
