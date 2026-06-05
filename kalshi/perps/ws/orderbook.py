"""Local margin orderbook manager from perps WebSocket snapshots and deltas.

This is a **fork** of :class:`kalshi.ws.orderbook.OrderbookManager`, not a reuse.
The prediction-API manager hardcodes ``yes`` / ``no`` sides and consumes
``OrderbookSnapshotMessage`` / ``OrderbookDeltaMessage`` whose ``side`` is
``yes``/``no``. Perps uses ``bid`` / ``ask`` (:class:`PerpsBookSide`) and the
margin snapshot carries ``bid`` / ``ask`` arrays of ``priceLevelDollarsCountFp``
(``[price_in_dollars, contract_count_fp]``) levels. Forking (per the #397
guidance) keeps the prediction-API manager and its tests untouched while the
Decimal price-indexed dict logic, lazy materialization, per-sid teardown
(:meth:`remove_by_sid`), and cache invalidation are mirrored verbatim.

The public view is :class:`kalshi.perps.models.markets.MarginOrderbook` (the
same ``bids`` / ``asks`` of ``[price, quantity]`` shape the REST orderbook
endpoint returns), so consumers get one orderbook type across REST and WS.

The apply paths consume the concrete ``MarginOrderbookSnapshotMessage`` /
``MarginOrderbookDeltaMessage`` channel models (#398): ``.sid``,
``.msg.market_ticker``, ``.msg.bid`` / ``.ask`` (price-indexed
``dict[Decimal, Decimal]`` maps) for snapshots, and ``.msg.price`` /
``.delta`` / ``.side`` for deltas. (#397 originally typed these via structural
Protocols to stay decoupled from the not-yet-written channel models; once #398
landed they were swapped for the concrete types.)

Timestamp note: per-level data carries no timestamps; delta envelopes may carry
``ts_ms`` (epoch-ms ``int``) on #398's payload model — this manager never reads
it, so the int-typed convention is preserved end to end.
"""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass, field
from decimal import Decimal

from kalshi.perps.models.markets import MarginOrderbook, MarginOrderbookLevel
from kalshi.perps.ws.models.orderbook import (
    MarginOrderbookDeltaMessage,
    MarginOrderbookSnapshotMessage,
)

logger = logging.getLogger("kalshi.perps.ws")


@dataclass
class _PerpsBookState:
    """Internal mutable state for one margin ticker's orderbook.

    Levels are price-indexed (``dict[Decimal, Decimal]``) per side so delta
    application is O(1) regardless of depth. The sorted public
    :class:`MarginOrderbook` view is materialized lazily and memoized; the
    cache is dropped by :meth:`invalidate` whenever a side mutates.
    """

    ticker: str
    bid: dict[Decimal, Decimal] = field(default_factory=dict)
    ask: dict[Decimal, Decimal] = field(default_factory=dict)
    sid: int | None = None
    _cached: MarginOrderbook | None = field(default=None, repr=False, compare=False)

    def to_orderbook(self) -> MarginOrderbook:
        """Build (or return the cached) :class:`MarginOrderbook` from current state.

        Levels are emitted price-ascending. Materialized via ``model_construct``
        (the dicts are already SDK-canonical ``Decimal`` -> ``Decimal``), so the
        per-level validators don't re-run on this hot path.
        """
        if self._cached is not None:
            return self._cached
        bid_levels = [
            MarginOrderbookLevel.model_construct(price=price, quantity=qty)
            for price, qty in sorted(self.bid.items())
        ]
        ask_levels = [
            MarginOrderbookLevel.model_construct(price=price, quantity=qty)
            for price, qty in sorted(self.ask.items())
        ]
        ob = MarginOrderbook.model_construct(
            ticker=self.ticker, bids=bid_levels, asks=ask_levels
        )
        self._cached = ob
        return ob

    def invalidate(self) -> None:
        """Drop the cached :class:`MarginOrderbook`; next read re-materializes."""
        self._cached = None


class PerpsOrderbookManager:
    """Maintains local margin orderbook state from the perps WebSocket stream.

    Prices and quantities are :class:`decimal.Decimal` throughout. Sides are
    ``bid`` / ``ask`` (NOT ``yes`` / ``no``). Per-sid tracking lets all-markets
    subscriptions be torn down without enumerating tickers.

    Usage::

        mgr = PerpsOrderbookManager()
        mgr.apply_snapshot(snapshot_msg)   # initialize
        mgr.apply_delta(delta_msg)         # update
        book = mgr.get("BTC-PERP")         # read current state
    """

    def __init__(self) -> None:
        self._books: dict[str, _PerpsBookState] = {}
        self._sid_tickers: dict[int, set[str]] = {}

    def _install_snapshot(
        self,
        ticker: str,
        sid_val: int | None,
        bid: dict[Decimal, Decimal],
        ask: dict[Decimal, Decimal],
    ) -> _PerpsBookState:
        """Replace the book for ``ticker`` with a freshly seeded state.

        The provided ``bid`` / ``ask`` dicts are adopted by identity; callers
        defensive-copy when their input must not alias internal state.
        """
        prior = self._books.get(ticker)
        if prior is not None and prior.sid is not None and prior.sid != sid_val:
            old_bucket = self._sid_tickers.get(prior.sid)
            if old_bucket is not None:
                old_bucket.discard(ticker)
                if not old_bucket:
                    self._sid_tickers.pop(prior.sid, None)

        state = _PerpsBookState(ticker=ticker, bid=bid, ask=ask, sid=sid_val)
        self._books[ticker] = state
        if sid_val is not None:
            bucket = self._sid_tickers.get(sid_val)
            if bucket is None:
                bucket = set()
                self._sid_tickers[sid_val] = bucket
            bucket.add(ticker)
        logger.debug(
            "Margin orderbook snapshot: %s (%d bid, %d ask levels, sid=%s)",
            ticker,
            len(bid),
            len(ask),
            sid_val,
        )
        return state

    def _apply_snapshot_inplace(
        self, msg: MarginOrderbookSnapshotMessage, sid: int | None = None
    ) -> None:
        """In-place state mutation for a snapshot. No materialization.

        Recv-loop hot-path entry point. ``msg.msg.bid`` / ``.ask`` are adopted
        by identity into the new ``_PerpsBookState``; callers must treat them
        as consumed. ``sid`` defaults to ``msg.sid``.
        """
        sid_val = sid if sid is not None else msg.sid
        self._install_snapshot(
            msg.msg.market_ticker, sid_val, msg.msg.bid, msg.msg.ask
        )

    def _apply_delta_inplace(self, msg: MarginOrderbookDeltaMessage) -> bool:
        """In-place state mutation for a delta. No materialization.

        Returns ``True`` if applied, ``False`` if no book exists yet for the
        ticker (delta arrived before snapshot).
        """
        ticker = msg.msg.market_ticker
        state = self._books.get(ticker)
        if state is None:
            logger.warning(
                "Margin delta for unknown ticker %s (no snapshot yet)", ticker
            )
            return False

        price = msg.msg.price
        delta = msg.msg.delta
        side = msg.msg.side

        # Compare against the enum's value so both ``PerpsBookSide.BID`` and the
        # raw wire string ``"bid"`` route to the bid dict.
        levels = state.bid if str(side) == "bid" else state.ask
        existing_qty = levels.get(price)

        if existing_qty is not None:
            new_qty = existing_qty + delta
            if new_qty <= 0:
                del levels[price]
                state.invalidate()
            elif new_qty != existing_qty:
                levels[price] = new_qty
                state.invalidate()
        elif delta > 0:
            levels[price] = delta
            state.invalidate()

        return True

    def apply_snapshot(
        self, msg: MarginOrderbookSnapshotMessage, sid: int | None = None
    ) -> MarginOrderbook:
        """Initialize (or reset) a book from a full snapshot.

        Public wrapper: seeds the book with a defensive single-copy of the
        caller's ``bid`` / ``ask`` dicts and materializes a fresh
        :class:`MarginOrderbook`. ``msg`` is safe to reuse afterward.
        """
        sid_val = sid if sid is not None else msg.sid
        state = self._install_snapshot(
            msg.msg.market_ticker,
            sid_val,
            dict(msg.msg.bid),
            dict(msg.msg.ask),
        )
        return state.to_orderbook()

    def apply_delta(self, msg: MarginOrderbookDeltaMessage) -> MarginOrderbook | None:
        """Apply an incremental delta. Returns the book, or ``None`` if unseeded."""
        if not self._apply_delta_inplace(msg):
            return None
        state = self._books.get(msg.msg.market_ticker)
        return state.to_orderbook() if state else None

    def get(self, ticker: str) -> MarginOrderbook | None:
        """Get current book state (non-blocking). Returns a fresh view."""
        state = self._books.get(ticker)
        if state is None:
            return None
        return state.to_orderbook()

    def remove(self, ticker: str) -> None:
        """Remove a book (e.g., on unsubscribe)."""
        state = self._books.pop(ticker, None)
        if state is not None and state.sid is not None:
            bucket = self._sid_tickers.get(state.sid)
            if bucket is not None:
                bucket.discard(ticker)
                if not bucket:
                    self._sid_tickers.pop(state.sid, None)

    def tickers_for_sid(self, sid: int) -> set[str]:
        """Return a fresh set of tickers currently tracked under ``sid``."""
        bucket = self._sid_tickers.get(sid)
        return set(bucket) if bucket is not None else set()

    def remove_by_sid(self, sid: int) -> builtins.list[str]:
        """Remove every book associated with ``sid``. Returns removed tickers."""
        bucket = self._sid_tickers.pop(sid, None)
        if not bucket:
            return []
        removed: builtins.list[str] = []
        for ticker in bucket:
            if self._books.pop(ticker, None) is not None:
                removed.append(ticker)
        return removed

    def clear(self) -> None:
        """Remove all books (e.g., on reconnect before resubscribe)."""
        self._books.clear()
        self._sid_tickers.clear()
