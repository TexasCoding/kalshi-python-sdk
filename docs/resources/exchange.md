# Exchange

Top-level exchange status, schedule, announcements, and your account's
"user data updated at" timestamp.

## Quick reference

| Method | Endpoint | Auth |
|---|---|---|
| `status()` | `GET /exchange/status` | no |
| `schedule()` | `GET /exchange/schedule` | no |
| `announcements()` | `GET /exchange/announcements` | no |
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

```python
for a in client.exchange.announcements():
    print(a.title, a.message, a.delivery_time)
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
