"""Multivariate and multivariate market lifecycle channel message models."""
from __future__ import annotations

from pydantic import BaseModel

from kalshi.types import NullableList
from kalshi.ws.models.market_lifecycle import MarketLifecyclePayload


class SelectedMarket(BaseModel):
    """A selected market within a multivariate collection."""

    event_ticker: str | None = None
    market_ticker: str | None = None
    side: str | None = None
    model_config = {"extra": "allow"}


class MultivariatePayload(BaseModel):
    """Payload for multivariate messages (public channel)."""

    collection_ticker: str
    event_ticker: str
    market_ticker: str
    selected_markets: NullableList[SelectedMarket]
    model_config = {"extra": "allow"}


class MultivariateMessage(BaseModel):
    """Multivariate update message. NO required seq."""

    type: str = "multivariate_lookup"
    sid: int
    seq: int | None = None
    msg: MultivariatePayload
    model_config = {"extra": "allow"}


class MultivariateLifecycleMessage(BaseModel):
    """Multivariate market lifecycle message. Same payload as MarketLifecycleMessage."""

    type: str = "multivariate_market_lifecycle"
    sid: int
    seq: int | None = None
    msg: MarketLifecyclePayload
    model_config = {"extra": "allow"}
