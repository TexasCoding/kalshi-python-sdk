"""Top-level export parity tests.

Ensures every model exposed via ``kalshi.models.__all__`` is also re-exported
from the top-level ``kalshi`` package, so users never need to reach into the
``kalshi.models.*`` private submodules to type a public method's return value.
"""

from __future__ import annotations

import pytest

import kalshi
import kalshi.models


def test_models_all_subset_of_kalshi_all() -> None:
    missing = set(kalshi.models.__all__) - set(kalshi.__all__)
    assert not missing, (
        f"{len(missing)} model(s) exported from kalshi.models.__all__ but not "
        f"re-exported from kalshi.__all__: {sorted(missing)}"
    )


@pytest.mark.parametrize("name", kalshi.models.__all__)
def test_model_identity_matches_top_level(name: str) -> None:
    top_level = getattr(kalshi, name)
    submodule = getattr(kalshi.models, name)
    assert top_level is submodule, (
        f"kalshi.{name} ({top_level!r}) is not the same object as "
        f"kalshi.models.{name} ({submodule!r})"
    )


def test_from_kalshi_import_star_exposes_all_models() -> None:
    namespace: dict[str, object] = {}
    exec("from kalshi import *", namespace)
    for name in kalshi.models.__all__:
        assert name in namespace, f"`from kalshi import *` did not bind {name}"
        assert namespace[name] is getattr(kalshi, name)
