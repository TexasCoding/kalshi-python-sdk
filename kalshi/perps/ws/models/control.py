"""Command and response/control envelope models for the Perps (margin) WebSocket API.

This module mirrors :mod:`kalshi.ws.models.base` but for the **perps margin**
exchange, whose command grammar and host differ from the prediction-API WS.
Only the command + response/control envelopes live here. The per-channel data
payloads (``ticker``, ``trade``, ``fill``, ``user_order``, ``orderbook_*``,
``order_group_updates``) land in the separate ``perps: WS channels`` issue
(#398) and will populate ``PerpsMessageDispatcher.MESSAGE_MODELS``.

Two model families:

* **Command params + wrappers** are *request-side*. They use
  ``model_config = {"extra": "forbid"}`` so a typo'd key fails at build time,
  and are serialized via ``model_dump(exclude_none=True, by_alias=True,
  mode="json")``.
* **Response/control envelopes** are *response-side* validating models. They
  use ``model_config = {"extra": "allow", "populate_by_name": True}`` so a
  future additive server field doesn't break parsing.

Timestamp convention (CRITICAL — perps differs from the event-contract WS):
perps WS timestamps are **Unix epoch milliseconds** (``int``) carried on
``_ms``-suffixed field names. None of those fields appear on the control/command
envelopes in this module (only ``seq``/``sid``/``id``/``code`` are integers
here), but the channel payload models added by #398 will carry ``ts_ms``,
``created_ts_ms``, ``last_updated_ts_ms``, ``expiration_ts_ms`` and
``next_funding_time_ms`` as raw ``int`` epoch-ms — the parse path stays
int-typed and MUST NOT coerce them to RFC3339 ``datetime`` objects.

Likewise, perps order/book sides are ``bid``/``ask`` (:class:`PerpsBookSide`),
**not** the prediction API's ``yes``/``no``. Channel payload prices ride as
:data:`~kalshi.types.DollarDecimal` dollar strings, counts as
:data:`~kalshi.types.FixedPointCount` ``_fp`` strings, and the funding rate as
:data:`~kalshi.types.MultiplierDecimal` (``number``/``double``).
"""

from __future__ import annotations

import builtins
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class PerpsChannel(StrEnum):
    """Spec ``subscribeCommandPayload.params.channels.items.enum`` — subscribable channels."""

    ORDERBOOK_DELTA = "orderbook_delta"
    TICKER = "ticker"
    TRADE = "trade"
    FILL = "fill"
    USER_ORDERS = "user_orders"
    ORDER_GROUP_UPDATES = "order_group_updates"


class UpdateSubscriptionAction(StrEnum):
    """Spec ``updateSubscriptionCommandPayload.params.action.enum`` — add or remove markets."""

    ADD_MARKETS = "add_markets"
    DELETE_MARKETS = "delete_markets"


class PerpsBookSide(StrEnum):
    """Spec ``bookSide`` — the side of an order or book level.

    Perps uses ``bid``/``ask`` (NOT the prediction API's ``yes``/``no``).
    """

    BID = "bid"
    ASK = "ask"


# ----------------------------------------------------------------------------
# Command params (request-side, extra="forbid")
# ----------------------------------------------------------------------------


class SubscribeParams(BaseModel):
    """Params for the ``subscribe`` command (``subscribeCommandPayload.params``)."""

    model_config = {"extra": "forbid"}

    channels: builtins.list[PerpsChannel]
    market_ticker: str | None = None
    market_tickers: builtins.list[str] | None = None
    send_initial_snapshot: bool | None = None
    skip_ticker_ack: bool | None = None


class UnsubscribeParams(BaseModel):
    """Params for the ``unsubscribe`` command (``unsubscribeCommandPayload.params``)."""

    model_config = {"extra": "forbid"}

    sids: builtins.list[int]


class UpdateSubscriptionParams(BaseModel):
    """Params for the ``update_subscription`` command.

    The array variant sets ``sids`` (max 1 per spec); the single-sid variant
    sets the scalar ``sid``. ``action`` selects add vs delete.
    """

    model_config = {"extra": "forbid"}

    action: UpdateSubscriptionAction
    sid: int | None = None
    sids: builtins.list[int] | None = None
    market_ticker: str | None = None
    market_tickers: builtins.list[str] | None = None
    send_initial_snapshot: bool | None = None


# ----------------------------------------------------------------------------
# Command wrappers (request-side, extra="forbid")
# ----------------------------------------------------------------------------


class SubscribeCommand(BaseModel):
    """Wire frame for ``subscribeCommandPayload`` (``cmd: "subscribe"``)."""

    model_config = {"extra": "forbid"}

    id: int
    cmd: Literal["subscribe"] = "subscribe"
    params: SubscribeParams


class UnsubscribeCommand(BaseModel):
    """Wire frame for ``unsubscribeCommandPayload`` (``cmd: "unsubscribe"``)."""

    model_config = {"extra": "forbid"}

    id: int
    cmd: Literal["unsubscribe"] = "unsubscribe"
    params: UnsubscribeParams


class UpdateSubscriptionCommand(BaseModel):
    """Wire frame for ``updateSubscriptionCommandPayload`` (``cmd: "update_subscription"``).

    Backs all three spec messages that share this payload — add markets,
    delete markets, and the single-sid variant — distinguished by
    ``params.action`` and whether ``params.sid`` or ``params.sids`` is set.
    """

    model_config = {"extra": "forbid"}

    id: int
    cmd: Literal["update_subscription"] = "update_subscription"
    params: UpdateSubscriptionParams


class ListSubscriptionsCommand(BaseModel):
    """Wire frame for ``listSubscriptionsCommandPayload`` (``cmd: "list_subscriptions"``).

    Has no ``params`` per spec.
    """

    model_config = {"extra": "forbid"}

    id: int
    cmd: Literal["list_subscriptions"] = "list_subscriptions"


# ----------------------------------------------------------------------------
# Response / control envelopes (response-side, validating)
# ----------------------------------------------------------------------------


class SubscribedMsg(BaseModel):
    """``subscribedResponsePayload.msg`` — channel + assigned sid."""

    model_config = {"extra": "allow", "populate_by_name": True}

    channel: str
    sid: int


class SubscribedResponse(BaseModel):
    """Spec ``subscribedResponsePayload`` (``type: "subscribed"``)."""

    model_config = {"extra": "allow", "populate_by_name": True}

    id: int | None = None
    type: Literal["subscribed"] = "subscribed"
    msg: SubscribedMsg


class UnsubscribedResponse(BaseModel):
    """Spec ``unsubscribedResponsePayload`` (``type: "unsubscribed"``).

    ``seq`` is the per-sid sequence number; this is a control frame (the
    sid/seq are top-level, not nested under ``msg``).
    """

    model_config = {"extra": "allow", "populate_by_name": True}

    id: int | None = None
    sid: int
    seq: int
    type: Literal["unsubscribed"] = "unsubscribed"


class OkMsg(BaseModel):
    """``okResponsePayload.msg`` — optional update-ack body.

    Object-shaped (carries ``market_tickers``). The ``list_subscriptions``
    reply also uses ``type: "ok"`` but its ``msg`` is an **array**; callers
    disambiguate on ``msg`` shape (see :class:`ListSubscriptionsResponse`).
    """

    model_config = {"extra": "allow", "populate_by_name": True}

    market_tickers: builtins.list[str] | None = None


class OkResponse(BaseModel):
    """Spec ``okResponsePayload`` (``type: "ok"``) — update-ack with object ``msg``."""

    model_config = {"extra": "allow", "populate_by_name": True}

    id: int | None = None
    sid: int | None = None
    seq: int | None = None
    type: Literal["ok"] = "ok"
    msg: OkMsg | None = None


class SubscriptionEntry(BaseModel):
    """One entry in a ``listSubscriptionsResponsePayload.msg`` array."""

    model_config = {"extra": "allow", "populate_by_name": True}

    channel: str
    sid: int


class ListSubscriptionsResponse(BaseModel):
    """Spec ``listSubscriptionsResponsePayload`` (``type: "ok"`` with array ``msg``).

    Shares the ``type: "ok"`` const with :class:`OkResponse`; the framing
    layer disambiguates by ``msg`` being an array (list-subscriptions) vs an
    object (update ack).
    """

    model_config = {"extra": "allow", "populate_by_name": True}

    id: int
    type: Literal["ok"] = "ok"
    msg: builtins.list[SubscriptionEntry]


class PerpsErrorMsg(BaseModel):
    """``errorResponsePayload.msg`` -- error code (1-18), message, optional ticker."""

    model_config = {"extra": "allow", "populate_by_name": True}

    code: int
    msg: str
    market_ticker: str | None = None


class PerpsErrorResponse(BaseModel):
    """Spec ``errorResponsePayload`` (``type: "error"``)."""

    model_config = {"extra": "allow", "populate_by_name": True}

    id: int | None = None
    type: Literal["error"] = "error"
    msg: PerpsErrorMsg
    sid: int | None = None
    seq: int | None = None
