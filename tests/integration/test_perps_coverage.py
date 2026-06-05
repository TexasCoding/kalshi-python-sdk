"""Meta-test: every public perps resource method has a registered scenario.

Parallels :mod:`tests.integration.test_coverage` but for the perps surface. It
imports the perps test files (so they populate ``PERPS_SCENARIO_REGISTRY`` at
import time), then compares the registered methods against what inspection
discovers on the actual perps resource classes via
``discover_perps_public_methods``.

Kept separate from ``test_coverage`` so the prediction-API
``test_discovery_finds_all_resources`` exact-set assertion stays intact.
"""

from __future__ import annotations

import pytest

# Force import of the perps test files so they register their methods.
import tests.integration.test_perps_balance_risk as _balance_risk  # noqa: F401
import tests.integration.test_perps_funding as _funding  # noqa: F401
import tests.integration.test_perps_markets as _markets  # noqa: F401
import tests.integration.test_perps_orders as _orders  # noqa: F401
import tests.integration.test_perps_ws as _ws  # noqa: F401
from tests.integration.coverage_harness import (
    PERPS_SCENARIO_REGISTRY,
    discover_perps_public_methods,
)


@pytest.mark.integration
class TestPerpsCoverageHarness:
    def test_all_methods_covered(self) -> None:
        """Every public method on every perps sync resource class is registered."""
        discovered = discover_perps_public_methods()
        missing: list[str] = []

        for cls_name, methods in discovered.items():
            registered = PERPS_SCENARIO_REGISTRY.get(cls_name, [])
            for method in methods:
                if method not in registered:
                    missing.append(f"{cls_name}.{method}")

        if missing:
            pytest.fail(
                f"Perps integration coverage gap — {len(missing)} method(s) "
                f"have no registered scenario:\n  " + "\n  ".join(missing)
            )

    def test_no_stale_registrations(self) -> None:
        """No registered perps method should reference a non-existent method.

        The ``PerpsWebSocket`` registry entry is exempt — it tracks a WS channel
        helper, not a REST resource class, so it never appears in the discovered
        resource methods.
        """
        discovered = discover_perps_public_methods()
        stale: list[str] = []

        for cls_name, methods in PERPS_SCENARIO_REGISTRY.items():
            if cls_name == "PerpsWebSocket":
                continue
            actual = discovered.get(cls_name, [])
            for method in methods:
                if method not in actual:
                    stale.append(f"{cls_name}.{method}")

        if stale:
            pytest.fail(
                f"Stale perps registrations — {len(stale)} method(s) registered "
                f"but no longer exist:\n  " + "\n  ".join(stale)
            )

    def test_discovery_finds_perps_resources(self) -> None:
        """Sanity check: discovery finds the expected perps resource classes."""
        discovered = discover_perps_public_methods()
        expected = {
            "PerpsExchangeResource",
            "FundingResource",
            "MarginAccountResource",
            "PerpsMarketsResource",
            "MarginOrdersResource",
            "PerpsPortfolioResource",
        }
        assert set(discovered.keys()) == expected, (
            f"Expected perps resources: {expected}, discovered: {set(discovered.keys())}"
        )
