"""Contract tests: verify hand-written SDK models match OpenAPI / AsyncAPI spec schemas.

Drift detection:
- Additive drift (spec has fields SDK doesn't): **FAILURE** (#163)
- Unmapped WS payload models: **FAILURE** (#163)
- Unmapped REST models: WARNING (sub-models / V2 family — separate mapping pass)
- Required mismatch (spec required, SDK optional): WARNING (SDK is intentionally permissive)
- Missing schema in spec: FAILURE

Intentional deviations require an entry in ``EXCLUSIONS``
(``tests/_contract_support.py``) with a typed ``kind`` and ``reason``.
"""

from __future__ import annotations

import importlib
import inspect
import typing
from decimal import Decimal
from pathlib import Path
from types import UnionType
from typing import Any, ClassVar

import pytest

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from pydantic import AliasChoices
from pydantic import BaseModel as PydanticBase
from pydantic.fields import FieldInfo

from kalshi._contract_map import CONTRACT_MAP, WS_CONTRACT_MAP, ContractEntry
from tests._contract_support import (
    EXCLUSIONS,
    METHOD_ENDPOINT_MAP,
    Exclusion,
    MethodEndpointEntry,
    _resolve_path_params,
    _resolve_request_body_schema,
)

SPEC_FILE = Path(__file__).parent.parent / "specs" / "openapi.yaml"


# ---------------------------------------------------------------------------
# Infrastructure tests
# ---------------------------------------------------------------------------


class TestContractSupportInfra:
    def test_exclusion_requires_reason(self) -> None:
        import dataclasses

        with pytest.raises(TypeError):
            Exclusion()  # type: ignore[call-arg]

        e = Exclusion(reason="because", kind="wire_normalization")
        assert e.reason == "because"
        assert e.kind == "wire_normalization"
        assert dataclasses.is_dataclass(e)

    def test_exclusions_bootstrap_has_cursor_entries(self) -> None:
        """Every paginator method must have a matching cursor exclusion.

        Derives the expected set from METHOD_ENDPOINT_MAP so adding a new
        ``*_all`` / ``list_all_*`` paginator method fails this test with a
        pointed error rather than a stale hardcoded count mismatch.
        """
        cursor_keys = {k for k in EXCLUSIONS if k[1] == "cursor"}
        paginator_methods = {
            e.sdk_method
            for e in METHOD_ENDPOINT_MAP
            if e.sdk_method.endswith("_all") or "list_all_" in e.sdk_method
        }
        covered = {k[0] for k in cursor_keys}
        assert covered == paginator_methods, (
            "Cursor exclusions out of sync with METHOD_ENDPOINT_MAP paginators. "
            f"Missing exclusions for: {sorted(paginator_methods - covered)}. "
            f"Orphaned cursor exclusions: {sorted(covered - paginator_methods)}."
        )
        for key in cursor_keys:
            assert EXCLUSIONS[key].kind == "paginator_handled"

    def test_exclusions_bootstrap_has_create_order_request_entries(self) -> None:
        create_keys = [k for k in EXCLUSIONS if k[0] == "kalshi.models.orders.CreateOrderRequest"]
        field_names = {k[1] for k in create_keys}
        assert {"yes_price", "no_price", "sell_position_floor"} <= field_names

    def test_method_endpoint_entry_has_request_body_schema(self) -> None:
        entry = MethodEndpointEntry(
            sdk_method="x",
            http_method="GET",
            path_template="/y",
        )
        assert entry.request_body_schema is None

        entry2 = MethodEndpointEntry(
            sdk_method="x",
            http_method="POST",
            path_template="/y",
            request_body_schema="#/components/schemas/Foo",
        )
        assert entry2.request_body_schema == "#/components/schemas/Foo"

    def test_resolve_request_body_schema_returns_none_for_get(self) -> None:
        spec: dict[str, Any] = {
            "paths": {
                "/markets": {
                    "get": {"parameters": []},
                },
            },
        }
        assert _resolve_request_body_schema(spec, "/markets", "GET") is None

    def test_resolve_request_body_schema_resolves_ref(self) -> None:
        spec = {
            "paths": {
                "/portfolio/orders": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Foo",
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "components": {
                "schemas": {
                    "Foo": {
                        "type": "object",
                        "properties": {"a": {"type": "string"}},
                    },
                },
            },
        }
        result = _resolve_request_body_schema(spec, "/portfolio/orders", "POST")
        assert result is not None
        assert "a" in result["properties"]

    def test_resolve_request_body_schema_inline_schema(self) -> None:
        spec = {
            "paths": {
                "/x": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"b": {"type": "integer"}},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        result = _resolve_request_body_schema(spec, "/x", "POST")
        assert result is not None
        assert "b" in result["properties"]

    def test_resolve_request_body_schema_delete_with_body(self) -> None:
        """DELETE operations with a requestBody (Kalshi's batch_cancel pattern)
        must resolve just like POST/PUT. Locks in the HTTP-method-agnostic
        behavior so ``TestRequestBodyDrift`` actually covers ``batch_cancel``.
        """
        spec = {
            "paths": {
                "/portfolio/orders/batched": {
                    "delete": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Bar",
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "components": {
                "schemas": {
                    "Bar": {
                        "type": "object",
                        "properties": {"orders": {"type": "array"}},
                    },
                },
            },
        }
        result = _resolve_request_body_schema(
            spec,
            "/portfolio/orders/batched",
            "DELETE",
        )
        assert result is not None
        assert "orders" in result["properties"]

    def test_batch_cancel_body_drift_is_actually_exercised(self) -> None:
        """Live check: ``batch_cancel`` is present in METHOD_ENDPOINT_MAP with
        a body schema ref, and the real OpenAPI spec's DELETE operation
        resolves to a non-empty schema. Without this, TestRequestBodyDrift
        could silently vacuum up a None schema and skip drift checks.
        """
        entries = [
            e
            for e in METHOD_ENDPOINT_MAP
            if e.http_method == "DELETE" and e.request_body_schema is not None
        ]
        assert entries, "Expected at least one DELETE entry with a body schema"

        spec = _load_spec()
        for entry in entries:
            resolved = _resolve_request_body_schema(
                spec,
                entry.path_template,
                entry.http_method,
            )
            assert resolved is not None, (
                f"DELETE {entry.path_template} has request_body_schema "
                f"{entry.request_body_schema!r} registered but the spec "
                f"resolves to None. Drift test would silently pass."
            )
            assert resolved.get("properties"), (
                f"DELETE {entry.path_template} resolved to an empty schema."
            )


# ---------------------------------------------------------------------------
# Spec helpers
# ---------------------------------------------------------------------------


def _load_spec() -> dict[str, Any]:
    """Load and return the OpenAPI spec."""
    if yaml is None:
        pytest.skip("pyyaml not installed. Run: uv sync --dev")
    if not SPEC_FILE.exists():
        pytest.skip("OpenAPI spec not found. Run: uv run python scripts/sync_spec.py")
    with open(SPEC_FILE) as f:
        return yaml.safe_load(f)


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolve a $ref pointer in the OpenAPI spec."""
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        node = node[part]
    return node  # type: ignore[return-value]


def _resolve_schema(spec: dict[str, Any], schema_name: str) -> dict[str, Any]:
    """Resolve a schema by name, supporting dotted-path syntax for inline schemas.

    Plain ``"Foo"`` looks up ``components.schemas.Foo``.
    Dotted ``"Foo.bar.items"`` walks ``components.schemas.Foo.properties.bar.items``
    where each segment after the first navigates ``properties[segment]`` unless the
    segment is the literal ``"items"`` (in which case it descends into the array
    items schema). Used to address inline object schemas that the spec doesn't
    name at the top level — e.g., the per-entry shapes inside ``Batch*Orders*``
    response wrappers.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    head, *rest = schema_name.split(".")
    node = schemas.get(head)
    if node is None:
        pytest.fail(f"Schema '{head}' not found in OpenAPI spec")
    for segment in rest:
        if "$ref" in node:
            node = _resolve_ref(spec, node["$ref"])
        if segment == "items":
            if "items" not in node:
                pytest.fail(
                    f"Schema path '{schema_name}' failed at segment {segment!r}: "
                    f"parent has no 'items'"
                )
            node = node["items"]
        else:
            properties = node.get("properties", {})
            if segment not in properties:
                pytest.fail(
                    f"Schema path '{schema_name}' failed at segment {segment!r}: "
                    f"not in parent properties"
                )
            node = properties[segment]
    if "$ref" in node:
        node = _resolve_ref(spec, node["$ref"])
    return node


def _get_schema_fields(spec: dict[str, Any], schema_name: str) -> dict[str, dict[str, Any]]:
    """Extract field names and their properties from a spec schema.

    Returns ``{}`` for schemas whose top-level type is not ``object`` (e.g., the
    positional ``PriceLevelDollarsCountFp`` 2-tuple), since they have no
    field-by-field shape to compare.
    """
    schema = _resolve_schema(spec, schema_name)

    # Handle allOf composition (merge all sub-schemas)
    if "allOf" in schema:
        merged: dict[str, dict[str, Any]] = {}
        for sub in schema["allOf"]:
            if "$ref" in sub:
                sub = _resolve_ref(spec, sub["$ref"])
            merged.update(sub.get("properties", {}))
        return merged

    # Handle oneOf/anyOf (union of all possible fields across variants)
    for key in ("oneOf", "anyOf"):
        if key in schema:
            merged = {}
            for sub in schema[key]:
                if "$ref" in sub:
                    sub = _resolve_ref(spec, sub["$ref"])
                merged.update(sub.get("properties", {}))
            merged.update(schema.get("properties", {}))
            return merged

    return schema.get("properties", {})


def _get_required_fields(spec: dict[str, Any], schema_name: str) -> set[str]:
    """Extract required field names from a spec schema, merging from allOf/oneOf/anyOf.

    Supports the same dotted-path syntax as :func:`_get_schema_fields`. Returns
    an empty set for non-object schemas.
    """
    schema = _resolve_schema(spec, schema_name)

    required: set[str] = set(schema.get("required", []))

    # Merge required from allOf sub-schemas
    if "allOf" in schema:
        for sub in schema["allOf"]:
            if "$ref" in sub:
                sub = _resolve_ref(spec, sub["$ref"])
            required.update(sub.get("required", []))

    # For oneOf/anyOf: only include fields required in ALL variants (intersection).
    # A field required in variant A but absent from variant B is not universally required.
    for key in ("oneOf", "anyOf"):
        if key in schema:
            variant_required_sets: list[set[str]] = []
            for sub in schema[key]:
                if "$ref" in sub:
                    sub = _resolve_ref(spec, sub["$ref"])
                variant_required_sets.append(set(sub.get("required", [])))
            if variant_required_sets:
                required.update(set.intersection(*variant_required_sets))

    return required


# ---------------------------------------------------------------------------
# SDK model helpers
# ---------------------------------------------------------------------------


def _get_sdk_model_class(model_path: str) -> type[PydanticBase]:
    """Import and return the SDK model class."""
    module_path, class_name = model_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)  # type: ignore[return-value]


def _extract_spec_names(field_info: FieldInfo, field_name: str) -> set[str]:
    """Extract all spec-side field names this SDK field accepts or produces.

    Auto-extracts from validation_alias (AliasChoices) and serialization_alias.
    Returns a set of possible spec wire names for this field.
    """
    names: set[str] = {field_name}

    # validation_alias: AliasChoices("yes_bid_dollars", "yes_bid")
    if isinstance(field_info.validation_alias, AliasChoices):
        for choice in field_info.validation_alias.choices:
            if isinstance(choice, str):
                names.add(choice)
    elif isinstance(field_info.validation_alias, str):
        names.add(field_info.validation_alias)

    # serialization_alias: "yes_price_dollars"
    if isinstance(field_info.serialization_alias, str):
        names.add(field_info.serialization_alias)

    return names


def _build_spec_to_sdk_map(
    model_class: type[PydanticBase],
) -> dict[str, str]:
    """Build a reverse map: spec_field_name → sdk_field_name.

    Uses the model's own alias metadata. No external manifest needed.
    """
    reverse: dict[str, str] = {}
    for sdk_name, field_info in model_class.model_fields.items():
        for spec_name in _extract_spec_names(field_info, sdk_name):
            reverse[spec_name] = sdk_name
    return reverse


# ---------------------------------------------------------------------------
# Drift classification
# ---------------------------------------------------------------------------


def _classify_drift(
    entry: ContractEntry,
    spec: dict[str, Any],
    spec_fields: dict[str, dict[str, Any]],
    model_class: type[PydanticBase],
) -> tuple[list[str], list[str]]:
    """Compare spec fields against SDK model fields.

    Returns (additive_issues, required_issues).
    Both are warnings, not failures (SDK is intentionally permissive).

    Per-field skips are honored in this order:
      1. ``entry.ignored_fields`` — per-contract-entry allowlist (legacy).
      2. ``EXCLUSIONS[(entry.sdk_model, field_name)]`` — typed, reasoned
         allowlist shared with the request-side drift checks (#157).
    """
    additive: list[str] = []
    required_issues: list[str] = []

    reverse_map = _build_spec_to_sdk_map(model_class)

    # Check every spec field has a corresponding SDK field
    for spec_field_name in spec_fields:
        if spec_field_name in entry.ignored_fields:
            continue
        if (entry.sdk_model, spec_field_name) in EXCLUSIONS:
            continue
        if spec_field_name not in reverse_map:
            additive.append(f"Spec field '{spec_field_name}' has no SDK mapping")

    # Check required fields in spec vs SDK (warning, not failure)
    required_fields = _get_required_fields(spec, entry.spec_schema)
    for req_field in required_fields:
        if req_field in entry.ignored_fields:
            continue
        if (entry.sdk_model, req_field) in EXCLUSIONS:
            continue
        sdk_name = reverse_map.get(req_field)
        if sdk_name and sdk_name in model_class.model_fields:
            field_info = model_class.model_fields[sdk_name]
            if not field_info.is_required():
                required_issues.append(
                    f"Spec requires '{req_field}' but SDK field '{sdk_name}' is optional"
                )

    return additive, required_issues


# ---------------------------------------------------------------------------
# AsyncAPI spec helpers (WebSocket models)
# ---------------------------------------------------------------------------

ASYNCAPI_FILE = Path(__file__).parent.parent / "specs" / "asyncapi.yaml"


def _load_asyncapi_spec() -> dict[str, Any]:
    """Load and return the AsyncAPI spec."""
    if yaml is None:
        pytest.skip("pyyaml not installed. Run: uv sync --dev")
    if not ASYNCAPI_FILE.exists():
        pytest.skip("AsyncAPI spec not found. Run: uv run python scripts/sync_spec.py")
    with open(ASYNCAPI_FILE) as f:
        return yaml.safe_load(f)


def _get_ws_msg_fields(spec: dict[str, Any], schema_name: str) -> dict[str, dict[str, Any]]:
    """Extract msg sub-object fields from an AsyncAPI payload schema.

    AsyncAPI payloads nest data fields under .properties.msg.properties,
    unlike OpenAPI which uses .properties directly.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    schema = schemas.get(schema_name)
    if schema is None:
        pytest.fail(f"Schema '{schema_name}' not found in AsyncAPI spec")

    # Handle allOf (e.g., multivariateMarketLifecyclePayload)
    if "allOf" in schema:
        merged: dict[str, dict[str, Any]] = {}
        for sub in schema["allOf"]:
            if "$ref" in sub:
                sub = _resolve_ref(spec, sub["$ref"])
            msg = sub.get("properties", {}).get("msg", {})
            merged.update(msg.get("properties", {}))
        return merged

    msg = schema.get("properties", {}).get("msg", {})
    return msg.get("properties", {})


def _get_ws_required_fields(spec: dict[str, Any], schema_name: str) -> set[str]:
    """Extract required fields from the msg sub-object.

    Handles allOf composition by merging required sets from all sub-schemas.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    schema = schemas.get(schema_name, {})

    # Handle allOf
    if "allOf" in schema:
        required: set[str] = set()
        for sub in schema["allOf"]:
            if "$ref" in sub:
                sub = _resolve_ref(spec, sub["$ref"])
            msg = sub.get("properties", {}).get("msg", {})
            required.update(msg.get("required", []))
        return required

    msg = schema.get("properties", {}).get("msg", {})
    return set(msg.get("required", []))


def _unwrap_annotation(ann: Any) -> Any:
    """Strip Optional/Union/Annotated wrappers, return the innermost concrete type.

    Returns the generic alias (e.g. ``list[str]``) or the plain class
    (e.g. ``int``, ``Decimal``). Suitable for kind-classification below.
    """
    # Annotated[X, ...] → X (DollarDecimal is Annotated[Decimal, ...]).
    # typing.get_args is the public API — __origin__ is a dunder implementation
    # detail that can drift across Python versions and Pydantic internals.
    if hasattr(ann, "__metadata__"):
        args = typing.get_args(ann)
        if args:
            return _unwrap_annotation(args[0])

    # Union / X | None → first non-None arg (one-level unwrap).
    # typing.get_origin does NOT normalize the two union syntaxes:
    #   - typing.Union[X, None]  → get_origin returns typing.Union
    #   - PEP 604 `X | None`     → get_origin returns types.UnionType
    # The codebase uses PEP 604 pervasively, but legacy annotations exist in
    # a few places, so both paths matter. isinstance(ann, UnionType) catches
    # the PEP 604 case directly because the runtime value itself IS a
    # UnionType instance.
    origin = typing.get_origin(ann)
    if origin is typing.Union or isinstance(ann, UnionType):
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        if len(args) == 1:
            return _unwrap_annotation(args[0])
    return ann


def _sdk_type_kind(ann: Any) -> str:
    """Classify a Pydantic field annotation into a spec-aligned kind label.

    Returns: ``'int'``, ``'str'``, ``'bool'``, ``'decimal'``, ``'list[<kind>]'``,
    or ``'unknown'``. Decimals (DollarDecimal, FixedPointCount) count as
    ``'decimal'`` — a Decimal-typed field is considered compatible with a
    spec-declared dollar string.
    """
    base = _unwrap_annotation(ann)
    if base is int:
        return "int"
    if base is str:
        return "str"
    if base is bool:
        return "bool"
    if base is Decimal:
        return "decimal"
    origin = typing.get_origin(base)
    if origin is list:
        args = typing.get_args(base)
        if args:
            return f"list[{_sdk_type_kind(args[0])}]"
        return "list[unknown]"
    if origin is tuple:
        args = typing.get_args(base)
        if args:
            inner = ",".join(_sdk_type_kind(a) for a in args if a is not Ellipsis)
            return f"tuple[{inner}]"
        return "tuple[unknown]"
    return "unknown"


def _spec_property_kind(spec_prop: dict[str, Any]) -> str:
    """Return the expected Python kind label for a JSON-schema property.

    Mirrors ``_sdk_type_kind`` so the two can be compared directly.
    """
    t = spec_prop.get("type")
    if t == "string":
        return "str"
    if t == "integer":
        return "int"
    if t == "boolean":
        return "bool"
    if t == "number":
        return "decimal"
    if t == "array":
        items = spec_prop.get("items") or {}
        return f"list[{_spec_property_kind(items)}]"
    return "unknown"


def _ws_field_type_violations(
    sdk_name: str,
    sdk_ann: Any,
    spec_name: str,
    spec_prop: dict[str, Any],
) -> list[str]:
    """Return human-readable type-drift violations for a single WS field.

    Targets the specific class of bug surfaced during v0.14.0 integration
    testing: ``_dollars``-aliased string fields on the wire are typed as
    ``int`` in the SDK, and ISO ``date-time`` fields are typed as ``int``.
    Both cause pydantic to reject real demo frames at ``model_validate``.
    """
    sdk_kind = _sdk_type_kind(sdk_ann)
    spec_type = spec_prop.get("type")
    spec_format = spec_prop.get("format")
    problems: list[str] = []

    # Rule 1: spec string with _dollars suffix (dollar-value wire) must be
    # DollarDecimal (decimal) or str on the SDK. An int-typed SDK field
    # rejects the wire string "0.0200".
    if (
        spec_type == "string"
        and spec_name.endswith("_dollars")
        and sdk_kind not in ("decimal", "str")
    ):
        problems.append(
            f"{sdk_name!r}: spec '{spec_name}' is string (dollars), "
            f"SDK typed as {sdk_kind}. Use DollarDecimal."
        )

    # Rule 2: spec string with format=date-time (ISO timestamp) must be str
    # on the SDK. An int-typed SDK field rejects the wire string
    # "2026-04-19T18:43:37.662364Z".
    if spec_type == "string" and spec_format == "date-time" and sdk_kind not in ("str",):
        problems.append(
            f"{sdk_name!r}: spec '{spec_name}' is string (date-time), "
            f"SDK typed as {sdk_kind}. Use str."
        )

    # Rule 3: spec array of strings (e.g. orderbook snapshot rows of
    # [price_dollars, count_fp]) must be list-of-string on SDK, not
    # list-of-int.
    if spec_type == "array":
        expected = _spec_property_kind(spec_prop)
        if (
            sdk_kind.startswith("list[")
            and expected.startswith("list[")
            and sdk_kind != expected
            and "int" in sdk_kind
            and "str" in expected
        ):
            problems.append(
                f"{sdk_name!r}: spec '{spec_name}' is {expected}, SDK typed as {sdk_kind}."
            )

    return problems


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSpecDrift:
    """Verify hand-written SDK models match the OpenAPI spec."""

    spec: dict[str, Any]

    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.spec = _load_spec()

    @pytest.mark.parametrize(
        "entry",
        CONTRACT_MAP,
        ids=[e.sdk_model.rsplit(".", 1)[1] for e in CONTRACT_MAP],
    )
    def test_additive_drift(self, entry: ContractEntry) -> None:
        """Warn about spec fields not present in SDK models."""
        spec_fields = _get_schema_fields(self.spec, entry.spec_schema)
        model_class = _get_sdk_model_class(entry.sdk_model)
        additive, _ = _classify_drift(entry, self.spec, spec_fields, model_class)
        if additive:
            pytest.fail(
                f"Additive drift in {entry.sdk_model}:\n" + "\n".join(f"  - {a}" for a in additive),
            )

    @pytest.mark.parametrize(
        "entry",
        CONTRACT_MAP,
        ids=[e.sdk_model.rsplit(".", 1)[1] for e in CONTRACT_MAP],
    )
    def test_required_drift(self, entry: ContractEntry) -> None:
        """Fail when SDK fields are optional but spec marks them required.

        Hard-fail since #172. Was warn-only while the SDK kept ~134 fields
        Optional[T] | None against spec's required: true. The deviation is
        either resolved (drop None default) or recorded in EXCLUSIONS with
        kind='server_omits_despite_required' citing a demo+prod observation.
        """
        spec_fields = _get_schema_fields(self.spec, entry.spec_schema)
        model_class = _get_sdk_model_class(entry.sdk_model)
        _, required_issues = _classify_drift(entry, self.spec, spec_fields, model_class)
        if required_issues:
            pytest.fail(
                f"Required drift in {entry.sdk_model}:\n"
                + "\n".join(f"  - {r}" for r in required_issues)
            )

    def test_schema_coverage(self) -> None:
        """Every mapped schema must resolve (supports dotted-path syntax)."""
        for entry in CONTRACT_MAP:
            # _resolve_schema fails the test internally if the path doesn't resolve.
            _resolve_schema(self.spec, entry.spec_schema)

    def test_contract_map_completeness(self) -> None:
        """Fail if any SDK model under ``kalshi.models.*`` lacks a ``CONTRACT_MAP`` entry.

        Hard-fail since #171. Was warn-only while ~42 sub-models / V2 family /
        internal containers were unmapped. Now every Pydantic class in the
        listed modules MUST have a ``ContractEntry`` (use the dotted-path
        ``Parent.field.items`` syntax for inline schemas; see notes in
        ``kalshi/_contract_map.py``).
        """
        mapped_models = {e.sdk_model for e in CONTRACT_MAP}
        unmapped: list[str] = []

        for module_name in (
            "markets",
            "orders",
            "events",
            "exchange",
            "portfolio",
            "historical",
            "series",
            "multivariate",
        ):
            module = importlib.import_module(f"kalshi.models.{module_name}")
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, PydanticBase)
                    and obj is not PydanticBase
                    and obj.__module__ == module.__name__
                ):
                    fqn = f"kalshi.models.{module_name}.{name}"
                    if fqn not in mapped_models:
                        unmapped.append(fqn)

        if unmapped:
            pytest.fail(
                "SDK models without contract map entries:\n"
                + "\n".join(f"  - {m}" for m in unmapped)
            )


# ---------------------------------------------------------------------------
# WS Spec Drift Tests
# ---------------------------------------------------------------------------


class TestWsSpecDrift:
    """Verify WS payload models match the AsyncAPI spec."""

    spec: dict[str, Any]

    # Documented (spec_schema, sdk_default_type) pairs where the SDK intentionally
    # diverges from the AsyncAPI spec. Empty for v0.14.0 -- all three known drifts
    # were resolved by aligning SDK to spec (Tasks 3-5). Future divergences must
    # be added here with an evidence citation in the notes field of the
    # corresponding WS_CONTRACT_MAP entry.
    _DEMO_DIVERGENCE_ALLOWLIST: ClassVar[set[tuple[str, str]]] = set()

    @pytest.fixture(autouse=True, scope="class")
    def _load(self, request: pytest.FixtureRequest) -> None:
        request.cls.spec = _load_asyncapi_spec()

    @pytest.mark.parametrize(
        "entry",
        WS_CONTRACT_MAP,
        ids=[e.sdk_model.rsplit(".", 1)[1] for e in WS_CONTRACT_MAP],
    )
    def test_ws_additive_drift(self, entry: ContractEntry) -> None:
        """Warn about AsyncAPI fields not present in SDK WS models."""
        spec_fields = _get_ws_msg_fields(self.spec, entry.spec_schema)
        model_class = _get_sdk_model_class(entry.sdk_model)
        additive, _ = _classify_drift(entry, self.spec, spec_fields, model_class)
        if additive:
            pytest.fail(
                f"WS additive drift in {entry.sdk_model}:\n"
                + "\n".join(f"  - {a}" for a in additive),
            )

    @pytest.mark.parametrize(
        "entry",
        WS_CONTRACT_MAP,
        ids=[e.sdk_model.rsplit(".", 1)[1] for e in WS_CONTRACT_MAP],
    )
    def test_ws_required_drift(self, entry: ContractEntry) -> None:
        """Fail when SDK WS fields are optional but spec marks them required.

        Hard-fail since #172, matching the REST sibling.
        """
        model_class = _get_sdk_model_class(entry.sdk_model)
        # Use WS-specific required extractor instead of REST _get_required_fields
        ws_required = _get_ws_required_fields(self.spec, entry.spec_schema)
        reverse_map = _build_spec_to_sdk_map(model_class)
        required_issues: list[str] = []
        for req_field in ws_required:
            if req_field in entry.ignored_fields:
                continue
            if (entry.sdk_model, req_field) in EXCLUSIONS:
                continue
            sdk_name = reverse_map.get(req_field)
            if sdk_name and sdk_name in model_class.model_fields:
                field_info = model_class.model_fields[sdk_name]
                if not field_info.is_required():
                    required_issues.append(
                        f"Spec requires '{req_field}' but SDK field '{sdk_name}' is optional"
                    )
        if required_issues:
            pytest.fail(
                f"WS required drift in {entry.sdk_model}:\n"
                + "\n".join(f"  - {r}" for r in required_issues)
            )

    def test_ws_schema_coverage(self) -> None:
        """Every mapped WS schema must exist in the AsyncAPI spec."""
        schemas = self.spec.get("components", {}).get("schemas", {})
        for entry in WS_CONTRACT_MAP:
            assert entry.spec_schema in schemas, (
                f"WS contract map references '{entry.spec_schema}' "
                f"but it doesn't exist in the AsyncAPI spec"
            )

    def test_ws_envelope_type_drift(self) -> None:
        """Warn if spec type const values differ from SDK message envelope type defaults."""
        schemas = self.spec.get("components", {}).get("schemas", {})
        # Collect structured mismatches: (spec_schema, spec_type, sdk_message_name, sdk_type)
        mismatches: list[tuple[str, str, str, str]] = []

        for entry in WS_CONTRACT_MAP:
            schema = schemas.get(entry.spec_schema, {})

            # Extract type const, handling allOf composition
            spec_type: str | None = None
            if "allOf" in schema:
                for sub in schema["allOf"]:
                    if "$ref" in sub:
                        sub = _resolve_ref(self.spec, sub["$ref"])
                    type_prop = sub.get("properties", {}).get("type", {})
                    if "const" in type_prop:
                        spec_type = type_prop["const"]
                        break
            else:
                type_prop = schema.get("properties", {}).get("type", {})
                spec_type = type_prop.get("const")

            if spec_type is None:
                continue

            # Find the Message class that wraps this Payload as its msg field
            model_class = _get_sdk_model_class(entry.sdk_model)
            module_path = entry.sdk_model.rsplit(".", 1)[0]
            module = importlib.import_module(module_path)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, PydanticBase)
                    and obj is not PydanticBase
                    and name.endswith("Message")
                    and "msg" in obj.model_fields
                ):
                    msg_field = obj.model_fields["msg"]
                    if msg_field.annotation == model_class:
                        sdk_type_field = obj.model_fields.get("type")
                        if sdk_type_field and sdk_type_field.default != spec_type:
                            mismatches.append(
                                (entry.spec_schema, spec_type, name, str(sdk_type_field.default))
                            )

        # Filter out documented divergences (Branch-B style intentional exceptions).
        # Allowlist compares tuples directly, so the assertion output format can
        # change without silently breaking the filter.
        unexpected = [m for m in mismatches if (m[0], m[3]) not in self._DEMO_DIVERGENCE_ALLOWLIST]

        assert not unexpected, (
            "WS envelope type drift (not on documented divergence allowlist):\n"
            + "\n".join(
                f"  - {schema}: spec type='{st}', SDK {cls}.type='{sdk}'"
                for schema, st, cls, sdk in unexpected
            )
        )

    @pytest.mark.parametrize(
        "entry",
        WS_CONTRACT_MAP,
        ids=[e.sdk_model.rsplit(".", 1)[1] for e in WS_CONTRACT_MAP],
    )
    def test_ws_payload_field_type_drift(self, entry: ContractEntry) -> None:
        """Hard-fail if SDK field type doesn't match AsyncAPI wire type.

        Targets the class of bug surfaced during v0.14.0 Task 11 integration
        tests: SDK models type ``_dollars``-aliased fields as ``int`` but demo
        sends dollar-decimal strings (``"0.0200"``), and types ``ts`` as int
        where the spec says ``string`` with ``format: date-time``. Both cases
        cause pydantic to reject real frames at ``model_validate`` time, which
        silently drops every matching message.

        A drift flagged here would have blocked the v0.14.0 envelope-only PR.
        """
        spec_fields = _get_ws_msg_fields(self.spec, entry.spec_schema)
        model_class = _get_sdk_model_class(entry.sdk_model)
        reverse_map = _build_spec_to_sdk_map(model_class)

        violations: list[str] = []
        for spec_name, spec_prop in spec_fields.items():
            if spec_name in entry.ignored_fields:
                continue
            sdk_name = reverse_map.get(spec_name)
            if sdk_name is None or sdk_name not in model_class.model_fields:
                continue
            field_info = model_class.model_fields[sdk_name]
            violations.extend(
                _ws_field_type_violations(
                    sdk_name,
                    field_info.annotation,
                    spec_name,
                    spec_prop,
                )
            )

        assert not violations, f"WS payload field type drift in {entry.sdk_model}:\n" + "\n".join(
            f"  - {v}" for v in violations
        )

    def test_ws_contract_map_completeness(self) -> None:
        """Warn if WS payload models exist without contract map entries."""
        mapped_models = {e.sdk_model for e in WS_CONTRACT_MAP}
        unmapped: list[str] = []

        import pkgutil

        import kalshi.ws.models as ws_pkg

        for mod_info in pkgutil.iter_modules(ws_pkg.__path__):
            if mod_info.name.startswith("_"):
                continue
            module = importlib.import_module(f"kalshi.ws.models.{mod_info.name}")
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, PydanticBase)
                    and obj is not PydanticBase
                    and obj.__module__ == module.__name__
                    and name.endswith("Payload")
                ):
                    fqn = f"kalshi.ws.models.{mod_info.name}.{name}"
                    if fqn not in mapped_models:
                        unmapped.append(fqn)

        if unmapped:
            pytest.fail(
                "WS payload models without contract map entries:\n"
                + "\n".join(f"  - {m}" for m in unmapped),
            )


# ---------------------------------------------------------------------------
# Request-side Drift Tests (v0.8.0)
# ---------------------------------------------------------------------------


def _signature_params(sdk_method_fqn: str) -> set[str]:
    """Return the set of keyword parameter names for an SDK method, minus
    ``self``. Resolves the dotted path ``module.Class.method``.

    Uses the rightmost-two-dots split so that FQNs like
    ``kalshi.resources.orders.OrdersResource.create`` resolve as
    module=``kalshi.resources.orders``, class=``OrdersResource``, method=``create``.
    """
    parts = sdk_method_fqn.split(".")
    method = parts[-1]
    cls_name = parts[-2]
    module_name = ".".join(parts[:-2])
    module = importlib.import_module(module_name)
    cls = getattr(module, cls_name)
    func = getattr(cls, method)
    sig = inspect.signature(func)
    return {
        name
        for name, param in sig.parameters.items()
        if name != "self"
        and param.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }


def _path_params_from_template(path_template: str) -> set[str]:
    """Extract ``{name}`` placeholders from a path template."""
    import re

    return set(re.findall(r"\{([^}]+)\}", path_template))


@pytest.mark.parametrize(
    "entry",
    [e for e in METHOD_ENDPOINT_MAP if e.http_method in ("GET", "DELETE")],
    ids=[
        e.sdk_method.rsplit(".", 1)[1]
        for e in METHOD_ENDPOINT_MAP
        if e.http_method in ("GET", "DELETE")
    ],
)
class TestRequestParamDrift:
    """Verify resource method signatures match OpenAPI spec query/path params.

    Parametrized over every GET/DELETE entry in ``METHOD_ENDPOINT_MAP``. For each,
    compares the SDK method's kwarg set (sync + async) to the spec's ``parameters``
    list, modulo the ``EXCLUSIONS`` allowlist.

    Async sibling derived via ``Async<ClassName>`` substitution — one map entry
    drives both sync and async tests. Asserts the async class exists; a missing
    sibling is a bug we want to see immediately.

    Hard-fails via ``pytest.fail``. See the docstring of
    ``tests/_contract_support.py`` for the broader rationale; as of #172/#171
    every contract gate in this file is now hard-fail.
    """

    spec: dict[str, Any]

    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.spec = _load_spec()

    def test_sync_params_match_spec(self, entry: MethodEndpointEntry) -> None:
        self._assert_params_match(entry, async_=False)

    def test_async_params_match_spec(self, entry: MethodEndpointEntry) -> None:
        self._assert_params_match(entry, async_=True)

    def _assert_params_match(
        self,
        entry: MethodEndpointEntry,
        *,
        async_: bool,
    ) -> None:
        sdk_fqn = entry.sdk_method
        if async_:
            parts = sdk_fqn.split(".")
            parts[-2] = f"Async{parts[-2]}"
            sdk_fqn = ".".join(parts)
            # Assert sibling exists
            module_name = ".".join(parts[:-2])
            cls_name = parts[-2]
            module = importlib.import_module(module_name)
            assert hasattr(module, cls_name), f"Missing async sibling {cls_name} in {module_name}"

        sdk_params = _signature_params(sdk_fqn)
        spec_params_list = _resolve_path_params(
            self.spec,
            entry.path_template,
            entry.http_method,
        )
        spec_params = {p["name"] for p in spec_params_list if p.get("in") in ("query", "path")}
        # Spec path params like ``{order_id}`` should appear in the path
        # template placeholders too; union them in so the test catches
        # cases where a spec operation declares a path param that the
        # SDK method signature doesn't accept.
        template_params = _path_params_from_template(entry.path_template)
        spec_params |= template_params

        # EXCLUSIONS is indexed by the SYNC method fqn; async tests reuse
        # the same allowlist entries.
        lookup_fqn = entry.sdk_method

        # ADD drift: spec has it, SDK missing
        missing = spec_params - sdk_params
        missing_unallowed = {p for p in missing if (lookup_fqn, p) not in EXCLUSIONS}
        # REMOVE drift: SDK has it, spec doesn't
        extra = sdk_params - spec_params
        extra_unallowed = {p for p in extra if (lookup_fqn, p) not in EXCLUSIONS}

        errors: list[str] = []
        if missing_unallowed:
            errors.append(f"[ADD drift] spec has params SDK missing: {sorted(missing_unallowed)}")
        if extra_unallowed:
            errors.append(f"[REMOVE drift] SDK has params spec doesn't: {sorted(extra_unallowed)}")
        if errors:
            pytest.fail(
                f"{sdk_fqn} <-> {entry.http_method} {entry.path_template}\n"
                + "\n".join(errors)
                + f"\n(Allowlist via EXCLUSIONS[({lookup_fqn!r}, '...')])"
            )


# ---------------------------------------------------------------------------
# Body Drift Tests (v0.8.0)
# ---------------------------------------------------------------------------


# Registry: spec $ref → SDK request model FQN.
# Update whenever a new POST/PUT/DELETE-with-body endpoint gets a request model.
BODY_MODEL_MAP: dict[str, str] = {
    "#/components/schemas/CreateOrderRequest": ("kalshi.models.orders.CreateOrderRequest"),
    "#/components/schemas/AmendOrderRequest": ("kalshi.models.orders.AmendOrderRequest"),
    "#/components/schemas/DecreaseOrderRequest": ("kalshi.models.orders.DecreaseOrderRequest"),
    "#/components/schemas/BatchCreateOrdersRequest": (
        "kalshi.models.orders.BatchCreateOrdersRequest"
    ),
    "#/components/schemas/BatchCancelOrdersRequest": (
        "kalshi.models.orders.BatchCancelOrdersRequest"
    ),
    "#/components/schemas/CreateOrderV2Request": ("kalshi.models.orders.CreateOrderV2Request"),
    "#/components/schemas/AmendOrderV2Request": ("kalshi.models.orders.AmendOrderV2Request"),
    "#/components/schemas/DecreaseOrderV2Request": ("kalshi.models.orders.DecreaseOrderV2Request"),
    "#/components/schemas/BatchCreateOrdersV2Request": (
        "kalshi.models.orders.BatchCreateOrdersV2Request"
    ),
    "#/components/schemas/BatchCancelOrdersV2Request": (
        "kalshi.models.orders.BatchCancelOrdersV2Request"
    ),
    "#/components/schemas/CreateMarketInMultivariateEventCollectionRequest": (
        "kalshi.models.multivariate.CreateMarketInMultivariateEventCollectionRequest"
    ),
    "#/components/schemas/LookupTickersForMarketInMultivariateEventCollectionRequest": (
        "kalshi.models.multivariate.LookupTickersForMarketInMultivariateEventCollectionRequest"
    ),
    "#/components/schemas/CreateOrderGroupRequest": (
        "kalshi.models.order_groups.CreateOrderGroupRequest"
    ),
    "#/components/schemas/UpdateOrderGroupLimitRequest": (
        "kalshi.models.order_groups.UpdateOrderGroupLimitRequest"
    ),
    "#/components/schemas/CreateRFQRequest": ("kalshi.models.communications.CreateRFQRequest"),
    "#/components/schemas/CreateQuoteRequest": ("kalshi.models.communications.CreateQuoteRequest"),
    "#/components/schemas/AcceptQuoteRequest": ("kalshi.models.communications.AcceptQuoteRequest"),
    "#/components/schemas/ApplySubaccountTransferRequest": (
        "kalshi.models.subaccounts.ApplySubaccountTransferRequest"
    ),
    "#/components/schemas/UpdateSubaccountNettingRequest": (
        "kalshi.models.subaccounts.UpdateSubaccountNettingRequest"
    ),
    "#/components/schemas/CreateApiKeyRequest": ("kalshi.models.api_keys.CreateApiKeyRequest"),
    "#/components/schemas/GenerateApiKeyRequest": ("kalshi.models.api_keys.GenerateApiKeyRequest"),
}


def _get_model_class_from_fqn(fqn: str) -> type[PydanticBase]:
    module_name, _, cls_name = fqn.rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, cls_name)  # type: ignore[no-any-return]


def _model_aliases(model_cls: type[PydanticBase]) -> set[str]:
    """Return the set of WIRE names the model emits — serialization_alias if
    set, else the field name. Compared to spec schema property names by
    ``TestRequestBodyDrift``.

    Top-level only. For nested ``BaseModel`` fields, see
    ``_iter_nested_body_models`` which walks one level deeper.
    """
    names: set[str] = set()
    for field_name, field in model_cls.model_fields.items():
        alias = field.serialization_alias or field_name
        names.add(alias)
    return names


def _extract_nested_basemodel(annotation: Any) -> type[PydanticBase] | None:
    """Return the inner ``BaseModel`` subclass from ``Foo``, ``list[Foo]``,
    ``Foo | None``, etc. ``None`` if the annotation does not wrap a model.

    Only one wrapper level is unwrapped (sufficient for current request body
    shapes: ``list[TickerPair]``, optional fields). Deeper nesting would
    require iterating ``get_args`` recursively — keep simple until needed.
    """
    inner = _unwrap_annotation(annotation)
    # list[X], builtins.list[X], typing.List[X] all resolve to `list` via
    # get_origin on Python 3.9+.
    if typing.get_origin(inner) is list:
        args = typing.get_args(inner)
        if args:
            inner = _unwrap_annotation(args[0])
    if isinstance(inner, type) and issubclass(inner, PydanticBase):
        return inner
    return None


def _iter_nested_body_models(
    model_cls: type[PydanticBase],
    spec_schema: dict[str, Any],
    spec: dict[str, Any],
) -> list[tuple[str, type[PydanticBase], dict[str, Any]]]:
    """Return ``(field_name, nested_model_cls, nested_spec_schema)`` triples
    for top-level fields whose value type is a ``BaseModel`` subclass (or a
    list thereof). Used by ``TestRequestBodyDrift`` to extend drift detection
    one level deeper into nested request bodies (issue #52).

    Resolves the nested spec schema via the property's ``items.$ref`` (array
    form) or ``$ref`` (object form). Properties without a ``$ref`` — scalars,
    inline schemas, ``oneOf`` / ``anyOf`` unions — are intentionally skipped
    here; extending the recursion to them is out of scope for #52.
    """
    spec_props = spec_schema.get("properties", {})
    pairs: list[tuple[str, type[PydanticBase], dict[str, Any]]] = []
    for field_name, field in model_cls.model_fields.items():
        nested_cls = _extract_nested_basemodel(field.annotation)
        if nested_cls is None:
            continue
        wire_name = field.serialization_alias or field_name
        prop = spec_props.get(wire_name)
        if not isinstance(prop, dict):
            continue
        ref: str | None = None
        if prop.get("type") == "array":
            items = prop.get("items", {})
            if isinstance(items, dict):
                ref = items.get("$ref")
        else:
            ref = prop.get("$ref")
        if ref is None:
            continue
        nested_schema = _resolve_ref(spec, ref)
        pairs.append((field_name, nested_cls, nested_schema))
    return pairs


def _check_model_drift(
    *,
    model_cls: type[PydanticBase],
    model_fqn: str,
    spec_schema: dict[str, Any],
    errors: list[str],
    context: str | None = None,
) -> None:
    """Compare SDK model wire names to spec schema properties, append errors.

    Pulled out so ``TestRequestBodyDrift`` can run the same drift check on a
    top-level body model AND on any nested ``BaseModel`` field one level
    down (issue #52). ``context`` prefixes nested-pair errors so the failure
    message points at the parent field that owns the nested model.
    """
    spec_props = set(spec_schema.get("properties", {}).keys())
    sdk_wire_names = _model_aliases(model_cls)

    # ADD drift: spec has property SDK model doesn't emit
    missing = spec_props - sdk_wire_names
    missing_unallowed = {p for p in missing if (model_fqn, p) not in EXCLUSIONS}
    # REMOVE drift: SDK emits wire name spec doesn't have
    extra = sdk_wire_names - spec_props
    extra_unallowed = {p for p in extra if (model_fqn, p) not in EXCLUSIONS}

    prefix = f"[nested {context} -> {model_fqn}] " if context else ""
    if missing_unallowed:
        errors.append(
            f"{prefix}[ADD drift] spec has properties SDK model missing: "
            f"{sorted(missing_unallowed)}"
        )
    if extra_unallowed:
        errors.append(
            f"{prefix}[REMOVE drift] SDK model emits wire names spec doesn't: "
            f"{sorted(extra_unallowed)}"
        )


_BODY_ENTRIES = [e for e in METHOD_ENDPOINT_MAP if e.request_body_schema is not None]


@pytest.mark.parametrize(
    "entry",
    _BODY_ENTRIES,
    ids=[e.sdk_method.rsplit(".", 1)[1] for e in _BODY_ENTRIES],
)
class TestRequestBodyDrift:
    """Verify request body models match OpenAPI spec body schemas.

    Parametrized over POST/PUT/DELETE entries with a ``request_body_schema``
    ref. Compares WIRE NAMES (``serialization_alias`` if set, else field
    name) of the SDK model against the spec body schema's ``properties``
    keys, modulo EXCLUSIONS.

    Hard-fails via ``pytest.fail`` on any drift not covered by the allowlist.
    Runs alongside ``TestRequestParamDrift`` in CI.
    """

    spec: dict[str, Any]

    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.spec = _load_spec()

    def test_body_properties_match_spec(
        self,
        entry: MethodEndpointEntry,
    ) -> None:
        assert entry.request_body_schema is not None
        model_fqn = BODY_MODEL_MAP.get(entry.request_body_schema)
        assert model_fqn is not None, (
            f"No request model registered in BODY_MODEL_MAP for "
            f"{entry.request_body_schema!r}. Add the mapping."
        )
        model_cls = _get_model_class_from_fqn(model_fqn)

        schema = _resolve_request_body_schema(
            self.spec,
            entry.path_template,
            entry.http_method,
        )
        assert schema is not None, (
            f"Spec has no body schema for {entry.http_method} {entry.path_template}"
        )

        errors: list[str] = []
        _check_model_drift(
            model_cls=model_cls,
            model_fqn=model_fqn,
            spec_schema=schema,
            errors=errors,
        )

        # Issue #52: also drift-check nested BaseModel fields (one level deep).
        for field_name, nested_cls, nested_schema in _iter_nested_body_models(
            model_cls,
            schema,
            self.spec,
        ):
            nested_fqn = f"{nested_cls.__module__}.{nested_cls.__qualname__}"
            _check_model_drift(
                model_cls=nested_cls,
                model_fqn=nested_fqn,
                spec_schema=nested_schema,
                errors=errors,
                context=f"{model_fqn}.{field_name}",
            )

        if errors:
            pytest.fail(f"{model_fqn} <-> {entry.request_body_schema}\n" + "\n".join(errors))


def test_exclusion_map_is_current() -> None:
    """Every EXCLUSIONS entry must describe real drift.

    If an entry references a spec-side key that is no longer in the spec's
    properties, or a SDK-side key the SDK now implements, the entry is
    stale. Stale entries give false confidence that a deviation is
    intentional — prevent that here.
    """
    spec = _load_spec()
    # Lazy-loaded on first WS-keyed exclusion (avoids parsing the AsyncAPI
    # YAML when no WS entry needs it; reused across all WS entries when one
    # does — currently exercised live by ``TickerPayload.time``).
    ws_spec: dict[str, Any] | None = None
    stale: list[str] = []

    for (fqn, name), excl in EXCLUSIONS.items():
        # Case 1: model-keyed exclusion. The FQN may belong to a request body
        # (``BODY_MODEL_MAP``), a REST response model (``CONTRACT_MAP``), a WS
        # payload (``WS_CONTRACT_MAP``), or several of these at once — e.g.
        # ``CreateOrderRequest`` is both a request body and a response schema.
        # ``name`` must appear in at least one of the spec sources, and the
        # SDK model must NOT emit it as a wire alias.
        if fqn.startswith("kalshi.models.") or fqn.startswith("kalshi.ws.models."):
            spec_sources: list[tuple[str, dict[str, Any]]] = []

            # Source 1: request body via BODY_MODEL_MAP + METHOD_ENDPOINT_MAP
            spec_ref = next(
                (ref for ref, m in BODY_MODEL_MAP.items() if m == fqn),
                None,
            )
            if spec_ref is not None:
                body_schema = None
                for e in METHOD_ENDPOINT_MAP:
                    if e.request_body_schema == spec_ref:
                        body_schema = _resolve_request_body_schema(
                            spec,
                            e.path_template,
                            e.http_method,
                        )
                        break
                if body_schema is None:
                    # METHOD_ENDPOINT_MAP / BODY_MODEL_MAP inconsistency is a
                    # real bug; surface it, but still try CONTRACT_MAP and
                    # WS_CONTRACT_MAP so a shared model isn't falsely flagged
                    # as unknown when one of its other sources would resolve.
                    stale.append(
                        f"EXCLUSIONS[{(fqn, name)}] references schema {spec_ref} "
                        f"not reachable via METHOD_ENDPOINT_MAP"
                    )
                else:
                    spec_sources.append(
                        (f"request body {spec_ref}", body_schema.get("properties", {}))
                    )

            # Source 2: REST response model via CONTRACT_MAP
            for c_entry in CONTRACT_MAP:
                if c_entry.sdk_model == fqn:
                    spec_sources.append(
                        (
                            f"response schema {c_entry.spec_schema}",
                            _get_schema_fields(spec, c_entry.spec_schema),
                        )
                    )
                    break

            # Source 3: WS payload model via WS_CONTRACT_MAP
            for w_entry in WS_CONTRACT_MAP:
                if w_entry.sdk_model == fqn:
                    if ws_spec is None:
                        ws_spec = _load_asyncapi_spec()
                    spec_sources.append(
                        (
                            f"WS schema {w_entry.spec_schema}",
                            _get_ws_msg_fields(ws_spec, w_entry.spec_schema),
                        )
                    )
                    break

            if not spec_sources:
                stale.append(
                    f"EXCLUSIONS[{(fqn, name)}] references unknown model {fqn} "
                    f"(not in BODY_MODEL_MAP, CONTRACT_MAP, or WS_CONTRACT_MAP); "
                    f"reason={excl.reason!r}"
                )
                continue

            if not any(name in props for _label, props in spec_sources):
                source_list = ", ".join(label for label, _ in spec_sources)
                stale.append(
                    f"EXCLUSIONS[{(fqn, name)}] claims spec has {name!r} on "
                    f"{fqn}, but it is absent from every spec source "
                    f"({source_list}) — entry is stale. reason={excl.reason!r}"
                )

            model_cls = _get_model_class_from_fqn(fqn)
            if name in _model_aliases(model_cls):
                stale.append(
                    f"EXCLUSIONS[{(fqn, name)}] claims SDK excludes {name!r} "
                    f"from {fqn}, but the model DOES emit it — entry is stale."
                )

        # Case 2: resource-method exclusion keyed on resource FQN
        elif fqn.startswith("kalshi.resources."):
            try:
                sdk_params = _signature_params(fqn)
            except (ImportError, AttributeError):
                stale.append(
                    f"EXCLUSIONS[{(fqn, name)}] references unknown method "
                    f"{fqn}; reason={excl.reason!r}"
                )
                continue
            # For resource-method exclusions, 'name' is the param name the SDK
            # should NOT have. If sdk_params DOES contain it, the entry is
            # stale — UNLESS the exclusion documents a deliberate kwarg shape
            # mismatch (body param like batch_cancel's 'orders', or a renamed
            # kwarg like 'milestone_type' for spec's 'type'), in which case the
            # kwarg legitimately exists in the signature. Distinguish by the
            # typed ``kind`` field (issue #51).
            sig_mismatch_kinds = {
                "body_param",
                "wire_normalization",
                "kwarg_rename",
                "client_only",
            }
            allowed_in_sig = excl.kind in sig_mismatch_kinds
            if name in sdk_params and not allowed_in_sig:
                stale.append(
                    f"EXCLUSIONS[{(fqn, name)}] claims SDK omits {name!r} from "
                    f"{fqn}, but the method DOES accept it as a kwarg — "
                    f"entry is stale. reason={excl.reason!r}"
                )

        else:
            stale.append(
                f"EXCLUSIONS[{(fqn, name)}] has unexpected FQN prefix; "
                f"expected kalshi.models.*, kalshi.ws.models.*, or "
                f"kalshi.resources.*"
            )

    if stale:
        pytest.fail("\n".join(stale))


def test_nested_body_drift_detects_phantom_field_on_nested_model() -> None:
    """Regression for issue #52: prove ``_check_model_drift`` catches a
    phantom field on a nested ``BaseModel`` reached via ``_iter_nested_body_models``.

    Constructs a one-off Pydantic model that wraps a ``TickerPair``-shaped
    nested model with an extra ``ghost_field`` not in the spec, then asserts
    the drift check reports it. This locks in the nested-recursion behavior
    introduced by issue #52 — if a future refactor accidentally drops the
    recursion, this test fails loudly instead of silently letting nested
    drift slip through.
    """
    from pydantic import create_model

    # Phantom nested model: real spec ``TickerPair`` plus ``ghost_field``.
    phantom_nested = create_model(
        "_PhantomTickerPair",
        market_ticker=(str, ...),
        event_ticker=(str, ...),
        side=(str, ...),
        ghost_field=(str, "spook"),
    )
    # Wrapping model that places the phantom in ``selected_markets`` so it
    # is reached the same way ``CreateMarketIn...Request`` reaches TickerPair.
    phantom_parent = create_model(
        "_PhantomCreateMarketRequest",
        selected_markets=(list[phantom_nested], ...),  # type: ignore[valid-type]
    )

    spec = _load_spec()
    # Real spec schema for the parent — we drift-check the phantom model
    # against it. The phantom nested model differs from spec TickerPair by
    # exactly one field (``ghost_field``).
    parent_schema = spec["components"]["schemas"][
        "CreateMarketInMultivariateEventCollectionRequest"
    ]

    nested_pairs = _iter_nested_body_models(phantom_parent, parent_schema, spec)
    assert nested_pairs, (
        "Expected _iter_nested_body_models to surface the nested model from "
        "selected_markets: list[_PhantomTickerPair] — regression in nested "
        "model traversal."
    )

    errors: list[str] = []
    for field_name, nested_cls, nested_schema in nested_pairs:
        _check_model_drift(
            model_cls=nested_cls,
            model_fqn="tests.test_contracts._PhantomTickerPair",
            spec_schema=nested_schema,
            errors=errors,
            context=f"_PhantomCreateMarketRequest.{field_name}",
        )

    assert any("ghost_field" in e for e in errors), (
        "Nested drift check failed to surface the phantom 'ghost_field' on "
        "the nested model. _check_model_drift / _iter_nested_body_models is "
        "no longer recursing into nested BaseModel fields. errors=" + repr(errors)
    )
