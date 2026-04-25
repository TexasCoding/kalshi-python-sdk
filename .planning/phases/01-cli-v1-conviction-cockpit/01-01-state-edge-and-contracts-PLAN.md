---
phase: 01-cli-v1-conviction-cockpit
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - kalshi/cli/__init__.py
  - kalshi/cli/state.py
  - kalshi/cli/edge.py
  - tests/cli/__init__.py
  - tests/cli/conftest.py
  - tests/cli/test_state.py
  - tests/cli/test_edge.py
  - tests/cli/test_contracts.py
autonomous: true
requirements: [CLI-Q01, CLI-Q02, CLI-Q03, CLI-06, CLI-08, CLI-09, CLI-10]
must_haves:
  truths:
    - "`kalshi.cli.state.Store` instantiates with auth-required precondition baked in"
    - "WS frames merge into the right state slice (orderbook_delta → OrderbookState; trade → DeltaTapeLog; user_orders → RestingOrdersState; fill → PositionState)"
    - "REST snapshot replaces account slices atomically (BalanceState, PositionState, RestingOrdersState replace, not merge)"
    - "edge_yes / edge_no / max_loss / max_gain produce exact Decimal results for the table-driven cases in the test plan"
    - "Contract drift test hard-fails (pytest.fail, not warnings.warn) when a cockpit-consumed SDK field is missing"
    - "DeltaTapeLog caps at 200 entries (deque maxlen)"
  artifacts:
    - path: "kalshi/cli/state.py"
      provides: "Store + slice dataclasses + apply_*/replace_*/merge_* mutators"
      contains: "class Store"
    - path: "kalshi/cli/edge.py"
      provides: "edge_yes / edge_no / max_loss_yes / max_gain_yes / max_loss_no / max_gain_no / edge_intensity"
      contains: "def edge_yes"
    - path: "tests/cli/test_state.py"
      provides: "Store mutator coverage incl. REST replace + WS merge"
    - path: "tests/cli/test_edge.py"
      provides: "Table-driven Decimal math"
    - path: "tests/cli/test_contracts.py"
      provides: "Cockpit ↔ SDK shape drift hard-fail"
    - path: "pyproject.toml"
      provides: "[cli] optional deps + [project.scripts] kalshi entry point"
      contains: "[project.optional-dependencies]"
  key_links:
    - from: "kalshi/cli/state.py"
      to: "kalshi/ws/orderbook.py:OrderbookManager"
      via: "Store reads Orderbook from OrderbookManager.get(ticker); does not duplicate orderbook merge logic"
      pattern: "OrderbookManager"
    - from: "tests/cli/test_contracts.py"
      to: "kalshi.models.markets / portfolio / orders / ws.models"
      via: "importlib.import_module + getattr to verify field presence"
      pattern: "COCKPIT_FIELD_DEPS"
---

<objective>
Land the foundation of `kalshi/cli/`: dependency declarations, the mutable state store, the pure edge math, and the contract drift test that locks the cockpit to the SDK shapes it depends on. This plan ships zero Textual code — the goal is to have `state.py` and `edge.py` fully covered by unit tests AND a hard-failing drift suite BEFORE any widget plan can drift the SDK out from under the cockpit.

Purpose: Wave 1 must produce two artifacts the rest of the phase depends on — (1) a state store with deterministic mutator semantics, and (2) a drift suite that fails the build if any SDK field the cockpit reads goes missing. Both are pure-Python, no Textual, no I/O — they unblock every subsequent plan.

Output: `kalshi/cli/__init__.py` + `state.py` + `edge.py` + `pyproject.toml` cli-extras + 3 test files (conftest helpers, state, edge, contracts) all passing under mypy strict + ruff.
</objective>

<execution_context>
@/Users/jeffreywest/Code/Python/kalshi-python-sdk/.planning/phases/01-cli-v1-conviction-cockpit/PATTERNS.md
@/Users/jeffreywest/.gstack/projects/kalshi-python-sdk/jeffreywest-main-design-20260424-190736.md
@/Users/jeffreywest/.gstack/projects/kalshi-python-sdk/jeffreywest-main-eng-review-test-plan-20260424-192732.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@.planning/STATE.md
@CLAUDE.md

# SDK shapes the cockpit reads (extracted from PATTERNS.md + design doc)
@kalshi/ws/orderbook.py
@kalshi/ws/sequence.py
@kalshi/models/markets.py
@kalshi/models/portfolio.py
@kalshi/models/orders.py
@kalshi/ws/models
@tests/test_contracts.py
@tests/_contract_support.py

# Mutator-pattern analog
@tests/ws/test_orderbook.py

# Existing entry-points + deps file
@pyproject.toml

<spike_decision>
PATTERNS.md (Spike 1 + Spike 2) resolves both architecture gates the eng-review originally
required as separate spike plans:

- OrderbookManager read API is sufficient (`OrderbookManager.get(ticker) -> Orderbook | None`,
  with `book.yes` / `book.no` already sorted ascending by price). state.py consumes the
  Orderbook reference directly — NO derived view layer needed.
- KalshiWebSocket(__init__, ..., on_state_change=...) is exposed at kalshi/ws/client.py:56-78.
  The Textual lifecycle worker registers an on_state_change callback; this is the correct
  seam for driving the cockpit's ConnectionState slice.

Therefore the originally-planned `01-01-spike-orderbook-read-api` and `01-02-spike-ws-lifecycle-seam`
plans are dropped. This is deliberate — both questions have answers in PATTERNS.md backed by
direct code references. If during implementation the executor finds the answers wrong, STOP
and re-open as a real spike (do not paper over with workarounds).
</spike_decision>

<sdk_shape_inventory>
Cockpit ↔ SDK field dependencies (these are the rows that go into COCKPIT_FIELD_DEPS in
test_contracts.py — confirm each via Read before writing the test):

REST GET shapes:
  kalshi.models.markets.Market           → ticker, title, close_time, event_ticker, rules_primary
  kalshi.models.events.Event             → title, markets
  kalshi.models.portfolio.MarketPosition → market_ticker, position
  kalshi.models.portfolio.Balance        → balance
  kalshi.models.orders.Order             → order_id, status, ticker, side, action, count
                                            (price field name TBD — see kalshi/models/orders.py;
                                             use the alias-mapped short name like yes_price /
                                             no_price, NOT _dollars suffix)

WS payload shapes:
  kalshi.ws.models.orderbook_delta.OrderbookDeltaPayload → market_ticker, price, delta, side
  kalshi.ws.models.ticker.TickerPayload                  → market_ticker, price, yes_bid, yes_ask
  kalshi.ws.models.trade.TradePayload                    → market_ticker, price, count, side, ts
  kalshi.ws.models.fill.FillPayload                      → trade_id, order_id, ticker, side, count
  kalshi.ws.models.user_orders.UserOrdersPayload         → order_id, status, ticker, side

VERIFY each model+field via `grep -n` against the actual source before locking the list.
If a field has been renamed or moved, fix the row — do not paper over with a permanent
EXCLUSIONS entry unless you have a written reason.
</sdk_shape_inventory>

<interfaces>
<!-- Contracts state.py exposes; downstream plans consume these. -->

```python
# kalshi/cli/state.py — public surface

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from kalshi.models.markets import Market, Orderbook
from kalshi.models.portfolio import Balance, MarketPosition
from kalshi.models.orders import Order
from kalshi.ws.models.orderbook_delta import OrderbookDeltaMessage
from kalshi.ws.models.ticker import TickerMessage
from kalshi.ws.models.trade import TradeMessage
from kalshi.ws.models.fill import FillMessage
from kalshi.ws.models.user_orders import UserOrdersMessage


class CockpitConnectionState(str, Enum):
    """Cockpit-facing connection state (collapsed from SDK's 6-state enum to 4)."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"


@dataclass
class MarketState:
    market: Market | None = None
    last_update_ts: datetime | None = None


@dataclass
class OrderbookState:
    book: Orderbook | None = None
    last_update_ts: datetime | None = None


@dataclass
class PositionState:
    positions: list[MarketPosition] = field(default_factory=list)
    last_update_ts: datetime | None = None


@dataclass
class BalanceState:
    balance: Balance | None = None
    last_update_ts: datetime | None = None


@dataclass
class RestingOrdersState:
    orders: list[Order] = field(default_factory=list)
    last_update_ts: datetime | None = None


@dataclass
class ConnectionStateSlice:
    state: CockpitConnectionState = CockpitConnectionState.CONNECTING
    last_change_ts: datetime | None = None


@dataclass
class TapeLine:
    ts: datetime
    text: str  # rendered "[HH:MM:SS.mmm side price size]" or "[disconnect]" / "[resync gap=N]"


@dataclass
class DeltaTapeLog:
    """Bounded ring of recent tape lines."""
    lines: deque[TapeLine] = field(default_factory=lambda: deque(maxlen=200))


@dataclass
class Store:
    """Single source of truth — Textual widgets reactive-subscribe to slices."""
    ticker: str
    fair: Decimal | None
    market: MarketState = field(default_factory=MarketState)
    orderbook: OrderbookState = field(default_factory=OrderbookState)
    positions: PositionState = field(default_factory=PositionState)
    balance: BalanceState = field(default_factory=BalanceState)
    resting_orders: RestingOrdersState = field(default_factory=RestingOrdersState)
    connection: ConnectionStateSlice = field(default_factory=ConnectionStateSlice)
    tape: DeltaTapeLog = field(default_factory=DeltaTapeLog)

    # REST snapshot replacement (called on initial mount + every reconnect)
    def replace_market(self, market: Market) -> None: ...
    def replace_balance(self, balance: Balance) -> None: ...
    def replace_positions(self, positions: list[MarketPosition]) -> None: ...
    def replace_resting_orders(self, orders: list[Order]) -> None: ...

    # Connection-state mutator (called from on_state_change callback)
    def set_connection(self, state: CockpitConnectionState) -> None: ...

    # WS frame merges
    def merge_orderbook(self, book: Orderbook | None) -> None: ...
    def merge_ticker(self, msg: TickerMessage) -> None: ...
    def merge_trade(self, msg: TradeMessage) -> None: ...
    def merge_fill(self, msg: FillMessage) -> None: ...
    def merge_user_order(self, msg: UserOrdersMessage) -> None: ...

    # Tape append (used by lifecycle for [disconnect] / [resync gap=N])
    def append_tape(self, line: TapeLine) -> None: ...
```

```python
# kalshi/cli/edge.py — pure functions, all-Decimal

from __future__ import annotations
from decimal import Decimal


def edge_yes(price: Decimal, fair: Decimal) -> Decimal: ...
def edge_no(price: Decimal, fair: Decimal) -> Decimal: ...
def max_loss_yes(price: Decimal) -> Decimal: ...
def max_gain_yes(price: Decimal) -> Decimal: ...
def max_loss_no(price: Decimal) -> Decimal: ...
def max_gain_no(price: Decimal) -> Decimal: ...
def edge_intensity(edge: Decimal, max_edge: Decimal = Decimal("0.30")) -> float:
    """Return |edge|/max_edge clamped to [0, 1]; below 0.005 returns 0.0 (neutral)."""
    ...
```

For binary contracts `edge_yes == ev_yes` (eng-review locked — single function, not separate
EV function). DO NOT add a separate `ev_yes` / `ev_no`.
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: pyproject.toml cli extras + package skeleton + tests/cli scaffold</name>
  <files>
    pyproject.toml,
    kalshi/cli/__init__.py,
    tests/cli/__init__.py,
    tests/cli/conftest.py
  </files>
  <behavior>
    - `pip install -e ".[cli]"` (or `uv sync --extra cli`) pulls typer, textual, rich at the pinned ranges from the design doc.
    - `[project.scripts] kalshi = "kalshi.cli.main:app"` declared (the actual main module ships in plan 02 — but the entry-point reference must be in place so plan 02 just needs to add main.py).
    - `kalshi/cli/__init__.py` is a minimal package marker (matches `kalshi/ws/__init__.py` shape; can be empty docstring + `from __future__ import annotations` for now).
    - `tests/cli/conftest.py` exposes shared fixtures used by all later test files in this plan AND in plans 02–05:
        * `sample_market: Market` — canonical Market fixture (ticker, title, close_time, event_ticker, rules_primary set)
        * `sample_orderbook: Orderbook` — both YES and NO sides populated with 5 levels each
        * `sample_balance: Balance` — Decimal balance > 0
        * `sample_positions: list[MarketPosition]` — 1 position
        * `sample_resting_orders: list[Order]` — 1 resting order
        * `make_orderbook_delta(ticker, side, price, delta) -> OrderbookDeltaMessage` helper
        * `make_trade(ticker, side, price, count) -> TradeMessage` helper
        * `make_fill(...) -> FillMessage` helper
        * `make_user_orders(...) -> UserOrdersMessage` helper
        * `store(sample_market) -> Store` — fresh Store keyed to sample_market.ticker, fair=Decimal("0.63")
    - Helpers under `tests/cli/conftest.py` reuse the existing patterns from `tests/ws/test_orderbook.py:14-55` (`make_snapshot` / `make_delta`) and `tests/ws/conftest.py`.
    - `tests/cli/__init__.py` is empty (per pytest convention; matches `tests/ws/__init__.py`).
  </behavior>
  <action>
    1. Read current pyproject.toml. Add (do NOT replace) a new section:

       ```toml
       [project.optional-dependencies]
       cli = [
         "typer>=0.12,<1",
         "textual>=0.85,<0.95",
         "rich>=13,<15",
       ]

       [project.scripts]
       kalshi = "kalshi.cli.main:app"
       ```

       If `[project.optional-dependencies]` already exists for some other extra, ADD the
       `cli` key, don't clobber. If `[project.scripts]` already exists, add the `kalshi`
       key. Run `uv sync --extra cli` or `uv pip install -e ".[cli]"` to verify the resolve.

    2. Create `kalshi/cli/__init__.py` (one-line module docstring + `from __future__ import annotations`).

    3. Create `tests/cli/__init__.py` (empty).

    4. Create `tests/cli/conftest.py` with the fixtures listed above. Reuse existing
       `test_auth`, `test_config` from `tests/conftest.py` (they're auto-discovered).
       Pattern to copy for the make_* helpers: `tests/ws/test_orderbook.py:14-55`.

       For `make_orderbook_delta`, build via `OrderbookDeltaMessage.model_validate(...)` —
       the SDK validates incoming WS frames as Pydantic models. Match the field names
       exactly (price as DollarDecimal-compatible string).

       The `store` fixture: `Store(ticker=sample_market.ticker, fair=Decimal("0.63"))`.

    5. Verify the cli entry-point resolves:
       `python -c "from kalshi.cli import __init__"` (smoke import — main.py is plan 02).
  </action>
  <verify>
    <automated>uv sync --extra cli && uv run python -c "from kalshi.cli import __init__" && uv run mypy kalshi/cli/ && uv run ruff check kalshi/cli/ tests/cli/</automated>
  </verify>
  <done>
    pyproject.toml has cli extras + scripts entry. Package skeleton imports clean. Fixtures
    are loadable (pytest --collect-only tests/cli/ should not error even though no tests
    exist yet). mypy clean.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: edge.py + test_edge.py (pure math, table-driven)</name>
  <files>
    kalshi/cli/edge.py,
    tests/cli/test_edge.py
  </files>
  <behavior>
    Tests assert (write FIRST, fail RED, then implement GREEN):

    - `edge_yes(price=0.50, fair=0.63) == Decimal("0.13")`
    - `edge_yes(price=0.70, fair=0.63) == Decimal("-0.07")`
    - `edge_yes(price=0.63, fair=0.63) == Decimal("0")`
    - `edge_no(price=0.40, fair=0.63) == Decimal("-0.03")` ← per test plan; (1 - 0.63) - 0.40 = -0.03
    - `edge_no(price=0.20, fair=0.63) == Decimal("0.17")`
    - `max_loss_yes(price=0.65) == Decimal("0.65")`
    - `max_gain_yes(price=0.65) == Decimal("0.35")`
    - `max_loss_no(price=0.40) == Decimal("0.40")`
    - `max_gain_no(price=0.40) == Decimal("0.60")`
    - Boundary fair=Decimal("0") and fair=Decimal("1") do NOT raise / produce NaN / divide by zero.
    - `edge_intensity(Decimal("0")) == 0.0`
    - `edge_intensity(Decimal("0.001")) == 0.0` (below neutral threshold)
    - `edge_intensity(Decimal("0.005")) == 0.005/0.30` (just at threshold — design says <0.005 neutral, so 0.005 is colored)
    - `edge_intensity(Decimal("0.30")) == 1.0` (clamped at max)
    - `edge_intensity(Decimal("0.50")) == 1.0` (clamped past max)
    - `edge_intensity(Decimal("-0.15")) == 0.5` (uses absolute value)
    - Table-driven test parametrizes over ≥12 (price, fair) pairs from test plan.

    NO ev_yes / ev_no — for binary contracts edge IS EV (eng-review locked).
  </behavior>
  <action>
    1. RED: write `tests/cli/test_edge.py` with the parametrized tables above. Run
       `uv run pytest tests/cli/test_edge.py -x` — confirm import error / missing-symbol
       failures (expected).

    2. GREEN: implement `kalshi/cli/edge.py`. All Decimal math, no float, no math import
       except in `edge_intensity` where `float()` cast is the LAST step. Use
       `from decimal import Decimal` (no `getcontext` — the SDK relies on default precision
       and Pydantic's DollarDecimal handles quantization upstream).

       Pseudocode:
       ```python
       def edge_yes(price: Decimal, fair: Decimal) -> Decimal:
           return fair - price

       def edge_no(price: Decimal, fair: Decimal) -> Decimal:
           return (Decimal("1") - fair) - price

       def max_loss_yes(price: Decimal) -> Decimal:
           return price

       def max_gain_yes(price: Decimal) -> Decimal:
           return Decimal("1") - price

       def max_loss_no(price: Decimal) -> Decimal:
           return price

       def max_gain_no(price: Decimal) -> Decimal:
           return Decimal("1") - price

       _NEUTRAL_THRESHOLD = Decimal("0.005")
       _DEFAULT_MAX_EDGE = Decimal("0.30")

       def edge_intensity(edge: Decimal, max_edge: Decimal = _DEFAULT_MAX_EDGE) -> float:
           abs_edge = abs(edge)
           if abs_edge < _NEUTRAL_THRESHOLD:
               return 0.0
           clamped = min(abs_edge, max_edge)
           return float(clamped / max_edge)
       ```

    3. Re-run `uv run pytest tests/cli/test_edge.py -x` — all green.

    4. mypy strict + ruff: `uv run mypy kalshi/cli/edge.py && uv run ruff check kalshi/cli/edge.py tests/cli/test_edge.py`.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/test_edge.py -v && uv run mypy kalshi/cli/edge.py && uv run ruff check kalshi/cli/edge.py tests/cli/test_edge.py</automated>
  </verify>
  <done>
    All edge tests green. mypy + ruff clean. The 12+ parametrized cases from the test plan
    are exhaustive — adding a 13th case would be redundant.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: state.py + test_state.py (mutable Store + REST replace + WS merge)</name>
  <files>
    kalshi/cli/state.py,
    tests/cli/test_state.py
  </files>
  <behavior>
    Tests assert (RED first):

    `class TestStoreInit`:
      - Store(ticker="T", fair=Decimal("0.63")) initializes with empty slices, all `last_update_ts is None`, `connection.state == CONNECTING`, tape is empty deque maxlen=200.

    `class TestStoreReplace` (REST snapshot replacement — not merge):
      - `store.replace_market(market)` → `store.market.market is market`, `last_update_ts` set to a recent UTC datetime.
      - `store.replace_balance(balance)` → `store.balance.balance is balance`.
      - `store.replace_positions([p1, p2])` → `store.positions.positions == [p1, p2]` (full replace, NOT append). A second call with `[p3]` REPLACES the list with `[p3]`.
      - `store.replace_resting_orders([o1])` → similar replace semantics.
      - Each replace bumps `last_update_ts`.

    `class TestStoreConnection`:
      - `store.set_connection(CONNECTED)` → `store.connection.state == CONNECTED`, `last_change_ts` set.
      - Successive set_connection(CONNECTING → CONNECTED → RECONNECTING → CONNECTED) all bump last_change_ts.

    `class TestStoreMerge`:
      - `store.merge_orderbook(orderbook)` → `store.orderbook.book is orderbook`, last_update_ts set.
      - `store.merge_orderbook(None)` (cleared book) → `store.orderbook.book is None`, last_update_ts set.
      - `store.merge_ticker(ticker_msg)` → market_state's ticker payload updated (or test plan TBD; if MarketState only carries Market metadata, ticker may flow into a separate slice — but for v1, the simplest design is MarketState carries Market + most-recent ticker payload as side info).
      - `store.merge_trade(trade_msg)` → tape gets a new line formatted as `[HH:MM:SS.mmm side price size]`.
      - `store.merge_fill(fill_msg)` → tape line appended (auth-only path — fills also flow into PositionState reconciliation, but read-only v1 lets the next REST refresh fix any drift, so just tape it).
      - `store.merge_user_order(msg)` with `status == "resting"` → adds to resting_orders.
      - `store.merge_user_order(msg)` with `status == "canceled"` for an existing order_id → removes from resting_orders.
      - `store.merge_user_order(msg)` with an updated count → replaces the matching order_id entry.

    `class TestTapeCap`:
      - Append 250 tape lines → `len(store.tape.lines) == 200` (deque maxlen).
      - Oldest line evicted (FIFO).

    `class TestStoreThreadingAssumption`:
      - One smoke test that documents the single-writer assumption — assert that calling
        `store.set_connection` from inside a `merge_*` call still leaves a coherent state
        (not a real concurrency test, just an annotation that we trust asyncio cooperative
        scheduling). This can be a single-line `pass` test with a docstring explaining the
        invariant; eng-review locked mutable state given single-writer assumption.
  </behavior>
  <action>
    1. RED: write `tests/cli/test_state.py` with the test classes above. Use the helpers
       from `tests/cli/conftest.py` (sample_market, make_orderbook_delta, make_trade,
       etc.). Run `uv run pytest tests/cli/test_state.py -x` — confirm all red.

    2. GREEN: implement `kalshi/cli/state.py` per the `<interfaces>` block above.

       Critical implementation notes:

       - `from __future__ import annotations` (every file in `kalshi/`).
       - Mutable @dataclass — DO NOT add frozen=True. Eng-review locked this.
       - `last_update_ts` set via `datetime.now(timezone.utc)` (use `datetime.now(UTC)` on Python 3.12+).
       - `merge_orderbook` REPLACES the OrderbookState.book reference — does NOT mutate
         the existing Orderbook in place. (Lifecycle worker reads
         `session._orderbook_mgr.get(ticker)` after each delta and passes that whole
         Orderbook reference to merge_orderbook — see PATTERNS.md § Spike 1.)
       - `merge_trade` formats the tape line as `[HH:MM:SS.mmm side price size]`
         (`f"[{ts:%H:%M:%S}.{ts.microsecond // 1000:03d} {side} {price} {size}]"` or
         equivalent). Side comes from the WS payload, price as the model field, size as
         `count`.
       - `merge_user_order` switches on the order's status field — match against the
         actual literal values in `kalshi.models.orders.Order.status` (verify via Read of
         that model file before locking the strings).
       - `DeltaTapeLog.lines` initialized via `field(default_factory=lambda: deque(maxlen=200))`.
       - Module-level `logger = logging.getLogger("kalshi.cli")`.

    3. Verify all WS message-class imports resolve. The import paths are:
       - `kalshi.ws.models.orderbook_delta.OrderbookDeltaMessage`
       - `kalshi.ws.models.ticker.TickerMessage`
       - `kalshi.ws.models.trade.TradeMessage`
       - `kalshi.ws.models.fill.FillMessage`
       - `kalshi.ws.models.user_orders.UserOrdersMessage`

       If a message-class name differs (some WS modules use `XxxFrame` or `XxxEvent`),
       fix the import — verify by `ls kalshi/ws/models/` and reading the actual class
       names. PATTERNS.md uses the `Message` suffix consistently with the SDK — but
       confirm.

    4. Re-run pytest until green. mypy strict + ruff clean.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/test_state.py -v && uv run mypy kalshi/cli/state.py && uv run ruff check kalshi/cli/state.py tests/cli/test_state.py</automated>
  </verify>
  <done>
    All Store mutator semantics covered, all green. REST replace semantics distinct from
    WS merge semantics (replace = whole-slice swap, merge = incremental). Tape capped.
    mypy + ruff clean. No frozen dataclasses anywhere.
  </done>
</task>

<task type="auto">
  <name>Task 4: test_contracts.py (cockpit ↔ SDK shape drift, hard-fail)</name>
  <files>
    tests/cli/test_contracts.py
  </files>
  <behavior>
    Test imports each SDK model class via importlib and asserts the listed field exists
    on the model (Pydantic v2: `Model.model_fields` dict). Uses `pytest.fail`, not
    `warnings.warn`. Parametrizes over `COCKPIT_FIELD_DEPS` list of `CockpitFieldDep`
    dataclass entries.

    Coverage from test plan § Contract drift:
      - Market: ticker, title, close_time, event_ticker, rules_primary
      - Event: title, markets
      - MarketPosition: market_ticker, position
      - Balance: balance
      - Order: order_id, status, ticker, side, action, count (and price-equivalent — see note)
      - OrderbookDeltaPayload: market_ticker, price, delta, side
      - TickerPayload: market_ticker, price (or yes_bid/yes_ask depending on what cockpit reads)
      - TradePayload: market_ticker, price, count, side, ts (or timestamp)
      - FillPayload: trade_id, order_id, ticker, side, count
      - UserOrdersPayload: order_id, status, ticker, side

    Mirror `tests/test_contracts.py:961-1217` parametrize-over-map pattern. Hard-fail
    (use `pytest.fail("Cockpit consumer X reads field Y from model Z, but model Z no
    longer has that field — drift detected")`). Allowlist via an `EXCLUSIONS` list with
    a required `reason` string per entry (mirror `tests/_contract_support.py:39-47`).

    The test should NOT catch import errors silently — if a model module is missing,
    that's also a drift signal and should hard-fail.
  </behavior>
  <action>
    1. Read `tests/test_contracts.py:961-1217` to internalize the parametrize-over-map
       pattern. Read `tests/_contract_support.py:39-47` for the Exclusion dataclass shape.

    2. Verify the actual SDK field names via `grep -n` on each model file:
       - `grep -n "^    [a-z_]*:" kalshi/models/markets.py` (Market, Orderbook, OrderbookLevel)
       - same for `kalshi/models/events.py`, `portfolio.py`, `orders.py`
       - same for `kalshi/ws/models/*.py`

       For each cockpit-consumed field, lock the EXACT model field name (the SHORT name —
       SDK convention is short Python names with `_dollars`-suffix `validation_alias` for
       wire format). The drift test asserts on the SHORT name.

       For Order, the price-equivalent field is `yes_price` / `no_price` (or whatever the
       SDK's actual short name is — verify by reading `kalshi/models/orders.py`). If the
       cockpit only needs one of them (the price relevant to the highlighted side), pick
       that one. The test plan says "Order.yes_price" — but the orders widget in plan 04
       might want both. List both in COCKPIT_FIELD_DEPS so we don't have to revisit later.

    3. Build `tests/cli/test_contracts.py`:

       ```python
       from __future__ import annotations
       import importlib
       from dataclasses import dataclass

       import pytest


       @dataclass(frozen=True)
       class CockpitFieldDep:
           sdk_model_fqn: str
           field_name: str
           cockpit_consumer: str

       COCKPIT_FIELD_DEPS: list[CockpitFieldDep] = [
           # ... full list from <sdk_shape_inventory> section, validated against grep ...
       ]

       @dataclass(frozen=True)
       class Exclusion:
           sdk_model_fqn: str
           field_name: str
           reason: str

       EXCLUSIONS: list[Exclusion] = []  # empty unless we hit a real drift we must accept


       def _load_model(fqn: str) -> type:
           module_path, class_name = fqn.rsplit(".", 1)
           module = importlib.import_module(module_path)
           return getattr(module, class_name)


       @pytest.mark.parametrize("dep", COCKPIT_FIELD_DEPS, ids=lambda d: f"{d.sdk_model_fqn.rsplit('.', 1)[1]}.{d.field_name}")
       def test_cockpit_field_present_on_sdk_model(dep: CockpitFieldDep) -> None:
           if any(e.sdk_model_fqn == dep.sdk_model_fqn and e.field_name == dep.field_name for e in EXCLUSIONS):
               pytest.skip(f"excluded — see EXCLUSIONS reason")
           model = _load_model(dep.sdk_model_fqn)
           if dep.field_name not in model.model_fields:
               pytest.fail(
                   f"Cockpit drift: {dep.cockpit_consumer} reads "
                   f"{dep.sdk_model_fqn}.{dep.field_name}, but field is missing. "
                   f"Either rename in cockpit, restore field in SDK model, or add EXCLUSIONS row."
               )
       ```

    4. Run `uv run pytest tests/cli/test_contracts.py -v`. Every parametrized case must
       pass — if any fails, the cockpit's expected shape doesn't match the SDK. Fix the
       FQN or field name before moving on.

    5. mypy strict + ruff clean.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/test_contracts.py -v && uv run mypy tests/cli/test_contracts.py && uv run ruff check tests/cli/test_contracts.py</automated>
  </verify>
  <done>
    All ≥25 parametrized drift cases green. EXCLUSIONS empty (no drift accepted). When a
    later SDK refactor renames a field the cockpit reads, this test reds CI.
  </done>
</task>

</tasks>

<threat_model>
Security enforcement is not flagged in config.json — but document the surface anyway since
this plan touches dependency declarations.

## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| pip → user venv | New optional deps (typer, textual, rich) install on `[cli]` extra. Pinned to known-stable ranges (textual<0.95 in particular — pre-1.0 ships breaking changes monthly). |
| ENV → process | KALSHI_KEY_ID + KALSHI_PRIVATE_KEY_PATH read by AsyncKalshiClient.from_env (already audited at SDK level — this plan adds no new env reads). |

## STRIDE

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-01-01 | T (tampering) | typer/textual/rich pin | mitigate | upper-bound pins prevent surprise major-version breakage; renovate/dependabot picks up patch updates (existing CI policy applies) |
| T-01-02 | I (info disclosure) | logger("kalshi.cli") | accept | new logger inherits root config; private key paths never logged at any level |
</threat_model>

<verification>
After all 4 tasks:

```bash
uv run pytest tests/cli/ -v --tb=short
uv run mypy kalshi/cli/ tests/cli/
uv run ruff check kalshi/cli/ tests/cli/
uv run pytest --collect-only tests/cli/  # smoke: pytest discovers everything

# Coverage check (≥80% line on the two real source files)
uv run pytest tests/cli/test_state.py tests/cli/test_edge.py --cov=kalshi/cli/state.py --cov=kalshi/cli/edge.py --cov-report=term-missing
```

Manual sanity check:
- `pip install -e ".[cli]"` (or `uv sync --extra cli`) succeeds.
- `python -c "from kalshi.cli.state import Store; from kalshi.cli.edge import edge_yes; print(edge_yes(__import__('decimal').Decimal('0.5'), __import__('decimal').Decimal('0.63')))"` prints `0.13`.
</verification>

<success_criteria>
- pyproject.toml `[cli]` extras + `[project.scripts] kalshi` entry land cleanly.
- `kalshi/cli/state.py` + `edge.py` exist, mypy-strict + ruff-clean.
- `tests/cli/test_state.py` covers REST replace semantics, WS merge semantics, tape cap, connection-state transitions — all green.
- `tests/cli/test_edge.py` covers the 12+ table cases from the test plan — all green.
- `tests/cli/test_contracts.py` parametrizes ≥25 cockpit ↔ SDK field deps — all green; EXCLUSIONS empty.
- Line coverage on `kalshi/cli/state.py` + `edge.py` ≥ 80%.
- No frozen dataclasses anywhere in `kalshi/cli/state.py`.
</success_criteria>

<output>
After completion, create `.planning/phases/01-cli-v1-conviction-cockpit/plans/01-01-state-edge-and-contracts/01-01-SUMMARY.md`
documenting: actual COCKPIT_FIELD_DEPS row count, any EXCLUSIONS added (and why), final
test count + coverage %, and any SDK field renames discovered during the grep pass.
</output>
