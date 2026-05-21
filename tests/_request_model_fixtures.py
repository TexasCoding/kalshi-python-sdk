"""Minimal-kwargs helper for Request models (#219).

Walks ``model_cls.model_fields`` and emits the smallest valid kwargs dict
the model accepts, so a parametrized phantom-kwarg test can assert
``extra='forbid'`` behavior (not just config) across every Request model
exported from ``kalshi.models``.

The walker handles primitives, ``Literal``, ``Union``/``Optional``,
``list[X]``, nested ``BaseModel`` subclasses, and ``UUID``. Anything else
must be supplied via the per-model override map ``_OVERRIDES`` below.
"""

from __future__ import annotations

import types
import typing
import uuid
from decimal import Decimal
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

_PRIMITIVE_DEFAULTS: dict[type, Any] = {
    str: "x",
    int: 1,
    bool: True,
    float: 1.0,
    Decimal: Decimal("1"),
    uuid.UUID: uuid.UUID(int=0),
    bytes: b"x",
}


def _generate_value(annotation: Any) -> Any:
    """Produce a minimal valid value for ``annotation``.

    Raises ``RuntimeError`` if the annotation isn't understood — that's
    the signal to add an override to ``_OVERRIDES``.
    """
    if annotation in _PRIMITIVE_DEFAULTS:
        return _PRIMITIVE_DEFAULTS[annotation]

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Literal:
        return args[0]

    if origin in (Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        if not non_none:
            raise RuntimeError(f"Union with only None: {annotation!r}")
        return _generate_value(non_none[0])

    if origin in (list, typing.List):  # noqa: UP006 — typing.List for safety
        inner = args[0] if args else str
        return [_generate_value(inner)]

    if origin in (tuple, typing.Tuple):  # noqa: UP006
        return tuple(_generate_value(a) for a in args if a is not Ellipsis)

    if origin in (set, frozenset):
        inner = args[0] if args else str
        return {_generate_value(inner)}

    if origin in (dict, typing.Dict):  # noqa: UP006
        return {}

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation(**minimal_kwargs(annotation))

    raise RuntimeError(
        f"Unsupported annotation for minimal_kwargs auto-builder: {annotation!r}. "
        "Add an entry to _OVERRIDES in tests/_request_model_fixtures.py."
    )


def _minimal_kwargs_no_override(model_cls: type[BaseModel]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fname, finfo in model_cls.model_fields.items():
        if not finfo.is_required():
            continue
        out[fname] = _generate_value(finfo.annotation)
    return out


# ---------------------------------------------------------------------------
# Per-model overrides for models the auto-builder cannot satisfy alone.
#
# Resolved lazily (by class name) so this module stays importable even if
# a model moves between submodules. The auto-builder runs first; entries
# here are merged on top.
# ---------------------------------------------------------------------------

_OVERRIDES: dict[str, dict[str, Any]] = {
    # ``DecreaseOrderRequest`` has a ``model_validator`` requiring exactly
    # one of ``reduce_by`` / ``reduce_to``. Both fields are optional so
    # the auto-builder skips them — populate one.
    "DecreaseOrderRequest": {"reduce_by": 1},
    "DecreaseOrderV2Request": {"reduce_by": Decimal("1")},
}


def minimal_kwargs(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Return a minimal valid kwargs dict for constructing ``model_cls``."""
    out = _minimal_kwargs_no_override(model_cls)
    out.update(_OVERRIDES.get(model_cls.__name__, {}))
    return out
