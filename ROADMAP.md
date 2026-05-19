# Roadmap

## Shipped

See `CHANGELOG.md` for full release history.

- **v2.1.0 (2026-05-18)** — OpenAPI sync v3.13.0 → v3.18.0 (`#155`). V2
  event-market orders family (`create_v2` / `amend_v2` / `decrease_v2` /
  `cancel_v2` + batched variants on `/portfolio/events/orders/*`),
  deposit/withdrawal history, account endpoint-cost introspection,
  `Balance.balance_dollars` (soft-breaking at construction sites only),
  optional `exchange_index` / `user_filter` / `rfq_user_filter` /
  `incentive_description` / `post_only` kwargs on existing endpoints.
  Also fixes a recurring false-alarm in the weekly spec-drift workflow
  by committing `specs/asyncapi.yaml` as a pinned snapshot.
- **v2.0.0 (2026-05-17)** — audit-driven hardening. 30 audit findings closed
  across five parallel waves (`#77`–`#106`) plus follow-ups: WebSocket
  recv-loop overhaul (5 reconnect races + narrowed exceptions),
  spec-sync supply-chain rewrite, single-parse WS hot path, public
  `max_pages` pagination cap, `extra="allow"` policy enforcement,
  trade-data + URL log-leak scrubs, and 3 deliberate breaking changes
  (`Order.type` → `.order_type`, `AccountApiLimits.{read,write}_limit`
  removed, count/size/volume fields retyped to `FixedPointCount`). See
  [`docs/migration.md`](docs/migration.md) for the v1 → v2 migration
  guide.
- **v1.1.0 (2026-05-16)** — model-first request API, DataFrame integration,
  record/replay mock transport, MkDocs documentation site, `Literal` enum
  kwargs, sync/async dedup refactor, weekly spec sync + nightly integration
  CI workflows.
- **v1.0.0 (2026-05-10)** — public API stable. 89/89 REST endpoints, 11 WS
  channels, contract drift tests, PyPI trusted-publisher release pipeline.

## Open trackers

- [#106](https://github.com/TexasCoding/kalshi-python-sdk/issues/106) —
  Wave 5 polish backlog umbrella. 5 items landed via #141; remaining
  sub-items (e.g. `MessageQueue.maxlen` defense-in-depth, RSA-sign via
  executor, `run_forever` foot-gun) are opportunistic.
- [#45](https://github.com/TexasCoding/kalshi-python-sdk/issues/45) —
  verify `json={}` workaround under prod credentials. Blocked on
  prod-key access.
- [#53](https://github.com/TexasCoding/kalshi-python-sdk/issues/53) —
  resolve nested `$ref` pointers in body-schema drift check. Spec
  currently has no nested refs; implement when one lands.

## Next milestone

Not scoped. Carry-overs from v2.1 and v2.0 audit backlog:

- **Response-side spec drift detection.** v2.1 contract tests cover request
  bodies (`TestRequestBodyDrift`) but not response models, which is how
  `Balance.balance_dollars` slipped through 5 rounds of review. Add a
  `RESPONSE_MODEL_MAP` + walker that asserts spec-required fields exist on
  the SDK model.

- Apply `extra="allow"` policy to WS envelope models (`kalshi/ws/models/`)
  to mirror the response-model uniformity from `#114`.
- `MessageQueue._buffer = collections.deque(maxlen=maxsize+1)` for
  defense-in-depth (#106 F-P-15 / F-R-02).
- `_to_decimal_dollars` / `_to_decimal_fp` consolidation (#106 F-N-09 +
  the follow-up noted in #140).
- WS UX foot-guns: auto-start recv loop when no `subscribe_*` was called,
  resubscribe-time data-frame stashing (#106 F-P-16 / F-R-13).

Pick from `gh issue list` and the deferred items in `#106` opportunistically.

## Execution conventions (carried from v2.0)

These are the patterns that proved out across the five v2.0 waves:

- Each wave's branches off `main` at the wave-start commit.
- Each branch isolated in a git worktree (`isolation: "worktree"` for
  agent runs).
- Each agent is **`general-purpose`**, not `octo:droids:octo-*` — the octo
  droids failed reliably in the v1.1 audit swarm (rejected, hung,
  hallucinated reports).
- Each agent commits in its worktree with `Closes #N`; PR opened by the
  orchestrator; bot review addressed; squash-merge; gitnexus index
  refreshed after each merge that changes `kalshi/` symbols.
- Sequential waves wait for prior waves to merge before starting.
- **Worktree CWD must be specified explicitly in every Bash call** — the
  harness resets CWD between calls and Wave 2's #102 and Wave 5's #106
  agents leaked commits onto local `main` because of CWD slip.
- For breaking changes, surface the version-bump decision (next minor vs
  next major) explicitly in the PR body and CHANGELOG so the release
  cutter doesn't have to dig.
