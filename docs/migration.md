# Migration

## v7.3 → v7.4.0

Reconciles upstream core OpenAPI content under version string **3.26.0** for
the settlement-advance subaccount surface (Closes #486). **No breaking
public-API removals.** Response parsing for `list_balances()` now expects the
new required balance fields from the live API.

### Added

- **`subaccounts.lock_settlement_advance()` / `unlock_settlement_advance()`**
  (sync + async) — lock/unlock a subaccount for settlement-advance work.
- **`SubaccountBalance.voluntarily_locked`**, **`settlement_advance`**,
  optional **`settlement_advance_state`**.

```python
lock = client.subaccounts.lock_settlement_advance(subaccount_number=1)
print(lock.settlement_advance_state)

resp = client.subaccounts.list_balances()
for bal in resp.subaccount_balances:
    print(bal.voluntarily_locked, bal.settlement_advance)

client.subaccounts.unlock_settlement_advance(subaccount_number=1)
```

See the [changelog](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/CHANGELOG.md)
for the full list.

## v7.2 → v7.3.0

Syncs the SDK to core OpenAPI **3.26.0** and closes residual Klear settlement
additive-optional drift (Closes #484). **No breaking changes.**

### Added

- **`historical.positions()` / `positions_all()`** (sync + async) —
  `GET /historical/positions`. Auth required. Returns `PositionsResponse`
  (same shape as `portfolio.positions()`). Filters: `limit`, `cursor`,
  `ticker`, `event_ticker` only — no `count_filter` / `subaccount`.
- **`HistoricalCutoff.market_positions_last_updated_ts`**
  (`AwareDatetime | None`) — archival boundary for historical positions.
- **`omitted_subtrader_count`** (`int | None`) on
  `GetSettlementEstimateResponse` and `AssetClassSettlementEstimate` (Klear).

```python
co = client.historical.cutoff()
if co.market_positions_last_updated_ts is not None:
    for mp in client.historical.positions_all():
        print(mp.ticker, mp.position)
```

See the [changelog](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/CHANGELOG.md)
for the full list.

## v7.1 → v7.2.0

Reconciles in-place OpenAPI/perps OpenAPI edits under version string **3.25.0**
(no `info.version` bump upstream). **No breaking public-API removals** —
one soft-deprecation and a defensive model relaxation.

### Deprecated: `PerpsClient.orders.list_fcm()` / `list_all_fcm()`

Kalshi removed `GET /margin/fcm/orders` from the perps OpenAPI, so the live
endpoint may 404. The methods (sync + async) are **retained** and emit a
`DeprecationWarning` on each call — same soft-deprecation pattern as
`exchange.announcements()` after 3.24.0. A future major release removes them
once the removal is confirmed permanent.

```python
# Still callable, but warns and may 404:
# perps.orders.list_fcm(subtrader_id="...")
# list(perps.orders.list_all_fcm(subtrader_id="..."))
```

Prediction-API FCM routes (`client.fcm.orders` / `client.fcm.positions` on
`/fcm/*`) are **unchanged**.

### Changed: `SubaccountTransfer` is cash-only on the wire

`GET /portfolio/subaccounts/transfers` no longer returns position-transfer
rows. Upstream dropped `transfer_type` and the position-only fields
(`market_ticker`, `side`, `count`, `price`) from the schema.

- New responses omit those fields; `t.transfer_type` is `None` unless a lagging
  server still sends it.
- Position moves continue via `subaccounts.transfer_position()` (and its
  request/response models) — not via the transfers list.
- The SDK keeps the dropped fields as **optional** so older payloads still
  parse (defensive optional-ization).

```python
page = client.subaccounts.list_transfers()
for t in page:
    # cash row only
    print(t.transfer_id, t.amount_cents, t.from_subaccount, t.to_subaccount)
    # t.transfer_type may be None (no longer required on the wire)
```

### Infra

Claude Code Action workflows (`claude-review` / `@claude`) were removed from
CI; they are not part of the public SDK surface.

See the [changelog](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/CHANGELOG.md)
for the full list.

## v7.0 → v7.1.0

Syncs the SDK to OpenAPI/AsyncAPI spec **3.25.0**. **No breaking changes.**

### Added

- **`MarginMarket.schedule`** (`MarginMarketSchedule | None`, required key) —
  current trading hours for a margin market. `None` means 24/7. Nested fields:
  `is_open`, `next_close_ts`, `next_open_ts` (Unix seconds; nullable by phase).
  If you construct `MarginMarket` instances by hand in tests, pass
  `schedule=None` or a `MarginMarketSchedule(...)`.

### Deferred

- Core OpenAPI lists `POST /portfolio/intra_exchange_instance_transfer`, still
  marked **currently not available**. The core client does not expose it; use
  `PerpsClient.transfers.transfer_instance()` on the margin product.

See the [changelog](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/CHANGELOG.md)
for the full list.

## v6 → v7.0.0

Syncs the SDK to OpenAPI/AsyncAPI spec **3.24.0**. One breaking change on the
subaccounts surface, one soft-deprecation, three new endpoints, and additive
field/param additions.

### Breaking: position-transfer price is fixed-point dollars, not integer cents

The per-contract price on `subaccounts.transfer_position()` (and the underlying
`ApplySubaccountPositionTransferRequest` / `SubaccountTransfer` models) is renamed
from **`price_cents`** (integer cents, 0–100) to **`price`** (`Decimal`,
fixed-point dollars, 0–1.0). Upstream renamed the wire field `price_cents` →
`price` (`FixedPointDollars`) in 3.24.0.

```python
from decimal import Decimal

# v6 (removed)
# client.subaccounts.transfer_position(
#     client_transfer_id=..., from_subaccount=0, to_subaccount=1,
#     market_ticker="MKT-A", side="yes", count=5, price_cents=55,
# )

# v7 — price is dollars, as a Decimal
client.subaccounts.transfer_position(
    client_transfer_id=...,
    from_subaccount=0,
    to_subaccount=1,
    market_ticker="MKT-A",
    side="yes",
    count=5,
    price=Decimal("0.55"),   # 55¢ cost basis
)
```

The old client-side `0–100` cap is gone. `price` uses `OrderPrice`, which guards
non-negativity and the `$0.0001` tick (matching `CreateOrderRequest`); the upper
bound is the server's to enforce.

### Deprecated: `exchange.announcements()`

Kalshi removed `GET /exchange/announcements` and the `Announcement` schema from
the spec in 3.24.0, so the live endpoint now 404s. `exchange.announcements()`
(sync + async) and the `Announcement` model are **retained** but emit a
`DeprecationWarning` — upstream has transiently dropped endpoints as publishing
glitches before, so the method is kept pending confirmation the removal is
permanent. A future major release removes them.

### Added

- **`communications.quotes.get_for_rfq(rfq_id, quote_id)`** (sync + async) —
  `GET /communications/rfqs/{rfq_id}/quotes/{quote_id}`, the RFQ-scoped get-quote
  (returns `GetQuoteResponse`, the same payload as the flat `quotes.get`).
- **`klear.margin.active_obligations()`** (sync + async) —
  `GET /margin/active_obligations`, all currently-active settlement obligations.
- **`klear.margin.settlement_estimate_by_asset_class()`** (sync + async) —
  `GET /margin/settlement_estimate_by_asset_class`, next-settlement estimates
  keyed by asset class.
- **`SubaccountNettingConfig.exchange_index`** (`int`, required).
- **`portfolio.balance(*, exchange_index=...)`** — optional query param to target
  a specific exchange shard (defaults to 0 server-side).
- **`ObligationEntry.asset_class`** (perps SCM / Klear; `Literal["Crypto"]`).

See the [changelog](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/CHANGELOG.md)
for the full list.

## v5 → v6.0.0

**Breaking: multivariate lookup-history is gone.** Kalshi removed the
`GET /multivariate_event_collections/{ticker}/lookup` endpoint
(`GetMultivariateEventCollectionLookupHistory`) and the `LookupPoint` schema from
the OpenAPI spec in 3.23.0, so the SDK removed the matching method and model.

### Removed

| Removed (v5)                                        | Replacement |
| --------------------------------------------------- | ----------- |
| `multivariate_collections.lookup_history(...)` (sync + async) | none — the endpoint was deleted upstream |
| `LookupPoint` model (exported from `kalshi` / `kalshi.models`) | none |

Everything else in 6.0.0 is additive and needs no code changes:

- New optional/required response fields on `ApiKey`, `SubaccountTransfer`,
  `MarginPosition`, `MarginRiskPosition`, `MarginOrder`, and the WS
  `market_lifecycle_v2` payload.
- New `subaccounts.transfer_position(...)` method (`POST
  /portfolio/subaccounts/positions/transfer`) for moving open positions between
  subaccounts.
- `subaccounts.create()` gained an optional `exchange_index` argument.

See the [changelog](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/CHANGELOG.md)
for the full list.

## v4 → v5.0.0

**Breaking: the V1 order-write API is gone.** Kalshi removed the V1 order
endpoints from the OpenAPI spec in 3.22.0, so the SDK removed the matching
methods and models. Order writes now go exclusively through the V2
`/portfolio/events/orders` family (the `*_v2` methods, available since 3.18.0).

Read endpoints are unchanged: `orders.get`, `orders.list`, `orders.list_all`,
`orders.queue_positions`, `orders.queue_position`, and `portfolio.fills` all keep
working exactly as before.

### Removed methods → replacement

| Removed (v4)                         | Use instead (v5)                                   |
| ------------------------------------ | -------------------------------------------------- |
| `orders.create(...)`                 | `orders.create_v2(request=CreateOrderV2Request(...))` |
| `orders.cancel(order_id)`            | `orders.cancel_v2(order_id, ...)`                  |
| `orders.amend(order_id, ...)`        | `orders.amend_v2(order_id, request=AmendOrderV2Request(...))` |
| `orders.decrease(order_id, ...)`     | `orders.decrease_v2(order_id, request=DecreaseOrderV2Request(...))` |
| `orders.batch_create(orders=[...])`  | `orders.batch_create_v2(request=BatchCreateOrdersV2Request(orders=[...]))` |
| `orders.batch_cancel(orders=[...])`  | `orders.batch_cancel_v2(request=BatchCancelOrdersV2Request(orders=[...]))` |

The V2 models use a single `price` with a `side` of `"bid"`/`"ask"` (book side),
rather than the V1 `yes_price` / `no_price` + `yes`/`no`:

```python
from decimal import Decimal
from kalshi.models import CreateOrderV2Request

# v4 (removed)
# order = client.orders.create(ticker="MKT-A", side="yes", action="buy", count=1, yes_price="0.56")

# v5
resp = client.orders.create_v2(
    request=CreateOrderV2Request(
        ticker="MKT-A",
        client_order_id="my-idempotency-key",
        side="bid",                      # book side, not yes/no
        count=Decimal("1"),
        price=Decimal("0.56"),
        time_in_force="good_till_canceled",
        self_trade_prevention_type="taker_at_cross",
    )
)
```

### Removed models

These are no longer exported from `kalshi` / `kalshi.models`:
`CreateOrderRequest`, `AmendOrderRequest`, `AmendOrderResponse`,
`DecreaseOrderRequest`, `BatchCreateOrdersRequest`, `BatchCreateOrdersResponse`,
`BatchCreateOrdersResponseEntry`, `BatchCancelOrdersRequest`,
`BatchCancelOrdersResponse`, `BatchCancelOrdersResponseEntry`,
`BatchCancelOrdersRequestOrder`, and the `ActionLiteral` alias. Use the `…V2…`
models instead.

### Other breaking changes

- `communications.quotes.list` / `list_all` (and the `communications.list_quotes`
  / `list_all_quotes` facades) no longer accept `event_ticker` / `market_ticker`
  — those filters were removed from `GET /communications/quotes` upstream.

### New in 5.0.0

- RFQ-scoped quote actions: `communications.quotes.accept_for_rfq`,
  `confirm_for_rfq`, and `delete_for_rfq` (take both `rfq_id` and `quote_id`).
- `cancel_v2(..., market_ticker=...)` and `BatchCancelOrdersV2RequestOrder.market_ticker`
  for `-1` (auto-route) exchange indices.
- `SubaccountBalance.exchange_index`; perps SCM `MarketSettlementEstimate`,
  `SettlementEstimate.positions`, `GetSettlementEstimateResponse.prev_settlement_prices`.

## v3 → v4.0.0

v4.0.0 has **one breaking change** — the Self-Clearing-Member "Klear" API
migrated from cookie-session login to a pre-generated **Bearer token**, because
upstream removed `POST /log_in`. Everything else in v4.0.0 is additive
(`cfbenchmarks_value` WS channel, `AccountResource.upgrade()`,
`AccountApiLimits.grants`, perps `api_limits()`, perps market notional/leverage
fields). The prediction and perps trade-api surfaces are unchanged.

For full BEFORE/AFTER snippets see [v3-to-v4.md](migrations/v3-to-v4.md). Quick
summary of the Klear break:

| Was (v3.x) | Now (v4.0.0) |
|---|---|
| `KlearClient(demo=True)` then `client.login(email=..., password=..., code=...)` | `KlearClient(admin_user_id=..., access_token=..., demo=True)` |
| `KlearClient.from_env()` (URL routing only — no credential env vars) | `KlearClient.from_env()` reads `KALSHI_KLEAR_ADMIN_USER_ID` / `KALSHI_KLEAR_ACCESS_TOKEN` |
| `client.is_authenticated`, `client.auth`, `LogInRequest`, `LogInResponse` | removed |

Generate the token / find your admin user id at <https://klearing.kalshi.com>
(the "Security" page).

## v2.7 → v3.0

v3.0.0 is the first major release in the v3 line. It renames three groups of
public methods (issues `#348`, `#349`, `#351`). The wire protocol is
unchanged from v2.7.0; v3 is purely a Python-API ergonomics break.

**One-release deprecation window.** All old names continue to work in v3.0.0
as `@typing_extensions.deprecated` aliases. Each emits `DeprecationWarning`
on every call. Aliases will be removed no sooner than v3.1.0.

For full BEFORE/AFTER snippets and a one-page search-and-replace cheat sheet,
see [v2-to-v3.md](migrations/v2-to-v3.md). Quick summary:

| Rename | Old (deprecated v3.0.0) | New (v3.0.0+) |
|---|---|---|
| Communications sub-namespaces | `client.communications.list_rfqs(...)` | `client.communications.rfqs.list(...)` |
|   | `client.communications.get_quote(id)` | `client.communications.quotes.get(id)` |
|   | (12 forwarders total across rfqs/quotes) | (same; sub-resource methods) |
| `*_all` naming | `client.markets.list_trades_all(...)` | `client.markets.list_all_trades(...)` |
| `fills` relocation | `client.orders.fills(...)` | `client.portfolio.fills(...)` |
|   | `client.orders.fills_all(...)` | `client.portfolio.fills_all(...)` |

## v2.5 → v2.6

v2.6 ships two behavioral fences, both surface bugs that were already wrong:
``bool`` no longer slips through on integer request fields (`#295`), and
``extra_headers`` cannot carry ``KALSHI-ACCESS-*`` keys (`#298`). Wire
format is unchanged.

### Breaking: `int` request fields reject `bool`

Per `#295`, every integer field on every Request model that lacks a
dedicated validator now rejects ``bool`` at construction. ``bool`` is an
``int`` subclass, so a caller passing ``True``/``False`` silently became
``1``/``0`` and money-routing fields (``subaccount``, ``from_subaccount``,
``amount_cents``, ``count``, etc.) silently misrouted. The fix mirrors
``CreateOrderRequest.buy_max_cost`` (`#243`) across all request models on
both V1 and V2 surfaces:

```python
# v2.5 (silent True → 1)
ApplySubaccountTransferRequest(
    client_transfer_id=uuid4(),
    from_subaccount=True,   # → 1, transfer from subaccount 1
    to_subaccount=True,     # → 1, transfer TO subaccount 1
    amount_cents=True,      # → 1, one cent
)

# v2.6 (raises ValidationError on each bool)
ApplySubaccountTransferRequest(
    client_transfer_id=uuid4(),
    from_subaccount=True,   # ➜ ValidationError: bool is not a valid int here
)
```

A new public alias ``kalshi.StrictInt = Annotated[int, BeforeValidator(...)]``
is exported for downstream models that want the same guard.

### Breaking: `KALSHI-ACCESS-*` rejected in `extra_headers`

Per `#298`, the SDK promised in docs that auth headers could not be forged
via ``extra_headers``. That promise relied on a case-sensitive Python dict
merge: a caller-supplied lowercase ``"kalshi-access-key"`` co-existed with
the SDK-signed uppercase ``"KALSHI-ACCESS-KEY"`` and httpx shipped both raw
header lines on the wire — a forge surface even though the documented
contract said otherwise. Now both the per-request ``extra_headers`` kwarg
and ``KalshiConfig(extra_headers=...)`` reject any key (case-insensitive)
that starts with ``kalshi-access-`` at the construction boundary:

```python
# v2.5 (silently shipped two KALSHI-ACCESS-KEY header lines)
client.markets.list(
    extra_headers={"kalshi-access-key": "forged"},
)

# v2.6 (raises ValueError naming the leaked keys)
client.markets.list(
    extra_headers={"kalshi-access-key": "forged"},
)
# ValueError: extra_headers must not include KALSHI-ACCESS-* keys ...

# Same rejection now fires at construction:
KalshiConfig(extra_headers={"kalshi-access-key": "x"})
# ValueError
```

Companion behavior: `_post(json=...)` / `_put(json=...)` /
`_delete_with_body(json=...)` (and async mirrors) now pin
``Content-Type: application/json`` explicitly. A caller-supplied
``extra_headers={"content-type": "text/plain"}`` previously suppressed
httpx's implicit inference and shipped a JSON body labelled as plain
text; the explicit pin prevents that. Most callers are unaffected.

### Behavioral note: raw `subscribe_orderbook_delta` consumers

Per `#296`, `OrderbookManager._apply_snapshot_inplace` now adopts
``msg.msg.yes`` / ``.no`` by identity for the recv-loop hot path. Raw
consumers of ``subscribe_orderbook_delta`` who receive an
``OrderbookSnapshotMessage`` and hold a reference to ``msg.msg.yes`` /
``.no`` will observe future delta mutations through that reference:

```python
# v2.6 raw subscriber
async for msg in stream:
    if isinstance(msg, OrderbookSnapshotMessage):
        held = msg.msg.yes        # ← LIVE dict, mutated by next delta
```

The high-level ``client.orderbook(ticker)`` / ``subscribe_book(ticker)``
iterators are unaffected — both materialize fresh ``Orderbook`` instances
that are safe to retain. The public ``OrderbookManager.apply_snapshot()``
is also unaffected: it defensively copies after the inplace adoption so
the caller-supplied ``msg`` keeps its original dicts. If you need an
immutable snapshot view from the raw stream, copy explicitly:

```python
async for msg in stream:
    if isinstance(msg, OrderbookSnapshotMessage):
        immutable_yes = dict(msg.msg.yes)
```

## v2.4 → v2.5

v2.5 ships two user-visible breaking changes — both surface bugs that
v2.4's audit missed — plus performance wins on the WS hot path, REST
per-request headers, and a pluggable REST JSON loader. Wire format is
unchanged.

### Breaking: `orders.create()` requires `count` and `action`

Per #242, the kwarg-form `client.orders.create(ticker=..., side=...)`
previously defaulted `action` to `"buy"` and `count` to `1` if you
forgot them — placing a 1-contract live buy with no error. Now both are
required on the kwarg path and the model: `CreateOrderRequest.count`
no longer has a default.

```python
# v2.4 (silent 1-contract buy on the missing kwargs)
client.orders.create(ticker="EXAMPLE-25-T", side="yes")

# v2.5 (raises TypeError before any HTTP request)
client.orders.create(ticker="EXAMPLE-25-T", side="yes")
# TypeError: create() requires `ticker`, `side`, `count`, and `action`

# v2.5 (explicit, works)
client.orders.create(
    ticker="EXAMPLE-25-T",
    side="yes",
    action="buy",
    count=10,
    yes_price="0.65",
)
```

The `request=...` overload is unaffected — `CreateOrderRequest(...)` is
the recommended path for programmatic order construction.

### Breaking: WS + REST model fields widened to `Decimal`

Per #258 and #259, nine model fields previously typed as `str` or
`float` are now `Decimal`-backed via `DollarDecimal` /
`FixedPointCount` / `Decimal`-via-`_coerce_decimal`. This brings them
under the same coercion contract every other money/count field in the
SDK has used since v2.0:

| Field | Was | Now |
|---|---|---|
| `OrderGroupPayload.contracts_limit` (WS) | `str \| None` | `FixedPointCount \| None` |
| `TickerPayload.dollar_volume` (WS) | `str` | `DollarDecimal` |
| `TickerPayload.dollar_open_interest` (WS) | `str` | `DollarDecimal` |
| `Market.floor_strike` | `Decimal \| None` (bare) | `DollarDecimal \| None` |
| `Market.cap_strike` | `Decimal \| None` (bare) | `DollarDecimal \| None` |
| `Event.fee_multiplier_override` | `Decimal \| None` (bare) | `Decimal \| None` (coerced) |
| `MarketLifecyclePayload.floor_strike` (WS) | `Decimal \| None` (bare) | `DollarDecimal \| None` |
| `Series.fee_multiplier` | `float` | `Decimal` (coerced) |
| `SeriesFeeChange.fee_multiplier` | `float` | `Decimal` (coerced) |

Wire format is unchanged — the spec already specified these as decimal
strings or fixed-point. The behavior change is at the Python boundary:

```python
# v2.4
ticker_payload.dollar_volume          # "1234.5600"  (str)
ticker_payload.dollar_volume + 1.0    # TypeError

# v2.5
ticker_payload.dollar_volume          # Decimal("1234.5600")
ticker_payload.dollar_volume + Decimal("1.00")  # Decimal arithmetic
```

If you were already wrapping these in `Decimal(...)` at the consumer
side, that wrapper now becomes a no-op identity coercion — safe to
keep or remove. Float arithmetic against `Series.fee_multiplier` will
now raise `TypeError`; coerce to `Decimal` first.

### Additive: per-request `extra_headers`

Per #253, every public REST resource method now accepts an
`extra_headers` kwarg for distributed-tracing, idempotency, or
per-call routing. `KALSHI-ACCESS-*` signing headers always win, so
callers cannot forge them via this surface.

```python
import uuid

client.orders.create(
    ticker="EXAMPLE-25-T", side="yes", action="buy",
    count=10, yes_price="0.65",
    extra_headers={"Idempotency-Key": str(uuid.uuid4())},
)
```

Client-wide defaults still go via `KalshiConfig.extra_headers`; per-call
values merge on top (later wins).

### Additive: pluggable REST JSON loader

Per #260, `KalshiConfig.rest_json_loads` mirrors the existing
`ws_json_loads` (v2.4 `#209`). Set to `orjson.loads` for ~2–3× faster
list-endpoint parsing:

```python
import orjson
from kalshi import KalshiClient, KalshiConfig

config = KalshiConfig(rest_json_loads=orjson.loads)
client = KalshiClient(auth=..., config=config)
```

Default (`None`) falls back to `httpx.Response.json()`.

### Additive: unknown-host default-fail

Per #250, `KalshiConfig` now rejects `base_url` / `ws_base_url` hosts
outside `{api.elections.kalshi.com, demo-api.kalshi.co, localhost,
127.0.0.1, ::1}` by default. A typo like `kalsi.com` no longer silently
delivers signed requests to the wrong endpoint. Opt-in for mock servers
or custom proxies:

```python
# Either:
config = KalshiConfig(
    base_url="https://my-mock-server.test/trade-api/v2",
    allow_unknown_host=True,
)

# Or process-wide:
os.environ["KALSHI_ALLOW_UNKNOWN_HOST"] = "1"
```

### Additive: split REST/WS environment guard

Per #239, `KalshiClient(demo=True, base_url="https://api.elections.kalshi.com/...")`
(or the env-var equivalent) now raises `ValueError` at construction
instead of silently producing a config where REST hits production but
WS hits demo. If you genuinely need mixed environments, build the
`KalshiConfig` explicitly with both `base_url` and `ws_base_url`
pointing at hosts in the same environment.

### Additive: new typed exceptions

- `KalshiNetworkError` (#240) — exhausted retries on `httpx.ConnectError`,
  `NetworkError`, `RemoteProtocolError`, `ReadError`, or `WriteError`.
  Transport now retries these on idempotent verbs (GET/HEAD/OPTIONS) and
  on `ConnectError` for POST/DELETE (request never reached the wire).
- `KalshiOrderbookUnavailableError` (#257) — raised by the high-level
  `subscribe_book` iterator when the local book is missing between a
  gap-recovery teardown and the new snapshot. Catch and reattach to a
  fresh iterator:

  ```python
  while True:
      try:
          async for book in session.subscribe_book(ticker="EXAMPLE-25-T"):
              ...
      except KalshiOrderbookUnavailableError:
          # gap recovery in flight; reattach
          continue
  ```

- `KalshiBackpressureError` now carries `channel`, `sid`, `client_id`,
  and `maxsize` (#256). Consumers iterating multiple subscriptions can
  route the error by channel:

  ```python
  try:
      async for msg in session.subscribe_ticker(tickers=[...]):
          ...
  except KalshiBackpressureError as e:
      logger.warning("backpressure on %s (sid=%s)", e.channel, e.sid)
  ```

### Additive: `from_env(**kwargs: Unpack[ClientInitKwargs])`

Per #266, `KalshiClient.from_env` and `AsyncKalshiClient.from_env` now
expose a `typing.Unpack`-driven TypedDict signature so typos like
`time_out=10` trip mypy strict at the call site. No runtime change.

### Additive: `portfolio.positions_all()` / `fcm.positions_all()`

Per #269, both endpoints now ship cursor-iterating `*_all()` helpers
matching the rest of the SDK's pagination convention.

```python
for position in client.portfolio.positions_all():
    print(position.ticker, position.position)
```

### Multivariate endpoints emit `DeprecationWarning`

Per #269, `multivariate.lookup_tickers` and `multivariate.create_market`
(sync + async) carry `@typing_extensions.deprecated` decorators citing
the spec's "should not be used for new integrations" guidance. Use RFQs
instead. The endpoints still work; calls just emit a `DeprecationWarning`
on first use.

(`multivariate.lookup_history`, also deprecated here in #269, was removed
entirely in 6.0.0 — see the [v5 → v6.0.0](#v5-v600) section above.)

### `orders.list(event_ticker=...)` accepts lists

Per #269, `event_ticker` accepts `list[str] | str | None` on
`OrdersResource.list` and `list_all` (sync + async). Lists are joined
via `_join_tickers` with a spec-enforced `max_items=10`:

```python
for order in client.orders.list_all(event_ticker=["EV1", "EV2", "EV3"]):
    ...
```

### Observable but not breaking

- WS recv loop no longer allocates a `Task` + `shield` per frame (#245).
  Pause/resume now uses a cooperative `Event` + 50 ms poll; lower
  allocation pressure on high-volume markets.
- `subscribe_book` iterator caches the materialized `Orderbook` per
  ticker (#244); consecutive `mgr.get(ticker)` calls without intervening
  mutations return the same object identity.
- `OrderbookSnapshotPayload.yes` and `.no` are now `dict[Decimal, Decimal]`
  rather than `list[tuple[Decimal, Decimal]]` (#263). External consumers
  reading these fields directly will see a dict; iterate `.items()` if
  you need the prior tuple shape.
- `OrderbookSnapshotPayload.yes`/`.no` are now required (no `default=[]`);
  a malformed snapshot raises `ValidationError` (#268).
- `Decimal('NaN')` / `Decimal('Infinity')` rejected at parse and at
  serialize (#270); construct fresh values from finite inputs.
- WS `user_orders` and `communications` payloads now use
  `pydantic.AwareDatetime` (#270); naive RFC3339 strings raise
  `ValidationError` (REST was already strict per v2.4 #234).
- V1 `CreateOrderRequest` enum-style fields (`side`, `action`,
  `time_in_force`, `self_trade_prevention_type`) are now
  `Literal[...]` typed (#270); typos fail at construction instead of
  server-side.
- `Retry-After: -5` and `Retry-After: <past HTTP-date>` now both clamp
  to 0.0 (retry immediately) — the delta-seconds form previously fell
  back to computed backoff while the date form already clamped (#267).

## v2.3 → v2.4

v2.4 ships one user-visible breaking change — the V1 batch order
return shape (#194) — plus several additive surfaces: new typed
exceptions, passphrase-protected PEMs, opt-in HTTP/2, and per-request
`extra_headers`.

### Breaking: `batch_create` / `batch_cancel` return typed envelopes

Per #194, `orders.batch_create` previously returned `list[Order]` and
crashed with `ValidationError` on the first failed leg;
`orders.batch_cancel` returned `None` and discarded the per-leg
`reduced_by_fp` counts the server actually sent. Both now return
typed envelopes matching the V2 family — pair legs by
`client_order_id` and check `entry.error` per leg.

```python
# v2.3
orders: list[Order] = client.orders.batch_create(request=req)
for order in orders:
    print(order.order_id, order.status)

# v2.4
from kalshi.models import BatchCreateOrdersResponse

resp: BatchCreateOrdersResponse = client.orders.batch_create(request=req)
for entry in resp.orders:
    if entry.error is not None:
        logger.error("leg %s failed: %s", entry.client_order_id, entry.error)
        continue
    assert entry.order is not None
    print(entry.order.order_id, entry.order.status)
```

`batch_cancel` follows the same shape: each `resp.orders[i]` exposes
`order_id`, `reduced_by_fp` (the count of contracts that actually
canceled — load-bearing for risk reconciliation), plus
`order`/`error` for the affected leg.

### New typed exceptions

Per #201 / #204 / #226, three new subclasses of `KalshiError` join
the existing hierarchy:

- `KalshiConflictError` — HTTP **409** (e.g. duplicate
  `client_order_id`).
- `KalshiTimeoutError` — `httpx.TimeoutException` at the request
  level. **The server may or may not have processed the request.**
  POST/DELETE still never retry on this; reconcile by querying with
  the original `client_order_id` before issuing a fresh attempt.
- `KalshiPoolExhaustedError` — `httpx.PoolTimeout`. The request
  never reached the wire and IS safe to retry on POST/DELETE.

422 now also routes to `KalshiValidationError` (was 400 only).

```python
from kalshi import (
    KalshiConflictError,
    KalshiTimeoutError,
    KalshiPoolExhaustedError,
)

try:
    client.orders.create(request=req)
except KalshiConflictError:
    existing = client.orders.get_by_client_order_id(req.client_order_id)
except KalshiPoolExhaustedError:
    # never touched the wire — safe to retry
    client.orders.create(request=req)
except KalshiTimeoutError:
    # reconcile before retrying — server may have committed
    existing = client.orders.get_by_client_order_id(req.client_order_id)
```

### Passphrase-protected PEMs

Per #217 / #233, `KalshiAuth.from_pem`, `from_key_path`, `from_env`,
and `try_from_env` accept a `password=` kwarg (`str` / `bytes` / a
zero-arg callable returning either — the callable form lets you
defer fetching the secret from a vault until load-time). `from_env`
/ `try_from_env` also read `KALSHI_PRIVATE_KEY_PASSPHRASE` from the
environment; the explicit `password=` wins when both are set.
Encrypted PEMs no longer have to be stripped to disk first.

```python
auth = KalshiAuth.from_key_path(
    "your-key-id",
    "~/.kalshi/private_key.pem",
    password=lambda: vault.get_secret("kalshi-pem-pass"),
)
```

### Opt-in HTTP/2

Per #233, `KalshiConfig(http2=True)` enables HTTP/2 on the REST
client (off by default for compat). The `h2` dependency is not
installed by default; `KalshiConfig.__post_init__` fail-fasts with a
clear message when `http2=True` is set without it:

```bash
pip install 'kalshi-sdk[http2]'
```

```python
config = KalshiConfig(http2=True)
client = KalshiClient(auth=auth, config=config)
```

### Per-request `extra_headers` (transport-only, for now)

Per #220, `KalshiConfig.extra_headers` sets client-wide default
headers, and `SyncTransport.request(..., extra_headers=...)` /
`AsyncTransport.request(..., extra_headers=...)` merge per-call
overrides on top. `KALSHI-ACCESS-*` signing headers always win, so
callers cannot forge them via this surface. Resource-method plumbing
— so e.g. `client.orders.create(..., extra_headers=...)` works
directly — is tracked in #253 and not yet shipped in v2.4; only the
transport-level entry point is public.

---

## v2.2 → v2.3

v2.3 is additive on the REST surface and **soft-breaking on the WebSocket
surface** in one place: `KalshiWebSocket.run_forever()` no longer returns
silently when nothing has been subscribed. Everything else is opt-in.

### `run_forever()` requires an active subscription

Per closed #175 / #185, `KalshiWebSocket.run_forever()` now raises
`KalshiSubscriptionError` at the call site when no `subscribe_*` call has
landed on the session. The previous silent no-op masked a common mistake —
registering an `@ws.on(channel)` callback without subscribing, then
wondering why no frames arrived (the server only sends frames for channels
the client explicitly subscribed to).

```python
# v2.2 — silently returned, recv loop never ran
async with ws.connect() as session:
    await session.run_forever()

# v2.3 — wrap a subscribe_* call before run_forever()
async with ws.connect() as session:
    await session.subscribe_ticker(tickers=["EXAMPLE-25-T"])
    await session.run_forever()
```

No production usage of the silent shape is known; the foot-gun was the
bug.

### Cooperative shutdown via `run_forever(stop_event=...)`

Per closed #177 / #186, `run_forever()` now accepts an optional
`stop_event: asyncio.Event | None = None`. When set, the recv loop
closes the connection and exits cleanly without raising `CancelledError`
— typically wired to `SIGINT` so Ctrl+C drains in-flight dispatches:

```python
import asyncio
import signal

stop = asyncio.Event()
asyncio.get_running_loop().add_signal_handler(signal.SIGINT, stop.set)

async with ws.connect() as session:
    await session.subscribe_ticker(tickers=["EXAMPLE-25-T"])
    await session.run_forever(stop_event=stop)
```

Omitting `stop_event` preserves v2.2 behavior — external cancellation
still propagates.

### WS resubscribe-window frame stashing

Per #176, the reconnect path used to silently drop data frames that
arrived between the moment `SubscriptionManager` cleared its
`sid → client_id` map and the moment the new sids landed in the
subscribe-response handler. Under burst reconnects on high-volume
channels (`ticker`, `trade`, `fill`), this lost tens of messages per
reconnect.

`SubscriptionManager` now stashes those frames in a per-sid bounded
`collections.deque(maxlen=stash_maxlen)` (default 1000 per sid). After
`resubscribe_all` completes, the stash is drained through the normal
dispatch path so seq trackers advance, orderbook state applies, and
iterator consumers receive the frames in arrival order. No API change —
behavior change only.

### Async RSA-PSS sign offload — `KalshiAuth.close()` for standalone users

Per #178, `KalshiAuth.sign_request_async()` now routes the RSA-PSS sign
through a dedicated `ThreadPoolExecutor(max_workers=2)` lazy-initialised
on first use, so signs don't queue behind `getaddrinfo` / file I/O / other
`to_thread()` work during WS reconnect storms.

If you use `KalshiAuth` **through** `KalshiClient` / `AsyncKalshiClient`,
`client.close()` already tears the executor down for you and no migration
is required. If you instantiate `KalshiAuth` **standalone** (e.g. signing
requests through a custom transport), call `auth.close()` to release the
executor:

```python
from kalshi import KalshiAuth

auth = KalshiAuth.from_key_path("your-key-id", "~/.kalshi/private_key.pem")
try:
    headers = await auth.sign_request_async("GET", "/trade-api/v2/markets")
    ...
finally:
    auth.close()
```

---

## v2.1 → v2.2

v2.2 is **soft-breaking at the response-parse boundary only** (per
#157 / #172). The wire format is unchanged. The behavior change: server
omission of a previously-optional spec-required field now raises
`pydantic.ValidationError` at parse time, instead of silently producing
`field=None` and pushing the surprise to a downstream `NoneType`
attribute access.

### What changed

226 fields across REST models, WS payloads, and helper classes flipped
from `Optional[X] = None` to required, matching what the OpenAPI /
AsyncAPI specs already declared.

Affected response model categories include `Market`, `Order`, `Fill`,
`Event`, `EventMetadata`, `Settlement`, `Trade`, `IncentiveProgram`,
`RFQ`, `Quote`, `OrderGroup` plus its three group-response shapes, and
11 WebSocket payloads — including the new `*_ts_ms` millisecond
timestamps and the `outcome_side` / `book_side` direction encoding the
server already emits. See `CHANGELOG.md` for the full per-model
breakdown.

### Recovery

If you parse live responses and previously branched on `field is None`
for an optional you read from the SDK, you may now hit
`pydantic.ValidationError` at the parse site when the server omits the
field on a malformed event. Wrap the call site:

```python
from pydantic import ValidationError

try:
    market = client.markets.get(ticker)
except ValidationError as exc:
    logger.warning("skipping malformed market %s: %s", ticker, exc)
    continue
```

The vast majority of fields were already populated in practice — only
models with legitimate live-server omission gaps need the try/except.
Two known cases (`Event.product_metadata`, `EventMetadata.market_details`)
ship in v2.3 with `server_omits_despite_required` exclusions baked in
and need no caller action.

### `extra="allow"` everywhere

All WS envelope and helper classes (and the five REST helpers from the
v2.0 sweep — `Page`, `Orderbook`, `OrderbookLevel`, `BidAskDistribution`,
`PriceDistribution`) now uniformly use `model_config = ConfigDict(extra="allow")`.
Additive server fields no longer raise; they land on
`__pydantic_extra__` and round-trip through `model_dump()`.

---

## v2.0 → v2.1

v2.1 syncs the SDK to OpenAPI spec v3.18.0. It's **additive at the resource
surface** — eight new endpoints, several new optional kwargs on existing
methods, and one soft-breaking model-construction change called out below.
Code that only consumes the SDK's responses needs no edits; code that
constructs models directly in tests/mocks needs one small update.

### `Balance.balance_dollars` — required, soft-breaking at construction

Spec v3.18.0 adds `balance_dollars: FixedPointDollars` to
`GetBalanceResponse` as a required field. The server now guarantees it, so
callers parsing API responses (`client.portfolio.balance()`) are unaffected.
**But** any code that builds `Balance(...)` directly — typically test mocks
— will hit `ValidationError` until it adds the field.

```python
# v2.0 — broken in v2.1
Balance(balance=50000, portfolio_value=75000, updated_ts=ts)

# v2.1
Balance(
    balance=50000,
    balance_dollars=Decimal("500.00"),   # new required field
    portfolio_value=75000,
    updated_ts=ts,
)
```

The accompanying optional `balance_breakdown: list[IndexedBalance] | None`
splits the total across exchange shards when present. `IndexedBalance.balance`
is `DollarDecimal` (matching `balance_dollars` units), not cents — same
field name as `Balance.balance` but a different type. Be deliberate when
reading from `balance.balance_breakdown[i].balance`.

### V2 event-market orders

Six new methods on `OrdersResource` / `AsyncOrdersResource` hit the new
`/portfolio/events/orders/*` paths:

- `create_v2(*, request: CreateOrderV2Request)`
- `cancel_v2(order_id, *, subaccount, exchange_index)`
- `amend_v2(order_id, *, request: AmendOrderV2Request, subaccount)`
- `decrease_v2(order_id, *, request: DecreaseOrderV2Request, subaccount)`
- `batch_create_v2(*, request: BatchCreateOrdersV2Request)`
- `batch_cancel_v2(*, request: BatchCancelOrdersV2Request)`

Legacy `/portfolio/orders` keeps working and will be deprecated no earlier
than May 6, 2026. No migration is required to stay on v1 paths. New
event-market trading should target the V2 family for the cleaner shape
(single `bid`/`ask` side, single `price` field, explicit idempotency).

Two important differences from V1:

1. **`client_order_id` is required** on `CreateOrderV2Request` and acts as
   the server-side idempotency key. Reusing a value returns the original
   order rather than placing a new one. Use a fresh UUID4 per call.
2. **`side` uses `BookSideLiteral` (`"bid"` / `"ask"`)**, not V1's
   `SideLiteral` (`"yes"` / `"no"`).

### Spec-driven asymmetry on V2 amend/decrease

`amend_v2` and `decrease_v2` accept `subaccount` as a **resource-method
kwarg** (query param on the wire) but read `exchange_index` from the
**request body**. `cancel_v2` differs again — both are query params there,
because that endpoint has no body. This mirrors the spec exactly:

```python
client.orders.amend_v2(
    "ord-1",
    subaccount=3,                          # query param
    request=AmendOrderV2Request(
        ticker="EVENT-MKT", side="bid",
        price=Decimal("0.55"),
        count=Decimal("10"),
        exchange_index=0,                  # body field
    ),
)
```

### New optional kwargs on existing endpoints

All additive — existing call sites keep working:

- `orders.cancel(*, exchange_index)`, `order_groups.delete(*, exchange_index)`
- `communications.list_rfqs(*, user_filter)`, `communications.list_all_rfqs(*, user_filter)`
- `communications.list_quotes(*, user_filter, rfq_user_filter)`, `communications.list_all_quotes(*, user_filter, rfq_user_filter)`. `user_filter="self"` and `rfq_user_filter="self"` are now standalone satisfiers for the server-side filter requirement (previously only `quote_creator_user_id` / `rfq_creator_user_id` worked).
- `incentive_programs.list(*, incentive_description)` and the `list_all` variant.
- `CreateQuoteRequest.post_only` — pass `post_only=True` to `create_quote()`.
- `exchange_index` on order/amend/decrease/batch-cancel request models.

### New endpoints (additive)

- `portfolio.deposits()` / `portfolio.deposits_all()` — deposit history.
- `portfolio.withdrawals()` / `portfolio.withdrawals_all()` — withdrawal history.
- `account.endpoint_costs()` — token costs for endpoints whose cost differs
  from the default.

### New public types

Added to `kalshi.*` and `kalshi.models.*`:

- Literals: `BookSideLiteral`, `UserFilterLiteral`, `PaymentStatusLiteral`, `PaymentTypeLiteral`.
- Models: `Deposit`, `Withdrawal`, `IndexedBalance`, `AccountEndpointCosts`, `EndpointTokenCost`, and the V2 request/response family.

---

## v1.x → v2.0

v2.0 is mostly additive (new `max_pages` kwarg, `KalshiConfig.http2`/`limits`,
`RateLimit` model export). There are **3 deliberate breaking changes** —
all on the response-model surface, all driven by spec-or-server reality.
Migrate by find/replace.

### `Order.type` → `Order.order_type`

Renamed to avoid shadowing the Python builtin (matching the existing
`milestone_type` / `target_type` / `incentive_type` pattern). Wire format
is unchanged — incoming JSON `type` still populates the field via
`validation_alias`.

```python
# v1
order = client.portfolio.orders.get(order_id="...")
print(order.type)        # → AttributeError after upgrade

# v2
print(order.order_type)  # str | None — "limit" or "market"
```

### `AccountApiLimits.read_limit` / `.write_limit` removed

Replaced with `AccountApiLimits.read` / `.write` of type `RateLimit`. The
published OpenAPI spec declares the limits as ints; the live server
actually returns nested token buckets. v2 matches the server. The old int
fields never worked against the live API.

```python
# v1
limits = client.account.limits()
limits.read_limit   # → AttributeError after upgrade

# v2
limits.read.bucket_capacity   # int
limits.read.refill_rate       # int
# new model exposed: kalshi.RateLimit
```

### Response-model count/size/volume fields retyped

Fields like `Market.volume`, `Fill.count`, `Trade.count`,
`MarketPosition.position` were annotated `DollarDecimal` but semantically
represent integer counts. v2 retypes them to `FixedPointCount`. Runtime
values still come back as `Decimal` — only the type annotation changed,
so `mypy --strict` users may need to update narrow assertions.
`isinstance(x, Decimal)` checks remain valid.

### Non-breaking but worth knowing

- **`*_all()` is now unbounded by default.** The previous internal 1000-page
  cap silently truncated callers iterating beyond ~100k items. Cursor-repeat
  guard is still the safety net against server bugs. Pass `max_pages=N` for
  an explicit cap.
- **Response models uniformly use `extra="allow"`.** 5 models (`Page`,
  `Orderbook`, `OrderbookLevel`, `BidAskDistribution`, `PriceDistribution`)
  that previously silently dropped unknown fields now preserve them on
  `__pydantic_extra__`.
- **WS callbacks no longer suppress queue delivery.** Holding both an `@on()`
  callback and an iterator on the same channel now sees both fire. A
  WARNING logs at register-time so the change is visible to upgraders.

See [CHANGELOG.md](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/CHANGELOG.md)
for the full list including the WS recv-loop overhaul (5 reconnect races
fixed), URL/trade-data log-leak scrubs, and spec-sync supply-chain
hardening.

---

## From `kalshi_python_async`

If you're coming from the predecessor community client `kalshi_python_async`,
this page summarizes the
v1 SDK differences you'll hit. **If you don't recognize that name, you can
skip this page** — there's nothing here that applies to a greenfield
project on `kalshi-sdk`.

The v1 SDK is a clean rewrite rather than an in-place upgrade, so the move
is closer to a port than a patch. Concrete details below are sourced from
the current SDK; predecessor specifics are documented where they exist
in-tree and called out as **unverified** where they don't.

## Why migrate

- **One transport, two surfaces.** v1 ships hand-crafted sync (`KalshiClient`)
  and async (`AsyncKalshiClient`) clients sharing one transport
  implementation — neither sync-wraps-async nor vice versa.
- **Spec-aligned with drift guards.** Models are generated from the Kalshi
  OpenAPI/AsyncAPI specs, and contract tests fail CI when query, request
  body, or WebSocket payload shapes drift from the spec.
- **`mypy --strict` clean**, `py.typed` shipped, Pydantic v2 models
  end-to-end.
- **Safe-by-default retries.** Only `GET`/`HEAD`/`OPTIONS` retry on transient
  errors; `POST`/`DELETE` never do.
- **v1 stability promise.** Public API is stable as of `1.0.0`; breaking
  changes go through a deprecation cycle.

## Imports

Top-level imports come from `kalshi`:

```python
# v1
from kalshi import (
    KalshiClient,
    AsyncKalshiClient,
    KalshiAuth,
    KalshiConfig,
    CreateOrderRequest,
    Market, Order, Page,
    SideLiteral, ActionLiteral, TimeInForceLiteral,
    KalshiError, KalshiNotFoundError, KalshiRateLimitError,
)
```

WebSocket primitives live in `kalshi.ws`:

```python
from kalshi.ws import KalshiWebSocket, OverflowStrategy, ConnectionState
```

The full export list is in
[`kalshi/__init__.py`](https://github.com/TexasCoding/kalshi-python-sdk/blob/main/kalshi/__init__.py).

If you previously imported `from kalshi_python_async import ...`, swap to
`from kalshi import ...`. The exact symbol-by-symbol map is **unverified**
— the v1 surface is not a renaming of an upstream surface, it's a new one
that happens to talk to the same API.

## Auth and client construction

```python
# v1 — three equivalent paths
from kalshi import KalshiClient, KalshiAuth

# A) key file path
client = KalshiClient(
    key_id="your-key-id",
    private_key_path="~/.kalshi/private_key.pem",
    demo=True,
)

# B) environment
#   KALSHI_KEY_ID, KALSHI_PRIVATE_KEY_PATH | KALSHI_PRIVATE_KEY,
#   KALSHI_DEMO=true, KALSHI_API_BASE_URL=...
client = KalshiClient.from_env()

# C) pre-built KalshiAuth (useful for sharing auth with the WebSocket client)
auth = KalshiAuth.from_key_path("your-key-id", "~/.kalshi/private_key.pem")
client = KalshiClient(auth=auth, demo=True)
```

Calling private endpoints on an unauthenticated client raises
`AuthRequiredError` before any network call. Public endpoints (market
data, events, exchange status) work on an unauthenticated client.

`demo=True` selects the sandbox base URL and WebSocket URL together. There
is no separate "base URL switch" you have to remember.

The signing scheme — RSA-PSS / SHA256 / MGF1(SHA256) / salt = digest length —
is identical to what every other Kalshi client uses. You don't touch it
yourself; pass the PEM and key id and you're done.

## Resource calls

The v1 resource methods accept two equivalent input styles:

```python
# kwargs (default for most call sites)
order = client.orders.create(
    ticker="KXPRES-24-DJT",
    side="yes",
    action="buy",
    count=10,
    yes_price="0.65",
    time_in_force="good_till_canceled",
)

# request model
from kalshi import CreateOrderRequest
order = client.orders.create(request=CreateOrderRequest(
    ticker="KXPRES-24-DJT",
    side="yes",
    action="buy",
    count=10,
    yes_price="0.65",
    time_in_force="good_till_canceled",
))
```

Mixing the two raises `TypeError`. Phantom kwargs (anything not on the
underlying request model) also raise `TypeError`. Enum-valued kwargs use
`Literal[...]` types (`SideLiteral`, `ActionLiteral`,
`TimeInForceLiteral`, etc.) so typos fail mypy and IDEs auto-complete the
values.

Prices and counts are decimal dollars. Pass `Decimal`, `int`, or `str`;
never `float`. Internally the SDK uses `Decimal` via the custom
`DollarDecimal` Pydantic type.

The async surface mirrors sync method-for-method on `AsyncKalshiClient`.

## WebSockets

The WebSocket client is async-only:

```python
import asyncio
from kalshi import KalshiAuth, KalshiConfig
from kalshi.ws import KalshiWebSocket

async def main() -> None:
    auth = KalshiAuth.from_key_path("your-key-id", "~/.kalshi/private_key.pem")
    config = KalshiConfig.demo()

    ws = KalshiWebSocket(auth=auth, config=config)
    async with ws.connect() as session:
        stream = await session.subscribe_orderbook_delta(tickers=["KXPRES-24-DJT"])
        async for msg in stream:
            print(msg)

asyncio.run(main())
```

If your predecessor used a sync-style streaming API, wrap the entry point
in `asyncio.run(...)`. The Kalshi feed is push-driven; a real sync API would
have to spawn a thread and bridge a queue, which is exactly what we don't
want to ship as a public surface. See
[WebSocket Streaming](websockets.md) for the full guide, including
per-channel subscribe methods, sequence-gap recovery, backpressure
strategies, and automatic reconnection semantics.

## Errors

The exception hierarchy is rooted at `KalshiError`. Subclasses correspond
to HTTP statuses (`KalshiAuthError` for 401/403, `KalshiNotFoundError` for
404, `KalshiValidationError` for 400, `KalshiRateLimitError` for 429,
`KalshiServerError` for 5xx) plus WebSocket-specific siblings
(`KalshiConnectionError`, `KalshiSubscriptionError`, etc.). See
[Error Handling](errors.md) for the full tree and the status-to-exception
map.

If your predecessor raised string-based errors or untyped exceptions, the
common rewrite is to catch the specific class:

```python
# Before (predecessor — unverified shape):
# try:
#     market = api.get_market(ticker)
# except Exception as e:
#     ...

# After
from kalshi import KalshiNotFoundError, KalshiRateLimitError

try:
    market = client.markets.get(ticker)
except KalshiNotFoundError:
    ...
except KalshiRateLimitError as e:
    backoff_seconds = e.retry_after
```

## Pagination

`Page[T]` replaces ad-hoc list responses:

```python
page = client.markets.list(status="open", limit=200)

for market in page:        # iterable over .items
    ...
len(page)                  # items on this page
page.cursor                # next-page cursor (None on the last page)
page.has_next              # bool

# pandas / polars (optional extras)
df = page.to_dataframe()
df = page.to_polars()
```

For multi-page traversal:

```python
# Sync — Iterator[T]
for market in client.markets.list_all(status="open"):
    ...

# Async — AsyncIterator[T], works directly with `async for`
async for market in async_client.markets.list_all(status="open"):
    ...
```

`list_all()` is unbounded by default — it walks cursors until the server
returns no more pages. Pass `max_pages=N` for an explicit cap; passing
`max_pages=0` raises `ValueError`. The cursor-repeat detector still raises
`KalshiError` if the server hands back a duplicate cursor. See
[Pagination](pagination.md) for the canonical contract.

## Still missing?

If you're porting a specific predecessor call and can't find the v1
equivalent, the [API Reference](reference.md) is the auto-generated
ground truth. Open an issue on
[`TexasCoding/kalshi-python-sdk`](https://github.com/TexasCoding/kalshi-python-sdk/issues)
with the predecessor call and the closest match you found and we'll either
fill in the gap or point to the right method.
