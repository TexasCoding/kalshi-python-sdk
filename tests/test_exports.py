"""Top-level export parity tests.

Ensures every model exposed via ``kalshi.models.__all__`` is also re-exported
from the top-level ``kalshi`` package, so users never need to reach into the
``kalshi.models.*`` private submodules to type a public method's return value.
"""

from __future__ import annotations

import importlib

import pytest

import kalshi
import kalshi.models

# Names added by issue #89 — keep this explicit so any future regression
# (e.g. a name silently dropped from kalshi/__init__.py) fails loudly with
# a clear list of what went missing.
NEWLY_EXPORTED: tuple[str, ...] = (
    "Announcement",
    "AssociatedEvent",
    "Balance",
    "CreateMarketResponse",
    "DailySchedule",
    "Event",
    "EventMetadata",
    "EventPosition",
    "ExchangeStatus",
    "ForecastPercentilesPoint",
    "HistoricalCutoff",
    "LookupPoint",
    "LookupTickersResponse",
    "MaintenanceWindow",
    "MarketMetadata",
    "MarketPosition",
    "PercentilePoint",
    "PositionsResponse",
    "Schedule",
    "Settlement",
    "SettlementSource",
    "Trade",
    "WeeklySchedule",
)


def test_models_all_subset_of_kalshi_all() -> None:
    """Every name in ``kalshi.models.__all__`` must appear in ``kalshi.__all__``."""
    missing = set(kalshi.models.__all__) - set(kalshi.__all__)
    assert not missing, (
        f"{len(missing)} model(s) exported from kalshi.models.__all__ but not "
        f"re-exported from kalshi.__all__: {sorted(missing)}"
    )


@pytest.mark.parametrize("name", NEWLY_EXPORTED)
def test_newly_exported_name_is_importable(name: str) -> None:
    """``from kalshi import X`` works and points to the same object as ``kalshi.models.X``."""
    top_level = getattr(kalshi, name)
    submodule = getattr(kalshi.models, name)
    assert top_level is submodule, (
        f"kalshi.{name} ({top_level!r}) is not the same object as "
        f"kalshi.models.{name} ({submodule!r})"
    )


@pytest.mark.parametrize("name", NEWLY_EXPORTED)
def test_newly_exported_name_in_kalshi_all(name: str) -> None:
    assert name in kalshi.__all__, f"{name} missing from kalshi.__all__"


def test_from_kalshi_import_star_exposes_newly_exported_names() -> None:
    """``from kalshi import *`` must surface every newly added name."""
    module = importlib.import_module("kalshi")
    namespace: dict[str, object] = {}
    exec("from kalshi import *", namespace)
    for name in NEWLY_EXPORTED:
        assert name in namespace, f"`from kalshi import *` did not bind {name}"
        assert namespace[name] is getattr(module, name)
