"""Local orderbook manager from WebSocket snapshots and deltas."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from kalshi.models.markets import Orderbook, OrderbookLevel
from kalshi.ws.models.orderbook_delta import (
    OrderbookDeltaMessage,
    OrderbookSnapshotMessage,
)

logger = logging.getLogger("kalshi.ws")


@dataclass
class _BookState:
    """Internal mutable state for one ticker's orderbook.

    Levels are stored price-indexed (``dict[Decimal, Decimal]``) so delta
    application is O(1) regardless of book depth. The sorted
    ``list[OrderbookLevel]`` exposed via :class:`Orderbook` is materialized
    lazily in :meth:`to_orderbook` (O(n log n), but only when a snapshot is
    actually emitted to a consumer).

    Kept separate from the public :class:`Orderbook` model so the manager can
    mutate freely without leaking changes to previously-handed-out snapshots.
    """

    ticker: str
    yes: dict[Decimal, Decimal] = field(default_factory=dict)
    no: dict[Decimal, Decimal] = field(default_factory=dict)

    def to_orderbook(self) -> Orderbook:
        """Build a fresh ``Orderbook`` snapshot from the current state.

        Levels are emitted price-ascending to match the historical wire-order
        contract that the previous list-backed implementation maintained via
        ``list.sort`` after every insert.
        """
        yes_levels = [
            OrderbookLevel(price=price, quantity=qty)
            for price, qty in sorted(self.yes.items())
        ]
        no_levels = [
            OrderbookLevel(price=price, quantity=qty)
            for price, qty in sorted(self.no.items())
        ]
        return Orderbook(ticker=self.ticker, yes=yes_levels, no=no_levels)


class OrderbookManager:
    """Maintains local orderbook state from WebSocket stream.

    Prices and quantities are :class:`decimal.Decimal` throughout. Wire format
    (per AsyncAPI spec) sends dollar-decimal strings for prices (e.g.
    ``"0.5500"``) and fixed-point contract-count strings (e.g. ``"100.00"``)
    for quantities; both parse directly into ``Decimal`` without any
    cents-to-dollars conversion.

    Each call to :meth:`apply_snapshot`, :meth:`apply_delta`, or :meth:`get`
    returns a fresh :class:`Orderbook` instance. Consumers may safely retain
    references; subsequent updates will not mutate previously-returned books.

    Usage:
        mgr = OrderbookManager()
        book = mgr.apply_snapshot(snapshot_msg)  # Initialize
        book = mgr.apply_delta(delta_msg)         # Update
        book = mgr.get("TICKER")                   # Read current state
    """

    def __init__(self) -> None:
        self._books: dict[str, _BookState] = {}

    def apply_snapshot(self, msg: OrderbookSnapshotMessage) -> Orderbook:
        """Initialize (or reset) a book from a full snapshot."""
        ticker = msg.msg.market_ticker
        yes_levels = {Decimal(p): Decimal(q) for p, q in msg.msg.yes}
        no_levels = {Decimal(p): Decimal(q) for p, q in msg.msg.no}
        state = _BookState(ticker=ticker, yes=yes_levels, no=no_levels)
        self._books[ticker] = state
        logger.debug(
            "Orderbook snapshot: %s (%d yes, %d no levels)",
            ticker,
            len(yes_levels),
            len(no_levels),
        )
        return state.to_orderbook()

    def apply_delta(self, msg: OrderbookDeltaMessage) -> Orderbook | None:
        """Apply an incremental delta to an existing book.

        O(1) on the update itself (price-indexed dict lookup); the returned
        Orderbook is materialized at O(n log n) only because consumers expect
        a sorted level list.

        Returns the updated Orderbook, or None if no book exists for this ticker
        (delta arrived before snapshot -- should not happen in normal flow).
        """
        ticker = msg.msg.market_ticker
        state = self._books.get(ticker)
        if state is None:
            logger.warning("Delta for unknown ticker %s (no snapshot yet)", ticker)
            return None

        price = msg.msg.price  # Decimal via DollarDecimal
        delta = msg.msg.delta  # Decimal via FixedPointCount
        side = msg.msg.side

        levels = state.yes if side == "yes" else state.no
        existing_qty = levels.get(price)

        if existing_qty is not None:
            new_qty = existing_qty + delta
            if new_qty <= 0:
                del levels[price]
            else:
                levels[price] = new_qty
        elif delta > 0:
            levels[price] = delta

        return state.to_orderbook()

    def get(self, ticker: str) -> Orderbook | None:
        """Get current book state (non-blocking).

        Returns a fresh :class:`Orderbook` snapshot; the caller is free to
        retain it without seeing future mutations leak in.
        """
        state = self._books.get(ticker)
        if state is None:
            return None
        return state.to_orderbook()

    def remove(self, ticker: str) -> None:
        """Remove a book (e.g., on unsubscribe)."""
        self._books.pop(ticker, None)

    def clear(self) -> None:
        """Remove all books (e.g., on reconnect before resubscribe)."""
        self._books.clear()
