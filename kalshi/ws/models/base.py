"""Base message envelope models for the Kalshi WebSocket API."""
from __future__ import annotations

from pydantic import BaseModel


class SubscriptionInfo(BaseModel):
    """Subscription confirmation payload."""
    channel: str
    sid: int
    model_config = {"extra": "allow", "populate_by_name": True}


class ErrorPayload(BaseModel):
    """Error message payload."""
    code: int
    msg: str
    market_ticker: str | None = None
    market_id: str | None = None
    market_tickers: list[str] | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class BaseMessage(BaseModel):
    """Base for all WebSocket messages."""
    id: int = 0
    type: str
    sid: int | None = None
    seq: int | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class SubscribedMessage(BaseModel):
    """Response to a subscribe command."""
    id: int = 0
    type: str = "subscribed"
    msg: SubscriptionInfo
    model_config = {"extra": "allow", "populate_by_name": True}


class UnsubscribedMessage(BaseModel):
    """Response to an unsubscribe command."""
    id: int = 0
    sid: int
    seq: int
    type: str = "unsubscribed"
    model_config = {"extra": "allow", "populate_by_name": True}


class OkMessage(BaseModel):
    """Generic success response (list_subscriptions, update_subscription)."""
    id: int = 0
    sid: int | None = None
    seq: int | None = None
    type: str = "ok"
    msg: dict[str, object] | list[object] | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class ErrorMessage(BaseModel):
    """Error response from the server."""
    id: int = 0
    type: str = "error"
    msg: ErrorPayload
    model_config = {"extra": "allow", "populate_by_name": True}
