"""Perps (margin) order groups — rolling 15-second contracts-limit groups for linked orders.

The margin-exchange twin of :mod:`kalshi.models.order_groups`. Schemas are
near-identical; the perps ``CreateOrderGroupResponse`` requires both
``order_group_id`` and ``subaccount`` and adds an optional ``exchange_index``.
Verified field-by-field against ``specs/perps_openapi.yaml``.
"""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import FixedPointCount, NullableList, StrictInt


class OrderGroup(BaseModel):
    """Spec ``OrderGroup`` — a single order group (list-response entry).

    Required: ``id``, ``is_auto_cancel_enabled``. The spec exposes only
    ``contracts_limit_fp`` (a :data:`~kalshi.types.FixedPointCount` string,
    2-decimal "fp"); the short Python name + alias mirrors the portfolio model.
    """

    id: str
    contracts_limit: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_limit_fp", "contracts_limit"),
    )
    is_auto_cancel_enabled: bool
    exchange_index: int | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class GetOrderGroupResponse(BaseModel):
    """Spec ``GetOrderGroupResponse`` — a single group plus its member order IDs.

    Required: ``is_auto_cancel_enabled``, ``orders``. Omits ``id`` (it is the
    path param).
    """

    is_auto_cancel_enabled: bool
    orders: NullableList[str]
    contracts_limit: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_limit_fp", "contracts_limit"),
    )
    exchange_index: int | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class CreateOrderGroupResponse(BaseModel):
    """Spec ``CreateOrderGroupResponse`` — wraps the new group's id.

    Required: ``order_group_id``, ``subaccount`` (0 for primary, 1-63 for
    subaccounts). The server echoes the routing context (subaccount + exchange
    shard) on the create response.
    """

    order_group_id: str
    subaccount: int
    exchange_index: int | None = None

    model_config = {"extra": "allow"}


class CreateOrderGroupRequest(BaseModel):
    """Spec ``CreateOrderGroupRequest`` — POST body (forbid).

    The SDK sends the integer ``contracts_limit`` form; the spec's alternate
    ``contracts_limit_fp`` string variant is unused (Kalshi accepts either).
    ``contracts_limit`` is required at the SDK level even though the spec marks
    it optional — mirrors the portfolio model.
    """

    contracts_limit: StrictInt = Field(..., ge=1)
    subaccount: StrictInt | None = Field(default=None, ge=0)
    exchange_index: StrictInt | None = None

    model_config = {"extra": "forbid"}


class UpdateOrderGroupLimitRequest(BaseModel):
    """Spec ``UpdateOrderGroupLimitRequest`` — PUT ``/limit`` body (forbid).

    SDK sends the integer ``contracts_limit`` form; the spec's
    ``contracts_limit_fp`` string variant is unused.
    """

    contracts_limit: StrictInt = Field(..., ge=1)

    model_config = {"extra": "forbid"}
