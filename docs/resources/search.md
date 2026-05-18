# Search

Discovery surfaces for tags and sport filters. Two methods, both public.

## Quick reference

| Method | Endpoint | Auth |
|---|---|---|
| `tags_by_categories()` | `GET /search/tags_by_categories` | no |
| `filters_by_sport()` | `GET /search/filters_by_sport` | no |

## Tags by category

```python
resp = client.search.tags_by_categories()
for category in resp.categories:
    print(category.name, [tag.name for tag in category.tags])
```

Returns a grouped tag tree for use in UI filters.

## Filters by sport

```python
resp = client.search.filters_by_sport()
for sport in resp.sports:
    print(sport.sport, sport.competitions, sport.target_types)
```

Lists the sports, competitions, and structured-target types available for use
as filter inputs in markets / events / [structured targets](structured-targets.md).

## Reference

::: kalshi.resources.search.SearchResource
    options:
      heading_level: 3

::: kalshi.resources.search.AsyncSearchResource
    options:
      heading_level: 3
