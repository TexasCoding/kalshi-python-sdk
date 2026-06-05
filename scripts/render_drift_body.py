"""Render the spec-drift issue body from environment variables.

Reads every template placeholder from os.environ and writes the substituted
markdown to stdout. Uses string.Template.substitute, which performs only
literal-string substitution — values are never re-interpreted as shell,
template syntax, or code. This is the safe replacement for the prior
heredoc-based body construction in spec-sync.yml, which used an unquoted
heredoc that would expand $(...) command substitutions present in
upstream-controlled values.
"""

import os
import sys
from string import Template

TEMPLATE = Template("""## Spec drift detected

Upstream specs changed since the last sync. This workflow runs with
`contents: read` only — it does NOT push a branch or open a PR.

**To resolve:** locally run `uv run python scripts/sync_spec.py` +
`uv run python scripts/generate.py`, audit the diff (including
`kalshi/_generated/models.py`), and open a PR whose body contains
`Closes #<this issue number>` so this issue auto-closes on merge.

- OpenAPI changed: `${OPENAPI_CHANGED}`
- AsyncAPI changed: `${ASYNCAPI_CHANGED}`
- Workflow run: ${RUN_URL}

### Spec checksums (sha256 of fetched upstream content)

- `specs/openapi.yaml`: `${OPENAPI_SHA}`
- `specs/asyncapi.yaml`: `${ASYNCAPI_SHA}`
- `specs/perps_openapi.yaml`: `${PERPS_OPENAPI_SHA}`
- `specs/perps_asyncapi.yaml`: `${PERPS_ASYNCAPI_SHA}`
- `specs/perps_scm_openapi.yaml`: `${PERPS_SCM_SHA}`

Reproduce locally and verify the same hashes before generating models.

### Perps (margin) specs

- perps OpenAPI changed: `${PERPS_OPENAPI_CHANGED}`
- perps AsyncAPI changed: `${PERPS_ASYNCAPI_CHANGED}`
- perps SCM/Klear changed: `${PERPS_SCM_CHANGED}`

A perps-spec change reds the perps contract-drift suites in
`tests/test_contracts.py` (the `TestPerps*Drift` classes). Re-vendor with
`scripts/sync_spec.py` and reconcile the perps models/maps under `kalshi/perps/`.

## OpenAPI

- Version: `${OLD_VERSION}` → `${NEW_VERSION}`
- Endpoints: ${OLD_PATH_COUNT} → ${NEW_PATH_COUNT} paths

### Added endpoints

```
${ADDED_PATHS}
```

### Removed endpoints

```
${REMOVED_PATHS}
```

## AsyncAPI

- Channels: ${OLD_CHANNEL_COUNT} → ${NEW_CHANNEL_COUNT}

### Added channels

```
${ADDED_CHANNELS}
```

### Removed channels

```
${REMOVED_CHANNELS}
```

<!-- spec-sync-bot: do not edit
fingerprint:${FINGERPRINT}
-->
""")


def main() -> int:
    try:
        sys.stdout.write(TEMPLATE.substitute(os.environ))
    except KeyError as exc:
        sys.exit(f"render_drift_body.py: missing environment variable {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
