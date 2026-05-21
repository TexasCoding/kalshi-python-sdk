# Roadmap

## Shipped

See `CHANGELOG.md` for full release history.

- **Unreleased (post-v2.2.0)** — WS reliability + auth polish batch:
  WS resubscribe-window frame stashing (`#176`), `run_forever(stop_event=...)`
  cooperative shutdown (`#177`), `run_forever()` raises on missing subscription
  instead of silently returning (`#175`), `MessageQueue` `maxlen` defense-in-depth
  (`#173`), `_to_decimal_*` consolidation into `_coerce_decimal` (`#174`),
  async RSA-PSS sign offload via dedicated `ThreadPoolExecutor` (`#178`),
  first two `server_omits_despite_required` exclusions for
  `Event.product_metadata` and `EventMetadata.market_details` (`#183`). All
  closed the open items previously tracked under #106's "Wave 5 polish backlog"
  umbrella; nothing remains.

- **v2.2.0 (2026-05-19)** — response-side spec drift hardening (`#157`).
  65 new optional fields backfilled across 16 REST + WS response models
  for OpenAPI v3.18.0 / AsyncAPI v0.14 (`Market`, `Order`, `Fill`,
  `Event`, `EventMetadata`, `Settlement`, `Trade`, `IncentiveProgram`,
  `RFQ`, `Quote`, `OrderGroup` + 3 group responses, plus 11 WS payloads
  including the new `*_ts_ms` Unix-ms timestamps and
  `outcome_side` / `book_side` direction encoding). Promoted additive
  drift from warn → hard fail in CI so the next missed field surfaces
  loudly. Relaxed the request-side `le=32` cap on six subaccount fields
  (demo allocates above 32). Registered `ErrorPayload` in
  `WS_CONTRACT_MAP`; applied `extra="allow"` to all WS envelope and
  helper classes to match the payload policy from `#143`.
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

None.

## Next milestone

Not scoped. Open candidates from the v2.0/v2.1 audit backlog:

- **Required-but-Optional drift policy decision** (~204 entries on
  `test_required_drift` / `test_ws_required_drift`). Currently warn-only;
  promote to fail behind either an allowlist or a tightening pass that drops
  `None` defaults on fields the server reliably sends.
- **Continued nightly-integration `server_omits_despite_required` triage.**
  `#183` was the first batch; the next nightly run against demo will catch
  the next set as they surface.

Pick from `gh issue list` opportunistically.

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
