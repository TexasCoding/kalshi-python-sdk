# Subaccounts

Logical wallet partitions under your main account. Subaccount `0` is your
primary; `1`–`63` are numbered extras. Auth required throughout.

## Quick reference

| Method | Endpoint |
|---|---|
| `create(*, exchange_index=None)` | `POST /portfolio/subaccounts` |
| `transfer(*, client_transfer_id, from_subaccount, to_subaccount, amount_cents)` | `POST /portfolio/subaccounts/transfer` |
| `transfer_position(*, client_transfer_id, from_subaccount, to_subaccount, market_ticker, side, count, price)` | `POST /portfolio/subaccounts/positions/transfer` |
| `list_balances()` | `GET /portfolio/subaccounts/balances` |
| `list_transfers(*, cursor=None, limit=None)` | `GET /portfolio/subaccounts/transfers` |
| `list_all_transfers(*, limit=None, max_pages=None)` | walks `list_transfers` |
| `update_netting(*, subaccount_number, enabled)` | `PUT /portfolio/subaccounts/netting` |
| `get_netting()` | `GET /portfolio/subaccounts/netting` |

## Create a subaccount

```python
resp = client.subaccounts.create()
print(resp.subaccount_number)

# Or target a specific exchange shard (spec v3.23.0; defaults to 0):
resp = client.subaccounts.create(exchange_index=0)
```

With no `exchange_index` the SDK sends `json={}` (an empty
`CreateSubaccountRequest`) to force a JSON content-type so demo doesn't reject
the call.

## Transfer cash between subaccounts

`amount_cents` is **integer cents**. `client_transfer_id` is a UUID — the
idempotency key for the transfer. `transfer()` returns `None` (the endpoint's
response body is empty); list transfers to reconcile:

```python
import uuid

client.subaccounts.transfer(
    client_transfer_id=uuid.uuid4(),     # or str
    from_subaccount=0,                   # primary
    to_subaccount=1,
    amount_cents=500,                    # $5.00
)
```

`client_transfer_id` accepts a `UUID` or a `str`. On a network failure, retry
with the same id; the server dedupes.

## Transfer a position between subaccounts

Spec v3.23.0 added `transfer_position()` for moving open contracts (not cash)
between subaccounts. Unlike `transfer()`, it returns a `position_transfer_id`.
`price` (spec v3.24.0 renamed it from `price_cents`) is the per-contract cost
basis in **fixed-point dollars** (0–1.0) — pass a `Decimal`:

```python
from decimal import Decimal

resp = client.subaccounts.transfer_position(
    client_transfer_id=uuid.uuid4(),     # or str
    from_subaccount=0,
    to_subaccount=1,
    market_ticker="KXBTC-25DEC31-B100000",
    side="yes",                          # "yes" | "no"
    count=10,                            # contracts (> 0)
    price=Decimal("0.55"),               # per-contract dollars, 0–1.0
)
print(resp.position_transfer_id)
```

## List balances

```python
resp = client.subaccounts.list_balances()
for bal in resp.subaccount_balances:
    print(bal.subaccount_number, bal.balance, bal.updated_ts, bal.exchange_index)
```

`bal.balance` is `DollarDecimal` (dollars). `bal.updated_ts` is Unix seconds
(not ISO datetime). `bal.exchange_index` is the exchange shard the balance is
held on.

## List transfers

```python
page = client.subaccounts.list_transfers(limit=100)
for t in page:
    print(t.transfer_id, t.amount_cents, t.from_subaccount, t.to_subaccount)

for t in client.subaccounts.list_all_transfers():
    ...
```

Standard `Page[SubaccountTransfer]` pagination. `t.created_ts` is Unix
seconds. Rows are **cash transfers only** — position moves use
`transfer_position()` and are not listed here.

## Netting

Netting offsets positions across subaccounts so they consume one margin pool.

```python
client.subaccounts.update_netting(subaccount_number=1, enabled=True)
resp = client.subaccounts.get_netting()
for cfg in resp.netting_configs:
    # `exchange_index` (int) added in spec v3.24.0.
    print(cfg.subaccount_number, cfg.enabled, cfg.exchange_index)
```

## Reference

::: kalshi.resources.subaccounts.SubaccountsResource
    options:
      heading_level: 3

::: kalshi.resources.subaccounts.AsyncSubaccountsResource
    options:
      heading_level: 3
