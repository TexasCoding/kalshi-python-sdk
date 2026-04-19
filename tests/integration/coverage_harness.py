"""Coverage harness — introspects resource classes and tracks tested methods.

The SCENARIO_REGISTRY maps resource class names to the list of methods
that have integration tests. test_coverage.py compares this against the
actual public methods discovered via inspect.
"""

from __future__ import annotations

import importlib
import inspect

from kalshi.resources._base import SyncResource

# Registry: each test file registers its covered methods here.
# Key = resource class name (e.g., "MarketsResource"), value = list of method names.
SCENARIO_REGISTRY: dict[str, list[str]] = {}

# Resource modules to introspect
RESOURCE_MODULES = [
    "kalshi.resources.account",
    "kalshi.resources.api_keys",
    "kalshi.resources.communications",
    "kalshi.resources.live_data",
    "kalshi.resources.markets",
    "kalshi.resources.milestones",
    "kalshi.resources.multivariate",
    "kalshi.resources.order_groups",
    "kalshi.resources.orders",
    "kalshi.resources.events",
    "kalshi.resources.exchange",
    "kalshi.resources.fcm",
    "kalshi.resources.historical",
    "kalshi.resources.portfolio",
    "kalshi.resources.search",
    "kalshi.resources.series",
    "kalshi.resources.structured_targets",
    "kalshi.resources.subaccounts",
]


def discover_public_methods() -> dict[str, list[str]]:
    """Discover all public methods on sync resource classes.

    Returns a dict mapping class name -> list of public method names.
    Uses __qualname__ to filter out inherited methods from SyncResource/object.
    Only includes methods defined directly on the concrete subclass.
    """
    result: dict[str, list[str]] = {}

    for mod_name in RESOURCE_MODULES:
        mod = importlib.import_module(mod_name)
        for name, cls in inspect.getmembers(mod, inspect.isclass):
            # Only sync resource subclasses, not Async* or base classes
            if not issubclass(cls, SyncResource):
                continue
            if cls is SyncResource:
                continue
            if name.startswith("Async"):
                continue

            methods: list[str] = []
            for method_name, method_obj in inspect.getmembers(cls, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                # Only methods defined on THIS class, not inherited
                qualname = getattr(method_obj, "__qualname__", "")
                if qualname.startswith(f"{name}."):
                    methods.append(method_name)

            if methods:
                result[name] = sorted(methods)

    return result


def register(resource_name: str, methods: list[str]) -> None:
    """Register methods as covered by integration tests."""
    SCENARIO_REGISTRY[resource_name] = sorted(methods)
