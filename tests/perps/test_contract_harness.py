"""Verify the perps contract-test harness wiring (foundation, #388).

The maps are empty at the foundation stage; these tests confirm the loaders,
maps, and drift-class scaffolding exist and are well-formed so dependent
per-resource issues can append entries.
"""

from __future__ import annotations

from kalshi._contract_map import PERPS_CONTRACT_MAP, PERPS_SCM_CONTRACT_MAP
from tests._contract_support import (
    PERPS_EXCLUSIONS,
    PERPS_METHOD_ENDPOINT_MAP,
    PERPS_SCM_METHOD_ENDPOINT_MAP,
)
from tests.test_contracts import (
    PERPS_BODY_MODEL_MAP,
    PERPS_SCM_BODY_MODEL_MAP,
    PERPS_SCM_SPEC_FILE,
    PERPS_SPEC_FILE,
    _load_perps_scm_spec,
    _load_perps_spec,
)


class TestPerpsSpecLoaders:
    def test_perps_spec_file_committed(self) -> None:
        assert PERPS_SPEC_FILE.exists(), PERPS_SPEC_FILE
        assert PERPS_SCM_SPEC_FILE.exists(), PERPS_SCM_SPEC_FILE

    def test_load_perps_spec_parses(self) -> None:
        spec = _load_perps_spec()
        assert "paths" in spec
        assert "components" in spec
        # Sanity: a known perps path is present.
        assert "/margin/exchange/status" in spec["paths"]

    def test_load_perps_scm_spec_parses(self) -> None:
        spec = _load_perps_scm_spec()
        assert "paths" in spec
        # SCM auth migrated to Bearer (#443) — /log_in is gone; a margin path remains.
        assert "/margin/reports" in spec["paths"]


class TestPerpsMapsWellFormed:
    def test_rest_maps_populated(self) -> None:
        # The REST resources (#389-396) populate these.
        assert len(PERPS_METHOD_ENDPOINT_MAP) > 0
        assert len(PERPS_BODY_MODEL_MAP) > 0
        assert len(PERPS_EXCLUSIONS) > 0
        assert len(PERPS_CONTRACT_MAP) > 0

    def test_scm_maps_populated(self) -> None:
        # The SCM/Klear endpoints (#399 auth, #400 margin) populate these.
        assert len(PERPS_SCM_METHOD_ENDPOINT_MAP) > 0
        assert len(PERPS_SCM_BODY_MODEL_MAP) > 0
        assert len(PERPS_SCM_CONTRACT_MAP) > 0

    def test_map_types(self) -> None:
        assert isinstance(PERPS_METHOD_ENDPOINT_MAP, list)
        assert isinstance(PERPS_EXCLUSIONS, dict)
        assert isinstance(PERPS_BODY_MODEL_MAP, dict)
