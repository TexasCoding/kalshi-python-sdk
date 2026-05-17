# Wave 5 Audit N — Architecture & Code Quality

Reviewed at commit `0a3fb23580b3497c1e004d1b79f783b2dda38e24` against the v1.1.0 release.

## Summary

The SDK has a clear and consistent layered architecture (transport → resource base → per-resource modules → typed models) and the discipline around contract testing, request-body model construction, and price-decimal type handling is unusually good for a Python SDK. The dual sync/async strategy is executed cleanly with shared pure helpers. The largest weaknesses are in three areas: (1) a top-level `kalshi.__all__` that is silently out of sync with `kalshi.models.__all__` so 23 documented response classes are not importable from the package root, (2) sloppy/aspirational type annotations on count/size fields (declared as `DollarDecimal` but commented as `FixedPointCount`) — semantically misleading even though the parser dedup makes it work, and (3) a few real WebSocket-loop concerns (JSON parsed twice, orderbook messages validated twice, private-method reach-through from `KalshiWebSocket` into `ConnectionManager`, broad `except Exception: continue` in the recv loop). None are critical for v1.1.0 callers but several represent debt worth picking up before v1.2.

## Findings

### F-N-01 — Public-API contract broken: 23 model classes missing from top-level `__all__` (severity: high)
**File:** `kalshi/__init__.py:116-225`
**Issue:** `kalshi/models/__init__.py` exports 23 user-facing response/data classes that are NOT re-exported from the package root: `Event`, `EventMetadata`, `MarketMetadata`, `SettlementSource`, `Balance`, `MarketPosition`, `EventPosition`, `PositionsResponse`, `Settlement`, `Trade`, `HistoricalCutoff`, `Announcement`, `DailySchedule`, `Schedule`, `WeeklySchedule`, `ExchangeStatus`, `MaintenanceWindow`, `ForecastPercentilesPoint`, `PercentilePoint`, `AssociatedEvent`, `CreateMarketResponse`, `LookupPoint`, `LookupTickersResponse`. Several of these are return types of public client methods (e.g. `client.exchange.status() -> ExchangeStatus`, `client.markets.list_trades_all() -> Iterator[Trade]`, `client.portfolio.balance() -> Balance`, `client.events.get() -> Event`) so users typing those returns must dig into the `kalshi.models.*` submodules. Empirically confirmed: `from kalshi import Trade` raises `ImportError`, as do `Event` and `Balance`.
**Evidence:** Compared `set(kalshi.__all__)` vs `set(kalshi.models.__all__)`; the diff above lists the 23 missing names. `ImportError: cannot import name 'Trade' from 'kalshi'`.
**Suggested fix:** Either re-export the missing names from `kalshi/__init__.py` (preferred — minimal, additive, no breakage), or document publicly that response models live under `kalshi.models`. The first option matches what `kalshi.models.__all__` is already trying to assert.

### F-N-02 — Volume/size/count fields annotated as `DollarDecimal` but mean `FixedPointCount` (severity: medium)
**File:** `kalshi/models/markets.py:84-111`, `kalshi/models/markets.py:220-227`, `kalshi/models/orders.py:111-114`
**Issue:** `Market.yes_bid_size`, `yes_ask_size`, `no_bid_size`, `no_ask_size`, `volume`, `volume_24h`, `open_interest`, plus `Candlestick.volume`, `Candlestick.open_interest`, and `Fill.count` are all declared as `DollarDecimal` even though their `validation_alias` is the `_fp` (FixedPointCount) wire name and the surrounding comments explicitly say "FixedPointCount". Today this works only because `_to_decimal_dollars` and `_to_decimal_fp` in `kalshi/types.py:13-27,47-60` are byte-identical implementations. If one parser ever diverges (e.g. to apply a scale factor or different precision rule for one of the families) every size/volume field silently breaks. Beyond the latent bug, the wrong type also misleads anyone reading the model — `DollarDecimal` strongly implies a price.
**Evidence:** `kalshi/models/markets.py:83` comment: `# Size/volume fields (FixedPointCount)` immediately above `yes_bid_size: DollarDecimal | None = ...`. `Fill.count: DollarDecimal` at `kalshi/models/orders.py:111` with alias `count_fp`. `_to_decimal_dollars` (types.py:13) and `_to_decimal_fp` (types.py:47) are duplicate definitions.
**Suggested fix:** Switch the size/volume/count fields to `FixedPointCount`. Either consolidate the two parser functions into one shared helper (since they are identical today) or leave them as named identity functions so future divergence is per-family.

### F-N-03 — `Order.type` field is dead and contradicts the spec (severity: medium)
**File:** `kalshi/models/orders.py:47`
**Issue:** `Order.type: str | None = None` is a leftover from the pre-v0.8.0 `CreateOrderRequest.type` field that v0.8.0 removed because it was never in the OpenAPI spec. The response `Order` model still carries it, which (a) re-exposes the removed concept, (b) shadows the Python `type` builtin in instances, and (c) lets the spec-drift contract test pass only because `Order` has `extra="allow"`. Either Kalshi actually returns `type` on `Order` (in which case it should be in the spec) or it doesn't (in which case the field is dead and `extra="allow"` would catch any surprise return value anyway).
**Evidence:** `kalshi/models/orders.py:47` — `type: str | None = None` inside `class Order`. The matching cleanup in `CreateOrderRequest` (line 144-147 docstring) explicitly removed `type` from the request side; only the response side still has it.
**Suggested fix:** Verify against demo whether the API ever returns a `type` field on `/portfolio/orders` responses. If not, remove the field. If it does return one, either keep it (and add it to the OpenAPI spec drift exclusions explicitly) or rely on `extra="allow"` so callers can still reach it via `order.model_extra`.

### F-N-04 — `OrderbookManager.apply_delta` does O(n) linear scan per price level (severity: medium)
**File:** `kalshi/ws/orderbook.py:73-94`
**Issue:** Every orderbook delta does a linear `for i, level in enumerate(levels): if level.price == price` scan over the side's levels, then on insert calls `levels.sort(key=lambda lv: lv.price)`. For a side with N levels each delta is O(N) for the lookup and O(N log N) for the insert. Active markets routinely have 50-100 levels per side and deltas arrive multiple times per second per subscription. The data structure should be price-indexed.
**Evidence:** `kalshi/ws/orderbook.py:75-94` — explicit `existing_idx = -1; for i, level in enumerate(levels): if level.price == price: existing_idx = i; break` followed by `levels.sort(...)` on insert.
**Suggested fix:** Maintain levels as `dict[Decimal, Decimal]` (price → quantity) internally and materialize the sorted `list[OrderbookLevel]` lazily in `get()`, or use `sortedcontainers.SortedDict`. Reduces deltas to O(log N) (insert) and O(1) (update/remove), and the materialized snapshot is still O(N) but only happens on observed read.

### F-N-05 — WebSocket recv loop parses JSON twice and re-validates orderbook messages (severity: medium)
**File:** `kalshi/ws/client.py:144-179`, `kalshi/ws/dispatch.py:68-95`
**Issue:** In `_recv_loop`, the raw frame is `json.loads`-parsed once at line 147 to inspect `sid`/`seq`/`type` for sequence tracking and orderbook state update, then handed to `await self._dispatcher.dispatch(raw)` at line 179, which immediately calls `json.loads(raw)` again at `dispatch.py:71`. For orderbook snapshots/deltas the message is also Pydantic-validated twice: once at `client.py:171-175` for `OrderbookManager`, and again at `dispatch.py:92` for queue routing. On a busy stream this is real cost (orderbook deltas can arrive 100s/sec on a watched market) and a maintenance hazard — two parsers can drift.
**Evidence:** `client.py:147 data = json.loads(raw)`; `client.py:171 snapshot = OrderbookSnapshotMessage.model_validate(data)`; `dispatch.py:71 data = json.loads(raw)`; `dispatch.py:92 parsed = model_cls.model_validate(data)`.
**Suggested fix:** Either (a) move sequence-tracking and orderbook-state update inside `MessageDispatcher.dispatch` so each frame is parsed and validated once, or (b) change the dispatcher signature to accept the pre-parsed `dict` from the recv loop. Option (a) keeps the loop simpler.

### F-N-06 — `KalshiWebSocket._recv_loop` reaches into a private method on `ConnectionManager` (severity: medium)
**File:** `kalshi/ws/client.py:196`
**Issue:** After successful reconnect, `KalshiWebSocket._recv_loop` calls `await self._connection._set_state(ConnectionState.STREAMING)`. `_set_state` is name-mangled-private on `ConnectionManager`; the rest of `ConnectionManager` treats state transitions as internal. This is a leaky abstraction — the client should not be poking the manager's state machine — and a refactor of `ConnectionManager` that renames or removes `_set_state` will silently break the streaming state report. The on_state_change callback would also fire from the "wrong" caller.
**Evidence:** `kalshi/ws/client.py:196` — `await self._connection._set_state(ConnectionState.STREAMING)`.
**Suggested fix:** Add a public `mark_streaming()` (or similar) on `ConnectionManager` that performs the same transition, or have `ConnectionManager.reconnect()` perform the `CONNECTED → STREAMING` transition itself after resubscribe so the client doesn't need to.

### F-N-07 — Recv loop swallows all non-`ConnectionClosed` exceptions with `continue` (severity: medium)
**File:** `kalshi/ws/client.py:204-207`
**Issue:** The recv loop's catch-all `except Exception as e: logger.warning("Error processing message: %s", e); continue` swallows every error short of `ConnectionClosed` — including `json.JSONDecodeError` (caught locally), Pydantic `ValidationError` from the dispatcher's typed parsing, `KalshiBackpressureError` from a full queue with `OverflowStrategy.ERROR`, and any bug in callback code. With backpressure-on-error this is exactly the "swallowed `KalshiBackpressureError`" issue already called out for the recv loop in audit-P, but the same swallowing also hides genuine programming errors. The dispatcher already logs parse/dispatch failures itself (`dispatch.py:88,94`), so this outer handler exists mostly to hide bugs.
**Evidence:** `kalshi/ws/client.py:204-207` — broad `except Exception` with `continue`.
**Suggested fix:** Narrow the outer catch to only the exceptions that genuinely should not kill the loop (e.g. `KalshiBackpressureError` if intentional, parse errors that the dispatcher should already have logged). Let everything else propagate or at minimum re-raise after logging.

### F-N-08 — Inconsistent bool query-param serialization across resources (severity: medium)
**File:** `kalshi/resources/events.py:29,30,49,139,233`, `kalshi/resources/series.py:30,31,43,101,191`
**Issue:** `kalshi/resources/_base.py:22-32` defines `_bool_param(value)` specifically to preserve the explicit-False case so callers can opt out when a server default flips. `markets.py` and `live_data.py` use it correctly. `events.py` and `series.py` instead use inline `"true" if include_volume else None` for every bool param — which is exactly the pattern the helper docstring warns against, and which makes `include_volume=False` (or `with_milestones=False`) indistinguishable from "not specified". For at least `include_volume` (which affects response shape and is volume-load-bearing) callers cannot turn it off explicitly.
**Evidence:** `events.py:29` — `with_nested_markets="true" if with_nested_markets else None`. `series.py:30` — `include_product_metadata="true" if include_product_metadata else None`. Compare `live_data.py:33` — `include_player_stats=_bool_param(include_player_stats)`. Helper docstring at `_base.py:23-29`.
**Suggested fix:** Replace the inline ternaries with `_bool_param(...)` everywhere. Mechanical and safe; the only behavioural difference is that `False` now becomes `"false"` instead of being dropped — which is the documented intent.

### F-N-09 — `_to_decimal_dollars` and `_to_decimal_fp` are byte-identical (severity: low)
**File:** `kalshi/types.py:13-27,47-60`
**Issue:** The two parser callables for `DollarDecimal` and `FixedPointCount` have identical bodies modulo docstring. This is fine as documentation-of-intent — keeping them separate makes the wire-shape vs. semantic split explicit at the type level — but it's at odds with F-N-02: today's parsers won't catch the wrong-family-annotated fields because they parse identically. Either commit to "they are intentionally distinct types with the same parser" or merge them.
**Evidence:** `kalshi/types.py:13-27` is identical to `kalshi/types.py:47-60` except for the function name and docstring.
**Suggested fix:** Add a `# Parsers are intentionally identical; keep the names distinct so we can diverge per-family later` comment, then have both `Annotated` aliases delegate to a single shared callable. Reduces a copy-paste hazard without losing the type distinction.

### F-N-10 — `AsyncKalshiClient.ws` creates a new `KalshiWebSocket` on every access; `KalshiClient` has no `.ws` at all (severity: low)
**File:** `kalshi/async_client.py:121-137`, `kalshi/client.py` (no `ws` property)
**Issue:** Every `client.ws` access on the async client constructs a fresh `KalshiWebSocket(auth=..., config=...)` (line 136-137). If a user writes `async with client.ws.connect() as a, client.ws.connect() as b:` (or just reuses `client.ws` twice in a script), they silently get two independent WS clients — not the singleton they probably expected from object-attribute syntax. The sync `KalshiClient` doesn't expose `ws` at all (consistent with KalshiWebSocket being async-only, but undocumented in the sync client; users who don't read async_client.py won't know where to find WS).
**Evidence:** `kalshi/async_client.py:122-137` — `@property def ws(self) -> KalshiWebSocket` does `from kalshi.ws.client import KalshiWebSocket as _KalshiWebSocket; return _KalshiWebSocket(auth=self._auth, config=self._config)` each call. No `ws` attribute on `KalshiClient` (`client.py`).
**Suggested fix:** Either cache the constructed `KalshiWebSocket` on the client (lazy-initialized in `__init__` and reused), or rename to `client.websocket()` so the construct-on-call behavior is explicit. Document on `KalshiClient` (sync) that WebSocket access requires the async client.
**Uncertainty:** This may be intentional so multiple concurrent sessions are possible from one client. If so, the property name is misleading; a `new_websocket()` factory method would communicate the semantics better.

### F-N-11 — `Fill.count` typed as `DollarDecimal` while sibling `Order.count` is `FixedPointCount` (severity: low)
**File:** `kalshi/models/orders.py:111`, `kalshi/models/orders.py:56`
**Issue:** Same-shape, same-meaning field annotated differently across sibling models. `Order.count: FixedPointCount` (line 56) is correct; `Fill.count: DollarDecimal` (line 111) is wrong, even though both wire-fields are `count_fp`. Subset of F-N-02 but worth calling out separately because it's a same-file inconsistency a maintainer is likely to copy-paste.
**Evidence:** `kalshi/models/orders.py:56,111` — both have `validation_alias=AliasChoices("count_fp", "count")` but different annotation.
**Suggested fix:** Change to `FixedPointCount` on `Fill.count`.

### F-N-12 — `OrderbookDeltaPayload.side` is `str` rather than `Literal["yes", "no"]` (severity: low)
**File:** `kalshi/ws/models/orderbook_delta.py:48`
**Issue:** The orderbook manager dispatches on `side == "yes"` vs anything-else (`orderbook.py:72 levels = book.yes if side == "yes" else book.no`). If a future spec or server bug emits a different value (e.g. `"YES"`, `"both"`) the message silently routes to the `no` side and corrupts the book without any validation error. Side values are an enum in every other place in the SDK (`SideLiteral = Literal["yes", "no"]` at `kalshi/models/orders.py:18`).
**Evidence:** `kalshi/ws/models/orderbook_delta.py:48` — `side: str`. `kalshi/ws/orderbook.py:72` — `levels = book.yes if side == "yes" else book.no`.
**Suggested fix:** Tighten to `side: Literal["yes", "no"]`. Pydantic will reject unknown values; the orderbook manager's truthiness fallback becomes safe.

### F-N-13 — Empty `kalshi/cli/` and `kalshi/cli/widgets/` directories left over from removed source (severity: low)
**File:** `kalshi/cli/`, `kalshi/cli/widgets/`
**Issue:** Both directories exist on disk but contain no `.py` files — only stale `__pycache__/` artifacts from since-removed modules. `git ls-tree HEAD kalshi/cli/` returns empty (not tracked). The directories are harmless but invite confusion: anyone scanning the source tree will see a `cli` package and wonder where it went. If a future contributor `os.walk`s `kalshi/` for packaging or doc purposes the empty dirs may show up unexpectedly.
**Evidence:** `find kalshi/cli -name '*.py'` returns nothing; `ls -la kalshi/cli/` shows only `__pycache__/widgets/`. `git ls-tree HEAD kalshi/cli/` returns empty.
**Suggested fix:** Delete both directories from the working tree and add a `.gitignore` pattern (or rely on the existing one) so stray `__pycache__` doesn't get committed.

### F-N-14 — Pagination-helper recursion uses unconfigurable safety cap of 1000 pages (severity: low)
**File:** `kalshi/resources/_base.py:147-184` (sync), `:260-291` (async)
**Issue:** `_list_all` hard-codes `max_pages: int = 1000`. The argument exists in the signature but is not exposed to the public `*_all` methods on any resource (none of them forward a `max_pages` kwarg). For long histories — e.g. `markets.list_trades_all` over years, `historical.trades_all` with no `min_ts` — 1000 pages × default page size could exhaust the data well before the user wants it to stop, returning a silent partial. Callers cannot raise the limit without subclassing the resource.
**Evidence:** `_base.py:147` — `max_pages: int = 1000` parameter is plumbed only inside `_list_all`; no resource forwards a `max_pages` parameter from its public `*_all()` method.
**Suggested fix:** Either expose `max_pages` as a kwarg on the public `*_all()` methods (with the same 1000 default), or raise a sentinel error when the cap is hit so users at least learn the iterator terminated artificially. Today the iterator just `break`s with no signal.

### F-N-15 — `WeeklySchedule` is exported via `kalshi.models.__all__` but has no docstring/usage trace, and `kalshi/__init__.py` skips it (severity: low)
**File:** `kalshi/__init__.py:116-225` (omission), `kalshi/models/__init__.py:43`
**Issue:** Specific instance of F-N-01 worth flagging because the schedule classes (`DailySchedule`, `WeeklySchedule`, `Schedule`, `MaintenanceWindow`) appear to be nested response components for `ExchangeStatus`. They are exported from `kalshi.models` but never used in any resource signature — only embedded as fields. Either they are intentionally internal (in which case they shouldn't be in `kalshi.models.__all__` either) or they are part of the public surface (in which case they belong at top level too).
**Evidence:** `kalshi/models/__init__.py:35-43` exports schedule classes; `grep` for `WeeklySchedule`/`DailySchedule` as a return-type or argument shows only the `Schedule` field inside `ExchangeStatus`.
**Suggested fix:** Decide if these are public or internal. If public, add to `kalshi/__init__.py` `__all__` (folds into F-N-01). If internal, drop from `kalshi.models.__all__`.

### F-N-16 — Sync resource `list_all` returns `Iterator` via a generator delegate inconsistently (severity: low)
**File:** `kalshi/resources/communications.py:206-222` vs `kalshi/resources/orders.py:389-406`
**Issue:** `CommunicationsResource.list_all_rfqs` uses `yield from self._list_all(...)` (line 222), while `OrdersResource.list_all` directly `return self._list_all(...)` (line 406). Both work because `_list_all` is itself a generator — the `yield from` is purely ceremonial — but the inconsistency is confusing. Worse, the async sibling in `communications.py:412-431` uses `async for ... yield item` while `OrdersResource.list_all` (async, line 714-732) returns the async iterator directly. Both styles work; mixing them in the same codebase is a paper cut.
**Evidence:** `communications.py:222` — `yield from self._list_all(...)`; `orders.py:406` — `return self._list_all(...)`. Async: `communications.py:428-431` uses `async for`/`yield`; `orders.py:732` directly `return`s.
**Suggested fix:** Standardize on `return self._list_all(...)` for sync and `return self._list_all(...)` for async (both directly return iterators). The `async for ... yield` wrapper turns an async generator function into an async-generator-returning function, which is the same shape but with an extra coroutine layer.

### F-N-17 — `Orderbook.yes`/`Orderbook.no` mutable default `= []` on a Pydantic model field (severity: low)
**File:** `kalshi/models/markets.py:156-157`
**Issue:** `yes: NullableList[OrderbookLevel] = []` and `no: NullableList[OrderbookLevel] = []`. Pydantic v2 deep-copies mutable defaults at model construction so the typical Python "shared mutable default" footgun doesn't fire, but ruff lint rule B006 would still flag it and a future migration off Pydantic (or to a strict mode) reintroduces the hazard. Same pattern in `MarketCandlesticks.candlesticks: NullableList[Candlestick] = []` (line 247).
**Evidence:** `kalshi/models/markets.py:156-157,247`.
**Suggested fix:** Switch to `Field(default_factory=list)`. Behaviourally identical under Pydantic v2 but unambiguous to readers and lint-clean.

---

End of findings.
