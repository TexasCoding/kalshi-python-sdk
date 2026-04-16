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

SPEC_FILE = Path(__file__).parent.parent / "specs" / "openapi.yaml"


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
            import warnings

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
            import warnings

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
            import warnings

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

    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.spec = _load_asyncapi_spec()

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
            import warnings

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
        spec_fields = _get_ws_msg_fields(self.spec, entry.spec_schema)
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
            import warnings

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
                    if msg_field.annotation is model_class:
                        sdk_type_field = obj.model_fields.get("type")
                        if sdk_type_field and sdk_type_field.default != spec_type:
                            mismatches.append(
                                f"{entry.spec_schema}: spec type='{spec_type}', "
                                f"SDK {name}.type='{sdk_type_field.default}'"
                            )

        if mismatches:
            import warnings

            warnings.warn(
                "WS envelope type drift:\n"
                + "\n".join(f"  - {m}" for m in mismatches),
                stacklevel=1,
            )

    def test_ws_contract_map_completeness(self) -> None:
        """Warn if WS payload models exist without contract map entries."""
        mapped_models = {e.sdk_model for e in WS_CONTRACT_MAP}
        unmapped: list[str] = []

        for module_name in (
            "ticker",
            "fill",
            "orderbook_delta",
            "trade",
            "user_orders",
            "market_lifecycle",
            "market_positions",
            "multivariate",
            "order_group",
            "communications",
        ):
            module = importlib.import_module(f"kalshi.ws.models.{module_name}")
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, PydanticBase)
                    and obj is not PydanticBase
                    and obj.__module__ == module.__name__
                    and name.endswith("Payload")
                ):
                    fqn = f"kalshi.ws.models.{module_name}.{name}"
                    if fqn not in mapped_models:
                        unmapped.append(fqn)

        if unmapped:
            import warnings

            warnings.warn(
                "WS payload models without contract map entries:\n"
                + "\n".join(f"  - {m}" for m in unmapped),
                stacklevel=1,
            )
