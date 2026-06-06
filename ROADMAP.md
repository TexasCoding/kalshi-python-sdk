# Roadmap

## Shipped

- **v3.3.0 (2026-06-06)** — complete **FIX protocol** subsystem (FIXT.1.1 /
  FIX50SP2) for both products: `FixClient` (prediction) + `MarginFixClient`
  (margin) over a hand-rolled async session engine, with six session types
  (order entry, drop copy, market data, order groups, post-trade settlement,
  RFQ), typed message models, order-book / settlement reassembly, and a
  model↔dictionary drift test (epic #402; follow-ups #432, #437). New
  [FIX guide](docs/fix.md). Additive — no changes to REST / WebSocket / Perps.
- **v3.2.0 (2026-06-05)** — full **Perps (margin) API** support: standalone
  `PerpsClient` / `AsyncPerpsClient` (REST), `PerpsWebSocket`, and the
  Self-Clearing-Member `KlearClient` (cookie-session + MFA settlement API),
  alongside the unchanged prediction-API surface. Also hardened the prediction
  and perps list endpoints to validate typed response envelopes (a missing
  spec-required array now surfaces as a `ValidationError`). Additive for
  existing `KalshiClient` users.
- **v3.1.0 (2026-06-04)** — OpenAPI sync v3.19.0 → v3.20.0: `events.fee_changes`,
  `is_block_trade`, and the `event_fee_update` frame on the `market_lifecycle_v2`
  WebSocket channel.
- **v3.0.1 (2026-05-26)** — OpenAPI sync v3.18.0 → v3.19.0.
- **v3.0.0 (2026-05-22)** — first major release in the v3 line. Three
  breaking-rename issues (`#348`, `#349`, `#351`) deferred from the v2.7.0
  audit closure land with one-release deprecation aliases:
  `CommunicationsResource` flat noun-prefixed methods split into
  `client.communications.{rfqs,quotes}.<verb>` sub-namespaces (`#348`);
  `MarketsResource.list_trades_all` → `list_all_trades` to match the
  `list_all_<noun>` convention used by Communications/Subaccounts (`#349`);
  `OrdersResource.fills` / `fills_all` relocate to `PortfolioResource`
  alongside `settlements` / `deposits` / `withdrawals` since the endpoint URL
  is `/portfolio/fills` (`#351`). Wire protocol unchanged. New
  `RFQsResource`/`QuotesResource`/`AsyncRFQsResource`/`AsyncQuotesResource`
  exported from `kalshi/__init__.py` for type annotations. 78 new regression
  tests covering deprecation-alias delegation and warning emission. Migration
  guide at `docs/migrations/v2-to-v3.md`. Aliases removed no sooner than
  v3.1.0.

See `CHANGELOG.md` for full release history.

- **v2.7.0 (2026-05-22)** — post-v2.6 independent multi-LLM reviewer audit
  closure (47 issues `#311`–`#357`, 44 closed; `#348` / `#349` / `#351`
  deferred to v3.0.0). Identified by a 9-reviewer parallel pass combining 7
  internal specialist agents with fresh-eyes Codex CLI (GPT-5) + Gemini CLI
  reviews. Five breaking fences folded in: `AmendOrderRequest.side`/`.action`
  narrowed to `Literal` (`#312`); `KalshiConfig.extra_headers` immutable
  post-construction (`#313`); communications `status` kwarg `Literal`
  (`#324`); `to_decimal()` rejects NaN/Inf (`#325`); `DollarDecimal` request
  fields reject negative/sub-tick (`#343`). Critical fixes: `from_env`
  caller-ownership invariant (`#311`), WS `TimeoutError` wrap (`#314`), WS
  zombie-subscription cleanup (`#315`). High-impact correctness: lazy
  `try_from_env` (`#316`), `sign_request` strips URL fragment (`#317`),
  `Retry-After` honored across 408/429/503/504 with jitter (`#321`, `#322`),
  success-body size cap (`#323`), V1 `ge=0` parity (`#326`), `Page._columns`
  None-first nested (`#328`), WS `OrderbookDeltaPayload.ts` AwareDatetime
  (`#331`), WS backpressure WS teardown (`#332`). Performance: orderbook
  `model_construct` (`#327`), zero-delta cache preservation (`#347`),
  `apply_snapshot` single-copy (`#344`), V2 batch bytes fast-path (`#329`),
  PSS config cache (`#345`), `track_sync` (`#330`), `asyncio.timeout` recv
  (`#356`), `method.upper` hoist (`#342`). Polish: async close
  cancellation-safe (`#333`), `_delete_with_body(params=)` (`#340`),
  non-adjacent pagination cycle (`#352`), orphan unsubscribe correlation
  (`#354`), reconnect exc_info (`#355`), `_stop()` teardown order (`#357`),
  dropped `extra_headers` dual pipeline (`#341`), `orders.create()` overload
  (`#350`), docs + docstring drift (`#318`–`#320`, `#334`–`#339`), OpenSSH
  key error message (`#335`). Dependencies: `pydantic>=2.4` (`#346`).
  Executed across 4 sequential waves (W0 docs, W1 HIGH, W2 MEDIUM, W3 LOW)
  in disjoint git worktrees — 17 PRs merged.

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
