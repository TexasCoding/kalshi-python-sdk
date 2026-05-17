# Roadmap

**v1.1 is feature-complete** — see `CHANGELOG.md`. The remaining two issues in
the [v1.1 milestone](https://github.com/TexasCoding/kalshi-python-sdk/milestone/1)
are deferred and don't block a release:

- **#45** — verify the `json={}` Content-Type workaround under production
  credentials. Blocked on prod-key access.
- **#53** — resolve nested `$ref` pointers in the body-schema drift check.
  Premature — the spec currently has no nested refs.

Future work lives in [GitHub Issues](https://github.com/TexasCoding/kalshi-python-sdk/issues).
File a new issue (or comment on an existing one) rather than editing this file.

## Shipped

See `CHANGELOG.md` for full release history.

- **v1.1.0 (2026-05-16)** — model-first request API, DataFrame integration,
  record/replay mock transport, MkDocs documentation site, `Literal` enum
  kwargs, sync/async dedup refactor, weekly spec sync + nightly integration
  CI workflows.
- **v1.0.0 (2026-05-10)** — public API stable. 89/89 REST endpoints, 11 WS
  channels, contract drift tests, PyPI trusted-publisher release pipeline.
