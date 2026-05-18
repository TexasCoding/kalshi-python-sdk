# Live data

Real-time state attached to a [milestone](milestones.md) — score, clock,
period, weather, etc. Pair with milestones to render live UI alongside
Kalshi markets.

Public — no auth required.

## Quick reference

| Method | Endpoint |
|---|---|
| `get(milestone_id, *, include_player_stats=None)` | `GET /live_data/{milestone_id}` |
| `batch(milestone_ids, *, include_player_stats=None)` | `GET /live_data` |
| `game_stats(milestone_id)` | `GET /live_data/{milestone_id}/game_stats` |
| `get_typed(live_data_type, milestone_id)` | `GET /live_data/{type}/milestone/{milestone_id}` (legacy) |

## Get one milestone's live data

```python
live = client.live_data.get("ms_abc", include_player_stats=True)
print(live.live_data_type, live.payload)
```

## Batch (up to 100 milestones)

```python
resp = client.live_data.batch(
    milestone_ids=["ms_a", "ms_b", "ms_c"],
    include_player_stats=False,
)
for entry in resp.live_data:
    print(entry.milestone_id, entry.payload)
```

`milestone_ids` is required and non-empty — passing `[]` raises `ValueError`.
Cap: 100 ids per call.

## Game stats / play-by-play

```python
pbp = client.live_data.game_stats("ms_abc")
if pbp.pbp is None:
    print("no play-by-play for this milestone type")
else:
    for period in pbp.pbp.periods:
        for play in period.plays:
            print(play.timestamp, play.description)
```

`game_stats` works only for sports milestones with play-by-play coverage.
Other milestone types return `pbp=None`.

## Legacy `get_typed`

```python
live = client.live_data.get_typed("sports_game", "ms_abc")
```

Prefer `get()` over `get_typed()`. The latter wraps the legacy
`/live_data/{type}/milestone/{id}` path and is retained only for callers that
still depend on it.

## Reference

::: kalshi.resources.live_data.LiveDataResource
    options:
      heading_level: 3

::: kalshi.resources.live_data.AsyncLiveDataResource
    options:
      heading_level: 3
