# Roadmap: Kalshi Python SDK

## Overview

Brownfield project at v0.15.0 (REST coverage 100%, WS parity complete). This roadmap covers the v0.16+ work — the active milestone is the CLI v1 conviction cockpit (Issue #11 reframe), which ships as `kalshi-sdk[cli]` extras and serves as the visible marketing artifact for the SDK's WebSocket quality.

Prior phases (v0.1 through v0.15) are listed in `REQUIREMENTS.md` under "Already Shipped" and are not re-tracked here.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: CLI v1 — Conviction Cockpit** — Read-only TUI shipped as `kalshi-sdk[cli]` extras
- [ ] **Phase 2 (TBD)**: CLI v2 — Order entry + microstructure labeler (deferred to v2 backlog; promotion when v1 ships and stabilizes)

## Phase Details

### Phase 1: CLI v1 — Conviction Cockpit

**Goal**: Ship `kalshi watch TICKER --fair 0.63` as a read-only Textual cockpit that proves the SDK's WebSocket quality. Marketing artifact (screenshot/GIF for README + Discord/Twitter) that drives Python developers to `pip install kalshi-sdk`. Read-only in v1 per Codex eng-review pushback (order entry deferred to v2).

**Depends on**: Nothing (first GSD-tracked phase; v0.15.0 SDK foundation already shipped).

**Requirements**: CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, CLI-07, CLI-08, CLI-09, CLI-10, CLI-11, CLI-12, CLI-Q01, CLI-Q02, CLI-Q03, CLI-Q04, CLI-L01, CLI-L02, CLI-L03

**Success Criteria** (what must be TRUE):
  1. A Python developer with demo credentials can run `pip install kalshi-sdk[cli] && kalshi watch <real demo ticker>` and see a live, polished orderbook cockpit within 5s.
  2. The cockpit uses Textual reactive descriptors (no central tick) and survives a mid-session WS disconnect with visible header indicator + automatic reconnect + REST snapshot refresh + `[resync]` tape line.
  3. `--fair 0.63` colors YES/NO levels by edge magnitude in a way that's screenshot-worthy on a real Kalshi market.
  4. Position / balance / resting-orders panels reflect demo account state after REST seed AND remain accurate after a forced disconnect-reconnect cycle (proves Codex's "private channels need REST bootstrap" requirement is satisfied).
  5. `--live` against production succeeds; the only difference from demo is base URL.
  6. mypy strict + ruff clean; all unit tests pass; integration tests against demo green; contract drift tests parametrize over the SDK shapes the cockpit depends on.
  7. README has a screenshot + GIF of the cockpit on a real demo market. CHANGELOG entry describes the cockpit. Issue #11 closed.

**Plans**: TBD by `/gsd-plan-phase 1` — expected ~6-8 wave-parallelized plans.

Plans (preliminary):
- [ ] 01-01: Spike OrderbookManager read-API surface (architecture gate, ~30 min)
- [ ] 01-02: Spike WS-lifecycle seam (architecture gate, ~half day)
- [ ] 01-03: state.py + edge.py + tests (after spikes)
- [ ] 01-04: Contract drift tests (`test_contracts.py`)
- [ ] 01-05: Widgets — orderbook + edge coloring + header + close countdown
- [ ] 01-06: Widgets — positions + balance + resting orders + rule + tape + too_small
- [ ] 01-07: Integration tests against demo (authed flow + lifecycle reconnect + sequence-gap resync + live mode)
- [ ] 01-08: README screenshot + GIF + CHANGELOG + close issue #11

**Spike-first protocol**: Plans 01-01 and 01-02 must complete before any widget plan. Both are architecture gates per the eng-review (Codex: "the 30-min spikes are not spikes — they're architecture gates"). If either spike reveals a fundamental block, return for plan re-work before widget plans run.

**Source artifacts**:
- Design doc: `~/.gstack/projects/kalshi-python-sdk/jeffreywest-main-design-20260424-190736.md` (APPROVED, post-eng-review revisions)
- Test plan: `~/.gstack/projects/kalshi-python-sdk/jeffreywest-main-eng-review-test-plan-20260424-192732.md`
- Reviewer concerns + cross-model tensions resolved: 4 architecture decisions (3 from Claude eng-review, 5 from Codex outside voice) → all resolved into v1 read-only / auth-required / REST-snapshot-lifecycle / Textual-reactive / mutable-state.

### Phase 2 (TBD): CLI v2 — Order entry + microstructure labeler

**Status**: Backlog (BACKLOG.md → "CLI v2 (deferred from phase-cli-v1)"). Promote when Phase 1 ships and v1 stabilizes (>1 month of read-only use).

**Anticipated requirements**: CLI-V2-01 through CLI-V2-06 (REQUIREMENTS.md).

**Goal (anticipated)**: Add order entry as a guarded modal (worker-dispatched, idempotent via `client_order_id`, REST reconciliation) AND ship the microstructure event labeler tuned against captured demo frames. Sibling-market navigation, multi-ticker grid, and REPL mode are individually-promoted backlog items.
