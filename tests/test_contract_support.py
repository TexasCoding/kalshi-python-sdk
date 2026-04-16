"""Tests for tests/_contract_support.py — request-side contract infra."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from tests._contract_support import (
    METHOD_ENDPOINT_MAP,
    MethodEndpointEntry,
    _resolve_path_params,
    _resolve_ref,
)


class TestMethodEndpointEntry:
    def test_instantiation(self) -> None:
        entry = MethodEndpointEntry(
            sdk_method="kalshi.resources.orders.OrdersResource.list",
            http_method="GET",
            path_template="/portfolio/orders",
        )
        assert entry.sdk_method == "kalshi.resources.orders.OrdersResource.list"
        assert entry.http_method == "GET"
        assert entry.path_template == "/portfolio/orders"

    def test_frozen(self) -> None:
        entry = MethodEndpointEntry(
            sdk_method="x.Y.z", http_method="GET", path_template="/x"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry.http_method = "POST"  # type: ignore[misc]


class TestResolveRef:
    def test_simple(self) -> None:
        spec: dict[str, Any] = {
            "components": {"parameters": {"Foo": {"name": "foo", "in": "query"}}}
        }
        result = _resolve_ref(spec, "#/components/parameters/Foo")
        assert result == {"name": "foo", "in": "query"}

    def test_chained(self) -> None:
        spec: dict[str, Any] = {
            "components": {
                "parameters": {
                    "Inner": {"name": "inner", "in": "query"},
                    "Outer": {"$ref": "#/components/parameters/Inner"},
                }
            }
        }
        result = _resolve_ref(spec, "#/components/parameters/Outer")
        assert result == {"name": "inner", "in": "query"}

    def test_recursion_cap_raises(self) -> None:
        # Circular ref: A → B → A
        spec: dict[str, Any] = {
            "components": {
                "parameters": {
                    "A": {"$ref": "#/components/parameters/B"},
                    "B": {"$ref": "#/components/parameters/A"},
                }
            }
        }
        with pytest.raises(RuntimeError, match="circular"):
            _resolve_ref(spec, "#/components/parameters/A", max_depth=4)


class TestResolvePathParams:
    def _base_spec(self) -> dict[str, Any]:
        return {
            "components": {
                "parameters": {
                    "SharedRef": {"name": "shared", "in": "query", "schema": {"type": "string"}},
                }
            },
            "paths": {},
        }

    def test_op_level_only(self) -> None:
        spec = self._base_spec()
        spec["paths"]["/x"] = {
            "get": {"parameters": [{"name": "a", "in": "query"}]}
        }
        result = _resolve_path_params(spec, "/x", "GET")
        assert [p["name"] for p in result] == ["a"]

    def test_path_level_only(self) -> None:
        spec = self._base_spec()
        spec["paths"]["/x"] = {
            "parameters": [{"name": "b", "in": "query"}],
            "get": {},
        }
        result = _resolve_path_params(spec, "/x", "GET")
        assert [p["name"] for p in result] == ["b"]

    def test_both_op_overrides_path(self) -> None:
        spec = self._base_spec()
        spec["paths"]["/x"] = {
            "parameters": [{"name": "status", "in": "query", "description": "from-path"}],
            "get": {
                "parameters": [{"name": "status", "in": "query", "description": "from-op"}]
            },
        }
        result = _resolve_path_params(spec, "/x", "GET")
        assert len(result) == 1
        assert result[0]["description"] == "from-op"

    def test_ref_resolution(self) -> None:
        spec = self._base_spec()
        spec["paths"]["/x"] = {
            "get": {"parameters": [{"$ref": "#/components/parameters/SharedRef"}]}
        }
        result = _resolve_path_params(spec, "/x", "GET")
        assert result[0]["name"] == "shared"

    def test_empty_params(self) -> None:
        spec = self._base_spec()
        spec["paths"]["/x"] = {"get": {}}
        result = _resolve_path_params(spec, "/x", "GET")
        assert result == []

    def test_missing_path_raises(self) -> None:
        spec = self._base_spec()
        with pytest.raises(KeyError, match="/nope"):
            _resolve_path_params(spec, "/nope", "GET")

    def test_mixed_path_level_and_op_level(self) -> None:
        spec = self._base_spec()
        spec["paths"]["/x"] = {
            "parameters": [
                {"name": "p1", "in": "query"},
                {"name": "p2", "in": "query"},
            ],
            "get": {"parameters": [{"name": "p3", "in": "query"}]},
        }
        result = _resolve_path_params(spec, "/x", "GET")
        names = {p["name"] for p in result}
        assert names == {"p1", "p2", "p3"}


class TestMethodEndpointMap:
    def test_map_is_list(self) -> None:
        assert isinstance(METHOD_ENDPOINT_MAP, list)

    def test_map_is_non_empty(self) -> None:
        assert len(METHOD_ENDPOINT_MAP) > 0

    def test_entries_are_frozen(self) -> None:
        for entry in METHOD_ENDPOINT_MAP:
            assert isinstance(entry, MethodEndpointEntry)
            with pytest.raises(dataclasses.FrozenInstanceError):
                entry.sdk_method = "x"  # type: ignore[misc]

    def test_no_async_entries(self) -> None:
        # Invariant: map contains ONLY sync-class entries.
        # Async siblings derived via Async<ClassName> substitution at test time.
        for entry in METHOD_ENDPOINT_MAP:
            assert "Async" not in entry.sdk_method, (
                f"Entry {entry.sdk_method!r} looks async; map is sync-only. "
                "See tests/_contract_support.py module docstring."
            )

    def test_http_method_is_valid(self) -> None:
        valid = {"GET", "POST", "DELETE", "PUT"}
        for entry in METHOD_ENDPOINT_MAP:
            assert entry.http_method in valid, (
                f"Entry {entry.sdk_method!r} has invalid http_method "
                f"{entry.http_method!r}; expected one of {valid}"
            )

    def test_sync_fqn_format(self) -> None:
        # Each FQN must be module.Class.method (class-qualified, not module-level).
        for entry in METHOD_ENDPOINT_MAP:
            parts = entry.sdk_method.split(".")
            assert len(parts) >= 4, (
                f"Entry {entry.sdk_method!r} is not class-qualified; "
                "expected format: kalshi.resources.<module>.<Class>.<method>"
            )
            assert parts[0] == "kalshi"
            assert parts[1] == "resources"

    def test_every_public_method_has_entry(self) -> None:
        """Completeness: iterate every sync Resource class across 8 resource
        modules; assert each public method has a METHOD_ENDPOINT_MAP entry."""
        import importlib
        import inspect

        resource_modules = [
            "kalshi.resources.markets",
            "kalshi.resources.events",
            "kalshi.resources.exchange",
            "kalshi.resources.historical",
            "kalshi.resources.orders",
            "kalshi.resources.portfolio",
            "kalshi.resources.series",
            "kalshi.resources.multivariate",
        ]

        mapped = {entry.sdk_method for entry in METHOD_ENDPOINT_MAP}
        missing: list[str] = []

        for mod_path in resource_modules:
            module = importlib.import_module(mod_path)
            for cls_name, cls in inspect.getmembers(module, inspect.isclass):
                # Only sync Resource classes — skip Async* and non-Resource types.
                if cls.__module__ != mod_path:
                    continue
                if cls_name.startswith("Async"):
                    continue
                if not cls_name.endswith("Resource"):
                    continue

                for method_name, _ in inspect.getmembers(
                    cls, predicate=inspect.isfunction
                ):
                    # Public methods only (no leading underscore).
                    if method_name.startswith("_"):
                        continue
                    # Skip methods inherited from SyncResource base
                    # (_require_auth is private; no public inherited methods
                    # currently exist that hit the wire).
                    if method_name not in cls.__dict__:
                        continue
                    fqn = f"{mod_path}.{cls_name}.{method_name}"
                    if fqn not in mapped:
                        missing.append(fqn)

        assert not missing, (
            f"METHOD_ENDPOINT_MAP missing {len(missing)} public method(s):\n  "
            + "\n  ".join(missing)
        )
