#!/usr/bin/env python3
"""scripts/llm_review.py — multi-LLM code review for the Kalshi Python SDK (dev only).

WHY THIS EXISTS
---------------
We want a clean, reproducible way to get *several* frontier models to review a
change to this SDK — whose request-construction correctness affects real-money
orders on the Kalshi exchange — and then compile their findings into one report,
without depending on any editor plugin or hosted service. Three CLIs are already
installed and logged in on this machine (paid subscriptions, no API keys needed):

    codex   (OpenAI Codex CLI)   -> `codex exec`
    gemini  (Google Gemini CLI)  -> `gemini -p`
    grok    (xAI Grok Build CLI) -> `grok --prompt-file`

This script fans a single, shared review prompt out to all three in parallel,
captures each verdict, and (optionally) has one model synthesize a consolidated,
de-duplicated report sorted by severity.

DESIGN — why injected context + isolated temp dirs
--------------------------------------------------
Each reviewer is run with the **full review context injected into the prompt**
(the git diff, or the files, or your question) and executed from a throwaway
**temp working directory**, with tools / MCP / memory / web-search stripped and
the sandbox forced read-only. That buys four things that matter for an SDK:

  * Determinism & parity — every model sees byte-for-byte the same context, not
    whatever each CLI happens to autoload from the repo (grok, run inside the
    repo, otherwise pulls in CLAUDE.md + the project skills + MCP servers).
  * Safety — a reviewer physically cannot edit the repo, run the test suite, or
    hit the Kalshi demo/live API. The temp cwd has nothing in it; read-only is
    belt & suspenders.
  * Speed — no MCP servers to spawn, no skill catalog to load.
  * Reproducibility — the exact prompt sent is saved to the run directory.

This is deliberately NOT an agentic "let each model explore the repo" tool. For a
deep dive, pass the relevant files explicitly (`files ...`) or ask a focused
question with context (`ask "..." path ...`). Determinism and safety win here.

USAGE
-----
    scripts/llm_review.py <verb> [OPTIONS] [args]

    # Review uncommitted changes (git diff HEAD):
    scripts/llm_review.py diff
    # Review staged only / a branch / a commit range / a path (args go to `git diff`):
    scripts/llm_review.py diff --staged
    scripts/llm_review.py diff main...HEAD
    scripts/llm_review.py diff HEAD~3 -- kalshi/resources/orders.py
    # Review whole files:
    scripts/llm_review.py files kalshi/perps/resources/orders.py kalshi/perps/models/orders.py
    # Free-form question, optionally with file context:
    scripts/llm_review.py ask "Are POST order requests safe to retry?" kalshi/_base_client.py

OPTIONS (placed AFTER the verb; for `diff`, before the git args so they aren't
swallowed by the `git diff` passthrough — e.g. `diff --dry-run -- src/...`)
    --models codex,gemini,grok   Reviewers to run (default: all installed).
    --synth  gemini|codex|grok   Model that writes the consolidated report
                                 (default: gemini). Use --no-synth to skip.
    --no-synth                   Skip synthesis; SUMMARY.md just concatenates reviews.
    --timeout SECONDS            Per-model wall-clock timeout (default: 600).
    --focus  "TEXT"              Extra focus appended to the rubric for this run.
    --rubric PATH                Override the rubric file.
    --out    DIR                 Output directory (default: reviews/<ts>-<verb>).
    --dry-run                    Build & print the prompt and the exact per-model
                                 argv, then exit. No model is called (free).
    --json                       Also print a machine-readable run summary to stdout.

OUTPUT
    reviews/<timestamp>-<verb>/
        prompt.md            the exact prompt sent to every reviewer
        codex.md             raw review from each model
        gemini.md
        grok.md
        <model>.stderr.log   captured stderr per model (debug)
        SUMMARY.md           consolidated report (synthesis or concatenation)
        manifest.json        run metadata (durations, exit status, paths)
    reviews/latest -> the newest run directory (symlink)

Exit code is 0 if at least one reviewer produced output, non-zero otherwise.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUBRIC = REPO_ROOT / "scripts" / "llm_review_rubric.md"
REVIEWS_DIR = REPO_ROOT / "reviews"

ALL_MODELS: tuple[str, ...] = ("codex", "gemini", "grok")
DEFAULT_SYNTH = "gemini"
DEFAULT_TIMEOUT = 600

# Map a file suffix to a Markdown fence language, for nicer rendering of `files`
# context. Anything unknown falls back to no language tag.
_LANG_BY_SUFFIX = {
    ".py": "python",
    ".pyi": "python",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".sh": "bash",
    ".sql": "sql",
    ".txt": "",
    ".cfg": "ini",
    ".ini": "ini",
}


# --------------------------------------------------------------------------- #
# Pure helpers (no subprocess / no LLM) — these are what the unit tests cover. #
# --------------------------------------------------------------------------- #


def slugify(text: str, max_len: int = 40) -> str:
    """Reduce arbitrary text to a filesystem-safe slug for the run directory."""
    out: list[str] = []
    for ch in text.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_/.":
            out.append("-")
        # everything else is dropped
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return (slug[:max_len].strip("-")) or "review"


def guess_lang(path: str) -> str:
    """Best-effort Markdown fence language for a path."""
    return _LANG_BY_SUFFIX.get(Path(path).suffix.lower(), "")


def number_lines(text: str) -> str:
    """Prefix each line with a 1-indexed, right-aligned line number.

    Line numbers let reviewers cite an accurate ``file:line`` in findings, which
    is the difference between an actionable report and a vague one.
    """
    lines = text.splitlines()
    width = max(4, len(str(len(lines))))
    return "\n".join(f"{i:>{width}}  {line}" for i, line in enumerate(lines, 1))


def format_file_block(path: str, content: str) -> str:
    """Render one file as a numbered, fenced Markdown block."""
    lang = guess_lang(path)
    fence = f"```{lang}" if lang else "```"
    return f"### File: {path}\n{fence}\n{number_lines(content)}\n```"


def build_prompt(
    rubric: str, focus: str | None, target_desc: str, context: str
) -> str:
    """Assemble the full reviewer prompt from its parts.

    Order matters: rubric (role + what to hunt + required format) first, then any
    per-run focus, then a one-line description of the target, then the context.
    """
    sections = [rubric.strip()]
    if focus:
        sections.append(f"## Additional focus for THIS review\n{focus.strip()}")
    sections.append(f"## Review target\n{target_desc.strip()}")
    sections.append(f"## Context to review\n{context.rstrip()}")
    return "\n\n---\n\n".join(sections) + "\n"


def build_synth_prompt(reviews: dict[str, str], target_desc: str) -> str:
    """Build the consolidation prompt fed to the synthesis model."""
    n = len(reviews)
    head = (
        "You are the lead reviewer consolidating independent code reviews of the "
        "same change to the Kalshi Python SDK (a client library for the Kalshi "
        f"prediction-markets API). Below are {n} review(s) from different AI "
        "reviewers.\n\n"
        "Produce ONE consolidated review:\n"
        "- Merge duplicate findings. When multiple reviewers raise the same issue, "
        "say so — agreement raises confidence.\n"
        "- When reviewers disagree or contradict, note the disagreement and give "
        "your own adjudication.\n"
        "- Discard findings that are wrong or hallucinated (e.g. cite code that "
        "isn't in the context).\n"
        "- Sort findings by severity, CRITICAL first. Keep concrete file:line "
        "locations and concrete fixes.\n"
        "- Use the SAME output format as the inputs (## Summary, ## Findings with "
        "severity-tagged subsections, ## Verdict).\n"
        "- After the Verdict, add a `## Top must-fix` list of at most 3 items "
        "(or `_none_`).\n\n"
        "Do not ask questions or use tools. Output only the consolidated report.\n\n"
        f"## Change under review\n{target_desc.strip()}\n"
    )
    parts = [head]
    for name, text in reviews.items():
        parts.append(f"\n===== Reviewer: {name} =====\n{text.strip()}\n")
    return "".join(parts)


def extract_verdict(review: str) -> str:
    """Pull a one-line verdict out of a review for the console digest."""
    lines = review.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        low = stripped.lower()
        if low.lstrip("#").strip().startswith("verdict"):
            # Verdict may be on the same line after a colon, or the next non-blank.
            # Locate the word case-insensitively, then slice the original-case text.
            idx = low.find("verdict")
            tail = stripped[idx + len("verdict") :].lstrip(" :").strip()
            if tail:
                return tail
            for nxt in lines[i + 1 :]:
                if nxt.strip():
                    return nxt.strip()
            return ""
    # Fallback: first line that names a verdict keyword.
    for line in lines:
        s = line.strip()
        if s and any(k in s.upper() for k in ("BLOCK", "APPROVE")):
            return s
    return ""


def parse_models_arg(value: str) -> list[str]:
    """Parse and validate a comma-separated --models value (order preserved)."""
    requested = [m.strip().lower() for m in value.split(",") if m.strip()]
    unknown = [m for m in requested if m not in ALL_MODELS]
    if unknown:
        raise ValueError(
            f"unknown model(s): {', '.join(unknown)} "
            f"(known: {', '.join(ALL_MODELS)})"
        )
    # De-dup, preserve first-seen order.
    seen: list[str] = []
    for m in requested:
        if m not in seen:
            seen.append(m)
    return seen


def compile_fallback_summary(
    target_desc: str, reviews: dict[str, str], header: str
) -> str:
    """SUMMARY.md when synthesis is skipped or fails: header + each raw review."""
    parts = [header, "\n_Synthesis skipped — raw reviews concatenated below._\n"]
    for name, text in reviews.items():
        parts.append(f"\n## ===== {name} =====\n\n{text.strip()}\n")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Context builders (these shell out to git for `diff`).                        #
# --------------------------------------------------------------------------- #


def build_diff_context(git_args: list[str]) -> tuple[str, str]:
    """Return (description, context) for a `diff` review.

    ``git_args`` is passed straight to ``git diff`` so the full git surface works
    (``--staged``, ``main...HEAD``, ``HEAD~3 -- path``, …). Defaults to ``HEAD``
    (all uncommitted changes to tracked files). A ``--stat`` header is prepended
    so the reviewer sees the shape of the change before the hunks.
    """
    args = git_args or ["HEAD"]
    stat = subprocess.run(
        ["git", "diff", "--stat", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    full = subprocess.run(
        ["git", "diff", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if full.returncode != 0:
        raise SystemExit(
            f"git diff {' '.join(args)} failed:\n{full.stderr.strip()}"
        )
    body = full.stdout
    if not body.strip():
        raise SystemExit(
            f"git diff {' '.join(args)} produced no changes to review.\n"
            "(Untracked new files are not in `git diff` — review them with "
            "`files <path>` instead.)"
        )
    desc = f"`git diff {' '.join(args)}`"
    ctx = (
        f"Diffstat:\n```\n{stat.stdout.strip()}\n```\n\n"
        f"Full diff:\n```diff\n{body.rstrip()}\n```"
    )
    return desc, ctx


def build_files_context(paths: list[str]) -> tuple[str, str]:
    """Return (description, context) for a `files` review."""
    if not paths:
        raise SystemExit("files: at least one path is required")
    blocks: list[str] = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            raise SystemExit(f"files: not a file: {p}")
        blocks.append(format_file_block(p, path.read_text(encoding="utf-8", errors="replace")))
    desc = f"{len(paths)} file(s): " + ", ".join(f"`{p}`" for p in paths)
    return desc, "\n\n".join(blocks)


def build_ask_context(question: str, paths: list[str]) -> tuple[str, str]:
    """Return (description, context) for an `ask` review."""
    if not question.strip():
        raise SystemExit("ask: a question is required")
    parts = [f"## Question\n{question.strip()}"]
    if paths:
        _, files_ctx = build_files_context(paths)
        parts.append(files_ctx)
    desc = f'ask: "{question.strip()[:80]}"'
    return desc, "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Model invocation.                                                           #
# --------------------------------------------------------------------------- #


@dataclasses.dataclass
class Invocation:
    """How to run one model: argv + cwd + how to feed prompt + how to read output."""

    argv: list[str]
    cwd: str
    stdin_text: str | None  # prompt piped to stdin, else None
    output_file: Path | None  # if set, the review text is this file; else stdout


@dataclasses.dataclass
class ModelRun:
    """Result of one model invocation."""

    model: str
    ok: bool
    text: str
    duration: float
    error: str | None
    argv: list[str]
    stderr: str
    returncode: int | None


def _build_codex(prompt: str, tmpdir: str, model: str | None) -> Invocation:
    # `codex exec` reads instructions from stdin when the prompt arg is `-`.
    # `-o` writes ONLY the final agent message to a file, which is the cleanest
    # capture (stdout also carries a session preamble). Read-only sandbox + a
    # temp working root make it physically unable to touch the repo.
    last = Path(tmpdir) / "codex_last.txt"
    opts = ["exec", "-C", tmpdir, "-s", "read-only", "--skip-git-repo-check",
            "--color", "never", "-o", str(last)]
    if model:
        opts += ["-m", model]
    return Invocation(
        argv=["codex", *opts, "-"],
        cwd=tmpdir,
        stdin_text=prompt,
        output_file=last,
    )


def _build_gemini(prompt: str, tmpdir: str, model: str | None) -> Invocation:
    # `--approval-mode plan` is Gemini's read-only mode (no edits/commands).
    # `-o text` forces plain output. Run from the temp dir so no project GEMINI.md
    # context bleeds in. The prompt goes on argv (no shell, so no quoting issues).
    argv = ["gemini", "-p", prompt, "--approval-mode", "plan", "--skip-trust",
            "-o", "text"]
    if model:
        argv += ["-m", model]
    return Invocation(argv=argv, cwd=tmpdir, stdin_text=None, output_file=None)


def _build_grok(prompt: str, tmpdir: str, model: str | None) -> Invocation:
    # `--prompt-file` keeps an arbitrarily large prompt off argv. The flags strip
    # everything that would make grok wander or pull in project context:
    # verbatim prompt, no subagents, no web search, no cross-session memory, no
    # plan mode. Running from the temp dir drops the project's .mcp.json servers.
    pf = Path(tmpdir) / "grok_prompt.txt"
    pf.write_text(prompt, encoding="utf-8")
    argv = ["grok", "--prompt-file", str(pf), "--verbatim", "--no-subagents",
            "--disable-web-search", "--no-memory", "--no-plan",
            "--output-format", "plain"]
    if model:
        argv += ["-m", model]
    return Invocation(argv=argv, cwd=tmpdir, stdin_text=None, output_file=None)


_BUILDERS = {
    "codex": _build_codex,
    "gemini": _build_gemini,
    "grok": _build_grok,
}


def _child_env() -> dict[str, str]:
    """Environment for the child CLIs: inherit (auth lives in ~/.codex etc.),
    but force color off so captured output is clean across any terminal."""
    env = dict(os.environ)
    env["NO_COLOR"] = "1"
    return env


def run_model(
    model: str, prompt: str, timeout: int, model_override: str | None = None
) -> ModelRun:
    """Run one model on ``prompt`` in an isolated temp dir; return its output.

    Never raises for model-side failures: a timeout, a non-zero exit, or empty
    output is captured into the returned ``ModelRun`` so one bad reviewer can't
    sink the batch.
    """
    builder = _BUILDERS[model]
    tmpdir = tempfile.mkdtemp(prefix=f"llmrev-{model}-")
    start = time.monotonic()
    try:
        inv = builder(prompt, tmpdir, model_override)
        try:
            proc = subprocess.run(
                inv.argv,
                cwd=inv.cwd,
                input=inv.stdin_text.encode("utf-8") if inv.stdin_text else None,
                capture_output=True,
                timeout=timeout,
                env=_child_env(),
            )
        except subprocess.TimeoutExpired as exc:
            dur = time.monotonic() - start
            partial = (exc.stdout or b"").decode("utf-8", "replace")
            return ModelRun(model, False, partial, dur,
                            f"timed out after {timeout}s", inv.argv,
                            (exc.stderr or b"").decode("utf-8", "replace"), None)
        except (OSError, ValueError) as exc:
            dur = time.monotonic() - start
            return ModelRun(model, False, "", dur, f"failed to launch: {exc}",
                            inv.argv, "", None)

        dur = time.monotonic() - start
        stdout = proc.stdout.decode("utf-8", "replace")
        stderr = proc.stderr.decode("utf-8", "replace")

        # Prefer the dedicated output file (codex) over stdout.
        if inv.output_file is not None and inv.output_file.exists():
            text = inv.output_file.read_text(encoding="utf-8", errors="replace").strip()
        else:
            text = stdout.strip()

        if not text:
            err = (f"exited {proc.returncode} with empty output"
                   if proc.returncode == 0 else f"exited {proc.returncode}")
            return ModelRun(model, False, "", dur, err, inv.argv, stderr,
                            proc.returncode)
        return ModelRun(model, True, text, dur, None, inv.argv, stderr,
                        proc.returncode)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Orchestration.                                                              #
# --------------------------------------------------------------------------- #


def installed_models(requested: list[str]) -> tuple[list[str], list[str]]:
    """Split requested models into (available, missing) by binary presence."""
    available: list[str] = []
    missing: list[str] = []
    for m in requested:
        (available if shutil.which(m) else missing).append(m)
    return available, missing


def run_reviews_parallel(
    models: list[str], prompt: str, timeout: int
) -> dict[str, ModelRun]:
    """Run all reviewers concurrently (each is its own subprocess; I/O-bound)."""
    results: dict[str, ModelRun] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as pool:
        futs = {pool.submit(run_model, m, prompt, timeout): m for m in models}
        for fut in concurrent.futures.as_completed(futs):
            run = fut.result()
            results[run.model] = run
    # Return in the caller's requested order for stable reports.
    return {m: results[m] for m in models if m in results}


def make_out_dir(verb: str, explicit: str | None) -> Path:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out = Path(explicit) if explicit else REVIEWS_DIR / f"{ts}-{slugify(verb)}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def update_latest_symlink(out_dir: Path) -> None:
    """Point reviews/latest at the newest run (best-effort)."""
    link = REVIEWS_DIR / "latest"
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(out_dir.resolve(), target_is_directory=True)
    except OSError:
        pass  # symlinks are a convenience, not a requirement


def report_header(target_desc: str, models: list[str], synth: str | None) -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        f"# Multi-LLM review\n\n"
        f"- **Target:** {target_desc}\n"
        f"- **Reviewers:** {', '.join(models)}\n"
        f"- **Synthesis:** {synth or 'none'}\n"
        f"- **Generated:** {ts}\n"
    )


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--models", default=",".join(ALL_MODELS),
                        help="comma-separated reviewers (default: all installed)")
    common.add_argument("--synth", default=DEFAULT_SYNTH,
                        help="synthesis model or 'none' (default: %(default)s)")
    common.add_argument("--no-synth", action="store_true", help="skip synthesis")
    common.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="per-model timeout seconds (default: %(default)s)")
    common.add_argument("--focus", default=None, help="extra focus appended to rubric")
    common.add_argument("--rubric", default=str(DEFAULT_RUBRIC), help="rubric file path")
    common.add_argument("--out", default=None, help="output directory")
    common.add_argument("--dry-run", action="store_true",
                        help="print prompt + per-model argv and exit (no model called)")
    common.add_argument("--json", action="store_true", dest="json_out",
                        help="print a machine-readable run summary to stdout")

    p = argparse.ArgumentParser(
        prog="llm_review.py",
        description="Multi-LLM code review for the Kalshi Python SDK (dev only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Add --dry-run to preview the prompt without calling any model.",
    )
    sub = p.add_subparsers(dest="verb", required=True, metavar="{diff,files,ask}")
    pd = sub.add_parser("diff", parents=[common],
                        help="review a git diff (extra args pass to `git diff`)")
    pd.add_argument("git_args", nargs=argparse.REMAINDER,
                    help="args for `git diff` (default: HEAD); put options first")
    pf = sub.add_parser("files", parents=[common], help="review whole files")
    pf.add_argument("paths", nargs="+", help="files to review")
    pa = sub.add_parser("ask", parents=[common],
                        help="free-form question, optionally with file context")
    pa.add_argument("question", help="the review question")
    pa.add_argument("paths", nargs="*", help="optional files for context")
    args = p.parse_args(argv)

    # Resolve the review target into (description, context).
    if args.verb == "diff":
        target_desc, context = build_diff_context(args.git_args)
    elif args.verb == "files":
        target_desc, context = build_files_context(args.paths)
    else:  # ask
        target_desc, context = build_ask_context(args.question, args.paths)

    rubric_path = Path(args.rubric)
    if not rubric_path.is_file():
        raise SystemExit(f"rubric not found: {rubric_path}")
    rubric = rubric_path.read_text(encoding="utf-8")
    prompt = build_prompt(rubric, args.focus, target_desc, context)

    # Resolve reviewers.
    try:
        requested = parse_models_arg(args.models)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    models, missing = installed_models(requested)
    for m in missing:
        print(f"warning: '{m}' not found on PATH — skipping", file=sys.stderr)
    if not models:
        raise SystemExit("no requested reviewer CLIs are installed")

    synth = None if args.no_synth or args.synth.lower() == "none" else args.synth.lower()
    if synth and synth not in ALL_MODELS:
        raise SystemExit(f"unknown synth model: {synth}")
    if synth and not shutil.which(synth):
        print(f"warning: synth model '{synth}' not installed — "
              "falling back to concatenation", file=sys.stderr)
        synth = None

    # --- dry run: show exactly what would be sent, call nothing. ---
    if args.dry_run:
        print(f"# DRY RUN\n\nTarget: {target_desc}\nReviewers: {', '.join(models)}\n"
              f"Synth: {synth or 'none'}\nTimeout: {args.timeout}s\n"
              f"Prompt chars: {len(prompt)}\n")
        for m in models:
            d = tempfile.mkdtemp(prefix=f"llmrev-dry-{m}-")
            try:
                inv = _BUILDERS[m](prompt, d, None)
                shown = [a if len(a) < 120 else a[:117] + "..." for a in inv.argv]
                stdin_note = " (prompt via stdin)" if inv.stdin_text else ""
                outf = f" (review <- {inv.output_file.name})" if inv.output_file else ""
                print(f"## {m}{stdin_note}{outf}\n  {' '.join(shown)}\n")
            finally:
                shutil.rmtree(d, ignore_errors=True)
        print("----- PROMPT -----")
        print(prompt)
        return 0

    out_dir = make_out_dir(args.verb, args.out)
    (out_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    print(f"Reviewing {target_desc}", file=sys.stderr)
    print(f"  reviewers: {', '.join(models)}  ->  {out_dir}", file=sys.stderr)

    runs = run_reviews_parallel(models, prompt, args.timeout)

    # Persist each raw review + stderr; collect successful ones for synthesis.
    reviews: dict[str, str] = {}
    for m, run in runs.items():
        (out_dir / f"{m}.stderr.log").write_text(run.stderr, encoding="utf-8")
        if run.ok:
            (out_dir / f"{m}.md").write_text(run.text, encoding="utf-8")
            reviews[m] = run.text
            print(f"  ✓ {m}: {run.duration:.0f}s — {extract_verdict(run.text) or 'ok'}",
                  file=sys.stderr)
        else:
            (out_dir / f"{m}.md").write_text(
                f"_Review failed: {run.error}_\n", encoding="utf-8")
            print(f"  ✗ {m}: {run.error}", file=sys.stderr)

    header = report_header(target_desc, models, synth if reviews else None)

    # Synthesis (only worthwhile with ≥2 reviews; with 1 the review IS the summary).
    synth_run: ModelRun | None = None
    if synth and len(reviews) >= 2:
        print(f"  synthesizing with {synth}...", file=sys.stderr)
        synth_run = run_model(synth, build_synth_prompt(reviews, target_desc),
                              args.timeout)
        (out_dir / f"_synth.{synth}.stderr.log").write_text(
            synth_run.stderr, encoding="utf-8")

    if synth_run and synth_run.ok:
        summary = (
            f"{header}\n> Consolidated by **{synth}** from "
            f"{len(reviews)} review(s).\n\n{synth_run.text.strip()}\n\n"
            f"---\n_Raw per-model reviews: "
            f"{', '.join(f'`{m}.md`' for m in reviews)}_\n"
        )
    elif len(reviews) == 1:
        only = next(iter(reviews))
        summary = (f"{header}\n> Single reviewer ({only}); no synthesis needed.\n\n"
                   f"{reviews[only].strip()}\n")
    else:
        if synth_run and not synth_run.ok:
            print(f"  synthesis failed ({synth_run.error}); "
                  "concatenating instead", file=sys.stderr)
        summary = compile_fallback_summary(target_desc, reviews, header)

    (out_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")

    manifest = {
        "target": target_desc,
        "verb": args.verb,
        "models": models,
        "synth": synth if synth_run and synth_run.ok else None,
        "out_dir": str(out_dir),
        "prompt_chars": len(prompt),
        "runs": {
            m: {
                "ok": r.ok,
                "duration_s": round(r.duration, 1),
                "error": r.error,
                "returncode": r.returncode,
                "verdict": extract_verdict(r.text) if r.ok else None,
            }
            for m, r in runs.items()
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    update_latest_symlink(out_dir)

    print(f"\nReport: {out_dir / 'SUMMARY.md'}", file=sys.stderr)
    if args.json_out:
        print(json.dumps(manifest, indent=2))

    return 0 if reviews else 1


if __name__ == "__main__":
    sys.exit(main())
