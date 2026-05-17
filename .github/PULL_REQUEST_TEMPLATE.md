<!--
Thanks for the PR! A few things to make review fast:

- Title: one-line summary in conventional-commit style (e.g. `fix(ws): ...`).
- Body: the WHY of the change. The diff shows the WHAT.
- Link issues with `Closes #N` so they auto-close on merge.
- For security-sensitive changes, see SECURITY.md.
-->

## Summary

<!-- One paragraph: what does this PR do, and why? -->

## Changes

<!-- Bullet list of the substantive changes. Skip if the summary covers it. -->

-

## Test plan

- [ ] `uv run pytest tests/ --ignore=tests/integration -q` — unit
- [ ] `uv run ruff check .` — lint
- [ ] `uv run mypy kalshi/` — type-check
- [ ] If touching live endpoints: `uv run pytest tests/integration/` against demo
- [ ] If adding a new endpoint: registered in `tests/_contract_support.py::METHOD_ENDPOINT_MAP`

## Notes for reviewers

<!--
Anything reviewers should know that isn't obvious from the diff?
- Behavior changes (call them out in CHANGELOG too)
- Non-obvious design decisions
- Things deferred to a follow-up
-->

## Issue links

<!-- Use `Closes #N` to auto-close on merge, or `Refs #N` for partial work. -->

Closes #
