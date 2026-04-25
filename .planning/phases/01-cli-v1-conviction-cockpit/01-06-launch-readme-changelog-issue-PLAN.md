---
phase: 01-cli-v1-conviction-cockpit
plan: 06
type: execute
wave: 6
depends_on: [01, 02, 03, 04, 05]
files_modified:
  - README.md
  - CHANGELOG.md
  - docs/cockpit-screenshot.png
  - docs/cockpit-demo.gif
autonomous: false  # checkpoint: human captures screenshot/GIF; closes issue #11
requirements: [CLI-L01, CLI-L02, CLI-L03]
must_haves:
  truths:
    - "README includes a screenshot AND a GIF showing `kalshi watch` against a real demo market with --fair coloring visible"
    - "CHANGELOG.md has a v0.16.0 entry describing the cockpit and the [cli] extras install"
    - "GitHub Issue #11 is closed with a link to the release notes"
  artifacts:
    - path: "README.md"
      provides: "screenshot embed + install instructions for [cli] extras + quick-start snippet"
    - path: "CHANGELOG.md"
      provides: "v0.16.0 entry"
    - path: "docs/cockpit-screenshot.png"
      provides: "a single high-quality screenshot of the cockpit on a real demo market"
    - path: "docs/cockpit-demo.gif"
      provides: "a 5-15 second loop of the cockpit running on a real demo market — orderbook updating, tape streaming, edge coloring visible"
  key_links:
    - from: "README.md"
      to: "docs/cockpit-screenshot.png + docs/cockpit-demo.gif"
      via: "markdown embed"
      pattern: "!\\[.*\\]\\(docs/cockpit"
    - from: "CHANGELOG.md"
      to: "GitHub Issue #11"
      via: "release notes link in issue close comment"
      pattern: "#11"
---

<objective>
Close out the launch criteria for Phase 1: capture the screenshot + GIF that ARE the
marketing artifact, write the CHANGELOG entry, and close GitHub Issue #11 with a link
to the release notes.

Purpose: Plans 01–05 ship the code. This plan ships the *visibility*. Without
README screenshot + GIF, the cockpit's core value proposition (visual proof of the
SDK's WebSocket quality) is invisible to anyone who hasn't already cloned the repo.
The CHANGELOG entry + closed issue tie the work to a release boundary.

This plan is NOT autonomous — capturing a quality screenshot/GIF requires human
judgment about which demo market is liveliest, which `--fair` value produces the most
visually striking edge coloring, and what 5-15 second slice of the live tape best
showcases the protocol-quality story. Claude can prep the README + CHANGELOG and run
the gh CLI to close the issue, but the user has to capture the artifacts.

Output: README updated with embeds + install + quick-start; CHANGELOG.md v0.16.0
entry; docs/cockpit-screenshot.png + docs/cockpit-demo.gif on disk; Issue #11 closed
on GitHub.
</objective>

<execution_context>
@/Users/jeffreywest/Code/Python/kalshi-python-sdk/.planning/phases/01-cli-v1-conviction-cockpit/PATTERNS.md
@/Users/jeffreywest/.gstack/projects/kalshi-python-sdk/jeffreywest-main-design-20260424-190736.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@README.md
@CHANGELOG.md
@CLAUDE.md
@pyproject.toml

<launch_context>
This is the only checkpoint plan in the phase. It's intentionally minimal:
- 1 auto task (README/CHANGELOG copy edits — Claude does this)
- 1 checkpoint task (human captures screenshot + GIF)
- 1 auto task (close GitHub issue via `gh` CLI — Claude does this AFTER human approves the screenshot)

The checkpoint exists because:
1. Selecting a "good" demo market for the screenshot (lively orderbook, rule that's not
   trivial, close-time that gives a meaningful countdown) requires human judgment.
2. GIF capture requires terminal-recording tooling (asciinema → agg, or Charm's vhs)
   that may need user-side install/setup the user prefers to control.
3. The screenshot/GIF ARE the marketing artifact — the user is the photographer here,
   not Claude.
</launch_context>

<screenshot_recipe>
Suggested capture flow (human runs):

1. Open a clean wide terminal (≥ 140 columns × 40 rows).
2. Set up env: `export KALSHI_DEMO=true KALSHI_KEY_ID=... KALSHI_PRIVATE_KEY_PATH=...`.
3. Pick a lively demo market — check `kalshi-python` examples or `tests/integration/`
   for a known-active demo ticker. Look for: open status, both YES and NO bids
   present, recent trade activity (use `client.trades.list` to spot-check).
4. Pick a `--fair` value that creates visual contrast on THAT market's current book —
   if mid is at 0.45, try `--fair 0.55` so several YES bids are positive-edge (green)
   and several are negative-edge (red).
5. Launch: `uv run kalshi watch <ticker> --fair <prob>`.
6. Wait until ladder, tape, header, rule, positions, orders all populate.
7. **Screenshot:** capture as PNG via OS native (Cmd+Shift+4 on macOS) → save as
   `docs/cockpit-screenshot.png`. Crop to remove desktop chrome.
8. **GIF:**
   - Tooling option A: `vhs` (charm.sh/vhs) — record a 10-15s loop showing tape
     streaming + ladder updates + countdown ticking.
   - Tooling option B: `asciinema rec demo.cast` then `agg demo.cast docs/cockpit-demo.gif`.
   - Tooling option C: macOS native screen recording → ffmpeg conversion.
   - Target: ≤ 5MB GIF (respects GitHub's repo size sensitivity); 15fps acceptable.
9. Visually inspect: the GIF should show at least one orderbook update AND one tape
   line being added. Edge coloring should be clearly visible.
</screenshot_recipe>

<readme_target>
README diff target (illustrative — adjust to match repo style):

```markdown
## CLI: Conviction Cockpit (new in v0.16.0)

`kalshi-sdk[cli]` ships a Textual TUI that opens a single full-screen cockpit on any
Kalshi market — live YES/NO ladder, raw delta tape, settlement rule, close countdown,
and account state. With `--fair PROB`, every level is colored by edge vs. your thesis.

![Cockpit screenshot](docs/cockpit-screenshot.png)

![Cockpit demo](docs/cockpit-demo.gif)

### Install

```bash
pip install "kalshi-sdk[cli]"
```

### Quick start

```bash
export KALSHI_KEY_ID=<your-demo-key-id>
export KALSHI_PRIVATE_KEY_PATH=<path-to-pem>
kalshi watch KXNFL-25NOV-RAVENS-T --fair 0.55
```

`--live` switches to the production API. Read-only in v1; order entry coming in v2.
```
</readme_target>

</context>

<tasks>

<task type="auto">
  <name>Task 1: README + CHANGELOG copy edits (no artifacts yet)</name>
  <files>
    README.md,
    CHANGELOG.md
  </files>
  <action>
    1. Read current README.md. Find the right insertion point — likely after the
       existing install/quick-start section, before any "API reference" or "Examples"
       section. Don't replace existing content; ADD a new "## CLI: Conviction Cockpit"
       section per the <readme_target> diff above.

       Use placeholder image paths `docs/cockpit-screenshot.png` and
       `docs/cockpit-demo.gif` — Task 2 fills the actual files.

       Quick-start example: pick a CURRENT demo ticker by looking at
       `tests/integration/test_websocket.py` or similar for a recently-used demo
       market. If none is documented, use a generic `<ticker>` placeholder.

    2. Read current CHANGELOG.md. Add a new section at the top (newest first):

       ```markdown
       ## [0.16.0] — 2026-MM-DD

       ### Added
       - **CLI Conviction Cockpit** — `pip install kalshi-sdk[cli]` ships a Textual
         TUI for live read-only market viewing: `kalshi watch TICKER --fair PROB`
         opens a single full-screen cockpit with edge-colored YES/NO ladder, raw
         WebSocket delta tape, pinned settlement rule, close countdown, and account
         state (positions / balance / resting orders) seeded via REST and updated via
         WS. Survives mid-session disconnects via SDK reconnect + REST snapshot
         refresh. Marketing artifact for the SDK's WebSocket quality (see Issue #11).
       - `[project.scripts] kalshi` entry point (`kalshi.cli.main:app`).
       - `[project.optional-dependencies] cli` group: typer, textual, rich.

       ### Notes
       - v1 is read-only by design (per Codex eng-review). Order entry deferred to
         v2 backlog.
       - Auth required (no anon mode) — Kalshi WebSocket protocol requires auth.
       - `--live` flag switches base URL from demo to production; behavior identical.
       ```

       Don't bump `version` in pyproject.toml here — that's a separate ship step
       handled at release time. Just record the user-facing change.

    3. Verify README + CHANGELOG render cleanly:
       ```bash
       # Preview locally if a markdown previewer is handy; otherwise just visual
       # inspect via cat or an editor.
       ```

    4. Commit (will need user approval before pushing):
       `docs(cli-v1): README + CHANGELOG entry for cockpit launch`
  </action>
  <verify>
    <automated>grep -q "Conviction Cockpit" README.md && grep -q "0.16.0" CHANGELOG.md && grep -q "docs/cockpit-screenshot.png" README.md && grep -q "docs/cockpit-demo.gif" README.md</automated>
  </verify>
  <done>
    README has the new CLI section with quick-start. CHANGELOG has v0.16.0 entry.
    Image references in place even though files don't exist yet (filled by Task 2).
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    Code is feature-complete. README + CHANGELOG mention the cockpit but the screenshot
    + GIF files don't exist yet. This checkpoint is for the user to capture them.
  </what-built>
  <how-to-verify>
    1. Pick a lively demo market. Suggested workflow:
       ```bash
       export KALSHI_DEMO=true
       export KALSHI_KEY_ID=<demo-key>
       export KALSHI_PRIVATE_KEY_PATH=<path>

       # Spot-check a few markets first
       uv run python -c "
       import asyncio, os
       from kalshi.async_client import AsyncKalshiClient
       async def main():
           c = AsyncKalshiClient.from_env()
           resp = await c.markets.list(status='open', limit=5)
           for m in resp.markets:
               print(m.ticker, m.title)
           await c.close()
       asyncio.run(main())
       "
       ```
    2. Pick the most active one. Launch:
       ```bash
       uv run kalshi watch <ticker> --fair <prob>
       ```
       Wait 30s for everything to populate (header, ladder, rule, tape, positions, orders).

    3. **Screenshot capture:** OS-native screenshot (Cmd+Shift+4 on macOS, etc.). Save
       to `docs/cockpit-screenshot.png`. Crop tightly to the cockpit, no terminal chrome.

    4. **GIF capture:** Use `vhs`, `asciinema + agg`, or any preferred tool. Target
       10-15 seconds, ≤ 5MB. Save to `docs/cockpit-demo.gif`.

    5. Verify both files exist:
       ```bash
       ls -lh docs/cockpit-screenshot.png docs/cockpit-demo.gif
       ```
       Reasonable sizes: PNG 200KB-2MB; GIF 1-5MB.

    6. Open README.md preview locally (VS Code preview, GitHub web, etc.) and confirm
       both images render correctly.

    7. Quality bar: would this image+GIF make a Python developer browsing GitHub
       *want* to `pip install kalshi-sdk[cli]`? If not, recapture.

    Type "approved — screenshot and GIF look good" to proceed to Task 3 (close issue).
    Or describe what's wrong (e.g. "GIF is too long, recapturing") and recapture.
  </how-to-verify>
  <resume-signal>Type "approved" or describe issues</resume-signal>
</task>

<task type="auto">
  <name>Task 3: Close GitHub Issue #11</name>
  <files>
    (no file changes — this is a `gh` CLI action)
  </files>
  <action>
    1. Verify the issue still exists and is open:
       ```bash
       gh issue view 11 --repo TexasCoding/kalshi-python-sdk
       ```

    2. Compose the close comment. Reference:
       - The released version (v0.16.0).
       - The README section + screenshot + GIF.
       - The reframe (original "generic CLI" → "conviction cockpit").
       - That order entry is deferred to v2 (link to BACKLOG.md or future tracking
         issue if one exists).

       Comment text:
       ```
       Closing this with v0.16.0 — shipped as `pip install kalshi-sdk[cli]` with the
       `kalshi watch TICKER --fair PROB` cockpit (Textual TUI). See README:
       https://github.com/TexasCoding/kalshi-python-sdk#cli-conviction-cockpit-new-in-v0160

       The original ask ("generic CLI: markets list / orders create / portfolio
       balance") was reframed via /office-hours into the conviction cockpit — a
       read-only single-screen TUI optimized as a marketing artifact for the SDK's
       WebSocket quality. Order entry (`b`/`s` ticket modal, etc.) is deferred to v2
       backlog (BACKLOG.md → "CLI v2"). Promote when v1 stabilizes.

       Design doc, eng-review, test plan, and v1 SUMMARYs all in the repo's .planning/
       directory.
       ```

    3. Close the issue:
       ```bash
       gh issue close 11 --repo TexasCoding/kalshi-python-sdk --comment "<above text>"
       ```

       Use a HEREDOC for the comment to preserve formatting:
       ```bash
       gh issue close 11 --repo TexasCoding/kalshi-python-sdk --comment "$(cat <<'EOF'
       Closing this with v0.16.0 — ...
       EOF
       )"
       ```

    4. Verify closed:
       ```bash
       gh issue view 11 --repo TexasCoding/kalshi-python-sdk --json state | jq .state
       # → "CLOSED"
       ```

    5. Final phase commit (do NOT push without explicit user OK):
       `chore(cli-v1): close issue #11; ship v0.16.0 cockpit`

       Note: this commit message claims a release. If the actual semver bump + tag
       happens in a separate ship plan (or via gsd-ship), defer the commit message
       wording to "docs(cli-v1): record cockpit launch in CHANGELOG; close #11".
  </action>
  <verify>
    <automated>gh issue view 11 --repo TexasCoding/kalshi-python-sdk --json state -q .state | grep -q CLOSED</automated>
  </verify>
  <done>
    Issue #11 closed on GitHub with the comment linking to release notes. Phase 1
    launch criteria CLI-L01, CLI-L02, CLI-L03 all satisfied.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| local repo → GitHub via `gh` | gh CLI uses the user's auth; no new credentials introduced |
| screenshot/GIF → repo binary | binaries committed; gif file size capped at ≤5MB to respect repo health |

## STRIDE

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-06-01 | I (info disclosure) | screenshot may capture PII (account balance, positions) | mitigate | use a demo account with no sensitive data; review screenshot before commit; balance footer can be redacted post-capture if needed |
| T-06-02 | T (tampering) | GIF tooling (vhs, agg, ffmpeg) | accept | standard open-source tools; user picks toolchain |
</threat_model>

<verification>
After all 3 tasks:
- `docs/cockpit-screenshot.png` and `docs/cockpit-demo.gif` exist with reasonable sizes.
- README.md preview shows both images embed correctly.
- CHANGELOG.md has v0.16.0 entry.
- `gh issue view 11` shows state=CLOSED with the close comment present.

Final phase verification:
```bash
uv run pytest tests/cli/ -v
uv run pytest tests/cli/integration/ -m integration -v   # with creds set
uv run mypy kalshi/cli/ tests/cli/
uv run ruff check kalshi/cli/ tests/cli/
uv run pytest tests/cli/ --cov=kalshi.cli --cov-report=term-missing
```
All green; coverage ≥80% on `kalshi/cli/`.
</verification>

<success_criteria>
- Screenshot + GIF embedded in README, render correctly.
- CHANGELOG v0.16.0 entry written.
- GitHub Issue #11 closed with a meaningful close comment.
- Launch criteria CLI-L01, CLI-L02, CLI-L03 all checked off in REQUIREMENTS.md.
- Phase 1 ship criteria + launch criteria both fully satisfied.
</success_criteria>

<output>
After completion, create `.planning/phases/01-cli-v1-conviction-cockpit/plans/01-06-launch-readme-changelog-issue/01-06-SUMMARY.md`
documenting: which demo market was used for the screenshot, GIF tooling chosen, GIF
duration + size, the close-comment text on Issue #11, and any open follow-ups for the
release process (e.g. version bump in pyproject.toml, git tag, PyPI publish — these
are typically separate from the launch-criteria plan).

Then update `.planning/STATE.md` to mark Phase 1 complete and write a brief Phase 1
retrospective in `.planning/RETROSPECTIVE.md` (or wherever the project tracks phase
retrospectives).
</output>
