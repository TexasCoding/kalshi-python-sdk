# Requirements: Kalshi Python SDK

**Defined:** 2026-04-25
**Core Value:** The only Python Kalshi SDK with 100% endpoint coverage + full WebSocket parity + spec-driven type safety + integration tests against demo.

## v0.16 Requirements (active)

Active scope. Phase 1 (CLI v1 Conviction Cockpit) maps here.

### CLI/TUI

- [ ] **CLI-01**: `pip install kalshi-sdk[cli]` works on a clean venv; `kalshi --help` lists `watch` as the headline command.
- [ ] **CLI-02**: `kalshi watch TICKER` opens the Textual cockpit against demo within 5s of command invocation.
- [ ] **CLI-03**: Auth required always (no anon mode). `KALSHI_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH` env vars must be set; missing env exits at typer-level before TUI mount with a clear error.
- [ ] **CLI-04**: `--live` flag switches base URL from demo to production; otherwise behavior is identical (read-only).
- [ ] **CLI-05**: Live YES/NO orderbook ladder updates without flicker on a moderately active market via Textual reactive descriptors.
- [ ] **CLI-06**: `--fair PROB` colors YES/NO levels by edge magnitude (positive-edge readable at a glance).
- [ ] **CLI-07**: Pinned event-rule text panel + close countdown header.
- [ ] **CLI-08**: Position / balance / resting-orders panels populate from REST snapshot on mount AND re-fetch via REST on every WS reconnect (per Codex tension #3).
- [ ] **CLI-09**: Connection-state indicator in header; tape gets `[disconnect]` and `[resync gap=N]` lines.
- [ ] **CLI-10**: Raw WS delta tape streams `orderbook_delta` events as `[HH:MM:SS.mmm side price size]` lines.
- [ ] **CLI-11**: Terminal-too-small overlay below 100×30; layout reflows on resize.
- [ ] **CLI-12**: WS lifecycle hosted via Textual `App.run_worker`; clean Ctrl-C exit (worker cancelled, `KalshiWebSocket.close()` awaited).

### Quality

- [ ] **CLI-Q01**: mypy strict + ruff clean on `kalshi/cli/` and `tests/cli/`.
- [ ] **CLI-Q02**: Unit test coverage on `state.py`, `edge.py` (table-driven), `lifecycle.py`. Smoke test on `app.py`.
- [ ] **CLI-Q03**: Contract drift test (`tests/cli/test_contracts.py`) parametrizes over the SDK shapes the cockpit depends on (markets/events/portfolio/orders REST + WS payload types).
- [ ] **CLI-Q04**: 4 critical-path E2E tests against demo: authed flow, lifecycle reconnect with REST refresh, sequence-gap resync, live-mode safety.

### Launch (separate from ship criteria)

- [ ] **CLI-L01**: README screenshot + GIF showing `kalshi watch` against a real demo market.
- [ ] **CLI-L02**: CHANGELOG.md entry describing the cockpit and `[cli]` extras.
- [ ] **CLI-L03**: GitHub issue #11 closed with link to release notes.

## v2 Backlog (deferred)

Tracked in `BACKLOG.md` under "CLI v2 (deferred from phase-cli-v1)". Not in active roadmap.

- **CLI-V2-01**: Order entry / ticket modal (`b`/`s` keys) with worker-dispatched orders, demo single-key vs `--live` typed-word confirm, `client_order_id` reconciliation, REST fallback for in-flight orders.
- **CLI-V2-02**: Microstructure event labeler (sweep/pull/reload/spread-widen/resync) tuned against captured demo frames.
- **CLI-V2-03**: Sibling-market navigation through `event.markets`.
- **CLI-V2-04**: Multi-ticker grid view (`kalshi watch` no args).
- **CLI-V2-05**: REPL mode (`kalshi shell`).
- **CLI-V2-06**: Optional anon WS support (SDK-side change to make `KalshiWebSocket` accept `auth: KalshiAuth | None`).

## Already Shipped (validated, v0.1-v0.15)

Reference for SDK callers and contributors. Each is a "validated" requirement.

| Version | Scope | Status |
|---------|-------|--------|
| v0.1 | Auth, Markets, Orders core, dual sync/async client, RSA-PSS signing | ✓ |
| v0.2 | Complete REST coverage (Events, Portfolio, Exchange, Historical) | ✓ |
| v0.3 | Spec-driven contract pipeline (datamodel-code-generator + drift tests) | ✓ |
| v0.4.0 | Unauthenticated client for public endpoints | ✓ |
| v0.4.1 | AsyncAPI WS contract test pipeline | ✓ |
| v0.5.0 | Order amendments, decrease, queue positions | ✓ |
| v0.6.0 | Series + Multivariate collections + Events/Multivariate endpoints | ✓ |
| v0.7.0 | Resource/spec alignment (BREAKING) | ✓ |
| v0.8.0 | Pydantic-everywhere request bodies + automated drift tests | ✓ |
| v0.9.0-v0.9.1 | Series + Multivariate integration coverage + NullableList | ✓ |
| v0.10.0 | Order Groups + Path B audit | ✓ |
| v0.11.0 | Communications/RFQ + Subaccounts (17 endpoints) | ✓ |
| v0.12.0 | API Keys + Bulk/Batch markets + Milestones + LiveData (13 endpoints) | ✓ |
| v0.13.0 | REST coverage complete (10 endpoints, 5 resources — Account.limits, StructuredTargets, FCM, Search, IncentivePrograms) | ✓ |
| v0.14.0 | WebSocket envelope drift sweep | ✓ |
| v0.15.0 | WebSocket payload type drift sweep + OrderbookManager rewrite | ✓ |

## Out of Scope

| Feature | Reason |
|---------|--------|
| Browser/web UI | TUI-only; pip-installable Python audience |
| Compiled binary distribution (homebrew, curl-pipe-bash) | Audience is Python developers who already trust pip |
| Backtesting framework | Out of SDK scope; users build their own atop the SDK |
| Strategy primitives / signal indicators | Out of SDK scope |
| OAuth / token-based auth | Kalshi uses RSA-PSS; no other auth modes supported by the API |
| Multi-exchange (Polymarket, etc.) | Kalshi-specific by design |
| Anon WebSocket on Kalshi | Kalshi protocol requires auth; SDK reflects that. v2 backlog reconsiders only if Kalshi adds public WS subscribe |
