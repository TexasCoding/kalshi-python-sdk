# Incentive programs

Time-boxed reward campaigns (maker rebates, volume bonuses) on specific
markets or series. List them to discover what's currently rewarded and on
what terms.

Public — no auth required.

## Quick reference

| Method | Endpoint |
|---|---|
| `list(...)` / `list_all(...)` | `GET /incentive_programs` |

## List active programs

```python
page = client.incentive_programs.list(
    status="active",                     # IncentiveProgramStatusLiteral
    incentive_type="liquidity",          # IncentiveProgramTypeLiteral — spec "type"
    incentive_description="Q2 maker",    # new in v2.1.0 — exact-match filter
    limit=100,
)
for p in page:
    print(p.program_id, p.title, p.start_ts, p.end_ts)
```

`incentive_description` (added in v2.1.0) is an exact-string filter on the
program's description — useful when multiple programs share a status/type.

Use `list_all` to walk every program:

```python
for p in client.incentive_programs.list_all(status="active"):
    ...
```

!!! info "Uses `next_cursor` on the wire"
    The Kalshi endpoint returns the next page cursor under the key
    `next_cursor` rather than the SDK-wide `cursor`. The SDK normalizes both
    directions — you pass `cursor=` and read `.cursor` just like any other
    list call.

!!! info "`incentive_type` is the SDK's name for spec `type`"
    Same renaming logic as [milestones](milestones.md) and
    [structured targets](structured-targets.md). The wire still sends `type=`.

### Available statuses and types

- `IncentiveProgramStatusLiteral`: `"all"`, `"active"`, `"upcoming"`,
  `"closed"`, and additional server-side categories.
- `IncentiveProgramTypeLiteral`: `"all"`, `"liquidity"`, `"volume"`.

## Reference

::: kalshi.resources.incentive_programs.IncentiveProgramsResource
    options:
      heading_level: 3

::: kalshi.resources.incentive_programs.AsyncIncentiveProgramsResource
    options:
      heading_level: 3
