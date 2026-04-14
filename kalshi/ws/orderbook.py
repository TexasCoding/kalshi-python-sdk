"""Local orderbook manager from WebSocket snapshots and deltas."""
from __future__ import annotations

import logging
from decimal import Decimal

from kalshi.models.markets import Orderbook, OrderbookLevel
from kalshi.ws.models.orderbook_delta import (
    OrderbookDeltaMessage,
    OrderbookSnapshotMessage,
)

logger = logging.getLogger("kalshi.ws")


def _cents_to_dollars(cents: int) -> Decimal:
    """Convert integer cents to Decimal dollars."""
    return Decimal(cents) / Decimal(100)


class OrderbookManager:
    """Maintains local orderbook state from WebSocket stream.

    Usage:
        mgr = OrderbookManager()
        book = mgr.apply_snapshot(snapshot_msg)  # Initialize
        book = mgr.apply_delta(delta_msg)         # Update
        book = mgr.get("TICKER")                   # Read current state
    """

    def __init__(self) -> None:
        self._books: dict[str, Orderbook] = {}

    def apply_snapshot(self, msg: OrderbookSnapshotMessage) -> Orderbook:
        """Initialize (or reset) a book from a full snapshot."""
        ticker = msg.msg.market_ticker
        yes_levels = [
            OrderbookLevel(price=_cents_to_dollars(p), quantity=_cents_to_dollars(q))
            for p, q in msg.msg.yes
        ]
        no_levels = [
            OrderbookLevel(price=_cents_to_dollars(p), quantity=_cents_to_dollars(q))
            for p, q in msg.msg.no
        ]
        book = Orderbook(ticker=ticker, yes=yes_levels, no=no_levels)
        self._books[ticker] = book
        logger.debug(
            "Orderbook snapshot: %s (%d yes, %d no levels)",
            ticker,
            len(yes_levels),
            len(no_levels),
        )
        return book

    def apply_delta(self, msg: OrderbookDeltaMessage) -> Orderbook | None:
        """Apply an incremental delta to an existing book.

        Returns the updated Orderbook, or None if no book exists for this ticker
        (delta arrived before snapshot -- should not happen in normal flow).
        """
        ticker = msg.msg.market_ticker
        book = self._books.get(ticker)
        if book is None:
            logger.warning("Delta for unknown ticker %s (no snapshot yet)", ticker)
            return None

        price = _cents_to_dollars(msg.msg.price)
        delta = msg.msg.delta
        side = msg.msg.side

        levels = book.yes if side == "yes" else book.no

        # Find existing level at this price
        existing_idx = -1
        for i, level in enumerate(levels):
            if level.price == price:
                existing_idx = i
                break

        if existing_idx >= 0:
            existing = levels[existing_idx]
            new_qty = int(existing.quantity * 100) + delta
            if new_qty <= 0:
                # Remove the level
                levels.pop(existing_idx)
            else:
                levels[existing_idx] = OrderbookLevel(
                    price=price, quantity=_cents_to_dollars(new_qty)
                )
        else:
            if delta > 0:
                # Add new level
                levels.append(
                    OrderbookLevel(price=price, quantity=_cents_to_dollars(delta))
                )
                # Keep sorted by price
                levels.sort(key=lambda lv: lv.price)

        return book

    def get(self, ticker: str) -> Orderbook | None:
        """Get current book state (non-blocking)."""
        return self._books.get(ticker)

    def remove(self, ticker: str) -> None:
        """Remove a book (e.g., on unsubscribe)."""
        self._books.pop(ticker, None)

    def clear(self) -> None:
        """Remove all books (e.g., on reconnect before resubscribe)."""
        self._books.clear()
