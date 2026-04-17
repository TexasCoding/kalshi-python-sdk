"""Tests for tests/_contract_support.py — request-side contract infra."""

from __future__ import annotations

import dataclasses
import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest
import yaml

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

    def test_missing_ref_raises_keyerror(self) -> None:
        spec: dict[str, Any] = {"components": {"parameters": {}}}
        with pytest.raises(KeyError):
            _resolve_ref(spec, "#/components/parameters/DoesNotExist")

    def test_non_local_ref_raises(self) -> None:
        """External refs (e.g., 'other.yaml#/X') aren't supported. Fail loud
        rather than silently mis-parse."""
        spec: dict[str, Any] = {}
        with pytest.raises(ValueError, match="local refs"):
            _resolve_ref(spec, "other.yaml#/components/parameters/X")

    def test_json_pointer_escapes_decoded(self) -> None:
        """Per RFC 6901 §4, ~1 decodes to / and ~0 decodes to ~. This matters
        for OpenAPI refs pointing to paths with literal slashes like
        '/markets/{ticker}' which show up as '~1markets~1{ticker}'."""
        spec: dict[str, Any] = {
            "paths": {
                "/markets/{ticker}": {"description": "a path entry"},
            }
        }
        result = _resolve_ref(spec, "#/paths/~1markets~1{ticker}")
        assert result == {"description": "a path entry"}


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

    def test_missing_op_raises(self) -> None:
        """If the path exists but the HTTP method doesn't, raise — don't
        silently return partial data. Guards against wrong MAP entries like
        GET /portfolio/orders/{id}/amend (actually POST)."""
        spec = self._base_spec()
        spec["paths"]["/x"] = {"post": {"parameters": []}}  # POST only
        with pytest.raises(KeyError, match="GET"):
            _resolve_path_params(spec, "/x", "GET")

    def test_same_name_different_in_both_kept(self) -> None:
        """OpenAPI allows the same param name in different locations. The
        merge key must be (name, in) — not just name — or we silently drop
        one of them. Uses a realistic path+query scenario."""
        spec = self._base_spec()
        spec["paths"]["/x"] = {
            "get": {
                "parameters": [
                    {"name": "ticker", "in": "path"},
                    {"name": "ticker", "in": "query"},
                ]
            }
        }
        result = _resolve_path_params(spec, "/x", "GET")
        locations = {(p["name"], p["in"]) for p in result}
        assert locations == {("ticker", "path"), ("ticker", "query")}


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
                "Async siblings are derived via Async<ClassName> substitution "
                "at test time — see the METHOD_ENDPOINT_MAP block comment in "
                "tests/_contract_support.py."
            )

    def test_http_method_is_valid(self) -> None:
        # PATCH intentionally excluded: Kalshi's OpenAPI spec (v3.13.0) has
        # no PATCH endpoints. If a future spec version adds PATCH, add it
        # here alongside a MAP entry.
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
        """Completeness: enumerate every resource module in kalshi/resources/
        dynamically, then assert each sync public method has a
        METHOD_ENDPOINT_MAP entry.

        Dynamic enumeration guards against 'added a 9th resource file and
        forgot to update the hardcoded list' drift.
        """
        resources_dir = (
            Path(__file__).parent.parent / "kalshi" / "resources"
        )
        assert resources_dir.is_dir(), (
            f"Expected kalshi/resources/ at {resources_dir}, not found"
        )

        # Discover modules: every *.py file in resources/ except __init__ and
        # _base (private base classes — no wire-hitting methods).
        skip = {"__init__", "_base"}
        resource_modules = sorted(
            f"kalshi.resources.{p.stem}"
            for p in resources_dir.glob("*.py")
            if p.stem not in skip
        )

        # Floor check: if enumeration misses everything (e.g., path resolution
        # breaks), the test shouldn't tautologically pass.
        # Floor is 8 resource files as of v0.6.1; raise it when adding a new
        # resource module so this guard keeps detecting silent discovery loss.
        assert len(resource_modules) >= 8, (
            f"Expected >=8 resource modules in kalshi/resources/, found "
            f"{len(resource_modules)}: {resource_modules}"
        )

        mapped = {entry.sdk_method for entry in METHOD_ENDPOINT_MAP}
        missing: list[str] = []
        discovered: list[str] = []

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
                    discovered.append(fqn)
                    if fqn not in mapped:
                        missing.append(fqn)

        # Guard against tautological pass: if discovery silently returns zero
        # methods (e.g., a refactor removes the Resource suffix), the test
        # would incorrectly pass with an empty missing list. Require a floor.
        # Floor is ~53 public methods as of v0.6.1; raise it as the surface
        # grows so accidental discovery regressions still fail.
        assert len(discovered) >= 50, (
            f"Expected >=50 public methods across {len(resource_modules)} "
            f"resources; discovered only {len(discovered)}. "
            "Check resource class naming (must end in 'Resource' and not start "
            "with 'Async')."
        )
        assert not missing, (
            f"METHOD_ENDPOINT_MAP missing {len(missing)} public method(s):\n  "
            + "\n  ".join(missing)
        )

    def test_every_mapped_path_resolves_in_spec(self) -> None:
        """Reverse completeness: every path_template in METHOD_ENDPOINT_MAP
        must exist in specs/openapi.yaml. Catches typos before Session 1b
        applies dispositions against the wrong paths."""
        spec_path = Path(__file__).parent.parent / "specs" / "openapi.yaml"
        # Fail loud, not skip: the spec IS committed to this repo. Silent skip
        # would turn this reverse-completeness test into a no-op in any CI or
        # clone that loses the spec — exactly when we need it to catch drift.
        assert spec_path.exists(), (
            f"specs/openapi.yaml missing at {spec_path}. "
            "Commit the spec or restore it; this test must always run."
        )

        with open(spec_path, encoding="utf-8") as f:
            spec = yaml.safe_load(f)

        unresolved: list[str] = []
        for entry in METHOD_ENDPOINT_MAP:
            try:
                _resolve_path_params(spec, entry.path_template, entry.http_method)
            except KeyError:
                unresolved.append(
                    f"{entry.sdk_method} → {entry.http_method} {entry.path_template}"
                )

        assert not unresolved, (
            f"{len(unresolved)} METHOD_ENDPOINT_MAP entries have path_templates "
            "not in specs/openapi.yaml:\n  " + "\n  ".join(unresolved)
        )
