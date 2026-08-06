# Request models

Every mutating endpoint (`POST`, `PUT`, `DELETE` with a body) takes its
parameters as a pre-built request model. You construct the model, then pass it
as `request=`.

## The request-model form

```python
import uuid
from decimal import Decimal
from kalshi import CreateOrderV2Request

req = CreateOrderV2Request(
    ticker="KXPRES-24-DJT",
    client_order_id=str(uuid.uuid4()),
    side="bid",
    count=Decimal("10"),
    price=Decimal("0.65"),
    time_in_force="good_till_canceled",
    self_trade_prevention_type="taker_at_cross",
)
order = client.orders.create_v2(request=req)
```

The request-model form lets you build orders out of band (config, queue, test
harness) and type-check the whole payload at construction time. Prices and
counts are `Decimal`; `side` is the book side (`"bid"` / `"ask"`, not
`"yes"` / `"no"`); `client_order_id` is required.

## `extra="forbid"` everywhere

Every request model has `model_config = {"extra": "forbid"}`. A misspelled or
removed field fails at construction with a Pydantic `ValidationError` —
**before** the HTTP request goes out.

```python
from kalshi import CreateOrderV2Request

CreateOrderV2Request(
    ticker="X", client_order_id="abc", side="bid", count=1, price="0.65",
    time_in_force="good_till_canceled", self_trade_prevention_type="taker_at_cross",
    typo_field=123,        # raises ValidationError immediately
)
```

The same models drive the body-drift contract tests in CI, so the wire format
exposed by each resource method stays in lockstep with the OpenAPI spec.

## Inventory

| Resource | Request model |
|---|---|
| `client.orders.create_v2` | `CreateOrderV2Request` |
| `client.orders.amend_v2` | `AmendOrderV2Request` |
| `client.orders.decrease_v2` | `DecreaseOrderV2Request` (XOR `reduce_by` / `reduce_to`) |
| `client.orders.batch_create_v2` | `BatchCreateOrdersV2Request` (wraps `list[CreateOrderV2Request]`) |
| `client.orders.batch_cancel_v2` | `BatchCancelOrdersV2Request` (wraps `list[BatchCancelOrdersV2RequestOrder]`) |
| `client.api_keys.create` | `CreateApiKeyRequest` |
| `client.api_keys.generate` | `GenerateApiKeyRequest` |
| `client.communications.create_rfq` | `CreateRFQRequest` |
| `client.communications.create_quote` | `CreateQuoteRequest` |
| `client.communications.accept_quote` | `AcceptQuoteRequest` |
| `client.communications.block_trade_proposals.create` | `ProposeBlockTradeRequest` |
| `client.communications.block_trade_proposals.accept` | `AcceptBlockTradeProposalRequest` |
| `client.multivariate_collections.create_market` | `CreateMarketInMultivariateEventCollectionRequest` |
| `client.order_groups.create` | `CreateOrderGroupRequest` |
| `client.order_groups.update_limit` | `UpdateOrderGroupLimitRequest` |
| `client.subaccounts.transfer` | `ApplySubaccountTransferRequest` |
| `client.subaccounts.update_netting` | `UpdateSubaccountNettingRequest` |

All are importable from the top-level `kalshi` package.

## Wire-format aliases

Several fields use `serialization_alias` to bridge a friendly Python name to
an awkward wire name:

| Model field | Wire name |
|---|---|
| `CreateRFQRequest.target_cost` | `target_cost_dollars` |
| `StructuredTarget.target_type` (response) | `type` (avoids shadowing the builtin) |

You never type these long names — they're an internal implementation detail.

## V2 idempotency keys

`CreateOrderV2Request.client_order_id` is required and the server treats it as
an idempotency key — reusing one returns the original order rather than placing
a new one. Generate a fresh UUID4 per call.

```python
import uuid
from decimal import Decimal
from kalshi import CreateOrderV2Request

req = CreateOrderV2Request(
    ticker="EVENT-MKT",
    client_order_id=str(uuid.uuid4()),   # required — idempotency key
    side="bid",
    count=Decimal("10"),
    price=Decimal("0.50"),
    time_in_force="good_till_canceled",
    self_trade_prevention_type="taker_at_cross",
)
client.orders.create_v2(request=req)
```

## Cross-field invariants

Some request models enforce relationships **before** the HTTP call:

- `DecreaseOrderV2Request` — exactly one of `reduce_by` / `reduce_to` is
  required (XOR enforced via a model validator).

Bad input fails locally with a clear traceback; no wasted round trip.

## Building bodies by hand

If you need to inspect or mutate the wire body, request models serialize like
this:

```python
from decimal import Decimal
from kalshi import CreateOrderV2Request

req = CreateOrderV2Request(
    ticker="X", client_order_id="abc", side="bid",
    count=Decimal("1"), price=Decimal("0.65"),
    time_in_force="good_till_canceled",
    self_trade_prevention_type="taker_at_cross",
)
body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
# {'ticker': 'X', 'client_order_id': 'abc', 'side': 'bid', 'count': '1',
#  'price': '0.65', 'time_in_force': 'good_till_canceled',
#  'self_trade_prevention_type': 'taker_at_cross'}
```

`exclude_none=True` and `by_alias=True` are exactly what every resource method
uses internally. `mode="json"` gives you a JSON-serializable dict (Decimals
become strings).
