"""Base message envelope models for the Kalshi WebSocket API."""
from __future__ import annotations

from pydantic import BaseModel


class SubscriptionInfo(BaseModel):
    """Subscription confirmation payload."""
    channel: str
    sid: int


class ErrorPayload(BaseModel):
    """Error message payload."""
    code: int
    msg: str
    market_ticker: str | None = None
    market_id: str | None = None


class BaseMessage(BaseModel):
    """Base for all WebSocket messages."""
    id: int = 0
    type: str
    sid: int | None = None
    seq: int | None = None
    model_config = {"extra": "allow"}


class SubscribedMessage(BaseModel):
    """Response to a subscribe command."""
    id: int = 0
    type: str = "subscribed"
    msg: SubscriptionInfo


class UnsubscribedMessage(BaseModel):
    """Response to an unsubscribe command."""
    id: int = 0
    sid: int
    seq: int
    type: str = "unsubscribed"


class OkMessage(BaseModel):
    """Generic success response (list_subscriptions, update_subscription)."""
    id: int = 0
    sid: int | None = None
    seq: int | None = None
    type: str = "ok"
    msg: dict[str, object] | list[object] | None = None
    model_config = {"extra": "allow"}


class ErrorMessage(BaseModel):
    """Error response from the server."""
    id: int = 0
    type: str = "error"
    msg: ErrorPayload
