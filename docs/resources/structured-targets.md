# Structured targets

A **structured target** is the entity a market is "about" — a team, player,
candidate, company. Two markets pointing at the same Yankees roster share a
structured target id, so you can group markets by underlying entity.

Public — no auth required.

## Quick reference

| Method | Endpoint |
|---|---|
| `list(...)` / `list_all(...)` | `GET /structured_targets` |
| `get(structured_target_id)` | `GET /structured_targets/{id}` |

## List structured targets

```python
page = client.structured_targets.list(
    target_type="team",                    # spec field "type"; renamed
    competition="MLB",
    page_size=500,                         # 1–2000, default 100 — note: not `limit`
    ids=["st_abc", "st_def"],              # bulk lookup
)
for t in page:
    print(t.structured_target_id, t.name, t.target_type)
```

!!! info "`page_size`, not `limit`"
    Unlike every other paginated endpoint, this one uses `page_size`. Range:
    1–2000. Default 100. The SDK accepts a `cursor` for pagination as usual.

!!! info "`target_type` is the SDK's name for spec `type`"
    Same renaming logic as [milestones](milestones.md) — avoids shadowing
    the Python builtin. The wire still sends `type=`.

## Get one structured target

```python
from kalshi.errors import KalshiNotFoundError

try:
    t = client.structured_targets.get("st_abc")
except KalshiNotFoundError:
    print("not found")
else:
    if t is None:
        # rare: server returned 200 with {"structured_target": null}
        print("soft-not-found")
    else:
        print(t.name, t.target_type)
```

A 404 from the server raises `KalshiNotFoundError`. `get()` returns `None`
only if the server responds 200 with `{"structured_target": null}` — a
server-side soft-not-found that the spec permits but is rare in practice.

## Reference

::: kalshi.resources.structured_targets.StructuredTargetsResource
    options:
      heading_level: 3

::: kalshi.resources.structured_targets.AsyncStructuredTargetsResource
    options:
      heading_level: 3
