---
name: llm-review
description: "Use when the user wants a multi-LLM / multi-model code review — fan a change (diff, files, or a question) out to several frontier model CLIs (codex, gemini, grok) in parallel and synthesize one consolidated, severity-sorted report. Examples: \"get a multi-LLM review of this diff\", \"have codex/gemini/grok review these changes\", \"second opinion on this PR from other models\", \"run llm_review on the perps changes\"."
---

# Multi-LLM code review

`scripts/llm_review.py` fans a single shared review prompt out to several
installed frontier-model CLIs in parallel, captures each verdict, and (by default)
has one model synthesize a consolidated, de-duplicated report sorted by severity.
It is dev-only tooling and is **not** shipped in the wheel.

Use it for a deeper, independent second opinion on a substantive change — beyond
the Claude-native review — e.g. before opening/merging a PR, on the money/auth/spec
paths, or when the user explicitly asks for codex/gemini/grok input.

## Prerequisites

Three CLIs must be installed and logged in (paid subscriptions, no API keys):
`codex` (OpenAI Codex), `gemini` (Google Gemini), `grok` (xAI Grok). Any missing
CLI is skipped with a warning. **Running real reviewers costs money** — prefer
`--dry-run` to preview the exact prompt + argv for free, and only run the full
fan-out when the user wants it.

## How it works (why it's safe + deterministic)

Each reviewer gets the **full context injected into the prompt** (the git diff, the
files, or the question) and runs from a throwaway **temp working dir** with tools /
MCP / memory / web-search stripped and the sandbox forced read-only. So every model
sees byte-for-byte the same context, and a reviewer physically cannot edit the repo,
run tests, or hit the Kalshi API. The rubric is `scripts/llm_review_rubric.md`
(SDK-specific: money-serialization, spec/contract drift, retry/idempotency,
sync/async parity, auth/secret safety, WebSocket correctness, types, tests).

## Usage

```bash
# Review uncommitted changes (git diff HEAD):
uv run python scripts/llm_review.py diff

# Staged only / a branch / a commit range / a path (args pass through to `git diff`):
uv run python scripts/llm_review.py diff --staged
uv run python scripts/llm_review.py diff main...HEAD
uv run python scripts/llm_review.py diff HEAD~3 -- kalshi/resources/orders.py

# Review whole files (best for new/untracked files — git diff won't show those):
uv run python scripts/llm_review.py files kalshi/perps/resources/orders.py kalshi/perps/models/orders.py

# Free-form question, optionally with file context:
uv run python scripts/llm_review.py ask "Are POST order requests safe to retry?" kalshi/_base_client.py
```

Useful options (place **after** the verb; for `diff`, put options before the
git passthrough args, e.g. `diff --dry-run -- kalshi/...`):

| Option | Effect |
|---|---|
| `--dry-run` | Build + print the prompt and the exact per-model argv, then exit. Calls no model (free). **Start here.** |
| `--models codex,gemini,grok` | Which reviewers to run (default: all installed). |
| `--synth gemini\|codex\|grok` | Model that writes the consolidated report (default: `gemini`). `--no-synth` concatenates instead. |
| `--focus "TEXT"` | Extra focus appended to the rubric for this run. |
| `--timeout SECONDS` | Per-model wall-clock timeout (default 600). |
| `--rubric PATH` / `--out DIR` | Override the rubric file / output directory. |
| `--json` | Also print a machine-readable run summary to stdout. |

## Output

Writes to `reviews/<timestamp>-<verb>/` (gitignored), with `reviews/latest`
symlinked to the newest run:

- `prompt.md` — the exact prompt sent to every reviewer
- `codex.md` / `gemini.md` / `grok.md` — each raw review (+ `<model>.stderr.log`)
- `SUMMARY.md` — the consolidated report (synthesis, or concatenation if synthesis
  is skipped / there is only one reviewer)
- `manifest.json` — run metadata (durations, exit status, verdicts)

Exit code is 0 if at least one reviewer produced output, non-zero otherwise. After
a run, read `reviews/latest/SUMMARY.md` and relay the consolidated findings +
verdict to the user.

## Notes

- Pure helpers + context builders are unit-tested in `tests/test_llm_review.py`
  (no model is called); the fan-out itself is verified by a live run.
- This is complementary to `/code-review` (Claude-native) — use this when the user
  wants *other* models' independent perspectives folded into one report.
