---
phase: 01-cli-v1-conviction-cockpit
plan: 05
type: execute
wave: 5
depends_on: [01, 02, 03, 04]
files_modified:
  - tests/cli/integration/__init__.py
  - tests/cli/integration/conftest.py
  - tests/cli/integration/test_watch.py
autonomous: true
requirements: [CLI-02, CLI-04, CLI-08, CLI-09, CLI-12, CLI-Q04]
must_haves:
  truths:
    - "Authed demo flow: cockpit mounts, REST snapshot completes, header renders with live close countdown, ladder fills with live data, all within 5s"
    - "Lifecycle reconnect with REST refresh: forced disconnect re-fetches REST snapshot AFTER the RECONNECTING→STREAMING transition; positions/balance/resting_orders match a fresh REST call"
    - "Sequence-gap resync: forced sequence gap triggers OrderbookManager.clear() inside the SDK; tape gets a [resync] line; ladder repopulates"
    - "Live mode safety: cockpit launches against api.elections.kalshi.com with valid live env (read-only — no order placement in v1)"
  artifacts:
    - path: "tests/cli/integration/__init__.py"
      provides: "package marker"
    - path: "tests/cli/integration/conftest.py"
      provides: "demo-API fixtures (reuse from tests/integration/) + cockpit-app harness fixture"
      contains: "cockpit_pilot"
    - path: "tests/cli/integration/test_watch.py"
      provides: "4 critical-path E2E tests against demo, marked @pytest.mark.integration"
      contains: "TestCockpitDemo"
  key_links:
    - from: "tests/cli/integration/test_watch.py"
      to: "kalshi.cli.app.CockpitApp"
      via: "App.run_test() with real AsyncKalshiClient against demo + assertions on store + DOM"
      pattern: "CockpitApp.*run_test|async with .*\\.run_test"
    - from: "tests/cli/integration/conftest.py"
      to: "tests/integration/conftest.py"
      via: "pytest fixture discovery (async_client, demo_market_ticker reused via parent conftest)"
      pattern: "async_client|demo_market_ticker"
---

<objective>
Land the 4 critical-path E2E tests against demo that prove the cockpit's marketing
claim: that the SDK's WebSocket quality is visibly excellent on a real exchange.
These tests are slow (each takes 5–30s of real network time), gated by
`@pytest.mark.integration`, and skip cleanly without demo creds — same pattern as
`tests/integration/test_websocket.py`.

Purpose: Unit tests prove the parts compose. Integration tests prove the whole works
against the actual exchange — this is what gates "ship". The lifecycle reconnect with
REST refresh test in particular is the last line of defense against the Codex eng-review
finding ("private channels need REST bootstrap on every reconnect"); if it passes here,
the architecture decision is validated end-to-end.

Output: 1 conftest.py with cockpit-pilot fixture + 1 test_watch.py with 4
@pytest.mark.integration tests, all gated on KALSHI_KEY_ID env presence and demo URL
safety check.
</objective>

<execution_context>
@/Users/jeffreywest/Code/Python/kalshi-python-sdk/.planning/phases/01-cli-v1-conviction-cockpit/PATTERNS.md
@/Users/jeffreywest/.gstack/projects/kalshi-python-sdk/jeffreywest-main-eng-review-test-plan-20260424-192732.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/phases/01-cli-v1-conviction-cockpit/plans/01-02-lifecycle-app-skeleton/PLAN.md
@CLAUDE.md

# Existing demo integration patterns
@tests/integration/conftest.py
@tests/integration/test_websocket.py

# What we're testing
@kalshi/cli/app.py
@kalshi/cli/lifecycle.py
@kalshi/cli/state.py

<integration_constraints>
1. **Demo URL safety check is mandatory.** `_assert_demo_url` from
   `tests/integration/conftest.py:86-99` MUST run before any test mounts the cockpit.
   If pointed at production by accident, hard-fail.

2. **Skip cleanly without creds.** `_credentials_available()` from
   `tests/integration/conftest.py:82-99` — every test should `pytest.skip` if KALSHI_KEY_ID
   is not set.

3. **Retry transient failures.** Demo network is flaky; use
   `@retry_transient(max_retries=2, delay=1.0)` from existing helpers (likely
   `tests/integration/helpers.py` — verify exact import path).

4. **Tests run in CI only on a separate job.** The CI job that runs `tests/cli/integration/`
   needs demo creds in env. Local devs without creds skip cleanly.

5. **Hard limit on test duration.** Each E2E test should complete in ≤ 30 seconds. The
   reconnect test will be the longest (force disconnect, wait for reconnect, wait for REST
   refresh) — budget 25s.

6. **Live-mode test runs read-only against production.** v1 has no order placement, so
   `--live` only changes URL. The live-mode test asserts: app mounts against
   api.elections.kalshi.com and the header renders. We do NOT keep the connection open
   long enough to consume any meaningful production data — connect, assert, exit.
</integration_constraints>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: integration conftest.py + cockpit_pilot fixture</name>
  <files>
    tests/cli/integration/__init__.py,
    tests/cli/integration/conftest.py
  </files>
  <behavior>
    `tests/cli/integration/conftest.py` provides:
      - Reuse `async_client` from `tests/integration/conftest.py` via fixture discovery
        (pytest discovers parent conftest.py automatically — confirm by adding a sanity
        test that requests the fixture and gets a real AsyncKalshiClient).
      - Reuse `demo_market_ticker` (or whatever fixture provides a known-active demo
        ticker; if not present, define one — pick a market that's reliably active on
        demo, e.g. an open `KXNFL-...` or `KXLATEST-...` ticker; document the choice
        and fallback strategy in the SUMMARY).
      - New fixture `cockpit_pilot(async_client, demo_market_ticker, request)` — async
        context-manager fixture that:
          1. Constructs `CockpitApp(client=async_client, ticker=demo_market_ticker, fair=Decimal("0.5"))`.
          2. Yields a `Pilot` from `App.run_test()`.
          3. On exit: app.exit() awaited, client.close() awaited, no zombie tasks.
        Pattern: pytest-asyncio's `@pytest_asyncio.fixture` + `async with app.run_test()`.
      - Demo URL safety assertion runs in fixture setup — hard-fail before any test mounts
        if pointed at production.
      - Skip-without-creds applied at module level via `pytestmark = pytest.mark.skipif(...)`.
  </behavior>
  <action>
    1. Read `tests/integration/conftest.py` end-to-end — internalize the credentials gate,
       the demo URL safety check, the async_client fixture lifecycle.

    2. Create `tests/cli/integration/__init__.py` (empty).

    3. Create `tests/cli/integration/conftest.py`:

       ```python
       from __future__ import annotations
       import os
       from collections.abc import AsyncIterator
       from decimal import Decimal

       import pytest
       import pytest_asyncio
       from textual.pilot import Pilot

       from kalshi.async_client import AsyncKalshiClient
       from kalshi.cli.app import CockpitApp


       def _credentials_available() -> bool:
           # Mirror tests/integration/conftest.py:82
           return bool(os.environ.get("KALSHI_KEY_ID"))


       def _assert_demo_url(base_url: str, ws_base_url: str) -> None:
           # Mirror tests/integration/conftest.py:86-99
           if "demo" not in base_url and "demo" not in ws_base_url:
               raise RuntimeError(
                   f"Cockpit integration tests refuse to run against non-demo URLs: "
                   f"base_url={base_url}, ws_base_url={ws_base_url}"
               )


       pytestmark = pytest.mark.skipif(
           not _credentials_available(),
           reason="KALSHI_KEY_ID not set — skipping cockpit integration tests",
       )


       @pytest_asyncio.fixture
       async def cockpit_pilot(
           async_client: AsyncKalshiClient,
           demo_market_ticker: str,
       ) -> AsyncIterator[Pilot]:
           _assert_demo_url(async_client._config.base_url, async_client._config.ws_base_url)
           app = CockpitApp(client=async_client, ticker=demo_market_ticker, fair=Decimal("0.5"))
           async with app.run_test() as pilot:
               yield pilot
           # CockpitApp.run_test() exit handles app.exit; async_client teardown is via
           # the parent fixture.
       ```

       If `demo_market_ticker` doesn't exist as a fixture in `tests/integration/conftest.py`
       (verify by reading), define it here:

       ```python
       @pytest_asyncio.fixture
       async def demo_market_ticker(async_client: AsyncKalshiClient) -> str:
           # Pick the first open market on demo. Could pin a known ticker, but
           # demo markets rotate, so query at runtime.
           markets_resp = await async_client.markets.list(status="open", limit=10)
           if not markets_resp.markets:
               pytest.skip("No open markets on demo — skipping")
           return markets_resp.markets[0].ticker
       ```

    4. Smoke-run the fixture by adding a one-line trivial test in `test_watch.py`
       (Task 2 below) that just requests `cockpit_pilot` — confirm it skips cleanly
       without creds and mounts cleanly with creds.

    5. mypy + ruff clean.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/integration/ --collect-only && uv run mypy tests/cli/integration/ && uv run ruff check tests/cli/integration/</automated>
  </verify>
  <done>
    Fixtures collect without error. Without KALSHI_KEY_ID, all tests in the directory
    skip. With KALSHI_KEY_ID, cockpit_pilot mounts the app against demo and yields a
    Pilot.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: test_watch.py — 4 critical-path E2E tests against demo</name>
  <files>
    tests/cli/integration/test_watch.py
  </files>
  <behavior>
    `class TestCockpitDemo` (with `@pytest.mark.integration` and `@pytest.mark.asyncio`):

    `test_authed_flow_e2e(cockpit_pilot)`:
      - Wait up to 5s for `app.store.connection.state == CockpitConnectionState.CONNECTED`.
      - Wait up to 10s for `app.store.orderbook.book` to be populated (best-effort:
        demo markets vary in liquidity; if book stays None for >10s, skip with a
        diagnostic).
      - Assert `app.store.market.market is not None` (REST snapshot completed).
      - Assert HeaderWidget rendered output contains the ticker.
      - Assert at least 1 tape line accumulated (orderbook_delta OR trade event).

    `test_lifecycle_reconnect_with_rest_refresh(async_client, demo_market_ticker)`:
      - Mount the cockpit (skip the cockpit_pilot fixture so we have full control over
        the lifecycle).
      - Wait for CONNECTED + first REST snapshot.
      - Capture `app.store.market.last_update_ts` and `app.store.balance.last_update_ts`.
      - Force a disconnect: call `app.lifecycle._ws._connection._websocket.close()` (or
        equivalent — verify the actual private path; possibly cleaner: invoke the SDK's
        own `connection.disconnect()` or trigger a `ConnectionClosed` exception).

        ALTERNATIVE if the SDK doesn't expose a clean disconnect-trigger: register a
        custom on_state_change side-effect that artificially calls
        `_handle_state_change(CONNECTED, RECONNECTING)` followed by
        `_handle_state_change(RECONNECTING, STREAMING)` directly on the lifecycle
        instance. This bypasses real network jitter and proves only the application-
        side behavior, which is the actual thing under test.

      - Wait up to 15s for `app.store.connection.state` to transition through
        RECONNECTING → CONNECTED.
      - Assert `app.store.market.last_update_ts > captured_market_ts` (REST refresh
        fired).
      - Assert `app.store.balance.last_update_ts > captured_balance_ts`.
      - Assert at least one tape line includes `[disconnect]` or `[resync]`.
      - Exit cleanly.

    `test_sequence_gap_resync(cockpit_pilot)`:
      - This is the hardest test to write — sequence gaps happen organically during
        load, not on demand. Two strategies:
          (a) Use `tests/ws/test_sequence.py` patterns to inject a forced gap into the
              SDK's sequence tracker by wrapping the WS at a lower level. Hard to do
              without modifying the SDK.
          (b) Run the cockpit for 60s on a busy demo market and assert NOTHING crashes;
              tape may or may not show `[resync]` depending on luck.
        PREFER (a) if a clean injection point exists; otherwise document (b) as a
        smoke-only test and downgrade the assertion to "tape contains [resync] OR test
        ran 60s without crash". The eng-review test plan calls for a forced-gap test —
        check the SDK's existing test infrastructure for an injection point.
      - Whichever path: assert tape gets a `[resync]` marker (path a) or no crash
        (path b).

    `test_live_mode_safety(monkeypatch, demo_market_ticker)`:
      - This test is the trickiest. It requires `--live` env vars, which are normally
        unavailable in CI (live trading on the prod API requires real funds).
      - Skip the test entirely unless an explicit `KALSHI_LIVE_TEST_OPT_IN=true` env
        var is set. (CI default: skip. Local dev with live creds: opt-in.)
      - When opted in: construct an AsyncKalshiClient with `demo=False`, assert
        `_assert_demo_url` is NOT called (or is bypassed for this one test), mount the
        cockpit briefly, assert app.store.connection reaches CONNECTED against
        api.elections.kalshi.com, then exit.
      - The test exists primarily as a smoke check — full live-mode coverage would be
        a launch-criteria item, not a ship-criteria one.

    Use the `@retry_transient(max_retries=2, delay=1.0)` decorator from existing
    integration helpers — verify the import path (`tests/integration/helpers.py`) and
    apply per test class or per test.
  </behavior>
  <action>
    1. RED: write the test class with all 4 tests. Mark each with
       `@pytest.mark.integration` and `@pytest.mark.asyncio`. Use
       `@retry_transient(max_retries=2, delay=1.0)` per existing pattern.

       For `test_lifecycle_reconnect_with_rest_refresh`: the cleanest fake-disconnect
       path is to directly invoke the lifecycle's `_handle_state_change` callback with
       a synthesized state transition. This tests OUR application code without
       depending on real network jitter. Document this as the chosen approach in the
       SUMMARY.

    2. Verify the actual import paths for `retry_transient` and any other helpers from
       `tests/integration/helpers.py`. If the helper doesn't exist with that name, find
       the equivalent or add a minimal one inline.

    3. Run integration tests on a workstation with KALSHI_KEY_ID set:
       ```bash
       export KALSHI_DEMO=true
       export KALSHI_KEY_ID=<demo-key>
       export KALSHI_PRIVATE_KEY_PATH=<path>
       uv run pytest tests/cli/integration/ -m integration -v --tb=short
       ```
       All 4 tests should pass within 60s wall-clock total.

    4. Re-run with `KALSHI_KEY_ID` unset → all tests skip cleanly.

    5. mypy + ruff clean.
  </action>
  <verify>
    <automated>uv run pytest tests/cli/integration/ -m integration -v --tb=short && uv run mypy tests/cli/integration/test_watch.py && uv run ruff check tests/cli/integration/test_watch.py</automated>
  </verify>
  <done>
    All 4 critical-path E2E tests pass against demo with creds set. Skip cleanly without
    creds. mypy + ruff clean. Total wall-clock ≤ 60s for the suite.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Test fixture → demo API | Real network; demo URL safety enforced; KALSHI_LIVE_TEST_OPT_IN gates the only test that touches production |

## STRIDE

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-05-01 | E (elevation) | accidental run against prod | mitigate | _assert_demo_url hard-fails; live-mode test skipped without explicit KALSHI_LIVE_TEST_OPT_IN |
| T-05-02 | T (tampering) | private-attribute access (_handle_state_change, _config, _ws) | accept | matches the SDK's own integration-test access patterns; if private surface changes, plan 01's drift test catches it |
</threat_model>

<verification>
```bash
# With creds set
export KALSHI_DEMO=true
export KALSHI_KEY_ID=<demo-key>
export KALSHI_PRIVATE_KEY_PATH=<path>
uv run pytest tests/cli/integration/ -m integration -v --tb=short

# Without creds — all skip
unset KALSHI_KEY_ID
uv run pytest tests/cli/integration/ -m integration -v
# Expected: all 4 tests in TestCockpitDemo report SKIPPED.

# Live-mode opt-in (only run on a workstation with real prod creds + a willingness)
export KALSHI_LIVE_TEST_OPT_IN=true
uv run pytest tests/cli/integration/test_watch.py::TestCockpitDemo::test_live_mode_safety -v
```

Manual cross-check: run `uv run kalshi watch <demo-ticker>` for 60s on a busy market;
toggle wifi off-and-on once mid-session; verify visually:
1. Header conn-state indicator goes ◐ (yellow) → ● (green).
2. Tape shows `[disconnect]` followed by `[resync]`.
3. Position/balance/orders panels values match a fresh manual REST query (no drift).
</verification>

<success_criteria>
- 4 critical-path E2E tests pass against demo with creds set.
- All tests skip cleanly without creds (CI default behavior).
- Live-mode test gated behind explicit KALSHI_LIVE_TEST_OPT_IN env var.
- Wall-clock ≤ 60s for the suite.
- Demo URL safety enforced — production accidentally pointed = hard-fail.
- mypy strict + ruff clean.
- Ship-criteria CLI-Q04 satisfied.
</success_criteria>

<output>
After completion, create `.planning/phases/01-cli-v1-conviction-cockpit/plans/01-05-integration-demo-e2e/01-05-SUMMARY.md`
documenting: chosen reconnect injection mechanism (real network drop vs synthesized
callback), demo ticker selected for tests (and rotation strategy), wall-clock
measurements per test, and any open issues for plan 06's launch criteria (e.g. flaky
tests that need quarantine).
</output>
