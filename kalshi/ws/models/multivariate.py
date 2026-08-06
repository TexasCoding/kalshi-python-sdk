"""Multivariate market lifecycle channel message models.

The standalone ``multivariate`` / ``multivariate_lookup`` channel and payload
were removed from AsyncAPI (spec drift 2026-08); only
``multivariate_market_lifecycle`` remains.
"""
from __future__ import annotations

from pydantic import BaseModel

from kalshi.ws.models.market_lifecycle import MarketLifecyclePayload


class MultivariateLifecycleMessage(BaseModel):
    """Multivariate market lifecycle message. Same payload as MarketLifecycleMessage."""

    type: str = "multivariate_market_lifecycle"
    sid: int
    seq: int | None = None
    msg: MarketLifecyclePayload
    model_config = {"extra": "allow", "populate_by_name": True}
