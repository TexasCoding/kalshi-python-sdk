"""Local order-book reconstruction from FIX market data (GH #426).

:class:`FixOrderBook` maintains aggregated per-market books from a
:class:`~kalshi.fix.messages.market_data.MarketDataSnapshotFullRefresh` (35=W)
plus :class:`~kalshi.fix.messages.market_data.MarketDataIncrementalRefresh`
(35=X) stream. Unlike the WebSocket book (signed yes/no *deltas*), FIX market
data is bid/offer with *absolute* level sizes: a snapshot replaces a market's
book, an incremental ``Change`` sets a level's new size, and ``Delete`` removes
the level.

Levels are price-indexed (``dict[Decimal, Decimal]``) so an incremental update is
O(1); the sorted public view is materialized lazily in :meth:`get`.

Gap recovery: ``KalshiMD`` does not support retransmission, so a sequence gap
tears the session down and the client reconnects and re-subscribes. Snapshot
replacement is **per market** (keyed on ``Symbol``), so the caller MUST call
:meth:`clear` before re-subscribing after any teardown/gap: a market that was
seeded before the gap but is not immediately re-snapshotted (a different/smaller
re-subscribe set, or a read in the window before its fresh snapshot arrives)
would otherwise keep serving its stale pre-gap book. An incremental for a market
with no snapshot yet is dropped (the book is not seeded).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from kalshi.fix.enums import MDEntryType, MDUpdateAction
from kalshi.fix.messages.market_data import (
    MarketDataIncrementalRefresh,
    MarketDataSnapshotFullRefresh,
)

logger = logging.getLogger("kalshi.fix")


@dataclass(frozen=True)
class BookLevel:
    """One aggregated price level: a price and its total size."""

    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class MarketDataBook:
    """An immutable view of one market's book.

    ``bids`` are ordered best-first (price descending) and ``offers`` best-first
    (price ascending).
    """

    symbol: str
    bids: tuple[BookLevel, ...]
    offers: tuple[BookLevel, ...]


@dataclass
class _BookState:
    """Mutable per-market state: price-indexed bid/offer levels."""

    symbol: str
    bids: dict[Decimal, Decimal] = field(default_factory=dict)
    offers: dict[Decimal, Decimal] = field(default_factory=dict)

    def side(self, md_entry_type: str) -> dict[Decimal, Decimal] | None:
        """The level dict for a wire ``MDEntryType`` char, or ``None`` if unknown."""
        if md_entry_type == MDEntryType.BID.value:
            return self.bids
        if md_entry_type == MDEntryType.OFFER.value:
            return self.offers
        return None

    def to_view(self) -> MarketDataBook:
        return MarketDataBook(
            symbol=self.symbol,
            bids=tuple(
                BookLevel(price=p, size=s) for p, s in sorted(self.bids.items(), reverse=True)
            ),
            offers=tuple(BookLevel(price=p, size=s) for p, s in sorted(self.offers.items())),
        )


class FixOrderBook:
    """Reconstructs aggregated market books from FIX W snapshots + X incrementals.

    Usage::

        book = FixOrderBook()
        book.apply(decode_app_message(raw))   # W or X (others ignored)
        view = book.get("KXNBAGAME-...")       # MarketDataBook | None
    """

    def __init__(self) -> None:
        self._books: dict[str, _BookState] = {}

    def apply_snapshot(self, msg: MarketDataSnapshotFullRefresh) -> None:
        """Replace a market's book from a full snapshot (35=W).

        A snapshot without a ``symbol`` is ignored (nothing to key on). Unknown
        ``MDEntryType`` entries are skipped, as are non-positive-size levels (a
        ``0`` size means "no level" — parity with an incremental ``Delete``). An
        empty snapshot is a valid empty book.
        """
        symbol = msg.symbol
        if symbol is None:
            logger.warning("FIX MD snapshot without Symbol; ignoring")
            return
        state = _BookState(symbol=symbol)
        for entry in msg.entries:
            levels = state.side(entry.md_entry_type)
            if levels is None:
                logger.debug(
                    "FIX MD snapshot %s: unknown MDEntryType %r", symbol, entry.md_entry_type
                )
                continue
            # A level needs a price and a positive size; a 0/absent size is "no
            # level" (parity with an incremental Delete).
            if entry.md_entry_px is None or entry.md_entry_size is None or entry.md_entry_size <= 0:
                continue
            levels[entry.md_entry_px] = entry.md_entry_size
        self._books[symbol] = state

    def apply_incremental(self, msg: MarketDataIncrementalRefresh) -> int:
        """Apply incremental level changes (35=X). Returns the number applied.

        Each entry routes by its own ``symbol``. ``Change`` sets the level's new
        absolute size (a non-positive size removes the level); ``Delete`` removes
        it. An entry for a market with no snapshot yet, or with an unknown
        ``MDUpdateAction``/``MDEntryType``, is skipped without mutating the book.
        """
        applied = 0
        for entry in msg.entries:
            state = self._books.get(entry.symbol)
            if state is None:
                logger.warning(
                    "FIX MD incremental for %s with no snapshot yet; dropping entry", entry.symbol
                )
                continue
            levels = state.side(entry.md_entry_type)
            if levels is None:
                logger.debug(
                    "FIX MD incremental %s: unknown MDEntryType %r",
                    entry.symbol,
                    entry.md_entry_type,
                )
                continue
            px = entry.md_entry_px
            if px is None:
                logger.debug(
                    "FIX MD incremental %s: entry without MDEntryPx; dropping", entry.symbol
                )
                continue
            # Check the action FIRST: an unknown action carrying size 0 must be
            # dropped, not routed into Delete by a leading size guard.
            action = entry.md_update_action
            if action == MDUpdateAction.DELETE.value:
                levels.pop(px, None)
            elif action == MDUpdateAction.CHANGE.value:
                size = entry.md_entry_size
                if size is None or size <= 0:
                    levels.pop(px, None)  # absent / 0 size clears the level
                else:
                    levels[px] = size
            else:
                # Out-of-spec action: don't silently mutate the book.
                logger.debug(
                    "FIX MD incremental %s: unknown MDUpdateAction %r; dropping entry",
                    entry.symbol,
                    action,
                )
                continue
            applied += 1
        return applied

    def apply(self, msg: object) -> None:
        """Apply a decoded W or X message; anything else is ignored.

        Convenience for feeding :func:`~kalshi.fix.messages.decode_app_message`
        output straight in without a type switch at the call site.
        """
        if isinstance(msg, MarketDataSnapshotFullRefresh):
            self.apply_snapshot(msg)
        elif isinstance(msg, MarketDataIncrementalRefresh):
            self.apply_incremental(msg)

    def get(self, symbol: str) -> MarketDataBook | None:
        """The current book view for ``symbol``, or ``None`` if not seeded."""
        state = self._books.get(symbol)
        return state.to_view() if state is not None else None

    def symbols(self) -> set[str]:
        """The set of markets with a seeded book."""
        return set(self._books)

    def remove(self, symbol: str) -> None:
        """Drop a market's book (e.g. on unsubscribe or settlement)."""
        self._books.pop(symbol, None)

    def clear(self) -> None:
        """Drop all books (e.g. before re-subscribing after a reconnect)."""
        self._books.clear()
