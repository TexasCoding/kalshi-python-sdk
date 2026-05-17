"""Enforce a uniform ``extra=`` policy across response models (#114).

Response models use ``extra="allow"`` so the SDK is forwards-compatible when
Kalshi adds new fields. Request bodies use ``extra="forbid"`` so the
client-side phantom-key check catches user typos at call time.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

import kalshi.models

# Request bodies must stay `extra="forbid"`. Identified by name suffix per
# the CLAUDE.md "Adding a new resource" convention. Both `Request` and the
# longer `RequestOrder` are needed: `BatchCancelOrdersRequestOrder` is a
# request-body sub-model whose name doesn't end in plain `Request`.
_REQUEST_BODY_SUFFIXES = ("Request", "RequestOrder")


def _exported_model_classes() -> list[tuple[str, type[BaseModel]]]:
    """Every BaseModel subclass re-exported from ``kalshi.models.__all__``.

    Scope assumption: this only enforces the policy on models exported via
    ``__all__``. A response model defined in a ``models/*.py`` file but
    never wired into ``__all__`` would silently escape the check. The
    project convention is to export every model; new models added without
    exporting them fall outside this guard by design.
    """
    out: list[tuple[str, type[BaseModel]]] = []
    for name in sorted(kalshi.models.__all__):
        obj = getattr(kalshi.models, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            out.append((name, obj))
    return out


def _is_request_body(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in _REQUEST_BODY_SUFFIXES)


_ALL_MODELS = _exported_model_classes()
_RESPONSE_MODELS = [(n, c) for n, c in _ALL_MODELS if not _is_request_body(n)]
_REQUEST_MODELS = [(n, c) for n, c in _ALL_MODELS if _is_request_body(n)]


@pytest.mark.parametrize(
    "name,cls", _RESPONSE_MODELS, ids=[n for n, _ in _RESPONSE_MODELS],
)
def test_response_models_use_extra_allow(name: str, cls: type[BaseModel]) -> None:
    cfg = getattr(cls, "model_config", {})
    extra = cfg.get("extra")
    assert extra == "allow", (
        f"Response model {name} has extra={extra!r}; expected 'allow' so the "
        f"SDK is forwards-compatible when Kalshi adds new fields (#114)."
    )


@pytest.mark.parametrize(
    "name,cls", _REQUEST_MODELS, ids=[n for n, _ in _REQUEST_MODELS],
)
def test_request_bodies_use_extra_forbid(name: str, cls: type[BaseModel]) -> None:
    cfg = getattr(cls, "model_config", {})
    extra = cfg.get("extra")
    assert extra == "forbid", (
        f"Request body {name} has extra={extra!r}; expected 'forbid' so "
        f"phantom kwargs fail at call time (CLAUDE.md key convention)."
    )
