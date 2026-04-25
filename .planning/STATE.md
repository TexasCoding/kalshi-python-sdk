---
project: kalshi-python-sdk
sdk_version: 0.15.0
gsd_initialized: 2026-04-25
current_phase: 1
current_phase_name: cli-v1-cockpit
current_phase_status: ready-to-plan
plans_total: 0
plans_completed: 0
last_activity: 2026-04-25
last_activity_summary: GSD initialized via /gsd-new-project synthesis from existing gstack artifacts (office-hours design + plan-eng-review test plan); ready to run /gsd-plan-phase 1
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-04-25)

**Core value:** The only Python Kalshi SDK with 100% endpoint coverage + full WebSocket parity + spec-driven type safety + integration tests against demo.
**Current focus:** Phase 1 — CLI v1 Conviction Cockpit (Issue #11 reframe).

## Current Position

Phase: 1 of TBD (CLI v1 Conviction Cockpit)
Plan: 0 of TBD (not yet planned)
Status: Ready to plan — run `/gsd-plan-phase 1`
Last activity: 2026-04-25 — GSD initialized; design doc + test plan + eng-review decisions synthesized into PROJECT.md / REQUIREMENTS.md / ROADMAP.md

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: N/A
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | TBD | — | — |

## Accumulated Context

### Decisions

(See `.planning/PROJECT.md` § Key Decisions for the canonical decision log.)

Phase 1 specifically:
- Auth required always (no anon mode) — KalshiWebSocket requires KalshiAuth.
- Read-only v1 (no order entry) — order entry deferred to v2 per Codex eng-review.
- Textual reactive descriptors for state updates (no central App.set_interval tick).
- Mutable dataclass state slices (no frozen=True) — single writer, cooperative async, simpler.
- `lifecycle.py` owns REST snapshot + WS delta merge + reconnect refresh — Codex's "private channels need REST bootstrap" requirement.
- Spike-first protocol enforced for plans 01-01 and 01-02 before widget plans run.

### External Artifacts (gstack-managed, outside .planning/)

- Design doc: `~/.gstack/projects/kalshi-python-sdk/jeffreywest-main-design-20260424-190736.md` (Status: APPROVED post-/plan-eng-review revisions)
- Test plan: `~/.gstack/projects/kalshi-python-sdk/jeffreywest-main-eng-review-test-plan-20260424-192732.md`
- Builder profile: `~/.gstack/builder-profile.jsonl` (session 36 of 36)
- Builder journey: `~/.gstack/builder-journey.md`

### Project Context Files (in repo)

- `CLAUDE.md` — architecture, conventions, command reference
- `TODOS.md` — north star + active phase entry for cli-v1
- `BACKLOG.md` — CLI v2 deferred items + various code-quality items
- `.planning/audit/` — completed feasibility audit (FINDINGS.md, openapi-endpoints.md, sdk-surface.md, test-coverage.md)
- `.planning/codebase/` — codebase map (ARCHITECTURE.md, CONCERNS.md, CONVENTIONS.md, TECH.md from prior `/gsd-map-codebase`)

### Notes

- This is a brownfield project. v0.1 through v0.15 phases shipped before GSD was initialized; they're recorded in `REQUIREMENTS.md` § Already Shipped, not in `.planning/phases/`.
- Phase 1 (`cli-v1-cockpit`) is the FIRST phase with a `.planning/phases/` directory.
- Two architecture-gate spikes (OrderbookManager read-API + WS-lifecycle seam) must complete before widget work; this is encoded in ROADMAP.md plan ordering.
