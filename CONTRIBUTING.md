# Contributing

Thanks for considering a contribution. This project is a Kalshi API SDK
and benefits from contributions that improve correctness, coverage,
performance, and developer experience.

## Before you start

- **Open an issue first** for anything non-trivial (new resource, public
  API change, behavior change). A 5-minute discussion saves a 50-line
  rewrite at PR time.
- **Search existing issues** — many ideas are already tracked.
- Read `CLAUDE.md` (root) for project conventions. They apply equally to
  human and AI contributors.

## Dev setup

```bash
git clone https://github.com/TexasCoding/kalshi-python-sdk
cd kalshi-python-sdk
uv sync
uv run pytest tests/ --ignore=tests/integration -v
uv run mypy kalshi/
uv run ruff check .
```

Python 3.12+ required. `uv` is the package manager.

## Project conventions

These are enforced by reviewers and CI:

- **Simplicity first.** Minimum code that solves the problem. No
  speculative abstractions or features beyond what was asked.
- **Surgical changes.** Touch only what you need. Don't refactor adjacent
  code in the same PR.
- **Type-safe.** `mypy --strict` clean. Public methods are typed end-to-end.
- **No comments referencing the current task or PR number** in
  production code. Those belong in the PR description and commit
  message — they rot in code as the codebase evolves.
- **`*Request` body models use `extra="forbid"`.** Phantom kwargs fail
  at call time, not silently on the wire.
- **Response models use `extra="allow"`.** Enforced by
  `tests/test_model_extra_policy.py`.
- **POST and DELETE are never retried.** Duplicate-order risk.

See `CLAUDE.md` for the full list, including the price/`_dollars` alias
convention, RSA-PSS signing payload format, and the spec-drift test
framework.

## Tests

Three suites:

- **Unit** — `uv run pytest tests/ --ignore=tests/integration -q`. Must
  pass on every PR. No network access; uses `respx` to mock httpx.
- **Integration** — `uv run pytest tests/integration/ -q`. Hits the
  Kalshi demo API. Requires `KALSHI_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH`
  env vars. Skipped automatically if creds are absent.
- **Contract drift** — `tests/test_contracts.py` parametrizes over
  every endpoint in `METHOD_ENDPOINT_MAP`. Hard-fails CI if the SDK
  signature drifts from the OpenAPI spec without an explicit exclusion.

If your change adds a new endpoint, register it in
`tests/_contract_support.py` `METHOD_ENDPOINT_MAP`.

## PR checklist

- [ ] Tests added or updated (regression test for bug fixes; happy +
      error + edge cases for new features).
- [ ] `uv run ruff check .` clean.
- [ ] `uv run mypy kalshi/` clean.
- [ ] `uv run pytest tests/ --ignore=tests/integration -q` passes.
- [ ] PR title is a concise summary; PR body explains the *why*.
- [ ] Commit messages reference issues via `Closes #N` or `Refs #N` so
      they auto-close on merge.
- [ ] For breaking changes: `CHANGELOG.md` entry under
      `[Unreleased] → Breaking`, plus a note in `docs/migration.md`.

## Review cycle

Most PRs receive an automated code review from Claude (the
`claude-review` check). This is **advisory, not required** — it fails
by design on Dependabot PRs and on PRs that modify the review workflow
itself. When it does run, please address the substantive feedback or
reply with a brief justification for skipping it. Maintainers
squash-merge after the required CI checks are green and review is
addressed.

## Reporting bugs / requesting features

Use the GitHub issue templates. For security issues, see `SECURITY.md`.

## License

By contributing, you agree that your contributions are licensed under
the project's MIT License (see `LICENSE`).
