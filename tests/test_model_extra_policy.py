"""Enforce a uniform ``extra=`` policy across response models (#114).

Response models use ``extra="allow"`` so the SDK is forwards-compatible when
Kalshi adds new fields. Request bodies use ``extra="forbid"`` so the
client-side phantom-key check catches user typos at call time.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

import kalshi.models
from tests._request_model_fixtures import minimal_kwargs

# Request bodies must stay `extra="forbid"`. Identified by name suffix per
# the CLAUDE.md "Adding a new resource" convention. Both `Request` and the
# longer `RequestOrder` are needed: `BatchCancelOrdersV2RequestOrder` is a
# request-body sub-model whose name doesn't end in plain `Request`.
# `Input` covers nested write models such as `TargetBalanceAllocationInput`.
_REQUEST_BODY_SUFFIXES = ("Request", "RequestOrder", "Input")


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


@pytest.mark.parametrize(
    "cls", [c for _, c in _REQUEST_MODELS], ids=[n for n, _ in _REQUEST_MODELS],
)
def test_request_model_rejects_phantom_field(cls: type[BaseModel]) -> None:
    """Behavioral pair for ``test_request_bodies_use_extra_forbid``.

    The config test pins ``model_config['extra'] == 'forbid'``; this one
    pins the resulting *behavior* — constructing the model with an unknown
    kwarg raises ``ValidationError`` with an ``extra_forbidden`` entry. A
    contributor who flips the config AND adds a typo'd field would slip
    the config gate but get caught here (#219).
    """
    valid = minimal_kwargs(cls)
    with pytest.raises(ValidationError) as exc:
        cls(**valid, ghost_field="x")
    assert any(err["type"] == "extra_forbidden" for err in exc.value.errors()), (
        f"{cls.__name__} did not raise an extra_forbidden error for "
        f"ghost_field='x'; got errors={exc.value.errors()!r}"
    )


def test_minimal_kwargs_helper_handles_all_request_models() -> None:
    """Meta-test: the auto-builder covers every model in ``_REQUEST_MODELS``.

    If a new Request model is added with an annotation the auto-builder
    can't synthesize, this fails before the parametrized phantom test
    surfaces a confusing per-case error.
    """
    failures: list[str] = []
    for name, cls in _REQUEST_MODELS:
        try:
            cls(**minimal_kwargs(cls))
        except (RuntimeError, TypeError) as e:
            failures.append(f"{name}: {type(e).__name__}: {e}")
    assert not failures, (
        "minimal_kwargs helper cannot build these Request models; add "
        f"overrides in tests/_request_model_fixtures.py: {failures}"
    )


# ---------------------------------------------------------------------------
# WebSocket models — payloads, envelopes, AND helpers all use extra="allow"
# (#163). The WS surface has no request bodies, so the policy is uniform.
# This pins the rule so a future model addition that forgets the config
# fails this test instead of slipping through.
# ---------------------------------------------------------------------------


def _ws_model_classes() -> list[tuple[str, type[BaseModel]]]:
    """Every BaseModel subclass defined in any ``kalshi.ws.models.*`` module."""
    import importlib
    import inspect
    import pkgutil

    import kalshi.ws.models as ws_pkg

    out: list[tuple[str, type[BaseModel]]] = []
    seen: set[type[BaseModel]] = set()
    for mod_info in pkgutil.iter_modules(ws_pkg.__path__):
        if mod_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"kalshi.ws.models.{mod_info.name}")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__ == module.__name__
                and obj not in seen
            ):
                out.append((f"{mod_info.name}.{name}", obj))
                seen.add(obj)
    return out


_WS_MODELS = _ws_model_classes()


@pytest.mark.parametrize(
    "name,cls", _WS_MODELS, ids=[n for n, _ in _WS_MODELS],
)
def test_ws_models_use_extra_allow(name: str, cls: type[BaseModel]) -> None:
    """Every WS model (payload, envelope, helper) must opt into ``extra='allow'``.

    Locks in the policy so a future WS model addition that omits the
    config fails CI loudly. Closes the matching ROADMAP item — payloads
    were already covered in #143; this extends it to the envelopes and
    helpers.
    """
    cfg = getattr(cls, "model_config", {})
    extra = cfg.get("extra")
    assert extra == "allow", (
        f"WS model {name} has extra={extra!r}; expected 'allow'. WS is "
        f"unidirectional and forwards-compatibility is the whole point — "
        f"the spec adds fields routinely (e.g. v0.14 ts_ms backfill)."
    )
