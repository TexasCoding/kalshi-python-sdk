---
phase: 01-cli-v1-conviction-cockpit
plan: 04
type: execute
wave: 4
depends_on: [01, 02, 03]
files_modified:
  - kalshi/cli/widgets/positions.py
  - kalshi/cli/widgets/orders.py
  - kalshi/cli/widgets/__init__.py
  - kalshi/cli/app.py
  - tests/cli/test_widgets_panels.py
autonomous: true
requirements: [CLI-08, CLI-Q01, CLI-Q02]
must_haves:
  truths:
    - "PositionsWidget renders one row per MarketPosition with size + avg cost + mark + P&L; balance footer shows current balance"
    - "OrdersWidget renders one row per resting Order with side, price, count, status (read-only — no `x` cancel binding in v1)"
    - "Both widgets handle empty list gracefully ('(no positions)' / '(no resting orders)')"
    - "Widgets refresh when REST snapshot replaces store slices (initial mount + every reconnect)"
    - "Widgets refresh when WS user_orders / fill frames merge into store (between REST refreshes)"
  artifacts:
    - path: "kalshi/cli/widgets/positions.py"
      provides: "PositionsWidget — position table + balance footer"
      contains: "class PositionsWidget"
    - path: "kalshi/cli/widgets/orders.py"
      provides: "OrdersWidget — resting orders table (read-only)"
      contains: "class OrdersWidget"
  key_links:
    - from: "kalshi/cli/widgets/positions.py"
      to: "kalshi/cli/state.py:PositionState + BalanceState"
      via: "reactive subscription; renders MarketPosition rows + Balance footer"
      pattern: "PositionState|BalanceState"
    - from: "kalshi/cli/widgets/orders.py"
      to: "kalshi/cli/state.py:RestingOrdersState"
      via: "reactive subscription; renders Order rows"
      pattern: "RestingOrdersState"
---

<objective>
Add the two account-data widgets that close the read-only cockpit: PositionsWidget
(position size + avg cost + mark + P&L + balance footer) and OrdersWidget (resting
orders table, read-only, no `x` cancel — order-mutation moved to v2 backlog per
eng-review).

Purpose: Plans 02 and 03 already plumb the REST snapshot + WS user_orders/fill streams
into the store. This plan is pure presentation — render the data that's already
flowing. Splitting it from plan 03 keeps each plan's scope under the ~50% context
target and makes Wave 3+4 trivially parallelizable if a future re-run wants more
parallelism (today, this plan stays sequential after plan 03 because they share
`app.py` compose() / CSS).

Output: 2 new widget files; CockpitApp.compose updated to include both in the right
column below RuleWidget; manual smoke against demo confirms position/balance/orders
update on initial mount AND remain accurate after a forced disconnect-reconnect.
</objective>

<execution_context>
@/Users/jeffreywest/Code/Python/kalshi-python-sdk/.planning/phases/01-cli-v1-conviction-cockpit/PATTERNS.md
@/Users/jeffreywest/.gstack/projects/kalshi-python-sdk/jeffreywest-main-design-20260424-190736.md
@/Users/jeffreywest/.gstack/projects/kalshi-python-sdk/jeffreywest-main-eng-review-test-plan-20260424-192732.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/phases/01-cli-v1-conviction-cockpit/plans/01-01-state-edge-and-contracts/PLAN.md
@.planning/phases/01-cli-v1-conviction-cockpit/plans/01-02-lifecycle-app-skeleton/PLAN.md
@.planning/phases/01-cli-v1-conviction-cockpit/plans/01-03-orderbook-rule-tape-too-small/PLAN.md
@CLAUDE.md

@kalshi/models/portfolio.py
@kalshi/models/orders.py
@kalshi/cli/state.py
@kalshi/cli/widgets/__init__.py
@kalshi/cli/app.py
@tests/cli/conftest.py

<read_only_v1_constraint>
Per eng-review locked decision: v1 is read-only. NO `x` keypress to cancel orders. NO
`b`/`s` to open ticket modal. Order mutation moved to v2 backlog (CLI-V2-01).

OrdersWidget displays the table; nothing more. If a Wave 3 reviewer or executor adds a
keybinding for `x`/`b`/`s`, that's a scope violation — push back.
</read_only_v1_constraint>

<pnl_computation>
P&L per position is derived (not on the SDK model directly). Verify the actual fields on
MarketPosition before locking the formula:

```bash
grep -n "^    [a-z_]*:" kalshi/models/portfolio.py
```

Likely fields (verify):
- `position` (signed contracts: positive = long YES; negative = long NO)
- `market_exposure` (current $ value)
- `realized_pnl` or similar
- A cost basis / avg-price field (name TBD)

If the SDK ships a P&L number directly: render that.

If not, derive via:
  current_mark = best YES bid for long-YES, best NO bid for long-NO
  pnl = (current_mark - avg_cost) × abs(position) × $1.00

Use store.orderbook.book to get the mark. If book is None, render "—" for mark and P&L.

If after grep the SDK has a P&L field, ALWAYS prefer that — it's authoritative. The
manual formula is a fallback only.
</pnl_computation>

<interfaces>
```python
# kalshi/cli/widgets/positions.py — public surface

from __future__ import annotations
from decimal import Decimal

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from kalshi.cli.state import (
    BalanceState,
    OrderbookState,
    PositionState,
    Store,
)


class PositionsWidget(Widget):
    positions: reactive[PositionState | None] = reactive(None, layout=True)
    balance: reactive[BalanceState | None] = reactive(None, layout=True)
    orderbook: reactive[OrderbookState | None] = reactive(None, layout=True)  # for mark

    def __init__(self, *, store: Store) -> None: ...
    def render(self) -> RenderableType: ...


# kalshi/cli/widgets/orders.py — public surface

from kalshi.cli.state import RestingOrdersState, Store


class OrdersWidget(Widget):
    resting_orders: reactive[RestingOrdersState | None] = reactive(None, layout=True)

    def __init__(self, *, store: Store) -> None: ...
    def render(self) -> RenderableType: ...
```
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: PositionsWidget + tests</name>
  <files>
    kalshi/cli/widgets/positions.py,
    kalshi/cli/widgets/__init__.py,
    kalshi/cli/app.py,
    tests/cli/test_widgets_panels.py
  </files>
  <behavior>
    Add to existing `tests/cli/test_widgets_panels.py`:

    `class TestPositionsWidget`:
      - With `sample_positions = [MarketPosition(market_ticker="T", position=10, ...)]`
        and `sample_balance = Balance(balance=Decimal("1000.00"))`: widget renders 1 row
        with the position size, plus a balance footer showing "$1000.00".
      - Empty positions list → "(no positions)" placeholder; balance footer still shown.
      - Empty positions AND balance=None → "(no account data)".
      - With orderbook present: position row shows mark price + P&L computed.
      - With orderbook=None: mark and P&L render as "—".
      - Updating store.positions to a new list → widget repaints (reactive).
      - Updating store.balance to a new Balance → footer repaints.
      - Long position (position > 0) renders with one indicator (e.g. ↑ or "LONG YES");
        short position (position < 0) with another (↓ or "LONG NO").

    Pattern: same Pilot/run_test/_Harness pattern as plan 03.
  </behavior>
  <action>
    1. RED: write the TestPositionsWidget class. Use existing fixtures from
       `tests/cli/conftest.py` (sample_positions, sample_balance, sample_orderbook).

    2. Verify SDK field names on MarketPosition + Balance via grep before writing render
       code:
       ```bash
       grep -n "^    [a-z_]*:" kalshi/models/portfolio.py
       ```
       Lock the field names used in render.

    3. GREEN: implement `kalshi/cli/widgets/positions.py`:

       ```python
       from __future__ import annotations
       from decimal import Decimal

       from rich.console import Group, RenderableType
       from rich.table import Table
       from rich.text import Text
       from textual.reactive import reactive
       from textual.widget import Widget

       from kalshi.cli.state import (
           BalanceState,
           OrderbookState,
           PositionState,
           Store,
       )


       def _compute_mark(book, position: int) -> Decimal | None:
           """Best price for the side the trader is long."""
           if book is None:
               return None
           if position > 0:
               # Long YES — mark = best YES bid (highest YES bid).
               yes = book.yes
               return yes[-1].price if yes else None
           if position < 0:
               # Long NO — mark = best NO bid.
               no = book.no
               return no[-1].price if no else None
           return None


       class PositionsWidget(Widget):
           positions: reactive[PositionState | None] = reactive(None, layout=True)
           balance: reactive[BalanceState | None] = reactive(None, layout=True)
           orderbook: reactive[OrderbookState | None] = reactive(None, layout=True)

           def __init__(self, *, store: Store) -> None:
               super().__init__()
               self._store = store

           def on_mount(self) -> None:
               self.positions = self._store.positions
               self.balance = self._store.balance
               self.orderbook = self._store.orderbook
               self.set_interval(0.5, self._sync_from_store)

           def _sync_from_store(self) -> None:
               self.positions = self._store.positions
               self.balance = self._store.balance
               self.orderbook = self._store.orderbook

           def render(self) -> RenderableType:
               p = self.positions
               b = self.balance
               ob = self.orderbook

               table = Table(show_header=True, header_style="bold")
               table.add_column("Ticker")
               table.add_column("Side")
               table.add_column("Size", justify="right")
               table.add_column("Mark", justify="right")
               table.add_column("P&L", justify="right")

               if p is None or len(p.positions) == 0:
                   table.add_row("(no positions)", "—", "—", "—", "—")
               else:
                   book = ob.book if ob else None
                   for pos in p.positions:
                       size = pos.position
                       side = "LONG YES" if size > 0 else "LONG NO" if size < 0 else "FLAT"
                       mark = _compute_mark(book, size)
                       mark_str = f"{mark:.2f}" if mark is not None else "—"
                       # P&L: prefer SDK field if available; else compute fallback.
                       # (Adjust based on the actual MarketPosition fields verified above.)
                       pnl = self._compute_pnl(pos, mark)
                       pnl_str = f"{pnl:+.2f}" if pnl is not None else "—"
                       table.add_row(
                           pos.market_ticker,
                           side,
                           f"{abs(size)}",
                           mark_str,
                           pnl_str,
                       )

               # Balance footer.
               footer = Text()
               if b is not None and b.balance is not None:
                   # Adjust attribute path based on actual Balance model — likely
                   # `b.balance.balance` if Balance has a `balance: Decimal` field.
                   bal_value = getattr(b.balance, "balance", None) or b.balance
                   footer.append(f"Balance: ${bal_value:.2f}", style="bold")
               else:
                   footer.append("Balance: —", style="dim")

               return Group(table, footer)

           def _compute_pnl(self, pos, mark: Decimal | None) -> Decimal | None:
               # Use SDK-provided P&L if available; otherwise return None and let
               # the renderer show "—". Don't fabricate an answer if data is incomplete.
               # Verify field name from grep above — examples: realized_pnl,
               # market_exposure, etc.
               return getattr(pos, "realized_pnl", None) or None
       ```

    4. Update `__init__.py` to re-export `PositionsWidget`.

    5. Update `kalshi/cli/app.py` `compose()` to include `PositionsWidget` in the right
       column below `RuleWidget`. Adjust CSS for the new row.

    6. Re-run tests until green. mypy + ruff clean.

       Manual smoke (requires demo creds + a position on demo):
       - `kalshi watch <demo-ticker-with-position>` → PositionsWidget shows the row
         within 5s of mount.
       - Briefly drop network → during `RECONNECTING`, widget data may go stale; on
         reconnect, REST refresh from plan 02 should restore exact values.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/test_widgets_panels.py::TestPositionsWidget -v && uv run mypy kalshi/cli/widgets/positions.py kalshi/cli/app.py && uv run ruff check kalshi/cli/widgets/positions.py kalshi/cli/app.py tests/cli/test_widgets_panels.py</automated>
  </verify>
  <done>
    PositionsWidget renders position table + balance footer. Empty states handled. P&L
    derived (or SDK-sourced) correctly. Manual demo smoke confirms reconcile-after-
    reconnect.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: OrdersWidget + tests</name>
  <files>
    kalshi/cli/widgets/orders.py,
    kalshi/cli/widgets/__init__.py,
    kalshi/cli/app.py,
    tests/cli/test_widgets_panels.py
  </files>
  <behavior>
    Add to `tests/cli/test_widgets_panels.py`:

    `class TestOrdersWidget`:
      - With sample_resting_orders = [Order(order_id=..., status="resting", ticker=..., side=..., count=..., yes_price=...)]:
        widget renders 1 row with side + price + count + status.
      - Empty list → "(no resting orders)" placeholder.
      - Multiple orders sorted by some stable order (server-assigned order_id is fine).
      - Updating store.resting_orders via merge_user_order (resting → canceled) → row
        removed from widget on next render.
      - NO keybinding tests for `x` — read-only v1.

    Pattern same as Task 1.
  </behavior>
  <action>
    1. RED: write `TestOrdersWidget` test class.

    2. Verify Order field names via grep:
       ```bash
       grep -n "^    [a-z_]*:" kalshi/models/orders.py
       ```
       Lock: order_id, status, ticker, side, count, yes_price/no_price (or whatever the
       actual price field name is — alias-mapped short names per CLAUDE.md).

    3. GREEN: implement `kalshi/cli/widgets/orders.py`:

       ```python
       from __future__ import annotations

       from rich.console import RenderableType
       from rich.table import Table
       from textual.reactive import reactive
       from textual.widget import Widget

       from kalshi.cli.state import RestingOrdersState, Store


       class OrdersWidget(Widget):
           resting_orders: reactive[RestingOrdersState | None] = reactive(None, layout=True)

           def __init__(self, *, store: Store) -> None:
               super().__init__()
               self._store = store

           def on_mount(self) -> None:
               self.resting_orders = self._store.resting_orders
               self.set_interval(0.5, lambda: setattr(self, "resting_orders", self._store.resting_orders))

           def render(self) -> RenderableType:
               r = self.resting_orders
               table = Table(show_header=True, header_style="bold")
               table.add_column("Order ID")
               table.add_column("Side")
               table.add_column("Price", justify="right")
               table.add_column("Count", justify="right")
               table.add_column("Status")

               if r is None or len(r.orders) == 0:
                   table.add_row("(no resting orders)", "—", "—", "—", "—")
                   return table

               for o in r.orders:
                   # Pick price by side: yes_price if YES side, no_price if NO.
                   # Adjust attribute names per the actual SDK Order model.
                   price = getattr(o, "yes_price", None) if o.side == "yes" else getattr(o, "no_price", None)
                   price_str = f"{price:.2f}" if price is not None else "—"
                   table.add_row(
                       str(o.order_id)[:8],  # truncate UUID for readability
                       o.side.upper(),
                       price_str,
                       str(o.count),
                       o.status,
                   )

               return table
       ```

    4. Update `__init__.py` and `app.py` `compose()`/CSS to add OrdersWidget below
       PositionsWidget in the right column.

    5. Re-run tests until green. mypy + ruff clean.

       Manual smoke (requires demo creds + a resting order on demo):
       - Place a resting order on demo via the SDK or web UI before launching cockpit.
       - `kalshi watch <demo-ticker>` → OrdersWidget shows the order within 5s of mount.
       - Cancel the order out-of-band → within seconds, the WS user_orders frame should
         flow in and the row disappears.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/test_widgets_panels.py::TestOrdersWidget -v && uv run mypy kalshi/cli/widgets/orders.py && uv run ruff check kalshi/cli/widgets/orders.py</automated>
  </verify>
  <done>
    OrdersWidget renders resting-orders table. Empty state handled. Read-only — no
    cancel binding. Manual demo smoke confirms WS user_orders flows into the widget.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Account REST/WS data → render | Same auth as already audited at SDK level; widgets render Pydantic-validated values |

## STRIDE

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-04-01 | I (info disclosure) | balance footer rendering | accept | this is the user's own balance; cockpit is read by the same user |
| T-04-02 | T (tampering) | order_id rendering (truncated) | accept | display-only — no actions taken on truncated ids |
</threat_model>

<verification>
```bash
uv run pytest tests/cli/test_widgets_panels.py -v
uv run mypy kalshi/cli/
uv run ruff check kalshi/cli/ tests/cli/
uv run pytest tests/cli/ --cov=kalshi.cli --cov-report=term-missing
```

Manual against demo:
1. Cockpit shows positions + balance + resting orders within 5s on a demo account that
   has at least 1 position and 1 resting order.
2. Force a network drop — after reconnect, all three panels reconcile back to current
   state via REST refresh from plan 02.
3. Cancel a resting order out-of-band → row disappears via WS user_orders merge.
</verification>

<success_criteria>
- PositionsWidget: 1 row per position; mark + P&L derived; balance footer; empty fallback.
- OrdersWidget: 1 row per resting order; side/price/count/status; empty fallback. NO cancel binding.
- Both widgets reactive: REST replace + WS merge both visible.
- mypy strict + ruff clean.
- Tests cover happy path + empty state + reconcile-after-WS-merge.
</success_criteria>

<output>
After completion, create `.planning/phases/01-cli-v1-conviction-cockpit/plans/01-04-positions-and-orders/01-04-SUMMARY.md`
documenting: actual P&L source (SDK field vs derived fallback), final compose() layout
diagram, any layout/CSS issues encountered fitting all 6 widgets in the 100×30 minimum.
</output>
