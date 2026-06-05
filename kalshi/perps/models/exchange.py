"""Perps (margin) exchange models — status, access gate, risk parameters.

These are the response models for the three read-only perps "exchange health /
access" endpoints (#389). ``number/format: double`` ratio fields use
:data:`~kalshi.types.MultiplierDecimal` (not bare ``float``) to avoid binary
float drift, matching the prediction-API convention for double-typed ratios.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from kalshi.types import MultiplierDecimal


class ExchangeStatus(BaseModel):
    """Spec ``ExchangeStatus`` — margin exchange operational status.

    Distinct from :class:`kalshi.models.exchange.ExchangeStatus`; the perps
    version is slimmer (no schedule / resume-time fields).
    """

    model_config = ConfigDict(extra="allow")

    exchange_active: bool
    trading_active: bool


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
