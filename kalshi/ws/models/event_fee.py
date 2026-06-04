"""Event fee override update message model (market_lifecycle_v2 channel)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from kalshi.types import MultiplierDecimal


class EventFeeUpdatePayload(BaseModel):
    """Payload for ``event_fee_update`` messages (market_lifecycle_v2 channel).

    Emitted when an event-level fee override is set or cleared.
    ``fee_type_override`` and ``fee_multiplier_override`` are both ``None``
    when the override has been cleared (the event falls back to the parent
    series' fee structure). Both are spec-required keys but nullable — the
    key is present; ``None`` is the meaningful "override cleared" signal, so
    neither carries a default.
    """

    event_ticker: str
    fee_type_override: str | None
    fee_multiplier_override: MultiplierDecimal | None

    model_config = {"extra": "allow", "populate_by_name": True}


class EventFeeUpdateMessage(BaseModel):
    """``event_fee_update`` message delivered on the market_lifecycle_v2 channel.

    Rides the same channel as :class:`MarketLifecycleMessage`; subscribers to
    ``subscribe_market_lifecycle`` receive both message types. NO required seq.
    """

    type: Literal["event_fee_update"] = "event_fee_update"
    sid: int
    # The AsyncAPI envelope does not declare `seq` for this message; it is
    # accepted-if-present for forward-compat and parity with the sibling
    # MarketLifecycleMessage on the same channel. The server does not emit it.
    seq: int | None = None
    msg: EventFeeUpdatePayload
    model_config = {"extra": "allow", "populate_by_name": True}
