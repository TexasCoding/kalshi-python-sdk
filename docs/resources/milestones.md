# Milestones

A **milestone** is a real-world reference event (a baseball game, an
election, an economic release) that Kalshi markets and live-data feeds anchor
to. The milestone id is the join key between a market and its live state.

Public — no auth required.

## Quick reference

| Method | Endpoint |
|---|---|
| `list(*, limit, ...)` | `GET /milestones` |
| `list_all(*, limit=None, max_pages=None, ...)` | walks `list` |
| `get(milestone_id)` | `GET /milestones/{milestone_id}` |

## List milestones

```python
from datetime import datetime, timezone

page = client.milestones.list(
    limit=100,                                  # required, 1–500
    milestone_type="sports_game",               # spec field name "type"; renamed
    competition="NFL",
    minimum_start_date=datetime(2026, 5, 17, tzinfo=timezone.utc),
    min_updated_ts=1_700_000_000,               # Unix seconds, for incremental polling
)
for m in page:
    print(m.milestone_id, m.title, m.scheduled_start)
```

!!! info "`limit` is required"
    Unlike most list endpoints, `milestones.list` requires `limit` (1–500).
    `list_all` handles this internally; pass `limit=` if you want a non-default
    page size.

!!! info "Datetime handling"
    `minimum_start_date` accepts a `datetime`. Naive datetimes are coerced to
    UTC. If you pass an RFC3339 string instead, it's forwarded unchanged — you
    own format correctness.

!!! info "`milestone_type` is the SDK's name for spec `type`"
    The OpenAPI spec calls this query parameter `type`. The SDK renames it to
    `milestone_type` to avoid shadowing the Python builtin. The wire still
    sends `type=`.

## Get one milestone

```python
m = client.milestones.get("ms_abc")
print(m.title, m.milestone_type, m.scheduled_start)
```

## Reference

::: kalshi.resources.milestones.MilestonesResource
    options:
      heading_level: 3

::: kalshi.resources.milestones.AsyncMilestonesResource
    options:
      heading_level: 3
