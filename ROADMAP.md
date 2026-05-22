# Roadmap

## Shipped

See `CHANGELOG.md` for full release history.

- **v2.6.0 (2026-05-22)** — post-v2.5 independent reviewer audit closure
  (`#273` follow-on, 7 issues `#295`–`#301`). Two breaking changes folded
  in: `int` request fields reject `bool` across V1+V2 via new
  `kalshi.StrictInt` (`#295`); `KALSHI-ACCESS-*` in `extra_headers` is
  rejected at both construction and per-request (`#298`). Critical fixes:
  WS session re-entry guard with state reset on partial connect failure
  (`#297`), case-insensitive transport header merge + explicit
  `Content-Type` pin on JSON body helpers (`#298`). Performance: orderbook
  snapshot identity adoption restored on the recv-loop bypass (`#296`),
  with public `apply_snapshot` keeping its defensive copy. Polish:
  `Sync/AsyncTransport.close()` idempotent (`#301`), docs corrections
  (`#299`, `#300`). Executed across 3 sequential waves (W0 docs, W1
  money/correctness, W2 polish) — 7 PRs merged.

- **v2.5.0 (2026-05-21)** — post-v2.4 multi-reviewer SDK audit closure
  (#273, 34 issues across 7 surfaces). Critical fixes: WS seq watermark
  rolls back on validation failure (#241), REST/WS split-environment
  rejected (#239), `buy_max_cost` rejects bool (#243), network-level
  httpx errors retry on idempotent verbs (#240, `KalshiNetworkError`).
  Two breaking changes folded in: `orders.create()` requires
  `count`+`action` (#242), six REST + three WS model fields widened
  `str`/`float` → `Decimal` (#258, #259). Performance wins on the WS
  hot path: per-frame Task/shield dropped (#245), materialized
  Orderbook cached on `_BookState` (#244), snapshot apply single dict
  walk (#263), `Page.to_dataframe` column-oriented (#264), pluggable
  REST JSON loader (#260). DX: `extra_headers=` plumbed through every
  public resource method (#253), `KalshiConfig.allow_unknown_host`
  default-fail (#250). Executed across 4 sequential waves (W0 docs,
  W1 money-risk, W2 medium, W3 polish) — 20 PRs merged.

- **v2.4.0 (2026-05-21)** — multi-reviewer SDK audit closure (#224, 33
  issues across 7 surfaces). Critical fixes: WS orderbook resync on
  sequence gap (#189), DataFrame Decimal preservation (#190), positional
  Decimal serialization (#191). One breaking change folded in:
  `orders.batch_create`/`batch_cancel` now return typed responses (#194).
  Tier 2 + polish bundles all landed across waves W2 + W3.

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

Not scoped. Pre-audit candidates still standing:

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
