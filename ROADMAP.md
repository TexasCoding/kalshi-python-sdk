# Roadmap

## v1.2 — Audit-driven hardening (planned)

30 issues opened from the post-v1.1.0 audit swarm (`#77`–`#106`). Implementation
plan below mirrors the wave-based parallel execution that produced v1.1: each
wave is a set of disjoint-file branches worked by parallel agents off `main`,
reviewed and merged one PR at a time. Sequential waves depend on prior waves
landing first.

### Wave 1 — Independent, low-risk fixes (parallel, 5 agents)

All touch disjoint files. No dependency between any item.

| Branch | Issues | Scope |
|---|---|---|
| `feat/issue-89-export-models` | [#89](https://github.com/TexasCoding/kalshi-python-sdk/issues/89) | Re-export 23 missing model classes from `kalshi.__all__` |
| `fix/issues-91-94-96-correctness` | [#91](https://github.com/TexasCoding/kalshi-python-sdk/issues/91) [#94](https://github.com/TexasCoding/kalshi-python-sdk/issues/94) [#96](https://github.com/TexasCoding/kalshi-python-sdk/issues/96) | `Order.type` cleanup + bool-param consistency, `KALSHI_API_BASE_URL` validation, `Retry-After` negative/NaN |
| `perf/issues-103-104-105` | [#103](https://github.com/TexasCoding/kalshi-python-sdk/issues/103) [#104](https://github.com/TexasCoding/kalshi-python-sdk/issues/104) [#105](https://github.com/TexasCoding/kalshi-python-sdk/issues/105) | `MessageQueue.qsize()` O(1), Full Jitter retry, `RecordingTransport` in-memory buffer |
| `infra/issues-93-95-pinning` | [#93](https://github.com/TexasCoding/kalshi-python-sdk/issues/93) [#95](https://github.com/TexasCoding/kalshi-python-sdk/issues/95) | SHA-pin Claude workflows, add Dependabot + `pip-audit` |
| `infra/issue-92-spec-sync-hardening` | [#92](https://github.com/TexasCoding/kalshi-python-sdk/issues/92) | Spec-sync supply-chain mitigations |

### Wave 2 — Test coverage backfill (parallel, 6 agents, after Wave 1)

Wave 2 lands after Wave 1 so `#97` can write tests against the fixed
`Retry-After` validator and `#98`'s `max_pages` work has the surrounding
correctness fixes already merged.

| Branch | Issues |
|---|---|
| `test/issue-97-retry-coverage` | [#97](https://github.com/TexasCoding/kalshi-python-sdk/issues/97) |
| `test/issue-98-max-pages` | [#98](https://github.com/TexasCoding/kalshi-python-sdk/issues/98) (test + public API kwarg) |
| `test/issue-99-config-coverage` | [#99](https://github.com/TexasCoding/kalshi-python-sdk/issues/99) |
| `test/issue-100-recorder-html` | [#100](https://github.com/TexasCoding/kalshi-python-sdk/issues/100) |
| `test/issue-101-dataframe-nested` | [#101](https://github.com/TexasCoding/kalshi-python-sdk/issues/101) |
| `test/issue-102-ws-backlog` | [#102](https://github.com/TexasCoding/kalshi-python-sdk/issues/102) |

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

v1.2 is ready to tag when:

- All **HIGH** severity items (`#77`, `#78`, `#79`, `#89`, `#92`, `#97`) are
  merged.
- All **MEDIUM** items are merged or explicitly deferred with a comment in
  `ROADMAP.md`.
- `CHANGELOG.md` has a `## 1.2.0` section.
- `pyproject.toml` and `kalshi/__init__.py` version bumped to `1.2.0`.

Then `git tag v1.2.0 && git push origin v1.2.0` per `docs/RELEASING.md`.

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
