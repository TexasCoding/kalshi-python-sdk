"""Generate reference Pydantic models from OpenAPI spec.

This is a local development tool, NOT run in CI.
Generated models serve as a reference when building new SDK resources.
Contract tests compare against the raw YAML spec directly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SPEC_FILE = Path(__file__).parent.parent / "specs" / "openapi.yaml"
OUTPUT_DIR = Path(__file__).parent.parent / "kalshi" / "_generated"


def generate() -> None:
    """Run datamodel-code-generator to produce reference models."""
    if not SPEC_FILE.exists():
        print("Spec not found. Run sync_spec.py first.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "datamodel_code_generator",
            "--input",
            str(SPEC_FILE),
            "--input-file-type",
            "openapi",
            "--output",
            str(OUTPUT_DIR / "models.py"),
            "--output-model-type",
            "pydantic_v2.BaseModel",
            "--target-python-version",
            "3.12",
            "--use-standard-collections",
            "--use-union-operator",
            "--field-constraints",
            "--collapse-root-models",
            "--strict-nullable",
        ],
        check=True,
    )
    print(f"Generated models written to {OUTPUT_DIR / 'models.py'}")


if __name__ == "__main__":
    generate()
