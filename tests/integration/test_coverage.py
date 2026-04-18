"""Meta-test: fails if any public resource method lacks an integration test.

This test imports coverage_harness, which is populated by all other test files
at import time. It then compares the registered methods against what inspect
discovers on the actual resource classes.
"""

from __future__ import annotations

import pytest

import tests.integration.test_events as _events  # noqa: F401

# Force import of all test files so they register their methods.
import tests.integration.test_exchange as _exchange  # noqa: F401
import tests.integration.test_historical as _historical  # noqa: F401
import tests.integration.test_markets as _markets  # noqa: F401
import tests.integration.test_multivariate as _multivariate  # noqa: F401
import tests.integration.test_orders as _orders  # noqa: F401
import tests.integration.test_portfolio as _portfolio  # noqa: F401
import tests.integration.test_series as _series  # noqa: F401
from tests.integration.coverage_harness import SCENARIO_REGISTRY, discover_public_methods


@pytest.mark.integration
class TestCoverageHarness:
    def test_all_methods_covered(self) -> None:
        """Every public method on every sync resource class must be registered."""
        discovered = discover_public_methods()
        missing: list[str] = []

        for cls_name, methods in discovered.items():
            registered = SCENARIO_REGISTRY.get(cls_name, [])
            for method in methods:
                if method not in registered:
                    missing.append(f"{cls_name}.{method}")

        if missing:
            pytest.fail(
                f"Integration test coverage gap — {len(missing)} method(s) "
                f"have no registered scenario:\n  " + "\n  ".join(missing)
            )

    def test_no_stale_registrations(self) -> None:
        """No registered methods should reference non-existent methods."""
        discovered = discover_public_methods()
        stale: list[str] = []

        for cls_name, methods in SCENARIO_REGISTRY.items():
            actual = discovered.get(cls_name, [])
            for method in methods:
                if method not in actual:
                    stale.append(f"{cls_name}.{method}")

        if stale:
            pytest.fail(
                f"Stale registrations — {len(stale)} method(s) registered "
                f"but no longer exist:\n  " + "\n  ".join(stale)
            )

    def test_discovery_finds_all_resources(self) -> None:
        """Sanity check: discover finds the expected 8 resource classes."""
        discovered = discover_public_methods()
        expected = {
            "MarketsResource",
            "OrdersResource",
            "EventsResource",
            "ExchangeResource",
            "HistoricalResource",
            "PortfolioResource",
            "SeriesResource",
            "MultivariateCollectionsResource",
        }
        assert set(discovered.keys()) == expected, (
            f"Expected resources: {expected}, discovered: {set(discovered.keys())}"
        )
