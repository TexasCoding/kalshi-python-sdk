# Roadmap

## v1.2 — Audit-driven hardening (in progress)

30 issues opened from the post-v1.1.0 audit swarm (`#77`–`#106`). Implementation
plan below mirrors the wave-based parallel execution that produced v1.1: each
wave is a set of disjoint-file branches worked by parallel agents off `main`,
reviewed and merged one PR at a time. Sequential waves depend on prior waves
landing first.

### Wave 1 — ✅ Shipped (2026-05-17)

5 PRs squash-merged, closing 10 issues. All disjoint-file work landed in one
day via parallel agents off `main`.

| PR | Closes | Scope |
|---|---|---|
| [#108](https://github.com/TexasCoding/kalshi-python-sdk/pull/108) | [#93](https://github.com/TexasCoding/kalshi-python-sdk/issues/93) [#95](https://github.com/TexasCoding/kalshi-python-sdk/issues/95) | SHA-pin Claude workflows, add Dependabot + `pip-audit` |
| [#109](https://github.com/TexasCoding/kalshi-python-sdk/pull/109) | [#92](https://github.com/TexasCoding/kalshi-python-sdk/issues/92) | Spec-sync supply-chain mitigations (drift now opens per-fingerprint issues, not auto-PRs) |
| [#110](https://github.com/TexasCoding/kalshi-python-sdk/pull/110) | [#89](https://github.com/TexasCoding/kalshi-python-sdk/issues/89) | Re-export 23 model classes from `kalshi.__all__` + dynamic parity test |
| [#111](https://github.com/TexasCoding/kalshi-python-sdk/pull/111) | [#103](https://github.com/TexasCoding/kalshi-python-sdk/issues/103) [#104](https://github.com/TexasCoding/kalshi-python-sdk/issues/104) [#105](https://github.com/TexasCoding/kalshi-python-sdk/issues/105) | `MessageQueue.qsize()` O(1), AWS Full Jitter retry, buffered `RecordingTransport` |
| [#112](https://github.com/TexasCoding/kalshi-python-sdk/pull/112) | [#91](https://github.com/TexasCoding/kalshi-python-sdk/issues/91) [#94](https://github.com/TexasCoding/kalshi-python-sdk/issues/94) [#96](https://github.com/TexasCoding/kalshi-python-sdk/issues/96) | ⚠️ **Breaking** `Order.type` → `Order.order_type` + base URL validation (http/https + ws/wss) + `Retry-After` NaN/negative/zero handling |
| [#120](https://github.com/TexasCoding/kalshi-python-sdk/pull/120) | (CI hotfix) | `uv pip install pip` so pip-audit can introspect the uv-managed venv |

**Wave 1 learnings worth carrying forward:**

- Bot review iterates multiple passes. Spec-sync (#109) needed 4 rounds — the long-lived tracking-issue pattern was the wrong shape; per-drift fingerprint-deduped issues replaced it.
- The `Order.type` rename in #112 is the only breaking change in Wave 1 and triggers the v1.2 vs v2.0 release decision (see Release-cut criteria below).
- Worktree CWD slips between Bash calls in the harness — agents that don't pass an explicit `cd` to every Bash call leak files into the parent repo. Reinforce in agent prompts.
- pip-audit needs `pip` seeded into the uv venv; uv doesn't put it there by default.

### Wave 2 — Test coverage backfill (⏸ paused; planned next)

Paused — interim work in flight (see *Interim work* below). Resume when those
items land. Wave 2 still depends on Wave 1's correctness fixes (already in
main), so unblocked technically; the pause is scope ordering, not dependency.

| Branch | Issues |
|---|---|
| `test/issue-97-retry-coverage` | [#97](https://github.com/TexasCoding/kalshi-python-sdk/issues/97) |
| `test/issue-98-max-pages` | [#98](https://github.com/TexasCoding/kalshi-python-sdk/issues/98) (test + public API kwarg) |
| `test/issue-99-config-coverage` | [#99](https://github.com/TexasCoding/kalshi-python-sdk/issues/99) |
| `test/issue-100-recorder-html` | [#100](https://github.com/TexasCoding/kalshi-python-sdk/issues/100) |
| `test/issue-101-dataframe-nested` | [#101](https://github.com/TexasCoding/kalshi-python-sdk/issues/101) |
| `test/issue-102-ws-backlog` | [#102](https://github.com/TexasCoding/kalshi-python-sdk/issues/102) |

### Interim work (before Wave 2)

Items in flight after Wave 1 landed. List grows / shrinks as work is scoped.

- TBD — fill in as items are scoped.

### Follow-ups opened during Wave 1 review

- [#114](https://github.com/TexasCoding/kalshi-python-sdk/issues/114) — audit response models for consistent `extra=` policy. Opened during #112 review; pre-existing gap unrelated to #91's scope. Candidate for Wave 5 polish.
- [#113](https://github.com/TexasCoding/kalshi-python-sdk/issues/113) — closed as superseded by #109's per-drift fingerprint pattern.

### Wave 3 — WebSocket overhaul (parallel by file boundary, 3 agents)

Three disjoint WS file scopes can land in parallel since they touch different
modules.

| Branch | Files | Issues |
|---|---|---|
| `fix/ws-orderbook-overhaul` | `kalshi/ws/orderbook.py` (+ model) | [#85](https://github.com/TexasCoding/kalshi-python-sdk/issues/85) mutate in place + [#87](https://github.com/TexasCoding/kalshi-python-sdk/issues/87) O(n) → dict-backed |
| `fix/ws-dispatcher-correctness` | `kalshi/ws/dispatch.py` | [#80](https://github.com/TexasCoding/kalshi-python-sdk/issues/80) callback collision + [#81](https://github.com/TexasCoding/kalshi-python-sdk/issues/81) server unsubscribe + [#82](https://github.com/TexasCoding/kalshi-python-sdk/issues/82) error envelope |
| `fix/ws-recv-loop-overhaul` | `kalshi/ws/client.py` + `channels.py` | [#77](https://github.com/TexasCoding/kalshi-python-sdk/issues/77) reconnect races + [#83](https://github.com/TexasCoding/kalshi-python-sdk/issues/83) broad except + [#84](https://github.com/TexasCoding/kalshi-python-sdk/issues/84) log leakage + [#86](https://github.com/TexasCoding/kalshi-python-sdk/issues/86) double-parse + [#88](https://github.com/TexasCoding/kalshi-python-sdk/issues/88) `_set_state` reach-through |

The recv-loop branch (`#77` umbrella) is the biggest unit of work in v1.2 and
must integrate the broad-except fix at the same time — its 5 reconnect race
fixes change the same `_recv_loop` exception block that `#83` narrows. One
agent, sequential commits within the branch.

### Wave 4 — Backpressure & gap correctness (after Wave 3)

Depends on the recv-loop overhaul because it changes when seq-tracking and
orderbook-apply happen relative to dispatch.

| Branch | Issues |
|---|---|
| `fix/ws-backpressure-gap-correctness` | [#78](https://github.com/TexasCoding/kalshi-python-sdk/issues/78) ERROR-overflow desync + [#79](https://github.com/TexasCoding/kalshi-python-sdk/issues/79) multi-ticker seq-gap |

### Wave 5 — Type-annotation cleanup + polish backlog

| Branch | Issues |
|---|---|
| `polish/issue-90-type-drift` | [#90](https://github.com/TexasCoding/kalshi-python-sdk/issues/90) |
| `polish/issue-106-backlog` | [#106](https://github.com/TexasCoding/kalshi-python-sdk/issues/106) (umbrella; pick off items opportunistically) |

### Release-cut criteria

Ready to tag when:

- All **HIGH** severity items merged:
  - ✅ `#89` (Wave 1, #110), ✅ `#92` (Wave 1, #109)
  - ⏳ `#77`, `#78`, `#79` (Waves 3 + 4)
  - ⏳ `#97` (Wave 2)
- All **MEDIUM** items merged or explicitly deferred with a comment in `ROADMAP.md`.
- `CHANGELOG.md` `[Unreleased]` section finalized into a versioned section.
- `pyproject.toml` and `kalshi/__init__.py` version bumped.

**Version-bump decision: v1.2.0 vs v2.0.0** — Wave 1 #112 renamed
`Order.type` → `Order.order_type` (wire format preserved via
`validation_alias`, but the Python attribute changed). The breaking-change
entry is already in `CHANGELOG.md` under `[Unreleased] → Breaking`. Decide
at tag time:

- **v1.2.0** treats it as a small-blast-radius break (the attribute is on
  a return-only model; no user-constructed `Order.type=` to migrate). Risk:
  semver-strict consumers on `^1.x` pins get an `AttributeError` with no
  deprecation period.
- **v2.0.0** is the semver-clean call. Heavier release narrative for what
  is otherwise mostly hardening work.

Then `git tag <vX.Y.Z> && git push origin <vX.Y.Z>` per `docs/RELEASING.md`.

### Execution conventions

Matches the wave pattern from v1.1:

- Each wave's branches off `main` at the wave-start commit.
- Each branch isolated in a git worktree (`isolation: "worktree"` for
  agent runs).
- Each agent is **`general-purpose`**, not `octo:droids:octo-*` — the octo
  droids failed reliably in the v1.1 audit swarm (rejected, hung, hallucinated
  reports).
- Each agent commits in its worktree with `Closes #N`; PR opened by the
  orchestrator; bot review addressed; squash-merge; gitnexus index refreshed.
- Sequential waves wait for prior waves to merge before starting.
- Worktree CWD must be specified explicitly in every Bash call — the harness
  resets CWD between calls and multiple v1.1 agents wrote files to the parent
  repo by accident.

### Deferred from v1.1 (not blockers)

- [#45](https://github.com/TexasCoding/kalshi-python-sdk/issues/45) — verify
  `json={}` workaround under production credentials. Blocked on prod-key access.
- [#53](https://github.com/TexasCoding/kalshi-python-sdk/issues/53) — resolve
  nested `$ref` pointers in body-schema drift check. Premature — the spec
  currently has no nested refs.

Both stay in the v1.1 GitHub milestone as tracking placeholders; they unblock
when their preconditions land, independent of v1.2.

## Shipped

See `CHANGELOG.md` for full release history.

- **v1.1.0 (2026-05-16)** — model-first request API, DataFrame integration,
  record/replay mock transport, MkDocs documentation site, `Literal` enum
  kwargs, sync/async dedup refactor, weekly spec sync + nightly integration
  CI workflows.
- **v1.0.0 (2026-05-10)** — public API stable. 89/89 REST endpoints, 11 WS
  channels, contract drift tests, PyPI trusted-publisher release pipeline.
