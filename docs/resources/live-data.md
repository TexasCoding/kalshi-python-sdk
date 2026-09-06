# Live data

Real-time state for markets — either keyed by a [milestone](milestones.md)
(score, clock, period, weather, …) or by an **event ticker** (crypto charts,
commodity timeseries, weather observations).

Public — no auth required.

## Quick reference

| Method | Endpoint |
|---|---|
| `get(milestone_id, *, include_player_stats=None)` | `GET /live_data/milestone/{milestone_id}` |
| `get_event(event_ticker, *, range=None)` | `GET /live_data/events/{event_ticker}` |
| `batch(milestone_ids, *, include_player_stats=None)` | `GET /live_data/batch` |
| `game_stats(milestone_id)` | `GET /live_data/milestone/{milestone_id}/game_stats` |
| `weather(city, *, from_ts, to, last_sec, detailed)` | `GET /live_data/weather/{city}` |
| `weather_calibrations(city)` | `GET /live_data/weather/{city}/calibrations` |
| `get_typed(milestone_type, milestone_id)` | `GET /live_data/{type}/milestone/{milestone_id}` (legacy) |

## Get one milestone's live data

```python
live = client.live_data.get("ms_abc", include_player_stats=True)
print(live.type, live.milestone_id, live.details)
```

`LiveData.details` is a loose `dict[str, Any]` — the shape varies by
`type` (football vs political race vs weather).

## Get event-keyed live data

```python
live = client.live_data.get_event("KXBTCD-25", range="1h")
print(live.type, live.details, live.default_range, live.range_options)
print(live.is_historical)  # True for matured crypto snapshots
```

`EventLiveData` has no `milestone_id`. Optional `range` is a chart-window
hint (`15min`, `1h`, `1d`, …) when the underlying type supports it.

## Batch (up to 100 milestones)

```python
entries = client.live_data.batch(
    milestone_ids=["ms_a", "ms_b", "ms_c"],
    include_player_stats=False,
)
for entry in entries:
    print(entry.milestone_id, entry.type, entry.details)
```

`milestone_ids` is required and non-empty — passing `[]` raises `ValueError`.
Cap: 100 ids per call.

## Game stats / play-by-play

```python
resp = client.live_data.game_stats("ms_abc")
if resp.pbp is None:
    print("no play-by-play for this milestone type")
else:
    for period in resp.pbp.periods:
        for event in period.events:
            print(event)  # free-form dict; shape varies by sport
```

`game_stats` works only for sports milestones with play-by-play coverage.
Other milestone types return `pbp=None`. Each period's `events` is a list of
loose dicts (no fixed play schema upstream).

## Weather index

```python
idx = client.live_data.weather("miami", last_sec=3600, detailed=True)
print(idx.city, idx.units, idx.config_version)
for point in idx.timeseries:
    print(point.t, point.status, point.v)
```

`from_ts` is the spec `from` query (unix milliseconds, inclusive). Named
`from_ts` to avoid the Python keyword; the wire key is still `from`.
`last_sec` is mutually exclusive with `from_ts`/`to` per spec. `detailed=True`
attaches per-station audit readings on every point.

```python
cals = client.live_data.weather_calibrations("miami")
for rec in cals.calibrations:
    print(rec.config_version, rec.effective_at_ms, rec.city_reference_c)
```

`weather_calibrations` returns the launch configuration plus every weekly
offset calibration, ascending by effective time. Units are always Celsius
on this endpoint (the published index value itself remains Fahrenheit).

## Legacy `get_typed`

```python
live = client.live_data.get_typed("sports_game", "ms_abc")
```

Prefer `get()` over `get_typed()`. The latter wraps the legacy
`/live_data/{type}/milestone/{id}` path and is retained only for callers that
still depend on it. The Python kwarg is `milestone_type` (not `type`) to avoid
shadowing the built-in; the wire path still uses `{type}`.

## Reference

::: kalshi.resources.live_data.LiveDataResource
    options:
      heading_level: 3

::: kalshi.resources.live_data.AsyncLiveDataResource
    options:
      heading_level: 3
