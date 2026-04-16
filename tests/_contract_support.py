"""Request-side contract support: SDK method → OpenAPI endpoint mapping and helpers.

This module is test infrastructure. It lives in ``tests/`` (not ``kalshi/``) so that
users importing the SDK don't get spec-parsing code shipped in the PyPI wheel.

The map covers ``path`` and ``query`` parameter surface. Body schemas (POST/PUT
request payloads built as inline dicts in ``orders.py::amend()`` etc.) are NOT
covered — those are audited by the separate inline-body-dict TODO.

Async siblings are derived at test time via ``Async<ClassName>`` substitution
with identical method names. Do NOT add separate async entries to the map.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MethodEndpointEntry:
    """Maps one sync SDK method to its OpenAPI endpoint."""

    sdk_method: str
    http_method: str
    path_template: str


METHOD_ENDPOINT_MAP: list[MethodEndpointEntry] = [
    # Populated per-resource in Session 1b. See docs/AUDIT-resource-params.md.
]


def _resolve_ref(
    spec: dict[str, Any],
    ref: str,
    *,
    depth: int = 0,
    max_depth: int = 8,
) -> dict[str, Any]:
    """Resolve a ``$ref`` pointer. Caps recursion depth to avoid silent infinite
    loops if the spec ever introduces a circular reference."""
    if depth > max_depth:
        raise RuntimeError(
            f"_resolve_ref exceeded max_depth={max_depth} resolving {ref!r}; "
            "check spec for circular $ref"
        )
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        node = node[part]
    if isinstance(node, dict) and "$ref" in node:
        return _resolve_ref(spec, node["$ref"], depth=depth + 1, max_depth=max_depth)
    return node  # type: ignore[no-any-return]


def _resolve_path_params(
    spec: dict[str, Any],
    path_template: str,
    http_method: str,
    *,
    max_ref_depth: int = 8,
) -> list[dict[str, Any]]:
    """Return the merged list of parameter objects for a specific operation.

    Walks BOTH path-level ``parameters`` (shared across operations on that path)
    AND operation-level ``parameters`` (specific to the given HTTP method).
    Operation-level entries override path-level by the ``name`` field.
    Any ``$ref`` entries are resolved via ``_resolve_ref``.

    Returns an empty list if the path has no parameters. Raises ``KeyError`` if the
    path does not exist in the spec (fail loud — do NOT silently return []).
    """
    paths = spec.get("paths", {})
    if path_template not in paths:
        raise KeyError(f"path {path_template!r} not found in spec")

    path_entry = paths[path_template]
    op_key = http_method.lower()

    def _collect(parameters_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for param in parameters_list:
            if "$ref" in param:
                resolved.append(_resolve_ref(spec, param["$ref"], max_depth=max_ref_depth))
            else:
                resolved.append(param)
        return resolved

    path_level = _collect(path_entry.get("parameters", []))
    op_level: list[dict[str, Any]] = []
    if op_key in path_entry:
        op_entry = path_entry[op_key]
        op_level = _collect(op_entry.get("parameters", []))

    # Merge with op-level overriding path-level by name.
    merged: dict[str, dict[str, Any]] = {p["name"]: p for p in path_level}
    for p in op_level:
        merged[p["name"]] = p
    return list(merged.values())
