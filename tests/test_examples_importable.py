"""Import-check every ``examples/perps_*.py`` so a broken example reds CI.

Imports each example module (which does NOT execute ``main()`` — that is guarded
by ``if __name__ == "__main__"``) to verify it parses, its imports resolve, and
the perps API surface it references still exists.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
_PERPS_EXAMPLES = sorted(_EXAMPLES_DIR.glob("perps_*.py"))


@pytest.mark.parametrize("path", _PERPS_EXAMPLES, ids=[p.stem for p in _PERPS_EXAMPLES])
def test_example_imports(path: Path) -> None:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # importing must not call main()
    assert hasattr(module, "main")


def test_perps_examples_present() -> None:
    # Guards against the glob silently matching nothing (e.g. a directory move).
    names = {p.name for p in _PERPS_EXAMPLES}
    assert names == {
        "perps_create_order.py",
        "perps_stream_ticker.py",
        "perps_balance_risk.py",
    }
