# Concepts

Short glossary of the Kalshi domain objects you'll hit. Each link goes to the
resource page that operates on them.

## Series, event, market

The three-level ticker hierarchy:

- **Series** — a recurring family (e.g. `KXPRES` covers presidential elections).
  Series tickers look like `KXPRES`. See [Series](resources/series.md).
- **Event** — one instance of a series (e.g. `KXPRES-24`, the 2024 election).
  See [Events](resources/events.md).
- **Market** — a single YES/NO contract under an event (e.g. `KXPRES-24-DJT`,
  "will Trump win"). See [Markets](resources/markets.md).

Every market belongs to exactly one event; every event belongs to exactly one
series.

## YES, NO, side, action

A Kalshi market trades two complementary contracts that always sum to $1:
**YES** and **NO**. Each trade has a `side` (which contract) and an `action`:

- `side="yes"`, `action="buy"` — buying YES.
- `side="yes"`, `action="sell"` — selling YES.
- `side="no"`, `action="buy"` — buying NO (equivalent to selling YES against
  the orderbook, but accounted separately).

These are `Literal` types — see [Types & literals](types.md).

## Prices

Prices live in `[0.00, 1.00]` and represent dollars (a YES at $0.65 implies a
65% market-implied probability). Always pass them as strings or `Decimal`:

```python
order = client.orders.create(..., yes_price="0.65")
order = client.orders.create(..., yes_price=Decimal("0.65"))
```

Float is a footgun; the SDK accepts it but normalizes through `str()` to avoid
`0.65 → 0.6499999…`. See [`DollarDecimal`](types.md).

The Kalshi API returns prices as JSON strings with a `_dollars` suffix
(`yes_bid_dollars: "0.5600"`). The SDK maps these to short field names
(`yes_bid: Decimal("0.5600")`). Both directions round-trip.

## Datetime semantics

REST response models type every server-emitted timestamp as
`pydantic.AwareDatetime` — Pydantic v2's tz-aware-only variant of
`datetime`. Kalshi's wire format is always RFC3339 with `Z` (UTC), so
live parsing is unaffected. The win is at construction time: tests and
fixtures that build a model directly **must** pass a tz-aware value, or
the model raises `ValidationError`. This catches naive `datetime.now()`
slipping into trading code, where tz arithmetic bugs would otherwise
corrupt expiration / settlement calculations.

```python
from datetime import datetime, UTC

Order(... created_time=datetime.now(UTC))                  # OK
Order(... created_time=datetime(2026, 1, 1, tzinfo=UTC))   # OK
Order(... created_time=datetime.now())                     # ValidationError — naive
```

WebSocket payload timestamps (`kalshi.ws.models.*`) currently keep the
bare `datetime` annotation; the AwareDatetime upgrade for WS models is a
separate, future change.

## Cents vs dollars

A few fields are **integer cents**, not dollars:

- `Balance.balance` / `portfolio_value` — cents.
- `CreateOrderRequest.buy_max_cost` — cents.
- `ApplySubaccountTransferRequest.amount_cents` — cents.

These are typed `int`. Passing a `Decimal` or `float` raises `ValueError` at
construction. The rule: anything with `_cents` / `buy_max_cost` is cents;
anything with `_dollars` or `yes_price` / `no_price` is `Decimal` dollars.

## Order, fill, position, settlement

- **Order** — your intent. Has a status (`resting`, `canceled`, `executed`).
- **Fill** — an actual execution against an order. One order can produce many
  fills.
- **Position** — your aggregate exposure on a market (signed by side).
- **Settlement** — what the exchange paid out when the market resolved.

Orders come in two families:

- **V1** — `/portfolio/orders/*`. Yes/no sides, paired `yes_price` /
  `no_price`. Stable surface; deprecation no earlier than May 6, 2026.
- **V2** — `/portfolio/events/orders/*`. Event-scoped, single-book
  `bid` / `ask` sides, single `price` field, required `client_order_id`
  acting as an idempotency key. Use this for new event-market integrations.

See [Orders](resources/orders.md), [Portfolio](resources/portfolio.md).

## RFQ and Quote

**RFQ** ("Request For Quote") — a private "Can someone make me a market on this
contract at this size?" message. **Quote** — a counterparty's answer ("I'll sell
you YES at $0.62 / buy from you at $0.60"). The requester picks a side and
accepts; the maker confirms.

This is Kalshi's bilateral block-trade rail, alongside the public order book.
See [Communications](resources/communications.md).

## Multivariate event collection

A template for combo bets: "Will it rain in NYC AND the Yankees win Saturday?"
The collection holds the building-block markets; calling `create_market` with a
list of leg selections mints a derived YES/NO contract.

See [Multivariate](resources/multivariate.md).

## Milestone

A real-world reference event a market is anchored to — a baseball game, an
economic release, an election. Live data (scores, clocks, weather) is keyed by
milestone id.

See [Milestones](resources/milestones.md), [Live data](resources/live-data.md).

## Structured target

The entity a market is "about" — a team, player, candidate, company. Two
markets pointing at the same Yankees roster share a structured target id, so
you can group markets by underlying entity.

See [Structured targets](resources/structured-targets.md).

## Incentive program

Time-boxed reward campaigns (maker rebates, volume bonuses) on specific
markets or series.

See [Incentive programs](resources/incentive-programs.md).

## Subaccount

A logical wallet partition under your main account. Used to isolate strategies
or risk pools. Subaccount `0` is your primary account; `1`–`32` are numbered
extras. Most resource methods accept a `subaccount=` kwarg to route the call.

See [Subaccounts](resources/subaccounts.md).

## Order group

A rolling contracts-limit bucket that several orders can share. Trips when the
group hits its cap; can be `reset()` or `trigger()`ed manually.

See [Order groups](resources/order-groups.md).

## FCM

**Futures Commission Merchant.** Kalshi-side broker designation. FCM members
get a separate `/fcm/*` surface that takes a `subtrader_id` discriminator and
returns the same shapes as `portfolio.*`. Non-FCM accounts get 401/403.

See [FCM](resources/fcm.md).

## API key, scope

Authentication identity. Has `read` and `write` scopes; `write` requires
`read`. Can be created via the web UI or via
`client.api_keys.generate()` / `client.api_keys.create()`.

See [API keys](resources/api-keys.md).
