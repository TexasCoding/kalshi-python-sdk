"""Contract tests: verify hand-written SDK models match OpenAPI spec schemas.

Drift detection:
- Additive drift (spec has fields SDK doesn't): WARNING
- Required mismatch (spec required, SDK optional): WARNING (SDK is intentionally permissive)
- Missing schema in spec: FAILURE
- Unmapped SDK models: WARNING
"""

from __future__ import annotations

import importlib
import inspect
import warnings
from pathlib import Path
from typing import Any

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

        e = Exclusion(reason="because")
        assert e.reason == "because"
        assert dataclasses.is_dataclass(e)

    def test_exclusions_bootstrap_has_cursor_entries(self) -> None:
        """Every paginator method must have a matching cursor exclusion.

        Derives the expected set from METHOD_ENDPOINT_MAP so adding a new
        ``*_all`` / ``list_all_*`` paginator method fails this test with a
        pointed error rather than a stale hardcoded count mismatch.
        """
        cursor_keys = {k for k in EXCLUSIONS if k[1] == "cursor"}
        paginator_methods = {
            e.sdk_method for e in METHOD_ENDPOINT_MAP
            if e.sdk_method.endswith("_all") or "list_all_" in e.sdk_method
        }
        covered = {k[0] for k in cursor_keys}
        assert covered == paginator_methods, (
            "Cursor exclusions out of sync with METHOD_ENDPOINT_MAP paginators. "
            f"Missing exclusions for: {sorted(paginator_methods - covered)}. "
            f"Orphaned cursor exclusions: {sorted(covered - paginator_methods)}."
        )
        for key in cursor_keys:
            assert "paginator" in EXCLUSIONS[key].reason.lower()

    def test_exclusions_bootstrap_has_create_order_request_entries(self) -> None:
        create_keys = [
            k for k in EXCLUSIONS
            if k[0] == "kalshi.models.orders.CreateOrderRequest"
        ]
        field_names = {k[1] for k in create_keys}
        assert {"yes_price", "no_price", "sell_position_floor"} <= field_names

    def test_method_endpoint_entry_has_request_body_schema(self) -> None:
        entry = MethodEndpointEntry(
            sdk_method="x", http_method="GET", path_template="/y",
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
            spec, "/portfolio/orders/batched", "DELETE",
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
            e for e in METHOD_ENDPOINT_MAP
            if e.http_method == "DELETE" and e.request_body_schema is not None
        ]
        assert entries, "Expected at least one DELETE entry with a body schema"

        spec = _load_spec()
        for entry in entries:
            resolved = _resolve_request_body_schema(
                spec, entry.path_template, entry.http_method,
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


def _get_schema_fields(spec: dict[str, Any], schema_name: str) -> dict[str, dict[str, Any]]:
    """Extract field names and their properties from a spec schema."""
    schemas = spec.get("components", {}).get("schemas", {})
    schema = schemas.get(schema_name)
    if schema is None:
        pytest.fail(f"Schema '{schema_name}' not found in OpenAPI spec")

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
    """Extract required field names from a spec schema, merging from allOf/oneOf/anyOf."""
    schemas = spec.get("components", {}).get("schemas", {})
    schema = schemas.get(schema_name, {})

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
    """
    additive: list[str] = []
    required_issues: list[str] = []

    reverse_map = _build_spec_to_sdk_map(model_class)

    # Check every spec field has a corresponding SDK field
    for spec_field_name in spec_fields:
        if spec_field_name in entry.ignored_fields:
            continue
        if spec_field_name not in reverse_map:
            additive.append(f"Spec field '{spec_field_name}' has no SDK mapping")

    # Check required fields in spec vs SDK (warning, not failure)
    required_fields = _get_required_fields(spec, entry.spec_schema)
    for req_field in required_fields:
        if req_field in entry.ignored_fields:
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
            warnings.warn(
                f"Additive drift in {entry.sdk_model}:\n"
                + "\n".join(f"  - {a}" for a in additive),
                stacklevel=1,
            )

    @pytest.mark.parametrize(
        "entry",
        CONTRACT_MAP,
        ids=[e.sdk_model.rsplit(".", 1)[1] for e in CONTRACT_MAP],
    )
    def test_required_drift(self, entry: ContractEntry) -> None:
        """Warn about required mismatches (spec required, SDK optional)."""
        spec_fields = _get_schema_fields(self.spec, entry.spec_schema)
        model_class = _get_sdk_model_class(entry.sdk_model)
        _, required_issues = _classify_drift(entry, self.spec, spec_fields, model_class)
        if required_issues:
            warnings.warn(
                f"Required drift in {entry.sdk_model}:\n"
                + "\n".join(f"  - {r}" for r in required_issues),
                stacklevel=1,
            )

    def test_schema_coverage(self) -> None:
        """Every mapped schema must exist in the spec."""
        schemas = self.spec.get("components", {}).get("schemas", {})
        for entry in CONTRACT_MAP:
            assert entry.spec_schema in schemas, (
                f"Contract map references '{entry.spec_schema}' "
                f"but it doesn't exist in the OpenAPI spec"
            )

    def test_contract_map_completeness(self) -> None:
        """Warn if SDK models exist without contract map entries."""
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
            warnings.warn(
                "SDK models without contract map entries:\n"
                + "\n".join(f"  - {m}" for m in unmapped),
                stacklevel=1,
            )


# ---------------------------------------------------------------------------
# WS Spec Drift Tests
# ---------------------------------------------------------------------------


class TestWsSpecDrift:
    """Verify WS payload models match the AsyncAPI spec."""

    spec: dict[str, Any]

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
            warnings.warn(
                f"WS additive drift in {entry.sdk_model}:\n"
                + "\n".join(f"  - {a}" for a in additive),
                stacklevel=1,
            )

    @pytest.mark.parametrize(
        "entry",
        WS_CONTRACT_MAP,
        ids=[e.sdk_model.rsplit(".", 1)[1] for e in WS_CONTRACT_MAP],
    )
    def test_ws_required_drift(self, entry: ContractEntry) -> None:
        """Warn about required mismatches in WS models."""
        model_class = _get_sdk_model_class(entry.sdk_model)
        # Use WS-specific required extractor instead of REST _get_required_fields
        ws_required = _get_ws_required_fields(self.spec, entry.spec_schema)
        reverse_map = _build_spec_to_sdk_map(model_class)
        required_issues: list[str] = []
        for req_field in ws_required:
            if req_field in entry.ignored_fields:
                continue
            sdk_name = reverse_map.get(req_field)
            if sdk_name and sdk_name in model_class.model_fields:
                field_info = model_class.model_fields[sdk_name]
                if not field_info.is_required():
                    required_issues.append(
                        f"Spec requires '{req_field}' but SDK field '{sdk_name}' is optional"
                    )
        if required_issues:
            warnings.warn(
                f"WS required drift in {entry.sdk_model}:\n"
                + "\n".join(f"  - {r}" for r in required_issues),
                stacklevel=1,
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
        mismatches: list[str] = []

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
                                f"{entry.spec_schema}: spec type='{spec_type}', "
                                f"SDK {name}.type='{sdk_type_field.default}'"
                            )

        if mismatches:
            warnings.warn(
                "WS envelope type drift:\n"
                + "\n".join(f"  - {m}" for m in mismatches),
                stacklevel=1,
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
            warnings.warn(
                "WS payload models without contract map entries:\n"
                + "\n".join(f"  - {m}" for m in unmapped),
                stacklevel=1,
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
        name for name, param in sig.parameters.items()
        if name != "self" and param.kind in (
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

    Hard-fails via ``pytest.fail`` (NOT ``warnings.warn``). Request-side drift
    is a user-facing capability gap. See the docstring of
    ``tests/_contract_support.py`` for the rationale on the asymmetry vs
    ``TestSpecDrift`` (response-side, which warns rather than fails).
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
        self, entry: MethodEndpointEntry, *, async_: bool,
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
            assert hasattr(module, cls_name), (
                f"Missing async sibling {cls_name} in {module_name}"
            )

        sdk_params = _signature_params(sdk_fqn)
        spec_params_list = _resolve_path_params(
            self.spec, entry.path_template, entry.http_method,
        )
        spec_params = {
            p["name"] for p in spec_params_list
            if p.get("in") in ("query", "path")
        }
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
        missing_unallowed = {
            p for p in missing
            if (lookup_fqn, p) not in EXCLUSIONS
        }
        # REMOVE drift: SDK has it, spec doesn't
        extra = sdk_params - spec_params
        extra_unallowed = {
            p for p in extra
            if (lookup_fqn, p) not in EXCLUSIONS
        }

        errors: list[str] = []
        if missing_unallowed:
            errors.append(
                f"[ADD drift] spec has params SDK missing: "
                f"{sorted(missing_unallowed)}"
            )
        if extra_unallowed:
            errors.append(
                f"[REMOVE drift] SDK has params spec doesn't: "
                f"{sorted(extra_unallowed)}"
            )
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
    "#/components/schemas/CreateOrderRequest": (
        "kalshi.models.orders.CreateOrderRequest"
    ),
    "#/components/schemas/AmendOrderRequest": (
        "kalshi.models.orders.AmendOrderRequest"
    ),
    "#/components/schemas/DecreaseOrderRequest": (
        "kalshi.models.orders.DecreaseOrderRequest"
    ),
    "#/components/schemas/BatchCreateOrdersRequest": (
        "kalshi.models.orders.BatchCreateOrdersRequest"
    ),
    "#/components/schemas/BatchCancelOrdersRequest": (
        "kalshi.models.orders.BatchCancelOrdersRequest"
    ),
    "#/components/schemas/CreateMarketInMultivariateEventCollectionRequest": (
        "kalshi.models.multivariate."
        "CreateMarketInMultivariateEventCollectionRequest"
    ),
    "#/components/schemas/LookupTickersForMarketInMultivariateEventCollectionRequest": (
        "kalshi.models.multivariate."
        "LookupTickersForMarketInMultivariateEventCollectionRequest"
    ),
    "#/components/schemas/CreateOrderGroupRequest": (
        "kalshi.models.order_groups.CreateOrderGroupRequest"
    ),
    "#/components/schemas/UpdateOrderGroupLimitRequest": (
        "kalshi.models.order_groups.UpdateOrderGroupLimitRequest"
    ),
}


def _get_model_class_from_fqn(fqn: str) -> type[PydanticBase]:
    module_name, _, cls_name = fqn.rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, cls_name)  # type: ignore[no-any-return]


def _model_aliases(model_cls: type[PydanticBase]) -> set[str]:
    """Return the set of WIRE names the model emits — serialization_alias if
    set, else the field name. Compared to spec schema property names by
    ``TestRequestBodyDrift``.

    Known gap: iterates only top-level fields. Nested Pydantic models
    (e.g., ``TickerPair`` inside ``selected_markets: list[TickerPair]``)
    are not recursively checked. See TODOS.md — v0.9 nested-model drift
    coverage.
    """
    names: set[str] = set()
    for field_name, field in model_cls.model_fields.items():
        alias = field.serialization_alias or field_name
        names.add(alias)
    return names


_BODY_ENTRIES = [
    e for e in METHOD_ENDPOINT_MAP
    if e.request_body_schema is not None
]


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
        self, entry: MethodEndpointEntry,
    ) -> None:
        assert entry.request_body_schema is not None
        model_fqn = BODY_MODEL_MAP.get(entry.request_body_schema)
        assert model_fqn is not None, (
            f"No request model registered in BODY_MODEL_MAP for "
            f"{entry.request_body_schema!r}. Add the mapping."
        )
        model_cls = _get_model_class_from_fqn(model_fqn)

        schema = _resolve_request_body_schema(
            self.spec, entry.path_template, entry.http_method,
        )
        assert schema is not None, (
            f"Spec has no body schema for {entry.http_method} "
            f"{entry.path_template}"
        )
        spec_props = set(schema.get("properties", {}).keys())
        sdk_wire_names = _model_aliases(model_cls)

        # ADD drift: spec has property SDK model doesn't emit
        missing = spec_props - sdk_wire_names
        missing_unallowed = {
            p for p in missing if (model_fqn, p) not in EXCLUSIONS
        }
        # REMOVE drift: SDK emits wire name spec doesn't have
        extra = sdk_wire_names - spec_props
        extra_unallowed = {
            p for p in extra if (model_fqn, p) not in EXCLUSIONS
        }

        errors: list[str] = []
        if missing_unallowed:
            errors.append(
                f"[ADD drift] spec has properties SDK model missing: "
                f"{sorted(missing_unallowed)}"
            )
        if extra_unallowed:
            errors.append(
                f"[REMOVE drift] SDK model emits wire names spec doesn't: "
                f"{sorted(extra_unallowed)}"
            )
        if errors:
            pytest.fail(
                f"{model_fqn} <-> {entry.request_body_schema}\n"
                + "\n".join(errors)
            )


def test_exclusion_map_is_current() -> None:
    """Every EXCLUSIONS entry must describe real drift.

    If an entry references a spec-side key that is no longer in the spec's
    properties, or a SDK-side key the SDK now implements, the entry is
    stale. Stale entries give false confidence that a deviation is
    intentional — prevent that here.
    """
    spec = _load_spec()
    stale: list[str] = []

    for (fqn, name), excl in EXCLUSIONS.items():
        # Case 1: spec-side exclusion keyed on a model FQN (kalshi.models.*)
        if fqn.startswith("kalshi.models."):
            spec_ref = next(
                (ref for ref, m in BODY_MODEL_MAP.items() if m == fqn),
                None,
            )
            if spec_ref is None:
                stale.append(
                    f"EXCLUSIONS[{(fqn, name)}] references unknown model "
                    f"{fqn} (not in BODY_MODEL_MAP); reason={excl.reason!r}"
                )
                continue
            schema = None
            for e in METHOD_ENDPOINT_MAP:
                if e.request_body_schema == spec_ref:
                    schema = _resolve_request_body_schema(
                        spec, e.path_template, e.http_method,
                    )
                    break
            if schema is None:
                stale.append(
                    f"EXCLUSIONS[{(fqn, name)}] references schema {spec_ref} "
                    f"not reachable via METHOD_ENDPOINT_MAP"
                )
                continue
            if name not in schema.get("properties", {}):
                stale.append(
                    f"EXCLUSIONS[{(fqn, name)}] claims spec has {name!r} on "
                    f"{spec_ref}, but spec does NOT — entry is stale. "
                    f"reason={excl.reason!r}"
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
            # stale — UNLESS it's a body-param exclusion (like batch_cancel's
            # 'orders'), in which case the kwarg legitimately exists in the
            # signature. Distinguish by checking whether the entry's reason
            # references a body parameter.
            reason_lower = excl.reason.lower()
            is_body_param_exclusion = (
                "body param" in reason_lower
                or "body param," in reason_lower
                or "not query/path" in reason_lower
            )
            if name in sdk_params and not is_body_param_exclusion:
                stale.append(
                    f"EXCLUSIONS[{(fqn, name)}] claims SDK omits {name!r} from "
                    f"{fqn}, but the method DOES accept it as a kwarg — "
                    f"entry is stale. reason={excl.reason!r}"
                )

        else:
            stale.append(
                f"EXCLUSIONS[{(fqn, name)}] has unexpected FQN prefix; "
                f"expected kalshi.models.* or kalshi.resources.*"
            )

    if stale:
        pytest.fail("\n".join(stale))
