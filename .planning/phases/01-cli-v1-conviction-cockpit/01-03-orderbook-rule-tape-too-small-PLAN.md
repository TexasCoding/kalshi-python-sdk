---
phase: 01-cli-v1-conviction-cockpit
plan: 03
type: execute
wave: 3
depends_on: [01, 02]
files_modified:
  - kalshi/cli/widgets/__init__.py
  - kalshi/cli/widgets/orderbook.py
  - kalshi/cli/widgets/rule.py
  - kalshi/cli/widgets/tape.py
  - kalshi/cli/widgets/too_small.py
  - kalshi/cli/app.py
  - tests/cli/test_widgets_orderbook.py
  - tests/cli/test_widgets_panels.py
autonomous: true
requirements: [CLI-05, CLI-06, CLI-07, CLI-09, CLI-10, CLI-11, CLI-Q01, CLI-Q02]
must_haves:
  truths:
    - "OrderbookWidget renders YES + NO ladders with at least 5 levels per side; empty book renders cleanly without exceptions"
    - "With --fair set, levels are colored by edge magnitude — positive-edge levels visibly distinct from negative-edge"
    - "During RECONNECTING, ladder shows stale tint (visibly different color/dimmed)"
    - "RuleWidget renders Market.rules_primary text; long text wraps without mid-word truncation"
    - "TapeWidget renders raw delta lines as `[HH:MM:SS.mmm side price size]` and connection markers as `[disconnect]` / `[resync gap=N]`; capped at 200 lines"
    - "TooSmallOverlay appears below 100x30 and dismisses at ≥100x30; layout reflows on resize"
  artifacts:
    - path: "kalshi/cli/widgets/orderbook.py"
      provides: "OrderbookWidget — YES/NO ladder with edge coloring + stale tint"
      contains: "class OrderbookWidget"
    - path: "kalshi/cli/widgets/rule.py"
      provides: "RuleWidget — pinned event-rule text panel"
      contains: "class RuleWidget"
    - path: "kalshi/cli/widgets/tape.py"
      provides: "TapeWidget — bounded ring of formatted tape lines"
      contains: "class TapeWidget"
    - path: "kalshi/cli/widgets/too_small.py"
      provides: "TooSmallOverlay — shown when terminal <100x30"
      contains: "class TooSmallOverlay"
  key_links:
    - from: "kalshi/cli/widgets/orderbook.py"
      to: "kalshi/cli/edge.py"
      via: "edge_yes/edge_no/edge_intensity called per level for color computation"
      pattern: "edge_yes|edge_no|edge_intensity"
    - from: "kalshi/cli/widgets/orderbook.py"
      to: "kalshi/cli/state.py:OrderbookState + ConnectionStateSlice"
      via: "reactive subscription; stale tint when connection.state == RECONNECTING"
      pattern: "reactive.*OrderbookState"
    - from: "kalshi/cli/app.py"
      to: "kalshi/cli/widgets/too_small.py"
      via: "App.on_resize handler measures size and toggles overlay visibility"
      pattern: "on_resize"
---

<objective>
Add the four "headline" widgets that make the cockpit visually distinctive: the
edge-colored YES/NO ladder, the pinned event-rule panel, the live delta tape, and the
terminal-too-small overlay. After this plan, the cockpit on a real demo market is
*screenshot-worthy* — the marketing artifact requirement.

Purpose: The orderbook widget is the centerpiece of "conviction cockpit" — it's where
`--fair 0.63` proves itself by coloring positive-edge bids visibly distinct from
overpriced asks. The tape and rule widgets surface what generic trading TUIs can't show
(raw protocol stream + Kalshi-specific settlement rule). Too-small overlay handles the
worst-case UX gracefully.

Output: 4 new widget files + 2 test files; CockpitApp.compose updated to include them
all in the layout grid; manual smoke against demo confirms the screenshot-worthy claim.
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
@CLAUDE.md

# Models the widgets read directly
@kalshi/models/markets.py
@kalshi/ws/orderbook.py
@kalshi/ws/models

# State + edge — input contracts
@kalshi/cli/state.py
@kalshi/cli/edge.py

# Existing app/header for compose() integration
@kalshi/cli/app.py
@kalshi/cli/widgets/header.py

<layout_target>
Reference layout (described, not pixel-prescriptive):

  ┌──────────────────────────── HeaderWidget (height=3, dock=top) ─────────────────────────────┐
  │ TICKER  Title  | closes in H:MM:SS  ●                                                       │
  ├─────────────── Body grid (2 columns) ───────────────────────────────────────────────────────┤
  │  Left col (~55% width)                          │  Right col (~45% width)                   │
  │  ┌─ OrderbookWidget ─────────────────────────┐  │  ┌─ RuleWidget (height=auto, scrollable) ┐│
  │  │  YES bids (top→bottom, best first)         │  │  │  Market.rules_primary (wrapped)       ││
  │  │  ─────────────                             │  │  └───────────────────────────────────────┘│
  │  │  NO bids                                    │  │  ┌─ PositionsWidget (plan 04) ──────────┐│
  │  └────────────────────────────────────────────┘  │  └───────────────────────────────────────┘│
  ├─────────────── TapeWidget (height=10, dock=bottom) ─────────────────────────────────────────┤
  │ [13:24:51.123 yes 0.65 50] [resync] [13:24:51.180 no 0.40 100] ...                          │
  └─────────────────────────────────────────────────────────────────────────────────────────────┘

Wave 4 plan adds: PositionsWidget, OrdersWidget (right column below RuleWidget).
</layout_target>

<reactive_seam_note>
Plan 02 picked one of two patterns for store→widget reactivity (whole-slice replacement
vs polling). This plan MUST follow the same pattern.

If plan 02 chose whole-slice replacement: every widget here uses
`reactive[OrderbookState | None]` (or similar) and Textual auto-refreshes when the
slice reference changes. The `on_mount` hook seeds the reactive from the store; the
widget then re-reads `self._store.orderbook` whenever any other code path triggers a
re-render. Cleanest approach.

If plan 02 chose polling fallback: this plan adopts the same `set_interval(1.0,
_sync_from_store)` pattern in each widget.

CHECK plan 02's SUMMARY.md before writing widget code. The reactive seam choice is
locked there.
</reactive_seam_note>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: OrderbookWidget — YES/NO ladder with edge coloring + stale tint</name>
  <files>
    kalshi/cli/widgets/orderbook.py,
    kalshi/cli/widgets/__init__.py,
    tests/cli/test_widgets_orderbook.py
  </files>
  <behavior>
    `tests/cli/test_widgets_orderbook.py` (using `App.run_test() / Pilot`):

    `class TestOrderbookRender`:
      - With sample_orderbook (5 YES levels at 0.40, 0.42, 0.45, 0.50, 0.55 and 5 NO
        levels at 0.40, 0.45, 0.48, 0.50, 0.52): widget renders both ladders. Top of YES
        side shows the highest YES bid (best YES bid = 0.55). Top of NO side shows the
        highest NO bid (best NO bid = 0.52). Each row shows price + quantity.
      - Empty orderbook (book=None or both sides empty): widget renders without
        exceptions; shows a placeholder like "(no book yet)".
      - Single level on each side: renders cleanly.
      - One-sided book (yes=[], no=[level]): renders YES side empty (no crash), NO side
        populated.

    `class TestEdgeColoring`:
      - With `--fair=0.63` (Decimal) and a YES level at 0.50: edge = 0.13 → positive
        → row's color attribute is in the green family. Assert via Pilot: render to a
        `Console` capture buffer, check the row's style markup.
      - YES level at 0.70 with fair=0.63: edge = -0.07 → negative → row in the red
        family.
      - YES level at 0.63 with fair=0.63: edge = 0 → neutral.
      - With `fair=None`: no coloring applied (default style).
      - Color saturation scales with abs(edge) — assert higher-edge level has visibly
        higher saturation than lower-edge level (using edge_intensity from edge.py).

    `class TestStaleTint`:
      - With store.connection.state=CONNECTED: rows render normal.
      - With store.connection.state=RECONNECTING: rows render with a dimmed/stale tint
        (e.g. `style="dim"` or a "stale" CSS class applied).
      - With store.connection.state=DISCONNECTED: same stale tint.

    `class TestEmptyAndDegenerate`:
      - book=None → "(no book yet)" placeholder.
      - book with empty yes and empty no → same placeholder OR two empty ladders with
        explicit "—" rows. Pick whichever feels cleaner; lock the behavior.
  </behavior>
  <action>
    1. RED: write `tests/cli/test_widgets_orderbook.py`.

       Pattern for Textual widget tests:

       ```python
       from textual.app import App, ComposeResult
       from kalshi.cli.widgets.orderbook import OrderbookWidget
       from kalshi.cli.state import Store, OrderbookState
       from decimal import Decimal


       class _Harness(App[None]):
           def __init__(self, store: Store, fair: Decimal | None) -> None:
               super().__init__()
               self._store = store
               self._fair = fair

           def compose(self) -> ComposeResult:
               yield OrderbookWidget(store=self._store, fair=self._fair)


       async def test_renders_both_sides(store: Store, sample_orderbook: Orderbook) -> None:
           store.merge_orderbook(sample_orderbook)
           async with _Harness(store, fair=Decimal("0.63")).run_test() as pilot:
               widget = pilot.app.query_one(OrderbookWidget)
               # Trigger a render and capture
               await pilot.pause()
               rendered = widget.render()
               # Assert against the rendered output
       ```

       For style introspection, capture via Rich's Console with `record=True`:
       ```python
       from rich.console import Console
       console = Console(record=True, width=80)
       console.print(widget.render())
       html_or_segments = console.export_text(styles=True)
       # parse for style markers
       ```

       Or use Pilot's `app.screen` query + `Strip` segment inspection (Textual API). Pick
       the simpler approach — direct `widget.render()` returns a Rich `Renderable`, which
       can be rendered to segments via `console.render(renderable)`.

    2. GREEN: implement `kalshi/cli/widgets/orderbook.py`:

       ```python
       from __future__ import annotations
       from decimal import Decimal

       from rich.console import RenderableType
       from rich.table import Table
       from rich.text import Text
       from textual.reactive import reactive
       from textual.widget import Widget

       from kalshi.cli.edge import edge_yes, edge_no, edge_intensity
       from kalshi.cli.state import (
           CockpitConnectionState,
           ConnectionStateSlice,
           OrderbookState,
           Store,
       )


       def _edge_color(edge: Decimal, intensity: float) -> str:
           """Return a Rich-compatible color string for a given (edge, intensity) pair."""
           if intensity == 0.0:
               return "white"
           # Map [0, 1] intensity to a green-or-red gradient.
           # Use 256-color palette: greens 22 (dark) to 46 (bright), reds 52 to 196.
           if edge > 0:
               # Positive edge — green family.
               return "green" if intensity < 0.5 else "bright_green"
           # Negative edge — red family.
           return "red" if intensity < 0.5 else "bright_red"


       class OrderbookWidget(Widget):
           orderbook: reactive[OrderbookState | None] = reactive(None, layout=True)
           connection: reactive[ConnectionStateSlice | None] = reactive(None, layout=True)

           def __init__(self, *, store: Store, fair: Decimal | None) -> None:
               super().__init__()
               self._store = store
               self._fair = fair

           def on_mount(self) -> None:
               self.orderbook = self._store.orderbook
               self.connection = self._store.connection
               # If plan 02 chose polling: also set_interval here.
               self.set_interval(0.1, self._sync_from_store)

           def _sync_from_store(self) -> None:
               self.orderbook = self._store.orderbook
               self.connection = self._store.connection

           def render(self) -> RenderableType:
               ob = self.orderbook
               stale = self.connection is not None and self.connection.state in (
                   CockpitConnectionState.RECONNECTING,
                   CockpitConnectionState.DISCONNECTED,
               )

               if ob is None or ob.book is None:
                   text = Text("(no book yet)")
                   if stale:
                       text.stylize("dim")
                   return text

               book = ob.book
               table = Table.grid(padding=(0, 1))
               table.add_column("YES side", justify="right")
               table.add_column("NO side", justify="right")

               # YES levels: book.yes is sorted ascending — best YES bid is last.
               yes_rows = list(reversed(book.yes))[:10]
               no_rows = list(reversed(book.no))[:10]

               for i in range(max(len(yes_rows), len(no_rows))):
                   yes_cell = self._format_level(yes_rows[i], side="yes") if i < len(yes_rows) else Text("—")
                   no_cell = self._format_level(no_rows[i], side="no") if i < len(no_rows) else Text("—")
                   table.add_row(yes_cell, no_cell)

               if stale:
                   # Wrap the entire table in a dim style by stylize-ing the rendered
                   # output. Easier: build a Group with a stale marker.
                   from rich.console import Group
                   marker = Text("[STALE — RECONNECTING]", style="yellow")
                   return Group(marker, table)

               return table

           def _format_level(self, level, side: str) -> Text:
               text = Text()
               text.append(f"{level.price:.2f} ", style="bold")
               text.append(f"{level.quantity:.0f}")
               if self._fair is not None:
                   if side == "yes":
                       e = edge_yes(level.price, self._fair)
                   else:
                       e = edge_no(level.price, self._fair)
                   intensity = edge_intensity(e)
                   color = _edge_color(e, intensity)
                   text.stylize(color)
               return text
       ```

    3. Update `kalshi/cli/widgets/__init__.py` to re-export `OrderbookWidget`.

    4. Update `kalshi/cli/app.py` `compose()` to include the OrderbookWidget in the
       layout grid (left column, ~55% width). Adjust CSS:
       ```python
       CSS = """
       Screen { background: $surface; }
       HeaderWidget { dock: top; height: 3; }
       OrderbookWidget { width: 55%; height: 1fr; }
       """
       ```

    5. Re-run tests until green. mypy strict + ruff clean.

       Manual smoke against demo: launch with `--fair 0.5` on an active market. Visually
       confirm: bids below 0.50 are green (positive YES edge), bids above 0.50 are red.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/test_widgets_orderbook.py -v && uv run mypy kalshi/cli/widgets/orderbook.py && uv run ruff check kalshi/cli/widgets/orderbook.py tests/cli/test_widgets_orderbook.py</automated>
  </verify>
  <done>
    OrderbookWidget renders both ladders, edge coloring works with --fair, stale tint
    appears during RECONNECTING, empty/degenerate books render without crashing. Manual
    demo smoke shows the colored ladder.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: RuleWidget + TapeWidget + TooSmallOverlay</name>
  <files>
    kalshi/cli/widgets/rule.py,
    kalshi/cli/widgets/tape.py,
    kalshi/cli/widgets/too_small.py,
    kalshi/cli/widgets/__init__.py,
    kalshi/cli/app.py,
    tests/cli/test_widgets_panels.py
  </files>
  <behavior>
    `tests/cli/test_widgets_panels.py`:

    `class TestRuleWidget`:
      - sample_market.market.rules_primary set to a multi-line string → widget renders
        the text wrapped to its width; no mid-word truncation.
      - rules_primary=None → renders "(no rule text available)" placeholder.
      - Long rule (1000 chars) → renders fully (wraps); does NOT truncate.

    `class TestTapeWidget`:
      - 10 tape lines added to store.tape → widget renders them in chronological order
        (newest at bottom or top — pick one and lock; design says tape format `[HH:MM:SS.mmm
        side price size]` reads top-down newest-last typically).
      - 250 tape lines added → widget shows 200 lines max (deque maxlen from plan 01).
      - Connection markers `[disconnect]` and `[resync gap=N]` render distinct (e.g.
        yellow/red color).
      - Empty tape → "(waiting for events...)" placeholder.

    `class TestTooSmallOverlay`:
      - At terminal size 80x20: overlay visible, contains current dimensions (e.g.
        "80×20 — resize to ≥100×30").
      - At terminal size 100x30: overlay HIDDEN (`display=False` or removed from DOM).
      - At 99x30: overlay visible.
      - At 100x29: overlay visible.
      - On resize from 80x20 to 110x35: overlay dismisses, main layout reflows back.

    Use Textual's `App.run_test(size=(width, height))` to set initial size. To trigger
    resize, use `pilot.resize(width, height)` (Textual ≥0.85).
  </behavior>
  <action>
    1. RED: write `tests/cli/test_widgets_panels.py` with the classes above.

    2. GREEN: implement `kalshi/cli/widgets/rule.py`:

       ```python
       from __future__ import annotations

       from rich.console import RenderableType
       from rich.markdown import Markdown
       from rich.text import Text
       from textual.reactive import reactive
       from textual.widget import Widget

       from kalshi.cli.state import MarketState, Store


       class RuleWidget(Widget):
           market: reactive[MarketState | None] = reactive(None, layout=True)

           def __init__(self, *, store: Store) -> None:
               super().__init__()
               self._store = store

           def on_mount(self) -> None:
               self.market = self._store.market
               self.set_interval(1.0, lambda: setattr(self, "market", self._store.market))

           def render(self) -> RenderableType:
               m = self.market
               if m is None or m.market is None or m.market.rules_primary is None:
                   return Text("(no rule text available)", style="dim")
               # Use Rich Text with .word_wrap=True (default) — Rich wraps automatically
               # to the renderable width.
               return Text(m.market.rules_primary)
       ```

    3. GREEN: implement `kalshi/cli/widgets/tape.py`:

       ```python
       from __future__ import annotations

       from rich.console import RenderableType
       from rich.text import Text
       from textual.reactive import reactive
       from textual.widget import Widget

       from kalshi.cli.state import DeltaTapeLog, Store


       class TapeWidget(Widget):
           tape: reactive[DeltaTapeLog | None] = reactive(None, layout=True)

           def __init__(self, *, store: Store) -> None:
               super().__init__()
               self._store = store

           def on_mount(self) -> None:
               self.tape = self._store.tape
               self.set_interval(0.1, lambda: setattr(self, "tape", self._store.tape))

           def render(self) -> RenderableType:
               t = self.tape
               if t is None or len(t.lines) == 0:
                   return Text("(waiting for events...)", style="dim")
               # Render newest-last (chronological reading order).
               rendered = Text()
               for line in t.lines:
                   style = "white"
                   if "[disconnect]" in line.text:
                       style = "yellow"
                   elif "[resync" in line.text:
                       style = "cyan"
                   elif "[REST error" in line.text:
                       style = "red"
                   rendered.append(line.text + "\n", style=style)
               return rendered
       ```

    4. GREEN: implement `kalshi/cli/widgets/too_small.py`:

       ```python
       from __future__ import annotations

       from rich.console import RenderableType
       from rich.align import Align
       from rich.text import Text
       from textual.widget import Widget


       MIN_WIDTH = 100
       MIN_HEIGHT = 30


       class TooSmallOverlay(Widget):
           def __init__(self) -> None:
               super().__init__()

           def render(self) -> RenderableType:
               size = self.app.size
               text = Text.assemble(
                   ("Terminal too small\n", "bold red"),
                   (f"{size.width}×{size.height} — resize to ≥{MIN_WIDTH}×{MIN_HEIGHT}", "white"),
               )
               return Align.center(text, vertical="middle")
       ```

       And in `kalshi/cli/app.py` add resize-aware mounting:

       ```python
       def on_resize(self, event) -> None:
           too_small = self.query_one(TooSmallOverlay)
           too_small.display = (
               event.size.width < MIN_WIDTH or event.size.height < MIN_HEIGHT
           )
       ```

       And in `compose()`:

       ```python
       def compose(self) -> ComposeResult:
           yield HeaderWidget(store=self.store)
           yield OrderbookWidget(store=self.store, fair=self.store.fair)
           yield RuleWidget(store=self.store)
           yield TapeWidget(store=self.store)
           yield TooSmallOverlay()  # last → renders on top via z-index in CSS
       ```

       CSS layout (illustrative — refine to match the diagram in <layout_target>):

       ```python
       CSS = """
       Screen { background: $surface; layout: vertical; }
       HeaderWidget { dock: top; height: 3; }
       TapeWidget { dock: bottom; height: 10; }
       OrderbookWidget { width: 55%; height: 1fr; }
       RuleWidget { width: 45%; height: 1fr; }
       TooSmallOverlay { layer: overlay; align: center middle; display: none; }
       /* on_resize toggles TooSmallOverlay.display */
       """
       ```

    5. Update `kalshi/cli/widgets/__init__.py` to re-export `RuleWidget`, `TapeWidget`,
       `TooSmallOverlay`.

    6. Re-run tests until green. mypy + ruff clean.

       Manual smoke against demo:
       - Launch cockpit. Verify all 4 widgets visible (header, ladder, rule, tape).
       - Resize terminal to 80×20 → overlay appears.
       - Resize back to 120×40 → overlay disappears, layout reflows.
       - Watch tape stream live `[HH:MM:SS.mmm side price size]` lines.
       - Force a brief disconnect (drop wifi for 5s, restore) → tape gets `[disconnect]`
         then `[resync]`; ladder shows stale tint while reconnecting.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/test_widgets_panels.py -v && uv run mypy kalshi/cli/widgets/ kalshi/cli/app.py && uv run ruff check kalshi/cli/widgets/ kalshi/cli/app.py tests/cli/test_widgets_panels.py</automated>
  </verify>
  <done>
    Rule, Tape, TooSmall widgets all render correctly. Tape shows live deltas. Stale tint
    on reconnect. Layout reflows on resize. mypy + ruff clean. Manual demo smoke confirms
    the screenshot-worthy claim.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| WS frame → render path | Pydantic-validated frames are read by widgets via store; no untrusted text rendering |
| Market.rules_primary → render | Server-controlled text inserted into Rich Text — Rich's Text class escapes markup by default, but verify with a test |

## STRIDE

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-03-01 | T (tampering) | RuleWidget rules_primary | mitigate | Rich `Text(s)` does not interpret markup unless `Text.from_markup(s)` used; we use the plain constructor — server can't inject styles |
| T-03-02 | I (info disclosure) | TapeWidget price/size rendering | accept | data is already public market data, no sensitive content |
| T-03-03 | D (DoS) | TapeWidget rendering 200 lines on every refresh | mitigate | Textual diffs render output; deque maxlen caps memory; refresh tied to slice mutation, not a hot tick |
</threat_model>

<verification>
```bash
uv run pytest tests/cli/test_widgets_orderbook.py tests/cli/test_widgets_panels.py -v
uv run mypy kalshi/cli/
uv run ruff check kalshi/cli/ tests/cli/

# Coverage check
uv run pytest tests/cli/ --cov=kalshi.cli --cov-report=term-missing
```

Manual against demo (5 minutes):
1. `kalshi watch <demo-ticker> --fair 0.5` — confirm: header live, ladder colored,
   rule visible, tape streaming.
2. Resize to 80×20 → too-small overlay; resize back → reflows.
3. Drop network briefly → `[disconnect]`/`[resync]` appear in tape; ladder dims.
</verification>

<success_criteria>
- OrderbookWidget renders YES/NO ladder with at least 5 levels per side.
- Edge coloring with --fair makes positive-edge levels visibly distinct from negative-edge.
- Stale tint visible during RECONNECTING.
- RuleWidget renders Market.rules_primary, wraps cleanly, falls back gracefully.
- TapeWidget renders [HH:MM:SS.mmm side price size] lines + [disconnect]/[resync]; capped at 200.
- TooSmallOverlay appears <100x30, dismisses ≥100x30, layout reflows on resize.
- mypy strict + ruff clean.
- `tests/cli/` line coverage ≥ 80% (already met since plan 01; this plan adds widget render coverage).
</success_criteria>

<output>
After completion, create `.planning/phases/01-cli-v1-conviction-cockpit/plans/01-03-orderbook-rule-tape-too-small/01-03-SUMMARY.md`
documenting: chosen reactive seam pattern (confirming match with plan 02), screenshot
filename(s) captured for plan 06 use, any styling/CSS adjustments made beyond the
illustrative layout in <layout_target>.
</output>
