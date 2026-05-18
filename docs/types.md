# Types & literals

The SDK exports a handful of helper types from `kalshi.types` and a family of
`Literal` aliases from `kalshi` (re-exported from `kalshi.models`).

## Money

### `DollarDecimal`

Used for every price field (`yes_bid`, `yes_ask`, `no_bid`, `no_ask`,
`yes_price`, `no_price`, `target_cost`, …).

- **On input** — accepts `Decimal`, `int`, `float`, or `str`. Anything that
  isn't one of those raises `TypeError`. Floats are normalized via `str(value)`
  so `Decimal(0.65)` rounding artifacts never make it to the wire.
- **On serialize** — emits a plain `str(decimal)`.
- **Recommended input** — strings (`"0.65"`) or `Decimal("0.65")`. Float works
  but `Decimal` is the canonical form.

```python
from decimal import Decimal
from kalshi import CreateOrderRequest

CreateOrderRequest(ticker="X", side="yes", action="buy", count=1, yes_price="0.65")
CreateOrderRequest(ticker="X", side="yes", action="buy", count=1, yes_price=Decimal("0.65"))
```

The Kalshi API uses **FixedPointDollars** strings (`"0.5600"`) with up to six
decimal places. Field names on the wire have a `_dollars` suffix
(`yes_bid_dollars`). The SDK's Pydantic models accept both the short and long
form on input (`validation_alias=AliasChoices("yes_bid_dollars", "yes_bid")`)
and emit the long form on output where required.

### `FixedPointCount`

Same machinery as `DollarDecimal`, used for count-like fields the API
fixed-points (e.g. queue position, `count_fp`). You shouldn't need to touch it
directly.

### Integer cents

Some fields are plain `int` cents, **not** `DollarDecimal`:

| Field | Where | Unit |
|---|---|---|
| `Balance.balance` / `portfolio_value` | `client.portfolio.balance()` | cents |
| `CreateOrderRequest.buy_max_cost` | `client.orders.create(..., buy_max_cost=500)` | cents — `500` means $5.00 |
| `ApplySubaccountTransferRequest.amount_cents` | `client.subaccounts.transfer(...)` | cents |

Passing a `Decimal` or `float` to one of these raises `ValueError` at
construction — by design, so silent ×100 corruption can't happen.

## Nullable lists

`NullableList[T]` coerces a server `null` into `[]`. Used on response fields
like `Orderbook.yes`, `Orderbook.no`, and `MarketCandlesticks.candlesticks`,
where the server may omit the array entirely on empty results. You read these
as plain `list[T]`.

## Literal aliases

Every enum-like kwarg uses a `Literal` alias so your IDE auto-completes and
`mypy` rejects typos.

| Alias | Values |
|---|---|
| `SideLiteral` | `"yes"`, `"no"` |
| `ActionLiteral` | `"buy"`, `"sell"` |
| `TimeInForceLiteral` | `"fill_or_kill"`, `"good_till_canceled"`, `"immediate_or_cancel"` |
| `SelfTradePreventionTypeLiteral` | `"taker_at_cross"`, `"maker"` |
| `OrderStatusLiteral` | `"resting"`, `"canceled"`, `"executed"` |
| `MarketStatusLiteral` | `"unopened"`, `"open"`, `"paused"`, `"closed"`, `"settled"` |
| `EventStatusLiteral` | `"unopened"`, `"open"`, `"closed"`, `"settled"` |
| `MveFilterLiteral` | `"only"`, `"exclude"` |
| `MveHistoricalFilterLiteral` | `"exclude"` |
| `MultivariateCollectionStatusLiteral` | `"unopened"`, `"open"`, `"closed"` |
| `SettlementStatusLiteral` | `"all"`, `"unsettled"`, `"settled"` |
| `IncentiveProgramStatusLiteral` | `"all"`, `"active"`, `"upcoming"`, `"closed"`, … |
| `IncentiveProgramTypeLiteral` | `"all"`, `"liquidity"`, `"volume"` |

!!! tip "Markets pause; events don't"
    `MarketStatusLiteral` has a `"paused"` value that `EventStatusLiteral`
    lacks. Filtering events by status will never see `"paused"`.

All aliases are exported from the top-level `kalshi` package:

```python
from kalshi import SideLiteral, ActionLiteral, TimeInForceLiteral

def place(side: SideLiteral, action: ActionLiteral, tif: TimeInForceLiteral) -> None:
    ...
```

## Wire-format suffixes

When you crack open a model and see a long alias on a field, here's what each
suffix means:

| Suffix | Wire type | SDK type |
|---|---|---|
| `_dollars` | FixedPointDollars string (e.g. `"0.5600"`) | `Decimal` via `DollarDecimal` |
| `_fp` | Integer fixed-point | `Decimal` via `FixedPointCount` |
| `_ts` | Unix seconds (int) | `int` |
| `_at` / no suffix | ISO-8601 datetime string | `datetime` |

A few legacy fields use `_cents`; those are plain `int` cents.
