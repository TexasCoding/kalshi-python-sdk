"""Perps (margin) exchange models — status, access gate, risk parameters.

These are the response models for the three read-only perps "exchange health /
access" endpoints (#389). ``number/format: double`` ratio fields use
:data:`~kalshi.types.MultiplierDecimal` (not bare ``float``) to avoid binary
float drift, matching the prediction-API convention for double-typed ratios.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict

from kalshi.types import MultiplierDecimal


class ExchangeIndexStatus(BaseModel):
    """Spec ``ExchangeIndexStatus`` — operational status of one exchange shard."""

    model_config = ConfigDict(extra="allow")

    exchange_index: int
    description: str
    exchange_active: bool
    trading_active: bool
    intra_exchange_transfers_active: bool


class ExchangeStatus(BaseModel):
    """Spec ``ExchangeStatus`` — margin exchange operational status.

    Distinct from :class:`kalshi.models.exchange.ExchangeStatus`. The spec
    documents that perps responses omit ``intra_exchange_transfers_active``
    and ``exchange_index_statuses``; the SDK keeps them optional so a payload
    that does include them still parses.
    """

    model_config = ConfigDict(extra="allow")

    exchange_active: bool
    trading_active: bool
    intra_exchange_transfers_active: bool | None = None
    exchange_estimated_resume_time: AwareDatetime | None = None
    exchange_index_statuses: list[ExchangeIndexStatus] | None = None


class MarginEnabledResponse(BaseModel):
    """Spec ``MarginEnabledResponse`` — the perps per-member access gate."""

    model_config = ConfigDict(extra="allow")

    enabled: bool


class GetMarginRiskParametersResponse(BaseModel):
    """Spec ``GetMarginRiskParametersResponse`` — system-wide risk parameters."""

    model_config = ConfigDict(extra="allow")

    liquidation_margin_ratio_threshold: MultiplierDecimal
    queue_entry_margin_ratio_threshold: MultiplierDecimal
    initial_margin_multiplier: dict[str, MultiplierDecimal]
