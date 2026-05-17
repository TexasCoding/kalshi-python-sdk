"""Render the spec-drift issue body from environment variables.

Reads every template placeholder from os.environ and writes the substituted
markdown to stdout. Uses string.Template.substitute, which performs only
literal-string substitution — values are never re-interpreted as shell,
template syntax, or code. This is the safe replacement for the prior
heredoc-based body construction in spec-sync.yml, which used an unquoted
heredoc that would expand $(...) command substitutions present in
upstream-controlled values.
"""

from __future__ import annotations

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

Reproduce locally and verify the same hashes before generating models.

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
    sys.stdout.write(TEMPLATE.substitute(os.environ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
