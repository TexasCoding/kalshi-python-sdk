# Order groups

A rolling contracts-limit bucket that several orders can share. Trips when
the group hits its cap; can be `reset()` or `trigger()`ed manually.

Auth required throughout.

## Quick reference

| Method | Endpoint |
|---|---|
| `list(*, subaccount=None)` | `GET /portfolio/order_groups` |
| `get(order_group_id, *, subaccount=None)` | `GET /portfolio/order_groups/{id}` |
| `create(*, contracts_limit, subaccount=None, exchange_index=None)` | `POST /portfolio/order_groups/create` |
| `delete(order_group_id, *, subaccount=None, exchange_index=None)` | `DELETE /portfolio/order_groups/{id}` |
| `reset(order_group_id, *, subaccount=None)` | `PUT /portfolio/order_groups/{id}/reset` |
| `trigger(order_group_id, *, subaccount=None)` | `PUT /portfolio/order_groups/{id}/trigger` |
| `update_limit(order_group_id, *, contracts_limit)` | `PUT /portfolio/order_groups/{id}/limit` |

!!! info "Non-standard create path"
    `create()` POSTs to `/portfolio/order_groups/create`, not `/portfolio/order_groups`.
    The other methods follow the conventional pattern.

## Lifecycle

```python
from kalshi import CreateOrderRequest

# 1) Create a group with a 100-contract cap.
group = client.order_groups.create(contracts_limit=100)
print(group.order_group_id)

# 2) Attach orders by id.
client.orders.create(
    ticker="KXPRES-24-DJT", side="yes", action="buy", count=10,
    yes_price="0.65", order_group_id=group.order_group_id,
)

# 3) Inspect.
detail = client.order_groups.get(group.order_group_id)
print(detail.orders)              # list[str] of order IDs in the group

# 4) Reset (clears the counter) or trigger (forces the cap).
client.order_groups.reset(group.order_group_id)
client.order_groups.trigger(group.order_group_id)

# 5) Tear down.
client.order_groups.delete(group.order_group_id)
```

## List

```python
for g in client.order_groups.list():
    print(g.order_group_id, g.contracts_limit, g.contracts_used)
```

Plain `list[OrderGroup]`, no cursor.

## Update limit

```python
client.order_groups.update_limit("og_abc", contracts_limit=200)
```

`update_limit` has **no `subaccount=` kwarg** — the OpenAPI spec omits the
subaccount query parameter on this path. Route via the group's own
subaccount-on-create instead.

## Exchange index (v2.1.0)

`create()` and `delete()` gained an optional `exchange_index: int | None`
parameter. Currently only `exchange_index=0` is supported per spec; the
field is reserved for future multi-shard fanout. Pass it for forward
compatibility if you're writing infrastructure that may target a non-zero
shard later:

```python
client.order_groups.create(contracts_limit=100, exchange_index=0)
client.order_groups.delete("og_abc", exchange_index=0)
```

## Reference

::: kalshi.resources.order_groups.OrderGroupsResource
    options:
      heading_level: 3

::: kalshi.resources.order_groups.AsyncOrderGroupsResource
    options:
      heading_level: 3
