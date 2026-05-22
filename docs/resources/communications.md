# Communications (RFQ / Quote)

Kalshi's bilateral block-trade rail. An **RFQ** is a private "make me a market
on this contract at this size?" message; a **Quote** is a counterparty's
answer. The requester accepts a side; the maker confirms; the trade settles.

Auth required throughout.

!!! warning "Deprecated since v3.0.0"
    The flat method names (`list_rfqs`, `get_rfq`, `create_rfq`, `delete_rfq`,
    `list_all_rfqs`, `list_quotes`, `get_quote`, `create_quote`,
    `delete_quote`, `list_all_quotes`, `accept_quote`, `confirm_quote`) on
    `CommunicationsResource` still work but emit `DeprecationWarning` and will
    be removed in a future release. Switch to the `rfqs.` / `quotes.`
    sub-namespaces documented below.

## Quick reference

| Method | Endpoint |
|---|---|
| `get_id()` | `GET /communications/id` |
| `rfqs.list(...)` / `rfqs.list_all(...)` | `GET /communications/rfqs` |
| `rfqs.get(rfq_id)` | `GET /communications/rfqs/{rfq_id}` |
| `rfqs.create(...)` | `POST /communications/rfqs` |
| `rfqs.delete(rfq_id)` | `DELETE /communications/rfqs/{rfq_id}` |
| `quotes.list(...)` / `quotes.list_all(...)` | `GET /communications/quotes` |
| `quotes.get(quote_id)` | `GET /communications/quotes/{quote_id}` |
| `quotes.create(...)` | `POST /communications/quotes` |
| `quotes.delete(quote_id)` | `DELETE /communications/quotes/{quote_id}` |
| `quotes.accept(quote_id, *, accepted_side)` | `POST /communications/quotes/{quote_id}/accept` |
| `quotes.confirm(quote_id)` | `POST /communications/quotes/{quote_id}/confirm` |

`get_id()` returns your `participant_id` — the value you'll pass as
`quote_creator_user_id` / `rfq_creator_user_id` when filtering lists. It stays
at the top level because it has no sub-noun.

## Requester flow

```python
# Identify yourself for filtering downstream.
me = client.communications.get_id()

# 1) Post an RFQ asking for a price on 500 contracts.
rfq = client.communications.rfqs.create(
    market_ticker="KXPRES-24-DJT",
    contracts=500,
    rest_remainder=True,
)
print(rfq.rfq.rfq_id)

# 2) Poll for incoming quotes (or subscribe to the `communications` WS channel).
quotes = client.communications.quotes.list(rfq_creator_user_id=me.user_id)
for q in quotes:
    print(q.quote_id, q.yes_bid, q.no_bid)

# 3) Accept a side on one of them.
accepted = client.communications.quotes.accept(
    quotes.items[0].quote_id, accepted_side="yes"
)
```

## Maker flow

```python
me = client.communications.get_id()

# 1) Watch for incoming RFQs.
for rfq in client.communications.rfqs.list_all(status="open"):
    print(rfq.rfq_id, rfq.market_ticker, rfq.contracts)

# 2) Quote one.
resp = client.communications.quotes.create(
    rfq_id="rfq_abc",
    yes_bid="0.60",
    no_bid="0.40",
    rest_remainder=False,
)

# 3) Wait for the counterparty to accept.
# 4) Confirm to lock the fill.
client.communications.quotes.confirm(resp.quote.quote_id)
```

!!! warning "`quotes.list` requires a user-id filter"
    `quotes.list` and `quotes.list_all` **must** be called with at least one of:

    - `quote_creator_user_id=` (filter to a specific quoter)
    - `rfq_creator_user_id=` (filter to a specific RFQ originator)
    - `user_filter="self"` (server-side shorthand for "the caller's quotes")
    - `rfq_user_filter="self"` (server-side shorthand for "quotes on the caller's RFQs")

    `user_filter` / `rfq_user_filter` were added in spec v3.18.0 and let
    you avoid round-tripping `get_id()` first. Passing `rfq_id=` alone
    raises `ValueError` locally before the round trip — this enforces a
    server-side requirement.

## Filtering shortcuts (v2.1.0)

```python
# All quotes you made — no get_id() needed.
for q in client.communications.quotes.list_all(user_filter="self"):
    print(q.quote_id, q.yes_bid)

# All quotes against RFQs you originated.
for q in client.communications.quotes.list_all(rfq_user_filter="self"):
    ...

# Same shortcut on RFQs:
for rfq in client.communications.rfqs.list_all(user_filter="self"):
    ...
```

`UserFilterLiteral` only accepts `"self"` today — the spec leaves room for
server-side shorthands like `"organization"` in the future without an SDK
upgrade.

## Post-only quotes

`quotes.create()` accepts `post_only=True` (added in v2.1.0) to ensure your
resting order is canceled rather than crossed if it would take liquidity:

```python
client.communications.quotes.create(
    rfq_id="rfq_abc",
    yes_bid="0.60", no_bid="0.40",
    rest_remainder=True,
    post_only=True,    # cancel rather than cross
)
```

!!! info "Delete is not server-idempotent"
    `rfqs.delete(rfq_id)` and `quotes.delete(quote_id)` propagate a 404 as
    `KalshiNotFoundError` when the RFQ or quote is already canceled,
    expired, or never existed. The SDK does **not** swallow it — the caller
    owns safe-retry idempotency:

    ```python
    from kalshi.errors import KalshiNotFoundError

    try:
        client.communications.rfqs.delete(rfq_id)
    except KalshiNotFoundError:
        pass  # already canceled — idempotent
    ```

## RFQ statuses

`open`, `accepted`, `confirmed`, `canceled`. Status filtering accepts these
literal strings.

## Migrating from v2.x

| v2.x (deprecated) | v3.0.0 (canonical) |
|---|---|
| `client.communications.list_rfqs(...)` | `client.communications.rfqs.list(...)` |
| `client.communications.list_all_rfqs(...)` | `client.communications.rfqs.list_all(...)` |
| `client.communications.get_rfq(rfq_id)` | `client.communications.rfqs.get(rfq_id)` |
| `client.communications.create_rfq(...)` | `client.communications.rfqs.create(...)` |
| `client.communications.delete_rfq(rfq_id)` | `client.communications.rfqs.delete(rfq_id)` |
| `client.communications.list_quotes(...)` | `client.communications.quotes.list(...)` |
| `client.communications.list_all_quotes(...)` | `client.communications.quotes.list_all(...)` |
| `client.communications.get_quote(quote_id)` | `client.communications.quotes.get(quote_id)` |
| `client.communications.create_quote(...)` | `client.communications.quotes.create(...)` |
| `client.communications.delete_quote(quote_id)` | `client.communications.quotes.delete(quote_id)` |
| `client.communications.accept_quote(quote_id, accepted_side=...)` | `client.communications.quotes.accept(quote_id, accepted_side=...)` |
| `client.communications.confirm_quote(quote_id)` | `client.communications.quotes.confirm(quote_id)` |

`get_id()` is unchanged.

## Reference

::: kalshi.resources.communications.CommunicationsResource
    options:
      heading_level: 3

::: kalshi.resources.communications.RFQsResource
    options:
      heading_level: 3

::: kalshi.resources.communications.QuotesResource
    options:
      heading_level: 3

::: kalshi.resources.communications.AsyncCommunicationsResource
    options:
      heading_level: 3

::: kalshi.resources.communications.AsyncRFQsResource
    options:
      heading_level: 3

::: kalshi.resources.communications.AsyncQuotesResource
    options:
      heading_level: 3
