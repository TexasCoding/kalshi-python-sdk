# Communications (RFQ / Quote)

Kalshi's bilateral block-trade rail. An **RFQ** is a private "make me a market
on this contract at this size?" message; a **Quote** is a counterparty's
answer. The requester accepts a side; the maker confirms; the trade settles.

Auth required throughout.

## Quick reference

| Method | Endpoint |
|---|---|
| `get_id()` | `GET /communications/id` |
| `list_rfqs(...)` / `list_all_rfqs(...)` | `GET /communications/rfqs` |
| `get_rfq(rfq_id)` | `GET /communications/rfqs/{rfq_id}` |
| `create_rfq(...)` | `POST /communications/rfqs` |
| `delete_rfq(rfq_id)` | `DELETE /communications/rfqs/{rfq_id}` |
| `list_quotes(...)` / `list_all_quotes(...)` | `GET /communications/quotes` |
| `get_quote(quote_id)` | `GET /communications/quotes/{quote_id}` |
| `create_quote(...)` | `POST /communications/quotes` |
| `delete_quote(quote_id)` | `DELETE /communications/quotes/{quote_id}` |
| `accept_quote(quote_id, *, accepted_side)` | `POST /communications/quotes/{quote_id}/accept` |
| `confirm_quote(quote_id)` | `POST /communications/quotes/{quote_id}/confirm` |

`get_id()` returns your `participant_id` — the value you'll pass as
`quote_creator_user_id` / `rfq_creator_user_id` when filtering lists.

## Requester flow

```python
# Identify yourself for filtering downstream.
me = client.communications.get_id()

# 1) Post an RFQ asking for a price on 500 contracts.
rfq = client.communications.create_rfq(
    market_ticker="KXPRES-24-DJT",
    contracts=500,
    rest_remainder=True,
)
print(rfq.rfq.rfq_id)

# 2) Poll for incoming quotes (or subscribe to the `communications` WS channel).
quotes = client.communications.list_quotes(rfq_creator_user_id=me.user_id)
for q in quotes:
    print(q.quote_id, q.yes_bid, q.no_bid)

# 3) Accept a side on one of them.
accepted = client.communications.accept_quote(quotes.items[0].quote_id, accepted_side="yes")
```

## Maker flow

```python
me = client.communications.get_id()

# 1) Watch for incoming RFQs.
for rfq in client.communications.list_all_rfqs(status="open"):
    print(rfq.rfq_id, rfq.market_ticker, rfq.contracts)

# 2) Quote one.
resp = client.communications.create_quote(
    rfq_id="rfq_abc",
    yes_bid="0.60",
    no_bid="0.40",
    rest_remainder=False,
)

# 3) Wait for the counterparty to accept.
# 4) Confirm to lock the fill.
client.communications.confirm_quote(resp.quote.quote_id)
```

!!! warning "`list_quotes` requires a user-id filter"
    `list_quotes` and `list_all_quotes` **must** be called with one of
    `quote_creator_user_id=` or `rfq_creator_user_id=`. Passing `rfq_id=`
    alone raises `ValueError` locally before the round trip — this enforces
    a server-side requirement.

## RFQ statuses

`open`, `accepted`, `confirmed`, `canceled`. Status filtering accepts these
literal strings.

## Reference

::: kalshi.resources.communications.CommunicationsResource
    options:
      heading_level: 3

::: kalshi.resources.communications.AsyncCommunicationsResource
    options:
      heading_level: 3
