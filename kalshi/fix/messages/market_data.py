"""Market-data FIX messages (GH #426).

Market data rides the dedicated ``KalshiMD`` session and is identical on both
products; only the price units differ (prediction dollars vs margin fixed-point
dollars under ``UseDollars``), and both ride the FIX ``Price`` field, so
:data:`~kalshi.types.DollarDecimal` parses either without float drift.

Outbound: :class:`MarketDataRequest` (35=V), :class:`SecurityStatusRequest`
(35=e). Inbound (code fields kept raw — compare against :mod:`kalshi.fix.enums`):
:class:`MarketDataSnapshotFullRefresh` (35=W), :class:`MarketDataIncrementalRefresh`
(35=X), :class:`MarketDataRequestReject` (35=Y), :class:`SecurityStatus` (35=f).
:class:`~kalshi.fix.orderbook.FixOrderBook` reconstructs a book from W + X.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from kalshi.fix.enums import MsgType, SubscriptionRequestType
from kalshi.fix.messages.base import (
    FixGroup,
    FixGroupMeta,
    FixMessage,
    FixType,
    fixfield,
    groupfield,
)
from kalshi.fix.tags import Tag
from kalshi.types import DollarDecimal, FixedPointCount

# ---------------------------------------------------------------------------
# Repeating-group entries
# ---------------------------------------------------------------------------


class RelatedSymbol(FixGroup):
    """One ``NoRelatedSym`` (146) entry — delimiter ``Symbol`` (55)."""

    symbol: str = fixfield(Tag.SYMBOL, FixType.STRING)


class MDSnapshotEntry(FixGroup):
    """One ``NoMDEntries`` (268) entry in a snapshot — delimiter ``MDEntryType`` (269).

    ``md_entry_type`` is a raw char (compare against
    :class:`~kalshi.fix.enums.MDEntryType`: ``0``=bid, ``1``=offer). Price/size
    are optional for inbound robustness (parse an off-spec entry rather than
    rejecting the whole message), matching the order-entry inbound convention.
    """

    md_entry_type: str = fixfield(Tag.MD_ENTRY_TYPE, FixType.CHAR)
    md_entry_px: DollarDecimal | None = fixfield(Tag.MD_ENTRY_PX, FixType.PRICE, default=None)
    md_entry_size: FixedPointCount | None = fixfield(Tag.MD_ENTRY_SIZE, FixType.QTY, default=None)


class MDIncrementalEntry(FixGroup):
    """One ``NoMDEntries`` (268) entry in an incremental — delimiter ``MDUpdateAction`` (279).

    ``md_update_action`` / ``md_entry_type`` are raw chars (compare against
    :class:`~kalshi.fix.enums.MDUpdateAction` / ``MDEntryType``). ``md_entry_size``
    is the *new* absolute size at the level (``0`` when the level is deleted).
    Price/size are optional for inbound robustness (a ``Delete`` that omits them
    still parses), matching the order-entry inbound convention.
    """

    md_update_action: str = fixfield(Tag.MD_UPDATE_ACTION, FixType.CHAR)
    symbol: str = fixfield(Tag.SYMBOL, FixType.STRING)
    md_entry_type: str = fixfield(Tag.MD_ENTRY_TYPE, FixType.CHAR)
    md_entry_px: DollarDecimal | None = fixfield(Tag.MD_ENTRY_PX, FixType.PRICE, default=None)
    md_entry_size: FixedPointCount | None = fixfield(Tag.MD_ENTRY_SIZE, FixType.QTY, default=None)


# ---------------------------------------------------------------------------
# Outbound requests
# ---------------------------------------------------------------------------


class MarketDataRequest(FixMessage):
    """MarketDataRequest (35=V) — request order-book snapshots / updates.

    Prefer the :meth:`snapshot` / :meth:`subscribe` / :meth:`unsubscribe` /
    :meth:`unsubscribe_all` constructors: ``NoRelatedSym``/``Symbol`` are required
    for snapshot and subscribe, and a cancel-all request omits them entirely.

    ``MDReqID`` (262) is intentionally omitted: the Kalshi MD docs do not define
    it on 35=V/W/X/Y (subscriptions and rejects correlate by ``Symbol``, not a
    request id), unlike generic FIX 5.0SP2.
    """

    MSG_TYPE = MsgType.MARKET_DATA_REQUEST

    subscription_request_type: SubscriptionRequestType = fixfield(
        Tag.SUBSCRIPTION_REQUEST_TYPE, FixType.CHAR
    )
    related_symbols: Annotated[
        list[RelatedSymbol], FixGroupMeta(Tag.NO_RELATED_SYM, RelatedSymbol)
    ] = groupfield()

    @classmethod
    def _for(
        cls, request_type: SubscriptionRequestType, symbols: Iterable[str]
    ) -> MarketDataRequest:
        return cls(
            subscription_request_type=request_type,
            related_symbols=[RelatedSymbol(symbol=s) for s in symbols],
        )

    @classmethod
    def snapshot(cls, symbols: Iterable[str]) -> MarketDataRequest:
        """A one-shot snapshot request (263=0) for the given market tickers."""
        req = cls._for(SubscriptionRequestType.SNAPSHOT, symbols)
        if not req.related_symbols:
            raise ValueError("snapshot() requires at least one symbol")
        return req

    @classmethod
    def subscribe(cls, symbols: Iterable[str]) -> MarketDataRequest:
        """A snapshot-plus-updates subscription (263=1) for the given tickers."""
        req = cls._for(SubscriptionRequestType.SNAPSHOT_PLUS_UPDATES, symbols)
        if not req.related_symbols:
            raise ValueError("subscribe() requires at least one symbol")
        return req

    @classmethod
    def unsubscribe(cls, symbols: Iterable[str]) -> MarketDataRequest:
        """Cancel the subscriptions (263=2) for the given tickers."""
        req = cls._for(SubscriptionRequestType.DISABLE, symbols)
        if not req.related_symbols:
            raise ValueError("unsubscribe() requires at least one symbol; "
                             "use unsubscribe_all() to cancel everything")
        return req

    @classmethod
    def unsubscribe_all(cls) -> MarketDataRequest:
        """Cancel every subscription on the session (263=2 with no symbols)."""
        return cls(subscription_request_type=SubscriptionRequestType.DISABLE)


class SecurityStatusRequest(FixMessage):
    """SecurityStatusRequest (35=e) — subscribe/unsubscribe a market's status stream."""

    MSG_TYPE = MsgType.SECURITY_STATUS_REQUEST

    subscription_request_type: SubscriptionRequestType = fixfield(
        Tag.SUBSCRIPTION_REQUEST_TYPE, FixType.CHAR
    )
    symbol: str = fixfield(Tag.SYMBOL, FixType.STRING)

    @classmethod
    def subscribe(cls, symbol: str) -> SecurityStatusRequest:
        """Subscribe (263=1) to ``symbol``'s trading-status changes."""
        return cls(
            subscription_request_type=SubscriptionRequestType.SNAPSHOT_PLUS_UPDATES,
            symbol=symbol,
        )

    @classmethod
    def unsubscribe(cls, symbol: str) -> SecurityStatusRequest:
        """Unsubscribe (263=2) from ``symbol``'s trading-status changes."""
        return cls(subscription_request_type=SubscriptionRequestType.DISABLE, symbol=symbol)


# ---------------------------------------------------------------------------
# Inbound messages (fields optional; codes raw for robustness)
# ---------------------------------------------------------------------------


class MarketDataSnapshotFullRefresh(FixMessage):
    """MarketDataSnapshotFullRefresh (35=W) — the full aggregated book for a market.

    Correlate by ``symbol``. An empty ``entries`` list is a valid empty book
    (the server returns one for a symbol it has no order book for).
    """

    MSG_TYPE = MsgType.MARKET_DATA_SNAPSHOT_FULL_REFRESH

    symbol: str | None = fixfield(Tag.SYMBOL, FixType.STRING, default=None)
    entries: Annotated[
        list[MDSnapshotEntry], FixGroupMeta(Tag.NO_MD_ENTRIES, MDSnapshotEntry)
    ] = groupfield()


class MarketDataIncrementalRefresh(FixMessage):
    """MarketDataIncrementalRefresh (35=X) — changed book levels.

    Each entry carries its own ``symbol`` (the group spans markets).
    """

    MSG_TYPE = MsgType.MARKET_DATA_INCREMENTAL_REFRESH

    entries: Annotated[
        list[MDIncrementalEntry], FixGroupMeta(Tag.NO_MD_ENTRIES, MDIncrementalEntry)
    ] = groupfield()


class MarketDataRequestReject(FixMessage):
    """MarketDataRequestReject (35=Y) — a MarketDataRequest could not be accepted.

    ``md_req_rej_reason`` is a raw char (compare against
    :class:`~kalshi.fix.enums.MDReqRejReason`).
    """

    MSG_TYPE = MsgType.MARKET_DATA_REQUEST_REJECT

    md_req_rej_reason: str | None = fixfield(Tag.MD_REQ_REJ_REASON, FixType.CHAR, default=None)
    text: str | None = fixfield(Tag.TEXT, FixType.STRING, default=None)


class SecurityStatus(FixMessage):
    """SecurityStatus (35=f) — a market's trading-status change.

    ``security_trading_status`` is a raw int (compare against
    :class:`~kalshi.fix.enums.SecurityTradingStatus`).
    """

    MSG_TYPE = MsgType.SECURITY_STATUS

    symbol: str | None = fixfield(Tag.SYMBOL, FixType.STRING, default=None)
    security_trading_status: int | None = fixfield(
        Tag.SECURITY_TRADING_STATUS, FixType.INT, default=None
    )
