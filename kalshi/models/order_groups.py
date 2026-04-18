"""Order Groups resource models.

Spec: ``specs/openapi.yaml`` components ``OrderGroup``, ``GetOrderGroupsResponse``,
``GetOrderGroupResponse``, ``CreateOrderGroupRequest``, ``CreateOrderGroupResponse``,
``UpdateOrderGroupLimitRequest``.

Order groups track a rolling 15-second contracts limit; when the limit is hit
all grouped orders cancel and no new orders post until the group is reset.
"""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import FixedPointCount, NullableList


class OrderGroup(BaseModel):
    """A single order group — spec ``components.schemas.OrderGroup``.

    ``contracts_limit`` maps to the wire field ``contracts_limit_fp`` (string
    FixedPointCount). Short-name ``contracts_limit`` accepted as well for
    parity with OrdersResource field naming. ``extra="allow"`` so spec-addition
    fields don't break parse.
    """

    id: str
    contracts_limit: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_limit_fp", "contracts_limit"),
    )
    is_auto_cancel_enabled: bool

    model_config = {"extra": "allow", "populate_by_name": True}


class GetOrderGroupResponse(BaseModel):
    """Response shape for ``GET /portfolio/order_groups/{order_group_id}``.

    Unlike ``OrderGroup`` (used in the list response), this shape omits ``id``
    (it's the path param) and adds an ``orders: list[str]`` of order IDs.
    """

    is_auto_cancel_enabled: bool
    orders: NullableList[str] = []
    contracts_limit: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_limit_fp", "contracts_limit"),
    )

    model_config = {"extra": "allow", "populate_by_name": True}


class CreateOrderGroupResponse(BaseModel):
    """Response shape for ``POST /portfolio/order_groups/create``."""

    order_group_id: str

    model_config = {"extra": "allow"}
