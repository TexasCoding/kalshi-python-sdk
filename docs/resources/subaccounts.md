# Subaccounts

Logical wallet partitions under your main account. Subaccount `0` is your
primary; `1`–`32` are numbered extras. Auth required throughout.

## Quick reference

| Method | Endpoint |
|---|---|
| `create()` | `POST /portfolio/subaccounts` |
| `transfer(*, client_transfer_id, from_subaccount, to_subaccount, amount_cents)` | `POST /portfolio/subaccounts/transfer` |
| `list_balances()` | `GET /portfolio/subaccounts/balances` |
| `list_transfers(*, cursor=None, limit=None)` | `GET /portfolio/subaccounts/transfers` |
| `list_all_transfers(*, limit=None, max_pages=None)` | walks `list_transfers` |
| `update_netting(*, subaccount_number, enabled)` | `PUT /portfolio/subaccounts/netting` |
| `get_netting()` | `GET /portfolio/subaccounts/netting` |

## Create a subaccount

```python
resp = client.subaccounts.create()
print(resp.subaccount_number)
```

The body is intentionally empty — the SDK sends `json={}` to force a JSON
content-type so demo doesn't reject the call.

## Transfer between subaccounts

`amount_cents` is **integer cents**. `client_transfer_id` is a UUID — the
idempotency key for the transfer:

```python
import uuid

resp = client.subaccounts.transfer(
    client_transfer_id=uuid.uuid4(),     # or str
    from_subaccount=0,                   # primary
    to_subaccount=1,
    amount_cents=500,                    # $5.00
)
print(resp.transfer_id)
```

`client_transfer_id` accepts a `UUID` or a `str`. On a network failure, retry
with the same id; the server dedupes. List transfers to reconcile (see
below).

## List balances

```python
resp = client.subaccounts.list_balances()
for bal in resp.subaccount_balances:
    print(bal.subaccount_number, bal.balance, bal.updated_ts)
```

`bal.balance` is a `DollarDecimal` (dollars). `bal.updated_ts` is Unix seconds
(not ISO datetime).

## List transfers

```python
page = client.subaccounts.list_transfers(limit=100)
for t in page:
    print(t.transfer_id, t.amount_cents, t.from_subaccount, t.to_subaccount)

for t in client.subaccounts.list_all_transfers():
    ...
```

Standard `Page[SubaccountTransfer]` pagination. `t.created_ts` is Unix
seconds.

## Netting

Netting offsets positions across subaccounts so they consume one margin pool.

```python
client.subaccounts.update_netting(subaccount_number=1, enabled=True)
config = client.subaccounts.get_netting()
print(config.netting_enabled_subaccounts)
```

## Reference

::: kalshi.resources.subaccounts.SubaccountsResource
    options:
      heading_level: 3

::: kalshi.resources.subaccounts.AsyncSubaccountsResource
    options:
      heading_level: 3
