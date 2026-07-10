# Exchange

Top-level exchange status, schedule, announcements, and your account's
"user data updated at" timestamp.

## Quick reference

| Method | Endpoint | Auth |
|---|---|---|
| `status()` | `GET /exchange/status` | no |
| `schedule()` | `GET /exchange/schedule` | no |
| `announcements()` *(deprecated in v7.0.0 — 404s)* | `GET /exchange/announcements` | no |
| `user_data_timestamp()` | `GET /exchange/user_data_timestamp` | **yes** |

## Exchange status

```python
status = client.exchange.status()
print(status.exchange_active, status.trading_active)
```

Use this as a liveness check before placing orders.

## Exchange schedule

```python
sched = client.exchange.schedule()
for week in sched.standard_hours:
    print(week.start_time, week.end_time)
for window in sched.maintenance_windows:
    print(window.start, window.end)
```

`Schedule.standard_hours` is a list of weekly recurring windows;
`maintenance_windows` is the upcoming downtime calendar.

## Announcements

!!! warning "Deprecated in v7.0.0"
    Kalshi removed `GET /exchange/announcements` and the `Announcement` schema
    from the spec in 3.24.0, so the live endpoint now **404s**. `announcements()`
    (sync + async) and the `Announcement` model are retained — each call emits a
    `DeprecationWarning` — pending confirmation the removal is permanent, and will
    be removed in a future major release.

```python
for a in client.exchange.announcements():   # emits DeprecationWarning
    print(a.type, a.message, a.delivery_time, a.status)
```

Plain list, not a `Page`.

## User-data timestamp

```python
ts = client.exchange.user_data_timestamp()
print(ts.last_updated_ts)
```

Auth-required. The SDK enforces auth client-side even though the OpenAPI
spec omits a security requirement, because the endpoint reports user-scoped
freshness.

## Reference

::: kalshi.resources.exchange.ExchangeResource
    options:
      heading_level: 3

::: kalshi.resources.exchange.AsyncExchangeResource
    options:
      heading_level: 3
