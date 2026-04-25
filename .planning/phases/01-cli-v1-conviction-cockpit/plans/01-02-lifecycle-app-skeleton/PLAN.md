---
phase: 01-cli-v1-conviction-cockpit
plan: 02
type: execute
wave: 2
depends_on: [01]
files_modified:
  - kalshi/cli/main.py
  - kalshi/cli/watch.py
  - kalshi/cli/app.py
  - kalshi/cli/lifecycle.py
  - kalshi/cli/widgets/__init__.py
  - kalshi/cli/widgets/header.py
  - tests/cli/test_main.py
  - tests/cli/test_watch.py
  - tests/cli/test_app.py
  - tests/cli/test_lifecycle.py
autonomous: true
requirements: [CLI-01, CLI-02, CLI-03, CLI-04, CLI-07, CLI-08, CLI-09, CLI-12, CLI-Q01, CLI-Q02]
must_haves:
  truths:
    - "`kalshi --help` exits 0 and lists `watch` as a subcommand"
    - "`kalshi watch TICKER --fair 1.5` rejects via Typer validation (probability must be in [0, 1])"
    - "`kalshi watch TICKER` with no auth env vars exits non-zero BEFORE Textual mounts, with a stderr message naming both KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH and a docs link"
    - "`kalshi watch TICKER` with auth env vars launches the Textual App against demo and the header widget renders ticker + close countdown + 1-char connection-state indicator"
    - "WSLifecycle worker fetches REST snapshot (markets.get + portfolio.balance + portfolio.positions + orders.list) on initial mount AND again on RECONNECTING→STREAMING transition"
    - "Ctrl-C exits cleanly: worker cancelled, KalshiWebSocket.close() awaited, no zombie tasks reported by asyncio"
    - "Worker raises unexpected exception → surfaces via Textual notification, app exits cleanly (no traceback to terminal)"
  artifacts:
    - path: "kalshi/cli/main.py"
      provides: "Typer app + watch subcommand registration"
      contains: "app = typer.Typer"
    - path: "kalshi/cli/watch.py"
      provides: "watch_command function (exposed as `kalshi watch TICKER`); auth fail-fast"
      contains: "def watch_command"
    - path: "kalshi/cli/app.py"
      provides: "CockpitApp(textual.App) — owns Store + spawns lifecycle worker"
      contains: "class CockpitApp"
    - path: "kalshi/cli/lifecycle.py"
      provides: "WSLifecycle: REST snapshot + on_state_change wiring + WS subscribe pumps"
      contains: "class WSLifecycle"
    - path: "kalshi/cli/widgets/header.py"
      provides: "HeaderWidget rendering ticker, title, close countdown, conn-state indicator"
      contains: "class HeaderWidget"
  key_links:
    - from: "kalshi/cli/lifecycle.py"
      to: "kalshi.ws.client.KalshiWebSocket"
      via: "async with ws.connect() inside Textual worker; on_state_change callback drives store.set_connection"
      pattern: "on_state_change"
    - from: "kalshi/cli/lifecycle.py"
      to: "kalshi.async_client.AsyncKalshiClient (markets/portfolio/orders)"
      via: "REST snapshot fetched on mount and on RECONNECTING→STREAMING transition; replaces store.market/balance/positions/resting_orders"
      pattern: "client.markets.get|client.portfolio|client.orders.list"
    - from: "kalshi/cli/app.py"
      to: "kalshi/cli/lifecycle.py"
      via: "App.run_worker(self.lifecycle.run, exclusive=True, exit_on_error=False); App.exit cancels worker"
      pattern: "run_worker"
    - from: "kalshi/cli/watch.py"
      to: "kalshi.async_client.AsyncKalshiClient"
      via: "from_env() + is_authenticated check before mounting Textual"
      pattern: "is_authenticated"
---

<objective>
Wire the load-bearing seam: Typer entrypoint → AsyncKalshiClient.from_env (auth-required
fail-fast) → Textual App → WSLifecycle worker that owns the WS connection, pumps REST
snapshots, and drives the connection-state slice. Ship the header widget as the *only*
widget so we can validate the end-to-end seam against demo before fanning out to the
ladder/positions/orders/rule/tape widgets in Wave 3.

This is the equivalent of the original "WS-lifecycle seam spike" — but it's not a throw-
away: every line written here ships. PATTERNS.md § Spike 2 confirmed the seam works
(KalshiWebSocket.__init__ accepts on_state_change; reconnect drives state transitions
internally; cancellation propagates cleanly through `async with ws.connect()`).

Purpose: This plan is the synchronization point of the phase. Every Wave 3 widget plan
attaches to the Store + ConnectionState slices that THIS plan plumbs end-to-end. If the
seam is broken here, every widget plan is broken downstream.

Output: 5 source files (`main.py`, `watch.py`, `app.py`, `lifecycle.py`, `widgets/header.py`)
+ 4 test files. After this plan, `kalshi watch <real demo ticker>` against demo shows a
header widget with live close-countdown and connection-state indicator, and survives
Ctrl-C cleanly.
</objective>

<execution_context>
@/Users/jeffreywest/Code/Python/kalshi-python-sdk/.planning/phases/01-cli-v1-conviction-cockpit/PATTERNS.md
@/Users/jeffreywest/.gstack/projects/kalshi-python-sdk/jeffreywest-main-design-20260424-190736.md
@/Users/jeffreywest/.gstack/projects/kalshi-python-sdk/jeffreywest-main-eng-review-test-plan-20260424-192732.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/phases/01-cli-v1-conviction-cockpit/plans/01-01-state-edge-and-contracts/PLAN.md
@CLAUDE.md

# Lifecycle analog — copy this pattern
@kalshi/ws/client.py
@kalshi/ws/connection.py
@kalshi/ws/dispatch.py
@kalshi/ws/orderbook.py

# Auth + client
@kalshi/async_client.py
@kalshi/auth.py

# REST resources we'll snapshot
@kalshi/resources/markets.py
@kalshi/resources/portfolio.py
@kalshi/resources/orders.py

# Test fixtures + analogs
@tests/conftest.py
@tests/ws/conftest.py
@tests/ws/test_client.py
@tests/integration/conftest.py

<seam_facts>
From PATTERNS.md § Spike 2 (already validated against the codebase):

1. KalshiWebSocket(__init__, *, auth, config, on_state_change=callback) at kalshi/ws/client.py:56-78.
   Pass an async callback `_handle_state_change(old: SDKConnState, new: SDKConnState) -> None`.
   The lifecycle worker translates SDK state → cockpit's CockpitConnectionState slice.

2. The SDK's reconnect lifecycle is internal — `_recv_loop` (kalshi/ws/client.py:137-207)
   catches `ConnectionClosed`, calls `self._connection.reconnect()` which transitions
   RECONNECTING→CONNECTING→CONNECTED→STREAMING. On reconnect the SDK clears its internal
   orderbook (mgr.clear()) and resubscribes — we do NOT need to re-call subscribe_*
   methods. We just need to detect the RECONNECTING→STREAMING transition in our
   callback and re-fetch REST snapshots.

3. Pump pattern (one Textual worker fans out 5 channels via asyncio.gather):
       async with ws.connect() as session:
           await asyncio.gather(
               self._pump_orderbook(session),
               self._pump_ticker(session),
               self._pump_trade(session),
               self._pump_fill(session),
               self._pump_user_orders(session),
           )

4. OrderbookManager access: after each orderbook_delta frame, read the *full* updated
   Orderbook reference via `session._orderbook_mgr.get(ticker)` (PATTERNS.md notes this
   is private-attribute access acceptable for v1 — same pattern as
   `tests/integration/test_websocket.py:30`). DO NOT replicate the delta-merge math —
   the SDK already did it.

5. Cancellation: Textual's `worker.cancel()` raises `CancelledError` into the worker
   coroutine. `async with ws.connect()` __aexit__ calls _stop() which cancels the recv
   task with `contextlib.suppress(asyncio.CancelledError)`, drains queues, and closes
   the connection. We do NOT need to suppress CancelledError ourselves — let it propagate.
</seam_facts>

<rest_snapshot_targets>
On mount and every RECONNECTING→STREAMING transition, lifecycle re-fetches:

  market = await client.markets.get(ticker)
  → store.replace_market(market)

  balance = await client.portfolio.get_balance()  # verify the exact method name in kalshi/resources/portfolio.py
  → store.replace_balance(balance)

  positions_response = await client.portfolio.list_positions(ticker=ticker)  # filter to current ticker
  → store.replace_positions(positions_response.market_positions)  # or whatever the field is

  orders_response = await client.orders.list(ticker=ticker, status="resting")
  → store.replace_resting_orders(orders_response.orders)

VERIFY each method name + return shape via `grep -n "def " kalshi/resources/portfolio.py`
and `kalshi/resources/orders.py` BEFORE writing the lifecycle code. The exact method
names matter; do not guess.
</rest_snapshot_targets>

<interfaces>
```python
# kalshi/cli/lifecycle.py — public surface

from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from kalshi.async_client import AsyncKalshiClient
from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.connection import ConnectionState as SDKConnectionState

from kalshi.cli.state import (
    Store,
    CockpitConnectionState,
    TapeLine,
)

logger = logging.getLogger("kalshi.cli")


class WSLifecycle:
    """Owns the WebSocket session for the lifetime of the App.

    Spawned via App.run_worker. On run():
      1. Fetch REST snapshot, populate store slices.
      2. Open `async with self.ws.connect() as session:`.
      3. asyncio.gather all subscribe-pump coroutines.
      4. on_state_change callback drives store.connection slice + triggers REST refresh
         on RECONNECTING→STREAMING.

    Cancellation: lets CancelledError propagate; ws.connect()'s __aexit__ handles cleanup.
    """

    def __init__(self, *, client: AsyncKalshiClient, ticker: str, store: Store) -> None:
        self.client = client
        self.ticker = ticker
        self.store = store
        self._ws: KalshiWebSocket | None = None
        self._last_sdk_state: SDKConnectionState | None = None

    async def run(self) -> None: ...

    async def _fetch_rest_snapshot(self) -> None:
        """Fetch market + balance + positions + resting orders, replace store slices."""
        ...

    async def _handle_state_change(
        self, old: SDKConnectionState, new: SDKConnectionState
    ) -> None:
        """Called by KalshiWebSocket on every internal state transition.
        Maps SDK state → cockpit CockpitConnectionState. On RECONNECTING→STREAMING,
        spawns a REST refresh task (does NOT block this callback)."""
        ...

    async def _pump_orderbook(self, session: KalshiWebSocket) -> None: ...
    async def _pump_ticker(self, session: KalshiWebSocket) -> None: ...
    async def _pump_trade(self, session: KalshiWebSocket) -> None: ...
    async def _pump_fill(self, session: KalshiWebSocket) -> None: ...
    async def _pump_user_orders(self, session: KalshiWebSocket) -> None: ...
```

```python
# kalshi/cli/app.py — public surface

from textual.app import App, ComposeResult
from textual.reactive import reactive

from kalshi.async_client import AsyncKalshiClient
from kalshi.cli.lifecycle import WSLifecycle
from kalshi.cli.state import Store
from kalshi.cli.widgets.header import HeaderWidget


class CockpitApp(App[None]):
    """Top-level Textual app. Wave 2 ships header-only; Wave 3 adds widgets via compose()."""

    CSS = """..."""  # minimal layout
    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self, *, client: AsyncKalshiClient, ticker: str, fair: Decimal | None) -> None: ...

    def compose(self) -> ComposeResult:
        yield HeaderWidget(store=self.store)
        # Wave 3 plans add: OrderbookWidget, RuleWidget, TapeWidget, TooSmallOverlay, etc.

    async def on_mount(self) -> None:
        """Spawn the lifecycle worker."""
        self.run_worker(self.lifecycle.run, exclusive=True, exit_on_error=False)
```

```python
# kalshi/cli/widgets/header.py — public surface

from textual.reactive import reactive
from textual.widget import Widget

from kalshi.cli.state import Store, MarketState, ConnectionStateSlice


class HeaderWidget(Widget):
    """Renders: ticker | title | close countdown (H:MM:SS or MM:SS or EXPIRED) | conn-state indicator (●/◐/○)."""

    market: reactive[MarketState | None] = reactive(None)
    connection: reactive[ConnectionStateSlice | None] = reactive(None)

    def __init__(self, *, store: Store) -> None: ...

    def render(self) -> str: ...  # Rich-formatted string or Renderable

    def on_mount(self) -> None:
        """Subscribe to store.market and store.connection — Textual's reactive
        descriptors auto-refresh when these change."""
```

```python
# kalshi/cli/main.py — Typer entry point

from __future__ import annotations
import typer

from kalshi.cli.watch import watch_command

app = typer.Typer(no_args_is_help=True, help="Kalshi SDK CLI — Conviction Cockpit")
app.command(name="watch")(watch_command)
```

```python
# kalshi/cli/watch.py — public surface

from __future__ import annotations
import os
import sys
from decimal import Decimal
from typing import Annotated

import typer

from kalshi.async_client import AsyncKalshiClient


def _validate_fair(value: float | None) -> Decimal | None:
    if value is None:
        return None
    if not 0 <= value <= 1:
        raise typer.BadParameter("--fair must be in [0, 1]")
    return Decimal(str(value))


def watch_command(
    ticker: Annotated[str, typer.Argument(help="Market ticker, e.g. PRES-2024-DJT")],
    fair: Annotated[float | None, typer.Option("--fair", help="Your fair-probability thesis (0-1)", callback=_validate_fair)] = None,
    live: Annotated[bool, typer.Option("--live", help="Use production API (requires auth env vars)")] = False,
) -> None:
    """Open the conviction cockpit for TICKER."""
    ...
```
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: main.py + watch.py with Typer surface + auth fail-fast</name>
  <files>
    kalshi/cli/main.py,
    kalshi/cli/watch.py,
    tests/cli/test_main.py,
    tests/cli/test_watch.py
  </files>
  <behavior>
    `tests/cli/test_main.py` (using `typer.testing.CliRunner`):
      `class TestKalshiHelp`:
        - `kalshi --help` exits 0 (CliRunner: result.exit_code == 0).
        - stdout contains "watch".
      `class TestKalshiWatchHelp`:
        - `kalshi watch --help` exits 0.
        - stdout lists `--fair`, `--live`, `TICKER` argument.
      `class TestFairValidation`:
        - `kalshi watch T --fair 1.5` exits non-zero, stderr mentions "[0, 1]".
        - `kalshi watch T --fair -0.1` exits non-zero.
        - `kalshi watch T --fair 0.0` parses to Decimal("0").
        - `kalshi watch T --fair 1.0` parses to Decimal("1").
        - `kalshi watch T --fair 0.63` parses to Decimal("0.63").

    `tests/cli/test_watch.py` (with monkeypatch on env vars + AsyncKalshiClient mocked):
      `class TestAuthFailFast`:
        - missing `KALSHI_KEY_ID` → exit 2, stderr names both env vars + has the docs link.
        - missing `KALSHI_PRIVATE_KEY_PATH` → same.
        - both set but invalid → AsyncKalshiClient.from_env succeeds (auth construction is
          lazy — actual signing fails at first authed request); is_authenticated returns
          True; watch proceeds to mount Textual. Mock the App so we don't actually run.
      `class TestLiveFlag`:
        - `--live` with both env vars → AsyncKalshiClient.from_env(demo=False) called.
        - no `--live` → demo=True (default).
        - `--live` without env vars → exit 2 (auth fail-fast still wins).

    Mock the Textual App run via monkeypatch — assert `CockpitApp.run` was called with the
    expected kwargs, but don't actually mount the TUI in the test.
  </behavior>
  <action>
    1. RED: write `tests/cli/test_main.py` and `tests/cli/test_watch.py` with the test
       classes above. Use `typer.testing.CliRunner` (Typer convention).

       For test_watch.py mocking: import the `app` from `kalshi.cli.main`, then
       monkeypatch `kalshi.cli.watch.CockpitApp` to a MagicMock that captures kwargs.
       Confirm assertions on the mock.

    2. GREEN: implement `kalshi/cli/main.py` (5 lines — just register the watch subcommand).

    3. GREEN: implement `kalshi/cli/watch.py`:

       ```python
       def watch_command(
           ticker: Annotated[str, typer.Argument(...)],
           fair: Annotated[float | None, typer.Option("--fair", callback=_validate_fair)] = None,
           live: Annotated[bool, typer.Option("--live")] = False,
       ) -> None:
           # 1. Auth fail-fast (BEFORE building the client, since from_env returns an
           #    unauthenticated client if env vars missing — but we want a clear error,
           #    not "AuthRequiredError" later).
           if not os.environ.get("KALSHI_KEY_ID") or not (
               os.environ.get("KALSHI_PRIVATE_KEY") or os.environ.get("KALSHI_PRIVATE_KEY_PATH")
           ):
               typer.echo(
                   "ERROR: KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH must be set.\n"
                   "Free demo creds: https://docs.kalshi.com/getting-started",
                   err=True,
               )
               raise typer.Exit(code=2)

           # 2. Build client (demo by default; --live → production)
           client = AsyncKalshiClient.from_env(demo=not live)

           # 3. Defense-in-depth: re-check is_authenticated. (try_from_env may have failed
           #    silently for unrelated reasons, e.g. unreadable PEM file.)
           if not client.is_authenticated:
               typer.echo("ERROR: client constructed without auth — check KALSHI_PRIVATE_KEY_PATH points at a readable PEM.", err=True)
               raise typer.Exit(code=2)

           # 4. Cast --fair to Decimal (the callback already validated range).
           fair_decimal = Decimal(str(fair)) if fair is not None else None

           # 5. Mount the Textual app.
           from kalshi.cli.app import CockpitApp
           app = CockpitApp(client=client, ticker=ticker, fair=fair_decimal)
           app.run()
       ```

       Note the lazy import of `CockpitApp` — keeps `kalshi.cli.main` importable without
       Textual installed (helpful for `kalshi --help` smoke tests in environments where
       only `typer` is on PYTHONPATH).

    4. Verify Typer's BadParameter behavior in `_validate_fair` returns the right exit
       code (Typer maps to exit 2 by default).

    5. mypy strict + ruff clean. Use `from __future__ import annotations`.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/test_main.py tests/cli/test_watch.py -v && uv run mypy kalshi/cli/main.py kalshi/cli/watch.py && uv run ruff check kalshi/cli/main.py kalshi/cli/watch.py tests/cli/test_main.py tests/cli/test_watch.py</automated>
  </verify>
  <done>
    `kalshi --help` works (manually verifiable: `uv run kalshi --help`). All Typer surface
    + auth fail-fast tests green. mypy + ruff clean.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: lifecycle.py + test_lifecycle.py (REST snapshot + WS pump + reconnect refresh)</name>
  <files>
    kalshi/cli/lifecycle.py,
    tests/cli/test_lifecycle.py
  </files>
  <behavior>
    `tests/cli/test_lifecycle.py` (uses respx for REST + FakeKalshiWS for WS):

    `class TestInitialMount`:
      - `WSLifecycle.run` fetches REST snapshot first → assert `client.markets.get`,
        `client.portfolio.get_balance`, `client.portfolio.list_positions`, `client.orders.list`
        all called once with the expected ticker filter.
      - After REST snapshot, store has `market`, `balance`, `positions`, `resting_orders`
        all populated.

    `class TestWSPump`:
      - Inject an `OrderbookDeltaMessage` via FakeKalshiWS → store.orderbook.book updated;
        tape gets a line.
      - Inject a `TickerMessage` → store.market updated (or whatever the merge_ticker
        plan defines).
      - Inject a `TradeMessage` → tape gets a line.
      - Inject a `UserOrdersMessage` (status=resting) → store.resting_orders includes it.
      - Inject a `FillMessage` → tape gets a line.

    `class TestConnectionStateCallback`:
      - Drive the SDK's on_state_change callback with each transition:
          DISCONNECTED → CONNECTING → CONNECTED → STREAMING → RECONNECTING → STREAMING → CLOSED
        Assert `store.connection.state` follows the cockpit-state collapse:
          {DISCONNECTED} → CONNECTING → {CONNECTED, STREAMING} → CONNECTED →
          RECONNECTING → CONNECTED → DISCONNECTED.
      - On the second STREAMING (after RECONNECTING), the REST snapshot is re-fetched
        (assert `client.markets.get` call count is now 2; balance/positions/orders also 2).

    `class TestShutdown`:
      - Cancel the worker task → `KalshiWebSocket.close()` is awaited (verify via mock
        spy), no zombie tasks (asyncio.all_tasks() returns empty set after gc).
      - Worker raises a non-Cancel exception → exception propagates to the caller (for
        Textual to surface via notification); the WS context-manager still cleanly closes.

    `class TestRestSnapshotErrorHandling`:
      - REST `markets.get` raises 404 (market not found) → store.market stays None,
        worker logs the error, but does NOT crash. Tape gets a `[REST error: ...]` line.
        (Design choice: a missing market mid-session shouldn't kill the cockpit; user can
        re-launch with a valid ticker.)
      - But if REST fails on initial mount BEFORE first STREAMING transition, exception
        propagates so the App can show a splash error and exit. (This matches the test
        plan edge case "Demo API returns 500 on REST seed: surfaces clean error in
        splash, no TUI mount.")

    Pattern: respx for REST mocks (`tests/test_markets.py:35-54`), FakeKalshiWS for WS
    (`tests/ws/conftest.py:16-171`, `tests/ws/test_client.py:15-49`).
  </behavior>
  <action>
    1. RED: write `tests/cli/test_lifecycle.py` with the classes above. The respx
       fixtures should return canonical Market / Balance / position-list / order-list
       responses. The FakeKalshiWS should let us push pre-built WS messages.

    2. Verify the actual REST method names by reading `kalshi/resources/portfolio.py`,
       `kalshi/resources/markets.py`, `kalshi/resources/orders.py`. The plan above
       uses `get_balance / list_positions / list / get` as guesses — REPLACE with the
       real names.

    3. GREEN: implement `kalshi/cli/lifecycle.py`:

       Pseudocode (refine against the seam_facts above + actual SDK types):

       ```python
       async def run(self) -> None:
           # Initial REST snapshot — propagates exceptions (App shows splash error).
           await self._fetch_rest_snapshot()

           # Build KalshiWebSocket with on_state_change callback hooked.
           self._ws = KalshiWebSocket(
               auth=self.client._auth,           # access via internal — same pattern as integration tests
               config=self.client._config,
               on_state_change=self._handle_state_change,
           )

           async with self._ws.connect() as session:
               # Set CONNECTING → CONNECTED transition will fire via callback.
               await asyncio.gather(
                   self._pump_orderbook(session),
                   self._pump_ticker(session),
                   self._pump_trade(session),
                   self._pump_fill(session),
                   self._pump_user_orders(session),
               )

       async def _fetch_rest_snapshot(self) -> None:
           # Issue them concurrently — they're independent.
           market_task = self.client.markets.get(self.ticker)
           balance_task = self.client.portfolio.get_balance()
           positions_task = self.client.portfolio.list_positions(ticker=self.ticker)
           orders_task = self.client.orders.list(ticker=self.ticker, status="resting")

           market, balance, positions_resp, orders_resp = await asyncio.gather(
               market_task, balance_task, positions_task, orders_task,
               return_exceptions=False,  # let exceptions propagate on initial mount
           )

           self.store.replace_market(market)
           self.store.replace_balance(balance)
           self.store.replace_positions(positions_resp.market_positions)  # check field name
           self.store.replace_resting_orders(orders_resp.orders)  # check field name

       async def _handle_state_change(
           self, old: SDKConnectionState, new: SDKConnectionState
       ) -> None:
           # Map SDK 6-state → cockpit 4-state.
           cockpit_state = _map_sdk_state(new)
           self.store.set_connection(cockpit_state)

           # Detect RECONNECTING → STREAMING (or RECONNECTING → CONNECTED) — refresh REST.
           if old == SDKConnectionState.RECONNECTING and new in (
               SDKConnectionState.STREAMING, SDKConnectionState.CONNECTED
           ):
               # Spawn the refresh as a fire-and-forget task — don't block the callback.
               # Errors during reconnect-refresh are tape-logged, not raised.
               asyncio.create_task(self._refresh_after_reconnect())

           # Tape a marker for human visibility.
           if new == SDKConnectionState.RECONNECTING:
               self.store.append_tape(TapeLine(
                   ts=datetime.now(timezone.utc),
                   text="[disconnect]",
               ))
           elif old == SDKConnectionState.RECONNECTING and new in (
               SDKConnectionState.STREAMING, SDKConnectionState.CONNECTED
           ):
               self.store.append_tape(TapeLine(
                   ts=datetime.now(timezone.utc),
                   text="[resync]",  # gap=N filled in if we have access to the sequence tracker
               ))

       async def _refresh_after_reconnect(self) -> None:
           try:
               await self._fetch_rest_snapshot()
           except Exception as exc:
               logger.warning("REST refresh after reconnect failed: %s", exc)
               self.store.append_tape(TapeLine(
                   ts=datetime.now(timezone.utc),
                   text=f"[REST error: {type(exc).__name__}]",
               ))

       async def _pump_orderbook(self, session: KalshiWebSocket) -> None:
           stream = await session.subscribe_orderbook_delta(tickers=[self.ticker])
           async for msg in stream:
               # Read the FULL updated Orderbook from the SDK's internal manager.
               book = session._orderbook_mgr.get(self.ticker)
               self.store.merge_orderbook(book)
               self.store.append_tape(TapeLine(
                   ts=datetime.now(timezone.utc),
                   text=_format_delta_tape(msg),
               ))

       # ... similar for ticker / trade / fill / user_orders ...
       ```

       Map SDK→cockpit state:
       ```python
       def _map_sdk_state(sdk: SDKConnectionState) -> CockpitConnectionState:
           if sdk == SDKConnectionState.RECONNECTING:
               return CockpitConnectionState.RECONNECTING
           if sdk in (SDKConnectionState.CLOSED, SDKConnectionState.DISCONNECTED):
               return CockpitConnectionState.DISCONNECTED
           if sdk == SDKConnectionState.CONNECTING:
               return CockpitConnectionState.CONNECTING
           # CONNECTED, STREAMING → CONNECTED for the user
           return CockpitConnectionState.CONNECTED
       ```

    4. Verify the SDK's actual exit values for SDKConnectionState (kalshi/ws/connection.py:24-32):
       `DISCONNECTED, CONNECTING, CONNECTED, STREAMING, RECONNECTING, CLOSED`.

    5. Subscribe-method name verification: `grep -n "def subscribe_" kalshi/ws/client.py`
       — confirm `subscribe_orderbook_delta`, `subscribe_ticker`, `subscribe_trade`,
       `subscribe_fill`, `subscribe_user_orders` exist with these exact names. If any is
       different, fix the call site.

    6. Re-run pytest until green. mypy strict + ruff clean.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/test_lifecycle.py -v && uv run mypy kalshi/cli/lifecycle.py && uv run ruff check kalshi/cli/lifecycle.py tests/cli/test_lifecycle.py</automated>
  </verify>
  <done>
    Lifecycle handles initial REST snapshot, all 5 WS pump channels, on_state_change
    state mapping, RECONNECTING→STREAMING REST refresh, and clean shutdown. All tests
    green. mypy + ruff clean. Cancellation propagates without leaking tasks.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: app.py + widgets/header.py + test_app.py (Textual smoke + header render)</name>
  <files>
    kalshi/cli/app.py,
    kalshi/cli/widgets/__init__.py,
    kalshi/cli/widgets/header.py,
    tests/cli/test_app.py
  </files>
  <behavior>
    `tests/cli/test_app.py` (using Textual's `App.run_test()` / `Pilot`):

    `class TestAppMount`:
      - `async with CockpitApp(client=mock_client, ticker="T", fair=Decimal("0.63")).run_test() as pilot:`
        — app mounts, `app.is_running` is True, lifecycle worker is spawned.
      - HeaderWidget is in the DOM (query by widget class).

    `class TestHeaderRender`:
      - With store.market = sample_market (close_time = now + 2h 30min):
        - rendered string contains "T" (ticker), the title, "2:30:00" (close countdown,
          format H:MM:SS for >1h).
        - 1-char conn-state indicator visible.
      - With store.market.market.close_time = now + 30min: countdown is "30:00" (MM:SS for <1h).
      - With store.market.market.close_time = now - 1min: countdown is "EXPIRED".
      - Conn-state CONNECTED: indicator is `●` (or whatever cockpit renders for connected).
      - Conn-state RECONNECTING: indicator is `◐`.
      - Conn-state DISCONNECTED: indicator is `○`.

    `class TestReactiveSubscription`:
      - Mutate `store.market` directly → HeaderWidget repaints (Textual reactive).
      - Mutate `store.connection` → HeaderWidget repaints.
      - Verify via Pilot's screen-capture or by querying widget.render() output before/after.

    `class TestShutdown`:
      - Pilot.press("ctrl+c") → app exits cleanly (`pilot.app.is_running` False, no zombie
        tasks).
  </behavior>
  <action>
    1. RED: write `tests/cli/test_app.py` with the classes above. The lifecycle worker
       will fail to actually connect inside the test (no real demo network) — that's
       expected. Either mock `WSLifecycle` to a no-op, OR pass a mock client whose REST
       calls respx-mock cleanly and a FakeKalshiWS so the worker connects to a fake
       endpoint. Pick the simpler path that lets us assert the widget rendering.

    2. GREEN: implement `kalshi/cli/widgets/__init__.py` (one-line docstring, exports
       HeaderWidget for now).

    3. GREEN: implement `kalshi/cli/widgets/header.py`:

       ```python
       from __future__ import annotations
       from datetime import datetime, timezone

       from rich.text import Text
       from textual.reactive import reactive
       from textual.widget import Widget

       from kalshi.cli.state import (
           CockpitConnectionState,
           ConnectionStateSlice,
           MarketState,
           Store,
       )


       _CONN_INDICATOR = {
           CockpitConnectionState.CONNECTED: ("●", "green"),
           CockpitConnectionState.CONNECTING: ("◐", "yellow"),
           CockpitConnectionState.RECONNECTING: ("◐", "yellow"),
           CockpitConnectionState.DISCONNECTED: ("○", "red"),
       }


       def _format_countdown(close_time: datetime | None, now: datetime) -> str:
           if close_time is None:
               return "—"
           delta = close_time - now
           total = int(delta.total_seconds())
           if total <= 0:
               return "EXPIRED"
           h, rem = divmod(total, 3600)
           m, s = divmod(rem, 60)
           if h > 0:
               return f"{h}:{m:02d}:{s:02d}"
           return f"{m:02d}:{s:02d}"


       class HeaderWidget(Widget):
           market: reactive[MarketState | None] = reactive(None, layout=True)
           connection: reactive[ConnectionStateSlice | None] = reactive(None, layout=True)

           def __init__(self, *, store: Store) -> None:
               super().__init__()
               self._store = store

           def on_mount(self) -> None:
               # Initial sync from store; lifecycle worker will mutate store and we
               # re-bind reactive descriptors via watch_store_* in a future iteration.
               # For Wave 2 we use a 1Hz polling-from-store fallback; Wave 3+ refactors
               # to push-from-mutator.
               self.market = self._store.market
               self.connection = self._store.connection
               self.set_interval(1.0, self._sync_from_store)

           def _sync_from_store(self) -> None:
               self.market = self._store.market
               self.connection = self._store.connection

           def render(self) -> Text:
               # Defensive: tolerate None during early mount.
               text = Text()
               m = self.market
               c = self.connection
               ticker = m.market.ticker if m and m.market else "—"
               title = m.market.title if m and m.market else "—"
               close = m.market.close_time if m and m.market else None
               countdown = _format_countdown(close, datetime.now(timezone.utc))
               indicator_char, color = _CONN_INDICATOR[c.state] if c else ("○", "red")
               text.append(f"{ticker} ", style="bold")
               text.append(f"{title} | ")
               text.append(f"closes in {countdown} ")
               text.append(indicator_char, style=color)
               return text
       ```

       NOTE on the reactive seam: pure `reactive[T]` watches identity changes. Since the
       lifecycle worker mutates `store.market` IN PLACE (not by replacing `store.market`
       with a new MarketState), Textual won't auto-detect the change. There are two
       reasonable patterns:

       A. **Replace whole slice on every mutation** (lifecycle calls
         `store.market = MarketState(market=new_market, last_update_ts=...)` instead of
         `store.market.market = new_market`). This is what the design doc § "Revised file
         layout" intends with reactive descriptors — slices are *whole* values. Mutators
         in state.py SHOULD construct a fresh slice on each call. (Re-check plan 01's
         test_state.py — if those tests assert in-place mutation of attributes, refactor
         to whole-slice replacement.)

       B. **1Hz polling from widget** (the simpler fallback shown above). Robust but
         loses the no-central-tick design intent. ONLY use as a fallback if the reactive
         seam fights us.

       PREFER A. The state.py mutators in plan 01 should already produce whole-slice
       replacements (`replace_*` is whole-slice; `merge_*` should also rebuild the slice
       wrapper even if internal data merges). Confirm before writing — and if plan 01
       did in-place mutation, return to plan 01 to fix it. Wave 3 widgets will all
       depend on this seam.

    4. GREEN: implement `kalshi/cli/app.py`:

       ```python
       from __future__ import annotations
       from decimal import Decimal

       from textual.app import App, ComposeResult

       from kalshi.async_client import AsyncKalshiClient
       from kalshi.cli.lifecycle import WSLifecycle
       from kalshi.cli.state import Store
       from kalshi.cli.widgets.header import HeaderWidget


       class CockpitApp(App[None]):
           CSS = """
           Screen { background: $surface; }
           HeaderWidget { dock: top; height: 3; }
           """
           BINDINGS = [("ctrl+c", "quit", "Quit")]

           def __init__(self, *, client: AsyncKalshiClient, ticker: str, fair: Decimal | None) -> None:
               super().__init__()
               self.client = client
               self.store = Store(ticker=ticker, fair=fair)
               self.lifecycle = WSLifecycle(client=client, ticker=ticker, store=self.store)

           def compose(self) -> ComposeResult:
               yield HeaderWidget(store=self.store)

           async def on_mount(self) -> None:
               self.run_worker(self.lifecycle.run, exclusive=True, exit_on_error=False)
       ```

       The `exit_on_error=False` lets us catch worker exceptions in `on_worker_state_changed`
       (Textual API) and surface as notifications:

       ```python
           def on_worker_state_changed(self, event) -> None:
               if event.state.name == "ERROR":
                   self.notify(
                       f"Lifecycle error: {event.worker.error}",
                       severity="error",
                       timeout=10,
                   )
                   self.exit(1)
       ```

    5. Re-run pytest until green. Verify against demo:
       `KALSHI_DEMO=true KALSHI_KEY_ID=... KALSHI_PRIVATE_KEY_PATH=... uv run kalshi watch <real-demo-ticker>`
       — header should render with live close countdown ticking down per second and
       conn-state indicator turning green within 5s.

    6. mypy strict + ruff clean.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/test_app.py -v && uv run mypy kalshi/cli/app.py kalshi/cli/widgets/ && uv run ruff check kalshi/cli/app.py kalshi/cli/widgets/ tests/cli/test_app.py</automated>
  </verify>
  <done>
    `uv run kalshi watch <demo-ticker>` (with auth env vars) launches the cockpit, renders
    the header with live close countdown + conn-state indicator, and exits cleanly on
    Ctrl-C. All test_app.py tests green. mypy + ruff clean.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| ENV → process | KALSHI_KEY_ID + KALSHI_PRIVATE_KEY[_PATH] read by AsyncKalshiClient.from_env |
| WS server → process | KalshiWebSocket consumes Pydantic-validated frames from kalshi.com |
| Textual worker → main thread | asyncio cooperative scheduling — single writer (worker), single reader (render) |

## STRIDE

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-02-01 | I (info disclosure) | watch.py error messages | mitigate | error messages name env-var keys but never values; PEM file path leaks are acceptable (path is not a secret) |
| T-02-02 | D (DoS) | reconnect refresh loop | mitigate | _refresh_after_reconnect is fire-and-forget but the SDK's reconnect logic has its own backoff (kalshi/ws/connection.py) — we don't add another loop |
| T-02-03 | T (tampering) | session._orderbook_mgr access | accept | private-attribute access; SDK contract honored at v0.15.0 — drift will surface in plan 01's test_contracts.py if the attribute moves |
| T-02-04 | E (elevation) | --live flag | mitigate | --live only changes base URL; v1 is read-only so no order-side risk; future plans gate writes behind additional confirms |
</threat_model>

<verification>
After all 3 tasks:

```bash
uv run pytest tests/cli/ -v --tb=short
uv run mypy kalshi/cli/ tests/cli/
uv run ruff check kalshi/cli/ tests/cli/
uv run kalshi --help
uv run kalshi watch --help
```

Manual smoke (requires demo creds):
```bash
export KALSHI_DEMO=true
export KALSHI_KEY_ID=<demo-key>
export KALSHI_PRIVATE_KEY_PATH=<path>
uv run kalshi watch <real-demo-ticker> --fair 0.5
# Header should render within 5s, close countdown ticks, indicator goes green.
# Ctrl-C → exits cleanly within 1s.
```

Coverage:
```bash
uv run pytest tests/cli/ --cov=kalshi.cli --cov-report=term-missing
# state + edge from plan 01 still ≥80%; main + watch + lifecycle + app ≥80%.
```
</verification>

<success_criteria>
- `kalshi --help` lists `watch`; `kalshi watch --help` lists `--fair`, `--live`.
- Auth fail-fast (no env vars → exit 2 with stderr message naming both vars + docs link).
- `--fair` validates [0, 1]; out of range exits 2.
- WSLifecycle: REST snapshot on mount + on RECONNECTING→STREAMING; 5 pump coroutines; clean cancellation.
- HeaderWidget renders ticker + title + close countdown (H:MM:SS / MM:SS / EXPIRED) + 1-char indicator (●/◐/○).
- Manual smoke against demo: cockpit opens within 5s, header is live, Ctrl-C exits cleanly.
- mypy strict + ruff clean.
- `tests/cli/` line coverage ≥ 80%.
</success_criteria>

<output>
After completion, create `.planning/phases/01-cli-v1-conviction-cockpit/plans/01-02-lifecycle-app-skeleton/01-02-SUMMARY.md`
documenting: actual REST method names used, the reactive seam pattern chosen (whole-slice
replacement vs polling fallback), any divergence from the seam_facts in PATTERNS.md, and
the manual smoke result on demo.
</output>
