"""Order Groups models — rolling 15-second contracts-limit groups for linked orders."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from kalshi.types import FixedPointCount, NullableList


class OrderGroup(BaseModel):
    """A single order group (list response entry)."""

    id: str
    contracts_limit: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_limit_fp", "contracts_limit"),
    )
    is_auto_cancel_enabled: bool

    # v3.18.0 backfill (#161). Mirrors exchange_index on Market/Order/Event.
    exchange_index: int | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class GetOrderGroupResponse(BaseModel):
    """Single-group response — omits id (path param), adds member order IDs."""

    is_auto_cancel_enabled: bool
    orders: NullableList[str] = []
    contracts_limit: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("contracts_limit_fp", "contracts_limit"),
    )

    # v3.18.0 backfill (#161).
    exchange_index: int | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class CreateOrderGroupResponse(BaseModel):
    """Create response — wraps the new group's id."""

    order_group_id: str

    # v3.18.0 backfill (#161). Server echoes the routing context (subaccount +
    # exchange shard) on the create response.
    subaccount: int | None = None
    exchange_index: int | None = None

    model_config = {"extra": "allow"}


class CreateOrderGroupRequest(BaseModel):
    """Create body. SDK sends integer form; spec's `contracts_limit_fp` string variant unused."""

    contracts_limit: int = Field(..., ge=1)
    subaccount: int | None = Field(default=None, ge=0)
    exchange_index: int | None = None

    model_config = {"extra": "forbid"}


class UpdateOrderGroupLimitRequest(BaseModel):
    """Update-limit body. No `subaccount` — spec omits SubaccountQuery on /limit."""

    contracts_limit: int = Field(..., ge=1)

    model_config = {"extra": "forbid"}
