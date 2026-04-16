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

    def test_entries_are_frozen(self) -> None:
        # When map is populated in Session 1b, verify invariant holds for each.
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
