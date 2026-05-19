# Request models

Every mutating endpoint (`POST`, `PUT`, `DELETE` with a body) accepts its
parameters two ways: as individual keyword arguments or as a pre-built request
model.

## The two forms

```python
# Form 1 — individual kwargs (default for most call sites)
order = client.orders.create(
    ticker="KXPRES-24-DJT",
    side="yes",
    action="buy",
    count=10,
    yes_price="0.65",
    time_in_force="good_till_canceled",
)

# Form 2 — pass a pre-built request model
from kalshi import CreateOrderRequest

req = CreateOrderRequest(
    ticker="KXPRES-24-DJT",
    side="yes",
    action="buy",
    count=10,
    yes_price="0.65",
    time_in_force="good_till_canceled",
)
order = client.orders.create(request=req)
```

The two forms are **mutually exclusive** — passing `request=` together with
any other kwarg raises `TypeError`. The request-model form is useful when you
build orders out of band (config, queue, test harness) and want to type-check
the whole payload at construction time.

## `extra="forbid"` everywhere

Every request model has `model_config = {"extra": "forbid"}`. A misspelled or
removed field fails at construction with a Pydantic `ValidationError` —
**before** the HTTP request goes out.

```python
from kalshi import CreateOrderRequest

CreateOrderRequest(
    ticker="X", side="yes", action="buy", count=1, yes_price="0.65",
    typo_field=123,        # raises ValidationError immediately
)
```

The same models drive the body-drift contract tests in CI, so the kwargs
exposed on each resource method and the wire format stay in lockstep with the
OpenAPI spec.

## Inventory

| Resource | Request model |
|---|---|
| `client.orders.create` | `CreateOrderRequest` |
| `client.orders.batch_create` | `BatchCreateOrdersRequest` (wraps `list[CreateOrderRequest]`) |
| `client.orders.batch_cancel` | `BatchCancelOrdersRequest` (wraps `list[BatchCancelOrdersRequestOrder]`) |
| `client.orders.amend` | `AmendOrderRequest` |
| `client.orders.decrease` | `DecreaseOrderRequest` |
| `client.orders.create_v2` | `CreateOrderV2Request` (V2 event-market — model-only, no kwarg form) |
| `client.orders.amend_v2` | `AmendOrderV2Request` (V2 — model-only) |
| `client.orders.decrease_v2` | `DecreaseOrderV2Request` (V2 — model-only, XOR `reduce_by`/`reduce_to`) |
| `client.orders.batch_create_v2` | `BatchCreateOrdersV2Request` (wraps `list[CreateOrderV2Request]`) |
| `client.orders.batch_cancel_v2` | `BatchCancelOrdersV2Request` (wraps `list[BatchCancelOrdersV2RequestOrder]`) |
| `client.api_keys.create` | `CreateApiKeyRequest` |
| `client.api_keys.generate` | `GenerateApiKeyRequest` |
| `client.communications.create_rfq` | `CreateRFQRequest` |
| `client.communications.create_quote` | `CreateQuoteRequest` |
| `client.communications.accept_quote` | `AcceptQuoteRequest` |
| `client.multivariate_collections.create_market` | `CreateMarketInMultivariateEventCollectionRequest` |
| `client.multivariate_collections.lookup_tickers` | `LookupTickersForMarketInMultivariateEventCollectionRequest` |
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
| `CreateOrderRequest.count` | `count_fp` |
| `CreateOrderRequest.yes_price` | `yes_price_dollars` |
| `CreateOrderRequest.no_price` | `no_price_dollars` |
| `AmendOrderRequest.yes_price` / `.no_price` / `.count` | `*_dollars` / `count_fp` |
| `CreateQuoteRequest.target_cost` | `target_cost_dollars` |
| `StructuredTarget.target_type` (response) | `type` (avoids shadowing the builtin) |

You never type these long names — they're an internal implementation detail.

## V2 surface: model-only

The V2 event-market order endpoints (`create_v2` / `amend_v2` / `decrease_v2`
/ `batch_*_v2`) don't accept individual kwargs — pass a fully-constructed
request model. This is intentional: V2 took the opportunity to drop the
V1 kwarg-overload surface entirely, so the model is the single source of
truth for the payload shape.

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

`CreateOrderV2Request.client_order_id` is required (V1's was optional) and
the server treats it as an idempotency key — reusing one returns the
original order rather than placing a new one. Generate a fresh UUID4 per
call.

## Cross-field invariants

Some request models enforce relationships **before** the HTTP call:

- `DecreaseOrderRequest` / `DecreaseOrderV2Request` — exactly one of
  `reduce_by` / `reduce_to` is required (XOR enforced via a model validator).
- `AmendOrderRequest` — at least one of `yes_price` / `no_price` / `count`
  must be present (enforced in the resource method, before the body is built).

Bad input fails locally with a clear traceback; no wasted round trip.

## Building bodies by hand

If you need to inspect or mutate the wire body, request models serialize like
this:

```python
from kalshi import CreateOrderRequest

req = CreateOrderRequest(ticker="X", side="yes", action="buy", count=1, yes_price="0.65")
body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
# {'ticker': 'X', 'side': 'yes', 'action': 'buy', 'count_fp': '1',
#  'yes_price_dollars': '0.65'}
```

`exclude_none=True` and `by_alias=True` are exactly what every resource method
uses internally. `mode="json"` gives you a JSON-serializable dict (Decimals
become strings).
