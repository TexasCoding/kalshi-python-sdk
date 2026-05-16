"""Extract metadata from an OpenAPI or AsyncAPI spec for the weekly spec-sync workflow.

Outputs JSON on stdout. Returns empty values when the file does not exist so the
workflow can handle the "no previous spec" snapshot case the same way it handles
"spec exists but empty section".

Usage:
    uv run python scripts/extract_spec_meta.py specs/openapi.yaml
    uv run python scripts/extract_spec_meta.py specs/asyncapi.yaml
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml


def extract(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": "", "paths": [], "channels": []}
    data = yaml.safe_load(path.read_text()) or {}
    version = (data.get("info") or {}).get("version", "")
    paths = sorted((data.get("paths") or {}).keys())
    channels = sorted((data.get("channels") or {}).keys())
    return {"version": version, "paths": paths, "channels": channels}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: extract_spec_meta.py <yaml-path>", file=sys.stderr)
        return 2
    print(json.dumps(extract(Path(argv[1]))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
