"""Enforce a uniform ``extra=`` policy across response models (#114).

Response models use ``extra="allow"`` so the SDK is forwards-compatible when
Kalshi adds new fields. Request bodies use ``extra="forbid"`` so the
client-side phantom-key check catches user typos at call time.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

import kalshi.models

# Request bodies must stay `extra="forbid"`. Identifiable by name suffix.
_REQUEST_BODY_SUFFIXES = ("Request", "RequestOrder")


def _exported_model_classes() -> list[tuple[str, type[BaseModel]]]:
    out: list[tuple[str, type[BaseModel]]] = []
    for name in sorted(kalshi.models.__all__):
        obj = getattr(kalshi.models, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            out.append((name, obj))
    return out


def _is_request_body(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in _REQUEST_BODY_SUFFIXES)


@pytest.mark.parametrize(
    "name,cls",
    [(n, c) for n, c in _exported_model_classes() if not _is_request_body(n)],
)
def test_response_models_use_extra_allow(name: str, cls: type[BaseModel]) -> None:
    cfg = getattr(cls, "model_config", {})
    extra = cfg.get("extra")
    assert extra == "allow", (
        f"Response model {name} has extra={extra!r}; expected 'allow' so the "
        f"SDK is forwards-compatible when Kalshi adds new fields (#114)."
    )


@pytest.mark.parametrize(
    "name,cls",
    [(n, c) for n, c in _exported_model_classes() if _is_request_body(n)],
)
def test_request_bodies_use_extra_forbid(name: str, cls: type[BaseModel]) -> None:
    cfg = getattr(cls, "model_config", {})
    extra = cfg.get("extra")
    assert extra == "forbid", (
        f"Request body {name} has extra={extra!r}; expected 'forbid' so "
        f"phantom kwargs fail at call time (CLAUDE.md key convention)."
    )
