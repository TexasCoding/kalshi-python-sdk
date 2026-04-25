# Kalshi Python SDK

## What This Is

A spec-first hybrid Python SDK for the Kalshi prediction-markets API. Hand-crafted client facade + Pydantic models, OpenAPI-generated reference models for contract drift detection, full sync/async parity, full WebSocket support with sequence-gap detection. Built for Python developers writing Kalshi trading bots who got burned by every existing SDK option (official falls behind API changes; community async client has auth bugs; pmxt requires a Node.js sidecar).

## Core Value

The only Python Kalshi SDK with **100% endpoint coverage + full WebSocket parity + spec-driven type safety + integration tests against demo**. If everything else fails, that quality bar must hold — it's the entire reason this exists.

## Requirements

### Validated

- [x] **REST coverage 100%** — every endpoint in `specs/openapi.yaml` has SDK + unit tests + integration test (with `integration_real_api_only` markers on 2 auth-gated endpoints).
- [x] **WebSocket parity** — 12 message types dispatched with envelope + payload type drift sweeps (v0.14.0 + v0.15.0).
- [x] **Sync/async parity** — every public method exists on both `KalshiClient` and `AsyncKalshiClient`.
- [x] **Hard-fail contract drift tests** — REST request/body drift + WS payload field type drift block CI on regression.
- [x] **Unauthenticated client** — `KalshiClient(demo=True)` works without RSA credentials for public endpoints (v0.4.0).
- [x] **OrderbookManager with DollarDecimal pricing** — sequence-gap-resilient orderbook merging.

### Active

- [ ] **CLI/TUI bonus feature** — `kalshi watch TICKER --fair 0.63` conviction cockpit (read-only v1) shipped as `kalshi-sdk[cli]` extras. Marketing artifact for the SDK's WebSocket quality. See `.planning/phases/01-cli-v1-cockpit/PLAN.md` and `~/.gstack/projects/kalshi-python-sdk/jeffreywest-main-design-20260424-190736.md`.

### Out of Scope

- **Order placement in CLI v1** — Codex eng-review pushback ("v1 is a screenshot toy AND a trading client"); read-only first, order entry to v2.
- **Anon WS support** — `KalshiWebSocket` requires auth; SDK-side change deferred to v2 backlog.
- **Microstructure event labeler** — needs empirical capture data first; v1 ships raw delta tape, labeler in v2.
- **Sibling-market navigation, multi-ticker grid, REPL mode** — v2 backlog (BACKLOG.md).
- **Order amendments + decrease + queue positions, FCM endpoints, structured targets, search, incentive programs, communications/RFQ, subaccounts, milestones, live data, API keys** — already shipped (v0.5-v0.13).

## Context

- Solo developer (Jeff West / TexasCoding) with deep Kalshi trading-bot domain expertise. Built bots against every existing SDK and was burned by all of them — that experience is the inspiration.
- Pre-release. No external users yet. The SDK has been proving itself by integration-testing against the Kalshi demo server, finding real bugs in the SDK before they reach users.
- 36 prior `/office-hours` sessions across 3 projects (kalshi-python-sdk, TexasCoding-cogbill-qc, ryanfrigo-kalshi-ai-trading-bot). 23 design docs shipped. Pattern: consistently picks the harder-correct option (type-safety > dynamic, spec-first > hand-roll, hard-fail drift tests > warnings).
- Project workflow stack: gstack (decision/review skills) + GSD (this framework: phase planning + execution) + Superpowers (TDD execution).
- API reference: `specs/openapi.yaml` v3.13.0 (90+ endpoints), `specs/asyncapi.yaml` (11 WS channels). Base URL: `https://api.elections.kalshi.com/trade-api/v2`. Demo: `https://demo-api.kalshi.co/trade-api/v2`.

## Constraints

- **Language**: Python 3.12+ (`requires-python = ">=3.12"`). Uses modern typing (`list[T]`, `dict[K,V]`, `T | None`).
- **Stack**: `httpx` (REST), `pydantic` v2 (models), `cryptography` (RSA-PSS auth), `websockets` v14+ (WS).
- **Quality bar**: mypy strict + ruff clean must pass on every commit; CI rejects PR otherwise. 917+ tests, integration coverage harness, hard-fail contract drift tests on REST request/body shapes and WS payload field types.
- **Distribution**: PyPI as `kalshi-sdk`. CLI ships as `kalshi-sdk[cli]` optional dependency group.
- **Auth**: RSA-PSS / SHA256 / MGF1(SHA256) / salt_length=DIGEST_LENGTH / base64. Signing payload: `str(timestamp_ms) + METHOD + path_only`.
- **Pricing convention**: All prices use `Decimal` via the `DollarDecimal` Pydantic type. Wire-format alias `_dollars`-suffix on serialization where the spec demands it.
- **POST/DELETE never retried** — duplicate order/cancel risk. Only GET/HEAD/OPTIONS retry on 429/500/502/503/504 with exponential backoff + jitter, capped at `retry_max_delay`.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Spec-first hybrid (hand-crafted client + generated reference models) | Auto-generation keeps drift detection automatic; hand-crafting keeps DX ergonomic | ✓ Good — caught real spec drifts in v0.7-v0.15 |
| `DollarDecimal` for all prices | Float arithmetic on prices is unforgivable in trading | ✓ Good — eliminated whole class of bugs |
| Sync + async parity via dual transport (not sync-wrapping-async) | True parity, no shared-runtime gotchas | ✓ Good — both clients feel native |
| Contract drift tests as hard-fails (not warnings) | Warnings get ignored | ✓ Good — every spec drift surfaces in CI |
| Unauthenticated client for public endpoints | Lower onboarding friction | ✓ Good (v0.4.0) |
| `OrderbookManager` quantity = contract count (not dollars) | Spec semantics; v0.14 was wrong | ✓ Good — fixed in v0.15.0 payload-type sweep |
| CLI ships as `kalshi-sdk[cli]` extras, not separate package | Distribution targets Python devs who already trust pip; TUI sells the SDK | ✓ Approved 2026-04-24 (office-hours + eng-review) |
| CLI v1 read-only (no order entry) | Codex eng-review pushback; complexity matched to "bonus feature" budget | ✓ Approved 2026-04-24 (eng-review tension #2) |
| CLI v1 auth-required always (no anon mode) | KalshiWebSocket requires auth on current SDK | ✓ Approved 2026-04-24 (eng-review tension #1) |

---
*Last updated: 2026-04-25 after /gsd-new-project synthesis from gstack office-hours + plan-eng-review artifacts*
