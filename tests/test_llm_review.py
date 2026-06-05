"""Tests for scripts/llm_review.py — the dev-only multi-LLM review orchestrator.

These cover the *pure* logic and the context builders without ever calling a
model: prompt assembly, synthesis-prompt assembly, verdict extraction, model-arg
parsing, file/ask/diff context building (against real temp files and a real temp
git repo), and the fallback summary. The actual model fan-out is verified by a
live run, not here.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "llm_review.py"
_spec = importlib.util.spec_from_file_location("llm_review", _MODULE_PATH)
assert _spec and _spec.loader
llm_review = importlib.util.module_from_spec(_spec)
sys.modules["llm_review"] = llm_review  # dataclasses needs the module registered
_spec.loader.exec_module(llm_review)


# --------------------------- small pure helpers ---------------------------- #


def test_slugify_is_filesystem_safe() -> None:
    assert llm_review.slugify("diff") == "diff"
    assert llm_review.slugify("ask: Is it safe?!") == "ask-is-it-safe"
    assert llm_review.slugify("main...HEAD").startswith("main")
    # Collapses separators and trims; never empty.
    assert llm_review.slugify("///___   ") == "review"
    assert "/" not in llm_review.slugify("a/b/c")
    assert " " not in llm_review.slugify("a b c")


def test_guess_lang_by_suffix() -> None:
    assert llm_review.guess_lang("x.py") == "python"
    assert llm_review.guess_lang("specs/openapi.yaml") == "yaml"
    assert llm_review.guess_lang("a.unknownext") == ""


def test_number_lines_prefixes_1_indexed() -> None:
    out = llm_review.number_lines("alpha\nbeta\ngamma")
    lines = out.splitlines()
    assert lines[0].endswith("alpha")
    assert lines[0].strip().startswith("1")
    assert lines[1].strip().startswith("2")
    assert lines[2].strip().startswith("3")


def test_format_file_block_has_path_fence_and_numbers() -> None:
    block = llm_review.format_file_block("foo.py", "import os\nx = 1\n")
    assert "### File: foo.py" in block
    assert "```python" in block
    assert block.count("```") == 2
    assert "1  import os" in block


# ------------------------------ build_prompt ------------------------------- #


def test_build_prompt_orders_sections_and_includes_all() -> None:
    prompt = llm_review.build_prompt(
        rubric="RUBRIC_BODY",
        focus="FOCUS_BODY",
        target_desc="TARGET_DESC",
        context="CONTEXT_BODY",
    )
    assert "RUBRIC_BODY" in prompt
    assert "FOCUS_BODY" in prompt
    assert "TARGET_DESC" in prompt
    assert "CONTEXT_BODY" in prompt
    # Ordering: rubric before focus before target before context.
    assert (
        prompt.index("RUBRIC_BODY")
        < prompt.index("FOCUS_BODY")
        < prompt.index("TARGET_DESC")
        < prompt.index("CONTEXT_BODY")
    )


def test_build_prompt_focus_optional() -> None:
    prompt = llm_review.build_prompt("R", None, "T", "C")
    assert "Additional focus" not in prompt
    assert "R" in prompt and "T" in prompt and "C" in prompt


# --------------------------- build_synth_prompt ---------------------------- #


def test_build_synth_prompt_embeds_every_review() -> None:
    reviews = {"codex": "CODEX_FINDINGS", "grok": "GROK_FINDINGS"}
    sp = llm_review.build_synth_prompt(reviews, "the change")
    assert "codex" in sp and "CODEX_FINDINGS" in sp
    assert "grok" in sp and "GROK_FINDINGS" in sp
    assert "2 review(s)" in sp
    assert "the change" in sp


# ----------------------------- extract_verdict ----------------------------- #


@pytest.mark.parametrize(
    "review, expected_contains",
    [
        ("## Verdict\nBLOCK — drift shipped in orders", "BLOCK"),
        ("## Verdict: APPROVE WITH CHANGES — fix serialization", "APPROVE WITH CHANGES"),
        ("## Summary\nstuff\n\n## Verdict\n\nAPPROVE — clean", "APPROVE"),
        ("no header here but BLOCK this change", "BLOCK"),
    ],
)
def test_extract_verdict_variants(review: str, expected_contains: str) -> None:
    assert expected_contains in llm_review.extract_verdict(review)


def test_extract_verdict_absent_returns_empty() -> None:
    assert llm_review.extract_verdict("## Summary\njust prose, no verdict") == ""


# ---------------------------- parse_models_arg ----------------------------- #


def test_parse_models_arg_valid_subset_and_order() -> None:
    assert llm_review.parse_models_arg("grok,codex") == ["grok", "codex"]
    assert llm_review.parse_models_arg("codex, gemini , grok") == ["codex", "gemini", "grok"]


def test_parse_models_arg_dedups_preserving_first_seen() -> None:
    assert llm_review.parse_models_arg("codex,codex,grok,codex") == ["codex", "grok"]


def test_parse_models_arg_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        llm_review.parse_models_arg("codex,llama")


# --------------------------- build_files_context --------------------------- #


def test_build_files_context_numbers_and_fences(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text("a = 1\nb = 2\n")
    desc, ctx = llm_review.build_files_context([str(f)])
    assert "1 file(s)" in desc
    assert "```python" in ctx
    assert "1  a = 1" in ctx
    assert "2  b = 2" in ctx


def test_build_files_context_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        llm_review.build_files_context([str(tmp_path / "nope.py")])


def test_build_files_context_requires_a_path() -> None:
    with pytest.raises(SystemExit):
        llm_review.build_files_context([])


# ---------------------------- build_ask_context ---------------------------- #


def test_build_ask_context_question_only() -> None:
    desc, ctx = llm_review.build_ask_context("Is X safe?", [])
    assert "Is X safe?" in ctx
    assert desc.startswith("ask:")


def test_build_ask_context_with_files(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("y = 0\n")
    _, ctx = llm_review.build_ask_context("Check this", [str(f)])
    assert "Check this" in ctx
    assert "### File:" in ctx
    assert "1  y = 0" in ctx


def test_build_ask_context_requires_question() -> None:
    with pytest.raises(SystemExit):
        llm_review.build_ask_context("   ", [])


# --------------------------- build_diff_context ---------------------------- #


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_build_diff_context_renders_real_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    target = repo / "money.py"
    target.write_text("rate = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    target.write_text("rate = 2\n")  # uncommitted change

    monkeypatch.setattr(llm_review, "REPO_ROOT", repo)
    desc, ctx = llm_review.build_diff_context([])
    assert "git diff HEAD" in desc
    assert "```diff" in ctx
    assert "money.py" in ctx
    assert "Diffstat:" in ctx


def test_build_diff_context_empty_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.py").write_text("x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")

    monkeypatch.setattr(llm_review, "REPO_ROOT", repo)
    with pytest.raises(SystemExit):
        llm_review.build_diff_context([])  # no changes -> guard fires


# ------------------------- compile_fallback_summary ------------------------ #


def test_compile_fallback_summary_includes_all() -> None:
    out = llm_review.compile_fallback_summary(
        "the target",
        {"codex": "CODEX_TEXT", "gemini": "GEMINI_TEXT"},
        header="HEADER_LINE",
    )
    assert "HEADER_LINE" in out
    assert "CODEX_TEXT" in out
    assert "GEMINI_TEXT" in out
    assert "codex" in out and "gemini" in out
