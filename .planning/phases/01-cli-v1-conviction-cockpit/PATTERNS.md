# Phase 1: cli-v1-conviction-cockpit — Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 22 (8 source + 14 tests)
**Analogs found:** 19 / 22 (3 have no close analog — Textual is novel)

This document maps each new file in `kalshi/cli/` and `tests/cli/` to the closest existing analog in the repo. Phase 1 is read-only, auth-required, Textual reactive descriptors, mutable dataclass state, with `lifecycle.py` owning REST snapshot + WS delta merge + reconnect refresh. Source-of-truth design doc: `~/.gstack/projects/kalshi-python-sdk/jeffreywest-main-design-20260424-190736.md` § "v1 REVISIONS (post-/plan-eng-review 2026-04-24)".

---

## Architecture-Gate Spike Findings (do these before widget work)

### Spike 1: `OrderbookManager` read API — RESOLVED, NOT BLOCKING

**File:** `kalshi/ws/orderbook.py:16-108`

Public read API is sufficient as-is. No derived-view layer needed in `state.py`.

```python
# kalshi/ws/orderbook.py:98-108
def get(self, ticker: str) -> Orderbook | None:
    """Get current book state (non-blocking)."""
    return self._books.get(ticker)

def remove(self, ticker: str) -> None: ...
def clear(self) -> None: ...
```

`Orderbook.yes` / `.no` are `list[OrderbookLevel]` already sorted by price (ascending) — `apply_delta` in `kalshi/ws/orderbook.py:88-94` calls `levels.sort(key=lambda lv: lv.price)` whenever a new level is added. `OrderbookLevel` (`kalshi/models/markets.py:134-142`) carries `price: DollarDecimal`, `quantity: DollarDecimal`. For top-N reads, slice the list. For best-bid / best-ask: index into `[-1]` for highest YES bid (sorted asc), `[0]` for lowest NO. **`state.py` consumes `OrderbookManager.get(ticker)` directly; no wrapper needed.** The OrderbookState slice can carry the `Orderbook | None` reference and a `last_update_ts: datetime`.

### Spike 2: WS-lifecycle seam (Textual worker hosts `KalshiWebSocket`) — DESIGN PATTERN CONFIRMED

**File:** `kalshi/ws/client.py:80-122` — `KalshiWebSocket` exposes:

| Method / property | Signature | What `lifecycle.py` does with it |
|-------------------|-----------|----------------------------------|
| `connect()` | `() -> _WebSocketSession` (async ctx mgr) | Open inside the Textual worker via `async with ws.connect() as session:` |
| `_start()` / `_stop()` | private, called by ctx mgr | Don't call directly — ctx mgr handles ordering |
| `subscribe_orderbook_delta(tickers=[...])` | `kalshi/ws/client.py:267-276`, returns `AsyncIterator[OrderbookSnapshotMessage \| OrderbookDeltaMessage]` | Pump frames into `state.py` mutators |
| `subscribe_ticker(tickers=[...])` | `kalshi/ws/client.py:256-265` | Pump market_state slice |
| `subscribe_trade(tickers=[...])` | `kalshi/ws/client.py:278-287` | Append to `DeltaTapeLog` |
| `subscribe_fill()` | `kalshi/ws/client.py:289-294` | Mutate `PositionState` |
| `subscribe_user_orders()` | `kalshi/ws/client.py:304-310` | Mutate `RestingOrdersState` |
| `subscribe_market_positions()` | `kalshi/ws/client.py:296-302` | Mutate `PositionState` |
| `on(channel)` decorator | `kalshi/ws/client.py:384-398` | Alternative to iterators — register coroutine callbacks; accepts pre- or post-connect |
| `KalshiWebSocket.__init__(auth, config, on_state_change=...)` | `kalshi/ws/client.py:56-78` | **Pass an `on_state_change` callback** that drives `ConnectionState` slice |

**Reconnect lifecycle is internal** — `_recv_loop` in `kalshi/ws/client.py:137-207` catches `ConnectionClosed` and calls `self._connection.reconnect()` which transitions through `RECONNECTING → CONNECTING → CONNECTED → STREAMING` (`kalshi/ws/connection.py:122-172`). On reconnect, `_recv_loop` clears the orderbook (`self._orderbook_mgr.clear()`), resets the sequence tracker, and resubscribes (`kalshi/ws/client.py:189-196`). **Lifecycle.py needs to: register `on_state_change` callback → on `STREAMING` after a `RECONNECTING`, fire a fresh REST snapshot fetch → replace store slices → existing WS resubscribe handles the WS side.**

Connection state enum lives in `kalshi/ws/connection.py:24-32` — exact values: `DISCONNECTED, CONNECTING, CONNECTED, STREAMING, RECONNECTING, CLOSED`. The cockpit `ConnectionState` slice (slightly different from the SDK enum — drop `CONNECTED` vs `STREAMING` distinction for the user) maps these to `CONNECTING / CONNECTED / RECONNECTING / DISCONNECTED`.

**Cancellation** is clean: `_WebSocketSession.__aexit__` calls `_stop()` which cancels `_recv_task` with `contextlib.suppress(asyncio.CancelledError)`, sends sentinels to all queues, then closes. Textual's `worker.cancel()` raises `CancelledError` into the worker coroutine, which propagates through `async with ws.connect()` and triggers `_stop()` cleanly.

### How `dispatch.py` consumption translates to `lifecycle.pump_frames()`

`MessageDispatcher` (`kalshi/ws/dispatch.py:46-114`) is **internal to `KalshiWebSocket._recv_loop`** — `lifecycle.py` does NOT instantiate or call dispatch directly. Instead, lifecycle.py:

1. Calls `await session.subscribe_orderbook_delta(tickers=[ticker])` etc., which returns typed `AsyncIterator[Message]` queues.
2. Spawns one Textual worker per channel (or fans out one worker that `asyncio.gather`s all streams).
3. Inside each worker: `async for msg in stream: state.merge_orderbook_delta(msg)` (or the relevant mutator).

The 12 message types in `MESSAGE_MODELS` (`kalshi/ws/dispatch.py:27-40`) are already routed to typed queues by the SDK; the cockpit picks **5 channels** (orderbook_delta, ticker, trade, fill, user_orders, optionally market_positions) and pumps each iterator into the right state slice. `OrderbookManager` is owned internally by `KalshiWebSocket` (constructed at `_start`) — read it via `session._orderbook_mgr.get(ticker)` after each `orderbook_delta` frame. (This is private-attribute access — flag in the spike for promotion to a public accessor, but acceptable for v1; integration tests already do this at `tests/integration/test_websocket.py:30`.)

### `AsyncTransport` request hooks for REST snapshot

**File:** `kalshi/_base_client.py:183-285`

`AsyncTransport` has no public hook surface. `lifecycle.py` does NOT touch the transport directly. It uses `AsyncKalshiClient` resources (`client.markets.get`, `client.events.get`, `client.portfolio.balance`, `client.portfolio.positions`, `client.orders.list(status="resting")`) which are already wired to the transport. Pattern: pass the `AsyncKalshiClient` instance into `lifecycle.WSLifecycle.__init__`, store it, and call `await self.client.markets.get(ticker)` etc. inside the worker.

Auth fail-fast happens at `AsyncKalshiClient.ws` property (`kalshi/async_client.py:118-134`) — raises `AuthRequiredError` if `self._auth is None`. v1 onboarding (`watch.py`) **must** check `client.is_authenticated` before mounting the TUI; eng-review locked auth-required.

---

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `kalshi/cli/__init__.py` | package marker | n/a | `kalshi/ws/__init__.py` | exact (same shape) |
| `kalshi/cli/main.py` | entrypoint | request-response | `kalshi/__init__.py:201` (re-exports) + `pyproject.toml:32-37` (entry-points) | partial — Typer is novel |
| `kalshi/cli/watch.py` | command bootstrap | request-response | `kalshi/async_client.py:136-151` (`from_env`) | role-match |
| `kalshi/cli/app.py` | TUI app shell | event-driven | (none — Textual is novel) | no analog — use upstream Textual docs |
| `kalshi/cli/lifecycle.py` | worker / merge engine | streaming + pub-sub | `kalshi/ws/client.py:84-207` (`_start`/`_recv_loop`/reconnect) | exact — same shape (own a connection, pump frames, handle reconnect) |
| `kalshi/cli/state.py` | mutable store | transform | `kalshi/ws/orderbook.py:16-108` (`OrderbookManager`) | exact — same shape (mutable state container with `apply_*` mutators) |
| `kalshi/cli/edge.py` | pure math | transform | `kalshi/ws/orderbook.py:56-96` (`apply_delta` math) + `kalshi/types.py` (`DollarDecimal`) | role-match (pure functions over `Decimal`) |
| `kalshi/cli/widgets/header.py` | Textual widget | event-driven | (none) | no analog — Textual reactive descriptors |
| `kalshi/cli/widgets/orderbook.py` | Textual widget | event-driven | (none — but math/coloring uses `edge.py`) | no analog |
| `kalshi/cli/widgets/positions.py` | Textual widget | event-driven | (none) | no analog |
| `kalshi/cli/widgets/orders.py` | Textual widget | event-driven | (none) | no analog |
| `kalshi/cli/widgets/rule.py` | Textual widget | event-driven | (none) | no analog |
| `kalshi/cli/widgets/tape.py` | Textual widget | event-driven | (none) | no analog |
| `kalshi/cli/widgets/too_small.py` | Textual widget | event-driven | (none) | no analog |
| `tests/cli/conftest.py` | fixtures | n/a | `tests/conftest.py` + `tests/ws/conftest.py` (FakeKalshiWS) + `tests/integration/conftest.py` (demo bridge) | exact (composed) |
| `tests/cli/test_main.py` | CLI test | request-response | `tests/test_async_client.py` (constructor / from_env tests) | role-match |
| `tests/cli/test_watch.py` | bootstrap test | request-response | `tests/test_async_client.py` + Typer's `CliRunner` (novel) | partial |
| `tests/cli/test_app.py` | smoke test | event-driven | (none — use Textual `App.run_test()`) | no analog |
| `tests/cli/test_lifecycle.py` | lifecycle test | streaming | `tests/ws/test_client.py:15-49` (lifecycle / state callback) | exact |
| `tests/cli/test_state.py` | state test | transform | `tests/ws/test_orderbook.py:58-100` (apply_snapshot / apply_delta) | exact |
| `tests/cli/test_edge.py` | math test | transform | `tests/ws/test_orderbook.py` (table-driven Decimal math) | role-match |
| `tests/cli/test_widgets_orderbook.py` | widget test | event-driven | (none — Textual `Pilot`) | no analog |
| `tests/cli/test_widgets_panels.py` | widget test | event-driven | (none — Textual `Pilot`) | no analog |
| `tests/cli/test_contracts.py` | drift test | n/a | `tests/test_contracts.py:961-1217` (`TestRequestParamDrift` / `TestRequestBodyDrift`) | exact — mirror this pattern |
| `tests/cli/integration/conftest.py` | integration fixtures | n/a | `tests/integration/conftest.py` | exact (reuse via import or share fixtures) |
| `tests/cli/integration/test_watch.py` | E2E test | streaming | `tests/integration/test_websocket.py:14-85` | exact |

---

## Pattern Assignments

### `kalshi/cli/__init__.py` (package marker)

**Analog:** `kalshi/ws/__init__.py:1-12`

Minimal re-export of public symbols. Match this shape:

```python
# kalshi/ws/__init__.py:1-12
"""Kalshi WebSocket client."""
from kalshi.ws.backpressure import MessageQueue, OverflowStrategy
from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.connection import ConnectionState

__all__ = [
    "ConnectionState",
    "KalshiWebSocket",
    ...
]
```

For v1 cli, keep it empty or re-export only `app: typer.Typer` from `kalshi.cli.main`. The Typer `app` symbol is what `[project.scripts] kalshi = "kalshi.cli.main:app"` resolves.

---

### `kalshi/cli/main.py` (Typer root)

**Analog:** `kalshi/async_client.py:38-46` (module-level docstring + import block) — but Typer is novel. **Use upstream Typer docs for the actual API.**

**Conventions to imitate from the SDK:**

- `from __future__ import annotations` (every file in `kalshi/`)
- Module-level docstring describing the surface
- Logger pattern: `logger = logging.getLogger("kalshi.cli")` (matches `kalshi/ws/client.py:36` — `logger = logging.getLogger("kalshi.ws")`)
- Typer subcommand registration (no analog — Typer convention):
  ```python
  app = typer.Typer(no_args_is_help=True, help="Kalshi SDK CLI")
  app.command(name="watch")(watch_command)  # registered from kalshi.cli.watch
  ```

**Wire-up step for the planner:** `pyproject.toml` needs `[project.scripts] kalshi = "kalshi.cli.main:app"` and a new `[project.optional-dependencies] cli = ["typer>=0.12,<1", "textual>=0.85,<0.95", "rich>=13,<15"]` block. See current `pyproject.toml:1-37`.

---

### `kalshi/cli/watch.py` (`kalshi watch TICKER` bootstrap)

**Analog:** `kalshi/async_client.py:136-151` (`AsyncKalshiClient.from_env`)

Builds the async client from env, validates auth-required preconditions, hands off to the Textual app. Match this shape:

```python
# kalshi/async_client.py:136-151 — from_env pattern to copy
@classmethod
def from_env(cls, **kwargs: object) -> AsyncKalshiClient:
    """Create async client from environment variables.

    Reads:
        KALSHI_KEY_ID (optional — omit for unauthenticated access)
        KALSHI_PRIVATE_KEY (PEM string) or KALSHI_PRIVATE_KEY_PATH (file path)
        KALSHI_API_BASE_URL (optional, overrides base_url)
        KALSHI_DEMO (optional, "true" for demo environment)

    Returns an unauthenticated client if no credentials are configured.
    """
    auth = KalshiAuth.try_from_env()
    demo = os.environ.get("KALSHI_DEMO", "").lower() == "true"
    base_url = os.environ.get("KALSHI_API_BASE_URL")
    return cls(auth=auth, demo=demo, base_url=base_url, **kwargs)
```

**Auth fail-fast (read-only v1 requires auth always):**

```python
# Check before mounting Textual
client = AsyncKalshiClient.from_env(demo=not live_mode)
if not client.is_authenticated:
    typer.echo(
        "ERROR: KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH must be set. "
        "Free demo creds: https://docs.kalshi.com/getting-started",
        err=True,
    )
    raise typer.Exit(code=2)
```

**Differences to expect:** Typer's `Annotated[float, Option(...)]` for `--fair PROB` validation (range `[0, 1]`); the existing SDK uses no CLI parsing — this is a novel surface. Validation pattern from the SDK that DOES translate: `kalshi/async_client.py:62-64` empty-string-rejection idiom.

---

### `kalshi/cli/app.py` (Textual `App` subclass)

**No close analog in the codebase.** Textual is novel. Use upstream Textual docs for `App`, `compose`, `Pilot.test_app`, `reactive[T]` descriptors.

**Conventions to carry over from the SDK:**

- File header: `"""Textual App for the kalshi watch cockpit."""` then `from __future__ import annotations` (matches every file in `kalshi/`).
- mypy strict — every method needs a return annotation, every reactive needs a typed descriptor.
- No central tick (eng-review locked this) — widgets reactive-subscribe to `state.py` slices; `lifecycle.py` mutates slices and Textual auto-refreshes.
- `App` owns the lifecycle worker via `App.run_worker(self.lifecycle.run, exclusive=True, exit_on_error=False)`. `App.exit()` cancels workers; `lifecycle.py` swallows `CancelledError` and awaits `KalshiWebSocket.close()` (mirrors `kalshi/ws/client.py:108-122` `_stop`).

**State plumbing (read-only v1):**
- App holds a single `Store` instance (from `state.py`), passes references to widgets via reactive descriptors.
- Use Textual's `reactive[OrderbookState]` on widgets that subscribe; the app sets `self.store.orderbook = new_value` in mutators and Textual auto-refreshes.

---

### `kalshi/cli/lifecycle.py` (worker — REST snapshot + WS delta merge + reconnect refresh)

**Analog:** `kalshi/ws/client.py:84-207` (`_start` / `_recv_loop` / reconnect handler)

**This is the load-bearing pattern.** Copy the shape:

```python
# kalshi/ws/client.py:84-122 — own connection + run loop + clean shutdown
async def _start(self) -> None:
    """Connect and initialize managers. Does NOT start recv_loop yet."""
    self._connection = ConnectionManager(
        auth=self._auth, config=self._config,
        heartbeat_timeout=self._heartbeat_timeout,
        on_state_change=self._on_state_change,
    )
    await self._connection.connect()
    # ... build sub_mgr, dispatcher, orderbook_mgr ...
    self._running = True

async def _stop(self) -> None:
    """Stop the receive loop and close the connection."""
    self._running = False
    if self._recv_task and not self._recv_task.done():
        self._recv_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._recv_task
    # ... send queue sentinels ...
    if self._connection:
        await self._connection.close()
```

**Reconnect-merge pattern (cockpit-specific addition):** copy reconnect detection from `kalshi/ws/client.py:182-203` (catch `ConnectionClosed`, call `self._connection.reconnect()`, clear orderbook, resubscribe), but ADD a fresh REST snapshot pull on reconnect — eng-review caught that `balance` is REST-only and account streams are event-only, so quiet reconnect = empty panels forever without a fresh REST seed.

**Connection-state callback (drives the header indicator):**

```python
# kalshi/ws/connection.py:84-91 — on_state_change signature
async def _set_state(self, new_state: ConnectionState) -> None:
    old = self._state
    self._state = new_state
    if self._on_state_change is not None:
        await self._on_state_change(old, new_state)
```

Lifecycle wires its own `_handle_state_change(old, new)` and pushes into `state.connection`. On `RECONNECTING → STREAMING` transition, dispatch the REST snapshot refresh.

**Frame-pump pattern (read iterator, mutate store):**

```python
# Pseudocode for lifecycle.pump_orderbook()
async def pump_orderbook(self, session: KalshiWebSocket, ticker: str) -> None:
    stream = await session.subscribe_orderbook_delta(tickers=[ticker])
    async for msg in stream:
        # Per spike: read full Orderbook from internal mgr
        book = session._orderbook_mgr.get(ticker)
        self.store.orderbook = OrderbookState(book=book, last_update=datetime.utcnow())
        self.store.tape.append(_format_delta(msg))
```

Compare with the dispatch test pattern in `tests/ws/test_dispatch.py:36-45` — the SDK already routes typed messages to queues; cockpit just consumes them.

---

### `kalshi/cli/state.py` (mutable dataclass slices)

**Analog:** `kalshi/ws/orderbook.py:16-108` (`OrderbookManager`)

This is the closest existing pattern: a mutable container with typed `apply_*` mutators. Match the shape:

```python
# kalshi/ws/orderbook.py:32-54 — mutable container + apply_* pattern
class OrderbookManager:
    def __init__(self) -> None:
        self._books: dict[str, Orderbook] = {}

    def apply_snapshot(self, msg: OrderbookSnapshotMessage) -> Orderbook:
        ticker = msg.msg.market_ticker
        # ... build levels ...
        book = Orderbook(ticker=ticker, yes=yes_levels, no=no_levels)
        self._books[ticker] = book
        logger.debug("Orderbook snapshot: %s ...", ticker)
        return book

    def apply_delta(self, msg: OrderbookDeltaMessage) -> Orderbook | None: ...
    def get(self, ticker: str) -> Orderbook | None: ...
    def clear(self) -> None: ...
```

**Differences for v1 cockpit:**

- `state.py` uses **mutable `@dataclass` slices** (eng-review locked — drop `frozen=True`). Reference: `kalshi/ws/sequence.py:14-21` for a simple dataclass:

  ```python
  # kalshi/ws/sequence.py:14-21
  @dataclass
  class SequenceGap:
      sid: int
      expected: int
      received: int
  ```

  Note: `SequenceGap` is NOT frozen. Match that.

- Slices: `MarketState`, `OrderbookState`, `PositionState`, `BalanceState`, `RestingOrdersState`, `ConnectionState`, `DeltaTapeLog`. Each holds its primary value plus a `last_update_ts: datetime | None`.

- Mutators are methods on a top-level `Store` class (mirroring `OrderbookManager`):
  ```python
  def replace_orderbook(self, book: Orderbook | None) -> None: ...
  def merge_user_order(self, msg: UserOrdersMessage) -> None: ...
  def append_tape(self, line: TapeLine) -> None: ...
  def replace_balance(self, balance: Balance) -> None: ...
  ```

- `DeltaTapeLog` should cap at N entries (e.g., 200) — use `collections.deque(maxlen=200)`.

**SDK-wide convention to imitate:**

- `from __future__ import annotations` at top.
- `from kalshi.models.markets import Orderbook` (use existing SDK types — don't re-define `OrderbookLevel`).
- `from kalshi.models.portfolio import Balance, MarketPosition` (auth-required — these come from REST snapshots).
- `logger = logging.getLogger("kalshi.cli")`.

---

### `kalshi/cli/edge.py` (pure math: edge / EV / max-loss / max-gain)

**Analog:** `kalshi/ws/orderbook.py:56-96` (`apply_delta` Decimal math) + `kalshi/types.py` (custom Pydantic types)

Match the convention of doing money math in `Decimal`, never `float`:

```python
# kalshi/ws/orderbook.py:67-72 — Decimal arithmetic on price/quantity
price = msg.msg.price  # Decimal via DollarDecimal
delta = msg.msg.delta  # Decimal via FixedPointCount
side = msg.msg.side
levels = book.yes if side == "yes" else book.no
```

**Imports pattern (SDK-wide):**

```python
from __future__ import annotations
from decimal import Decimal
```

**v1 functions (per design doc § Architecture Sketch):**

```python
# All inputs/outputs are Decimal (DollarDecimal-compatible)
def edge_yes(price: Decimal, fair: Decimal) -> Decimal:
    return fair - price

def edge_no(price: Decimal, fair: Decimal) -> Decimal:
    return (Decimal("1") - fair) - price

def max_loss_yes(price: Decimal) -> Decimal:
    return price

def max_gain_yes(price: Decimal) -> Decimal:
    return Decimal("1") - price

# Color saturation (clamp |edge| to [0, 0.30] then normalize to [0, 1])
def edge_intensity(edge: Decimal, max_edge: Decimal = Decimal("0.30")) -> float:
    abs_edge = abs(edge)
    if abs_edge < Decimal("0.005"):
        return 0.0
    return float(min(abs_edge, max_edge) / max_edge)
```

For binary contracts `edge_yes == ev_yes` (eng-review caught this — single function, not separate). Test pattern: table-driven (12+ pairs), see `tests/ws/test_orderbook.py:74-90` for example shape.

---

### `kalshi/cli/widgets/*.py` (Textual widgets)

**No close analog in the codebase.** Textual is novel.

**SDK conventions to carry into widgets:**
- `from __future__ import annotations`
- mypy strict — every reactive descriptor and event handler needs annotations
- Logger: `logger = logging.getLogger("kalshi.cli")`
- Use `kalshi.models.markets.Orderbook`, `OrderbookLevel`, `kalshi.models.portfolio.MarketPosition`, etc. directly — don't re-shape SDK models in widget code

**Per-widget specifics:**

| Widget | Reactive subscription | Renders |
|--------|----------------------|---------|
| `header.py` | `MarketState`, `ConnectionState` | ticker, title, status, close countdown (`market.close_time` → `timedelta`), 1-char conn-state indicator (●/◐/○) |
| `orderbook.py` | `OrderbookState` (+ `--fair` from app config) | YES/NO ladder; calls `edge.edge_yes / edge_no / edge_intensity` per level for coloring; stale tint when `ConnectionState != CONNECTED` |
| `positions.py` | `PositionState`, `BalanceState` | one row per position + balance footer |
| `orders.py` | `RestingOrdersState` | one row per resting order (read-only, no `x` cancel in v1) |
| `rule.py` | `MarketState` | `market.rules_primary` (and `rules_secondary` if present) — see `kalshi/models/markets.py:128-129` |
| `tape.py` | `DeltaTapeLog` | `[HH:MM:SS.mmm side price size]` lines + `[disconnect]` / `[resync]` markers |
| `too_small.py` | terminal dimensions | static overlay at <100×30 |

**Stale-tint trigger** comes from comparing `state.connection.state == ConnectionState.RECONNECTING` (note: the cockpit's own `ConnectionState` enum — not the SDK's `kalshi.ws.connection.ConnectionState`). Decide naming to avoid confusion at build time.

---

### `tests/cli/conftest.py`

**Analogs (composed):**

1. `tests/conftest.py:1-49` — RSA key + auth + config fixtures (REUSE, don't redefine; tests/cli will see these via pytest fixture discovery from `tests/conftest.py`).
2. `tests/ws/conftest.py:16-171` — `FakeKalshiWS` server fixture (REUSE for full-stack CLI tests that need a real WS endpoint).
3. `tests/integration/conftest.py:108-135` — async client fixture pattern.

**New fixtures `tests/cli/conftest.py` should provide:**

```python
# Mock the AsyncKalshiClient for unit tests
@pytest.fixture
def mock_async_client(monkeypatch, test_auth, test_config):
    """An AsyncKalshiClient with respx-mocked transport + fake_ws WebSocket."""
    # Wire AsyncTransport with respx, KalshiWebSocket with FakeKalshiWS

@pytest.fixture
def sample_market() -> Market:
    """A canonical Market fixture used across widget render tests."""

@pytest.fixture
def sample_orderbook() -> Orderbook:
    """A canonical Orderbook with both sides populated."""

@pytest.fixture
def store():
    """A fresh Store instance with auth flag set."""
```

**Pattern for respx-mocked async client** — see `tests/test_async_markets.py` and `tests/test_markets.py:20-32`:

```python
# tests/test_markets.py:20-32 — respx fixture for HTTP mocking
@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )

@pytest.fixture
def markets(test_auth: KalshiAuth, config: KalshiConfig) -> MarketsResource:
    return MarketsResource(SyncTransport(test_auth, config))
```

---

### `tests/cli/test_main.py` (Typer surface)

**Analog:** `tests/test_async_client.py` (constructor / from_env tests) for shape; **Typer's `CliRunner` for the actual mechanics** — novel.

Match the test class structure:

```python
# tests/test_markets.py:34-72 — class-based test grouping
class TestMarketsList:
    @respx.mock
    def test_returns_page_of_markets(self, markets: MarketsResource) -> None: ...
    def test_market_type_kwarg_removed(self, markets: MarketsResource) -> None: ...
```

For `test_main.py`:
- `class TestKalshiHelp` — `--help` exits 0, mentions `watch`
- `class TestKalshiWatchCommand` — `watch --help` lists `--fair`, `--live`, `--refresh-ms`
- Use `typer.testing.CliRunner` (Typer convention; novel to this repo)

---

### `tests/cli/test_watch.py` (bootstrap — auth-required, REST seed)

**Analog:** `tests/test_async_client.py` (env-var handling) + `tests/integration/conftest.py:82-99` (`_assert_demo_url` safety check)

Pattern: monkeypatch env vars, instantiate a `CliRunner`, assert exit code + stderr message.

```python
# tests/integration/conftest.py:82-99 — credentials gating pattern
def _credentials_available() -> bool:
    return bool(os.environ.get("KALSHI_KEY_ID"))
```

Adapt for the CLI:

```python
def test_watch_without_auth_exits_clean(monkeypatch):
    monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
    result = CliRunner().invoke(app, ["watch", "TICKER"])
    assert result.exit_code != 0
    assert "KALSHI_KEY_ID" in result.stderr
```

---

### `tests/cli/test_app.py` (Textual smoke test)

**No close analog.** Use Textual's `App.run_test()` / `Pilot` — novel to this repo. v1 explicitly defers pixel-exact snapshot tests (design doc § Open Questions).

Match SDK conventions: `from __future__ import annotations`, type-annotated test methods.

---

### `tests/cli/test_lifecycle.py` (worker shutdown / reconnect / REST refresh)

**Analog:** `tests/ws/test_client.py:15-49` (lifecycle / state callback tests)

Direct shape match — fake_ws fixture from `tests/ws/conftest.py`, exercise connect/close/state-change callbacks:

```python
# tests/ws/test_client.py:23-29 — close-sets-state pattern to copy
async def test_close_sets_state(self, fake_ws, test_auth) -> None:
    config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
    ws = KalshiWebSocket(auth=test_auth, config=config)
    async with ws.connect():
        pass
    assert ws._connection is not None
    assert ws._connection.state == ConnectionState.CLOSED
```

Cockpit-specific tests on top:
- REST snapshot fires on initial mount (assert `client.markets.get` called).
- REST snapshot fires AGAIN on `RECONNECTING → STREAMING` transition.
- WS frame consumed → store mutated → assert specific slice value.
- Worker raises → app surfaces via Textual notification, no zombie tasks.

---

### `tests/cli/test_state.py`

**Analog:** `tests/ws/test_orderbook.py:58-100` (`apply_snapshot` / `apply_delta` table-driven tests)

Match exactly:

```python
# tests/ws/test_orderbook.py:58-72 — pattern to copy
class TestOrderbookManager:
    def test_apply_snapshot(self) -> None:
        mgr = OrderbookManager()
        book = mgr.apply_snapshot(
            make_snapshot(yes=[["0.50", "100.00"], ["0.55", "200.00"]],
                          no=[["0.45", "150.00"]])
        )
        assert book.ticker == "T"
        assert len(book.yes) == 2
```

For `test_state.py`:
- `TestStoreReplace` — REST snapshot replaces a slice atomically
- `TestStoreMerge` — WS frame merges into existing slice
- `TestTapeCap` — `DeltaTapeLog` caps at maxlen

Use the `make_snapshot` / `make_delta` helpers from `tests/ws/test_orderbook.py:14-55` — copy them into `tests/cli/conftest.py` or reference via shared module.

---

### `tests/cli/test_edge.py`

**Analog:** `tests/ws/test_orderbook.py` for table-driven Decimal math pattern

```python
# Pattern: parametrize, all-Decimal, cover edge cases (fair=0, fair=1, fair=0.5)
@pytest.mark.parametrize("price,fair,expected", [
    (Decimal("0.50"), Decimal("0.63"), Decimal("0.13")),
    (Decimal("0.70"), Decimal("0.63"), Decimal("-0.07")),
    # ... 12+ pairs from test plan ...
])
def test_edge_yes(price: Decimal, fair: Decimal, expected: Decimal) -> None:
    assert edge_yes(price, fair) == expected
```

---

### `tests/cli/test_widgets_*.py`

**No close analog.** Use Textual's `Pilot` for widget testing. Render-and-snapshot is explicitly deferred (design doc § Open Questions #2). Focus on: widget-given-store-renders-without-exception + slice-mutation-triggers-reactive-refresh.

---

### `tests/cli/test_contracts.py` (cockpit ↔ SDK shape drift, hard-fail)

**Analog:** `tests/test_contracts.py:961-1217` (`TestRequestParamDrift` + `TestRequestBodyDrift`)

**Mirror this pattern exactly.** The cockpit's drift-source is different (cockpit code reads `Market.ticker`, `Market.title`, `Market.close_time`, `Market.rules_primary`, `Event.title`, `MarketPosition.position`, `Order.order_id`, etc.), but the test mechanism is identical: parametrize over a list of (cockpit-symbol → SDK-model-field) entries, assert the SDK model still has that field.

```python
# tests/test_contracts.py:961-988 — parametrize-over-map pattern
@pytest.mark.parametrize(
    "entry",
    [e for e in METHOD_ENDPOINT_MAP if e.http_method in ("GET", "DELETE")],
    ids=[e.sdk_method.rsplit(".", 1)[1] for e in METHOD_ENDPOINT_MAP if ...],
)
class TestRequestParamDrift:
    """Hard-fails via pytest.fail (NOT warnings.warn). Request-side drift
    is a user-facing capability gap."""

    spec: dict[str, Any]

    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.spec = _load_spec()

    def test_sync_params_match_spec(self, entry: MethodEndpointEntry) -> None:
        self._assert_params_match(entry, async_=False)
```

**For cockpit:** the parametrize source is a new `COCKPIT_FIELD_DEPS` list, e.g.:

```python
# tests/cli/test_contracts.py
@dataclass(frozen=True)
class CockpitFieldDep:
    """One field the cockpit reads from an SDK model."""
    sdk_model_fqn: str       # "kalshi.models.markets.Market"
    field_name: str          # "close_time"
    cockpit_consumer: str    # "kalshi.cli.widgets.header"

COCKPIT_FIELD_DEPS = [
    CockpitFieldDep("kalshi.models.markets.Market", "ticker", "kalshi.cli.widgets.header"),
    CockpitFieldDep("kalshi.models.markets.Market", "title", "kalshi.cli.widgets.header"),
    CockpitFieldDep("kalshi.models.markets.Market", "close_time", "kalshi.cli.widgets.header"),
    CockpitFieldDep("kalshi.models.markets.Market", "rules_primary", "kalshi.cli.widgets.rule"),
    CockpitFieldDep("kalshi.models.portfolio.MarketPosition", "position", "kalshi.cli.widgets.positions"),
    CockpitFieldDep("kalshi.models.portfolio.Balance", "balance", "kalshi.cli.widgets.positions"),
    CockpitFieldDep("kalshi.models.orders.Order", "order_id", "kalshi.cli.widgets.orders"),
    CockpitFieldDep("kalshi.models.orders.Order", "status", "kalshi.cli.widgets.orders"),
    CockpitFieldDep("kalshi.ws.models.orderbook_delta.OrderbookDeltaPayload", "price", "kalshi.cli.widgets.tape"),
    CockpitFieldDep("kalshi.ws.models.orderbook_delta.OrderbookDeltaPayload", "delta", "kalshi.cli.widgets.tape"),
    CockpitFieldDep("kalshi.ws.models.orderbook_delta.OrderbookDeltaPayload", "side", "kalshi.cli.widgets.tape"),
    # ... see test plan for full list ...
]
```

Reuse `_get_sdk_model_class` from `tests/test_contracts.py:318-322` (or import the helper). Hard-fail (`pytest.fail`), not `warnings.warn` — a missing field means a widget will `AttributeError` at render time.

**Match the WS payload type drift test pattern at `tests/test_contracts.py:849-882`** for WS shapes the cockpit reads (`OrderbookDeltaPayload`, `Ticker`, `Trade`, `Fill`, `UserOrders`).

---

### `tests/cli/integration/conftest.py`

**Analog:** `tests/integration/conftest.py:82-271`

REUSE existing fixtures via shared discovery (pytest discovers `tests/conftest.py` and `tests/integration/conftest.py` from subdirectories). The cockpit integration tests can import the existing `async_client`, `demo_market_ticker`, `ws_session` fixtures directly.

```python
# tests/integration/conftest.py:125-134 — async_client pattern
@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncKalshiClient]:
    if not _credentials_available():
        pytest.skip("KALSHI_KEY_ID not set — skipping integration tests")
    os.environ.setdefault("KALSHI_DEMO", "true")
    client = AsyncKalshiClient.from_env()
    _assert_demo_url(client._config.base_url, client._config.ws_base_url)
    yield client
    with contextlib.suppress(RuntimeError):
        await client.close()
```

`_assert_demo_url` (`tests/integration/conftest.py:86-99`) hard-fails if not pointed at demo — copy this safety check to the cockpit integration suite.

**New cockpit-specific fixture:** spawn the Textual app under `Pilot` against a real demo ticker. Use `App.run_test()` (Textual API).

---

### `tests/cli/integration/test_watch.py` (E2E demo flow)

**Analog:** `tests/integration/test_websocket.py:14-130`

Match the test class structure + retry decorator:

```python
# tests/integration/test_websocket.py:14-29 — class header pattern
@pytest.mark.integration
@pytest.mark.asyncio
class TestWebSocketLive:
    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_connect_and_auth(
        self, ws_session: KalshiWebSocket
    ) -> None: ...
```

For cockpit:

```python
@pytest.mark.integration
@pytest.mark.asyncio
class TestCockpitDemo:
    @retry_transient(max_retries=2, delay=1.0)
    async def test_authed_flow(
        self, async_client: AsyncKalshiClient, demo_market_ticker: str
    ) -> None:
        """Mount cockpit, verify orderbook fills, header renders."""

    @retry_transient(max_retries=2, delay=1.0)
    async def test_lifecycle_reconnect_with_rest_refresh(self, ...): ...

    @retry_transient(max_retries=2, delay=1.0)
    async def test_sequence_gap_resync(self, ...): ...
```

---

## Shared Patterns (Apply to All Files)

### Pattern S1: `from __future__ import annotations`
**Source:** every file in `kalshi/`. Example: `kalshi/ws/client.py:2`, `kalshi/_base_client.py:7`.
**Apply to:** every new `.py` file in `kalshi/cli/` and `tests/cli/`.

### Pattern S2: Module-level logger
**Source:** `kalshi/ws/client.py:36`
```python
logger = logging.getLogger("kalshi.ws")
```
**Apply to:** `kalshi/cli/lifecycle.py`, `kalshi/cli/state.py`, `kalshi/cli/app.py`, etc. — use `"kalshi.cli"` as the logger name.

### Pattern S3: `Decimal`-only money math
**Source:** `kalshi/types.py` (`DollarDecimal`), `kalshi/ws/orderbook.py:67-72`.
**Apply to:** `kalshi/cli/edge.py`, anything in `widgets/orderbook.py` and `widgets/positions.py` that does math. Never `float`. The `--fair PROB` Typer arg should be parsed as `Decimal` immediately on entry.

### Pattern S4: Auth fail-fast at the surface
**Source:** `kalshi/resources/portfolio.py:21` (`self._require_auth()` first line of every authed method); `kalshi/async_client.py:128-132` (raise `AuthRequiredError` for ws property).
**Apply to:** `kalshi/cli/watch.py` checks `client.is_authenticated` BEFORE mounting Textual; exit 2 with a stderr message pointing at demo-creds docs.

### Pattern S5: `respx.mock` for HTTP unit tests
**Source:** `tests/test_markets.py:35-54`.
**Apply to:** `tests/cli/test_lifecycle.py` (REST snapshot), `tests/cli/test_watch.py` (bootstrap), `tests/cli/test_state.py` (REST seed).

### Pattern S6: `FakeKalshiWS` for WebSocket unit tests
**Source:** `tests/ws/conftest.py:16-171` + `tests/ws/test_client.py:15-49`.
**Apply to:** `tests/cli/test_lifecycle.py` for full reconnect-and-merge tests without hitting demo.

### Pattern S7: `@pytest.mark.integration` + `@retry_transient` for demo E2E
**Source:** `tests/integration/test_websocket.py:14-29`.
**Apply to:** `tests/cli/integration/test_watch.py`. Demo network is flaky; retries are expected.

### Pattern S8: mypy strict — `builtins.list[T]` inside resource classes
**Source:** `kalshi/resources/markets.py:5` (`import builtins`), then `builtins.list[str]` in signatures. See CLAUDE.md "List builtin shadowed by `.list()` methods."
**Apply to:** `state.py` if it has a `.list()` method on `Store`. Probably won't trigger here (cockpit `state.py` mutators are named `merge_*`, `replace_*`), but worth flagging.

### Pattern S9: Test class grouping with descriptive names
**Source:** `tests/test_markets.py:34` (`class TestMarketsList`), `tests/ws/test_orderbook.py:58` (`class TestOrderbookManager`).
**Apply to:** all `tests/cli/test_*.py` files. Group by feature (e.g., `class TestStoreMutators`, `class TestEdgeYes`, `class TestLifecycleReconnect`).

### Pattern S10: Drift-test exclusion allowlist with required `reason`
**Source:** `tests/_contract_support.py:39-47` (`Exclusion` dataclass, `reason` field required).
**Apply to:** `tests/cli/test_contracts.py` if any cockpit field intentionally diverges from the SDK model field name. Carry the `reason` discipline.

### Pattern S11: Demo URL safety assertion
**Source:** `tests/integration/conftest.py:86-99` (`_assert_demo_url`).
**Apply to:** `tests/cli/integration/conftest.py` — hard-fail if cockpit integration tests are accidentally pointed at production.

---

## No Analog Found

These files have no close codebase analog because the underlying tech (Textual) is novel:

| File | Role | Reason |
|------|------|--------|
| `kalshi/cli/app.py` | Textual `App` shell | First Textual code in repo — use upstream Textual docs |
| `kalshi/cli/widgets/*.py` (7 files) | Textual widgets with reactive descriptors | Same |
| `tests/cli/test_app.py` | Textual smoke test | Use `App.run_test()` — Textual API |
| `tests/cli/test_widgets_*.py` (2 files) | Widget render tests with `Pilot` | Same |

For these, follow Textual's documented patterns and apply SDK-wide conventions (S1, S2, S3, S8) as a baseline.

---

## Metadata

**Analog search scope:** `kalshi/`, `tests/`, `pyproject.toml`
**Files scanned:** ~40 source + test files
**Pattern extraction date:** 2026-04-24
**Source-of-truth design:** `~/.gstack/projects/kalshi-python-sdk/jeffreywest-main-design-20260424-190736.md`
**Source-of-truth test plan:** `~/.gstack/projects/kalshi-python-sdk/jeffreywest-main-eng-review-test-plan-20260424-192732.md`
