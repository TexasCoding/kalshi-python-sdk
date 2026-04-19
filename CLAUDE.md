# Kalshi Python SDK

## Behavioral Guidelines

Apply these before and during every task. They override default speed/verbosity bias.
For trivial tasks, use judgment — but bias toward caution over speed.

### 1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First
Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite it.

Test: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes
Touch only what you must. Clean up only your own mess.
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken. Match existing style.
- Remove imports/vars/functions only if YOUR changes orphaned them.
- Don't delete pre-existing dead code — mention it instead.

Test: every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution
Define success criteria. Loop until verified.
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan with `verify:` checks per step.

## Commands

```bash
uv sync                         # install dependencies
uv run pytest tests/ -v         # run all tests
uv run ruff check .             # lint
uv run ruff check . --fix       # lint + auto-fix
uv run mypy kalshi/             # type check (MUST pass before every commit)
```

**Always run mypy before committing.** CI runs mypy strict and will reject the PR if it fails.
The `list` builtin is shadowed by resource `.list()` methods. Use `builtins.list[T]` in type
annotations inside resource classes (not bare `list[T]`).

## Architecture

Spec-First Hybrid SDK: hand-crafted client facade + Pydantic models. OpenAPI-generated
models live in `kalshi/_generated/` and feed contract tests via `_contract_map.py`.

```
kalshi/
  __init__.py              # Public API exports + __version__
  client.py / async_client.py     # Sync and async facades
  _base_client.py          # SyncTransport + AsyncTransport (httpx, retry, error mapping)
  _contract_map.py         # Maps SDK models ↔ generated OpenAPI models for contract tests
  _generated/              # OpenAPI-generated models (do not hand-edit)
  auth.py                  # RSA-PSS signer
  config.py                # KalshiConfig (base URL, timeouts, retry policy)
  errors.py                # Exception hierarchy
  types.py                 # DollarDecimal custom Pydantic type
  models/                  # common, markets, orders, events, exchange, historical,
                           # multivariate, portfolio, series
  resources/               # Sync + async resources matching models/
  ws/                      # WebSocket: client, connection, channels, dispatch,
                           # backpressure, sequence, orderbook, models/
tests/
  conftest.py              # Shared fixtures (RSA keys, auth, config)
  _contract_support.py     # Contract test helpers
  integration/             # Live API integration tests
  ws/                      # WebSocket tests
  test_*.py                # Per-resource + per-feature tests (827 total)
```

## Key conventions

- **Price format:** Kalshi API returns prices as FixedPointDollars strings (e.g. `"0.5600"`)
  with `_dollars` suffix field names. SDK models use short Python names (`yes_bid`)
  with `validation_alias=AliasChoices("yes_bid_dollars", "yes_bid")` to accept both.
  `CreateOrderRequest` serializes with `_dollars` suffix via `serialization_alias`.
  Verified against OpenAPI spec v3.13.0 on 2026-04-12.
- All prices use `Decimal` via the `DollarDecimal` custom Pydantic type.
- Auth signing payload: `str(timestamp_ms) + METHOD + path_only` (path from urlparse,
  no query params, no trailing slash).
- POST and DELETE are NEVER retried (duplicate order/cancel risk). Only GET/HEAD/OPTIONS retry.
- Retry on 429/502/503/504 with exponential backoff + jitter, capped at `retry_max_delay`.
- `Retry-After` header is capped at `retry_max_delay` (prevents server-controlled sleep).
- Sync and async share logic via dual transport abstraction (not sync-wrapping-async).
- Async `list_all()` returns `AsyncIterator` directly — `async for item in client.markets.list_all():` works.
- **Request bodies are Pydantic models with `extra="forbid"` (v0.8.0+).** Every POST/PUT/DELETE-with-body method builds a request model internally and serializes via `model.model_dump(exclude_none=True, by_alias=True, mode="json")`. Don't build inline dict bodies in resource methods. Phantom keys fail at call time via the model's forbid.
- **Drift tests hard-fail.** `TestRequestParamDrift` (query+path) and `TestRequestBodyDrift` (body) parametrize over `METHOD_ENDPOINT_MAP`. Adding a new kwarg the spec doesn't have, or missing one the spec has, reds CI. Intentional deviations go in `EXCLUSIONS` (`tests/_contract_support.py`) with a required `reason` string.

## Adding a new resource

1. Create `kalshi/models/new_resource.py` with Pydantic models. Use `DollarDecimal` for
   prices, `validation_alias=AliasChoices("api_name_dollars", "short_name")` for API field mapping.
2. For POST/PUT/DELETE endpoints with a request body: create a request model (e.g. `CreateThingRequest`) with `model_config = {"extra": "forbid"}`. Set `serialization_alias="foo_dollars"` / `"count_fp"` for wire-format mismatches.
3. Create `kalshi/resources/new_resource.py` with both `NewResource(SyncResource)` and
   `AsyncNewResource(AsyncResource)`. POST/PUT/DELETE methods build their request model internally, then serialize via `model.model_dump(exclude_none=True, by_alias=True, mode="json")`.
4. Wire into `KalshiClient.__init__` and `AsyncKalshiClient.__init__`.
5. Export from `kalshi/models/__init__.py` and `kalshi/__init__.py`.
6. Add tests in `tests/test_new_resource.py` using `respx.mock`.
7. Every public method needs at least: happy path, error path, edge case.
8. Register endpoints in `METHOD_ENDPOINT_MAP` (`tests/_contract_support.py`). POST/PUT/DELETE entries must set `request_body_schema` to the spec ref (e.g., `"#/components/schemas/CreateThingRequest"`). Add the spec-ref → model-FQN mapping to `BODY_MODEL_MAP` in `tests/test_contracts.py` so the body drift test can diff it.
9. If the resource has generated OpenAPI counterparts, register them in `_contract_map.py`.

## Testing

- pytest + pytest-asyncio + respx (httpx mock); 917 tests.
- Use `respx.mock` for HTTP mocking. Generate test RSA keys via conftest.py fixtures.
- New function → write a test. Bug fix → write a regression test. New error path → write a test that triggers it.

## API Reference

- OpenAPI spec: https://docs.kalshi.com/openapi.yaml (v3.13.0, 90+ endpoints)
- AsyncAPI spec: https://docs.kalshi.com/asyncapi.yaml (11 WebSocket channels)
- Base URL: https://api.elections.kalshi.com/trade-api/v2
- Demo URL: https://demo-api.kalshi.co/trade-api/v2
- Auth: RSA-PSS / SHA256 / MGF1(SHA256) / salt_length=DIGEST_LENGTH / base64

## Skill routing — three-layer stack

We compose three frameworks deliberately. Each constrains a different dimension;
don't install-and-invoke everything.

> **gstack thinks → GSD stabilizes → Superpowers executes**

Heuristics for picking a layer:
- Requirements still fuzzy → start with **gstack** (decision)
- Work keeps diverging across sessions → add **GSD** (context)
- You want execution steady and closed-loop → lean on **Superpowers** (execution)

When a request matches a skill, invoke it via the Skill tool BEFORE answering or
running other tools. Avoid running the full ceremony on trivial asks (a two-line
config fix doesn't need brainstorm → plan → TDD).

### Layer 1 — Decision → gstack
Decide *what* to build and *whether* to build it before touching code.
- Fuzzy requirements / "is this worth building" → `office-hours`
- Stress-test scope and ambition → `plan-ceo-review`
- Lock architecture, data flow, edge cases → `plan-eng-review`
- UI/UX in scope → `plan-design-review`
- Run the full decision gauntlet → `autoplan`

### Layer 2 — Context → GSD
Anchor specs, status, and boundaries in `.planning/` so context doesn't rot
across sessions. Atomic commits, fresh context per task, persisted state.
- New project / new milestone → `gsd-new-project`, `gsd-new-milestone`
- Plan / execute a phase → `gsd-plan-phase`, `gsd-execute-phase`
- Resume after a break or context reset → `gsd-resume-work`, `checkpoint`
- Pause mid-phase → `gsd-pause-work`
- Cross-AI peer review of a plan → `gsd-review`
- Systematic debugging across context resets → `gsd-debug`
- Ship the phase (PR + verification) → `gsd-ship`
- Verify / validate a completed phase → `gsd-verify-work`, `gsd-validate-phase`

### Layer 3 — Execution → Superpowers
Closed loop: brainstorm → plan → TDD → review → finalize. TDD is mandatory —
write the test first; code written before tests gets deleted.
- Any creative work, before designing → `superpowers:brainstorming`
- Multi-step task with a spec → `superpowers:writing-plans` → `superpowers:executing-plans`
- Implementing any feature or bugfix → `superpowers:test-driven-development`
- 2+ independent tasks → `superpowers:dispatching-parallel-agents` or `superpowers:subagent-driven-development`
- Before claiming "done" → `superpowers:verification-before-completion`
- Asking for review → `superpowers:requesting-code-review`
- Receiving review feedback → `superpowers:receiving-code-review`
- Closing out work → `superpowers:finishing-a-development-branch`
- Worktree-isolated branch work → `superpowers:using-git-worktrees`

### Cross-cutting (use as needed)
- Bug, error, "why is this broken" → `investigate` (light) or `gsd-debug` (multi-session)
- Code review of a diff → `review`, `superpowers:requesting-code-review`, or `gsd-code-review`
- Update docs after shipping → `document-release` or `gsd-docs-update`
- Code health / quality dashboard → `health`

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **kalshi-python-sdk** (5058 symbols, 12149 relationships, 283 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/kalshi-python-sdk/context` | Codebase overview, check index freshness |
| `gitnexus://repo/kalshi-python-sdk/clusters` | All functional areas |
| `gitnexus://repo/kalshi-python-sdk/processes` | All execution flows |
| `gitnexus://repo/kalshi-python-sdk/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
