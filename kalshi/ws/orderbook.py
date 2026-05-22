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

    ``sid`` records the server-assigned subscription id that produced this
    book's most recent snapshot. Used by
    :meth:`OrderbookManager.remove_by_sid` so all-markets subscriptions
    (no ``market_tickers`` param) can be cleanly torn down on gap recovery
    or unsubscribe without the caller having to know which tickers the
    server happened to forward through that sid.

    #244: ``_cached`` memoizes the materialized :class:`Orderbook` so the
    high-frequency ``subscribe_book`` iterator path doesn't pay an
    O(n log n) sort + 2N :class:`OrderbookLevel` validations + 1
    :class:`Orderbook` validation on every delta. The cache is invalidated
    by :meth:`_apply_delta_inplace` / :meth:`_apply_snapshot_inplace`
    whenever a side mutates. Identity-stable: consecutive ``get(ticker)``
    calls without intervening mutations return the *same* object.
    """

    ticker: str
    yes: dict[Decimal, Decimal] = field(default_factory=dict)
    no: dict[Decimal, Decimal] = field(default_factory=dict)
    sid: int | None = None
    # #244: lazy memoization of the materialized public Orderbook view.
    # ``None`` means "stale — rebuild on next read".
    _cached: Orderbook | None = field(default=None, repr=False, compare=False)

    def to_orderbook(self) -> Orderbook:
        """Build (or return cached) ``Orderbook`` snapshot from current state.

        Levels are emitted price-ascending to match the historical wire-order
        contract that the previous list-backed implementation maintained via
        ``list.sort`` after every insert. #244: the result is cached and
        invalidated only when ``_apply_*_inplace`` mutates a side.

        #327: levels are materialized via :meth:`BaseModel.model_construct`
        rather than the validating constructor. The ``yes`` / ``no`` dicts
        are already SDK-canonical (``Decimal`` price -> ``Decimal`` quantity)
        — they came either through ``_levels_to_dict`` on the snapshot wire
        decode or through arithmetic on already-validated Decimals in
        :meth:`OrderbookManager._apply_delta_inplace`. Re-running the
        per-level ``DollarDecimal`` / ``FixedPointCount`` validators on every
        materialization (O(n) cost on a hot path the #244 cache exists to
        protect) was pure overhead.
        """
        if self._cached is not None:
            return self._cached
        yes_levels = [
            OrderbookLevel.model_construct(price=price, quantity=qty)
            for price, qty in sorted(self.yes.items())
        ]
        no_levels = [
            OrderbookLevel.model_construct(price=price, quantity=qty)
            for price, qty in sorted(self.no.items())
        ]
        ob = Orderbook.model_construct(
            ticker=self.ticker, yes=yes_levels, no=no_levels
        )
        self._cached = ob
        return ob

    def invalidate(self) -> None:
        """Drop the cached :class:`Orderbook` view; next read re-materializes."""
        self._cached = None


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
    Input ``OrderbookSnapshotMessage`` arguments are also safe to reuse on
    the public API — see :meth:`apply_snapshot`. Raw
    ``subscribe_orderbook_delta`` consumers, which bypass this wrapper, see
    the live ``_BookState`` dicts; see :class:`OrderbookSnapshotPayload`.

    Per-sid tracking (:meth:`tickers_for_sid`, :meth:`remove_by_sid`) lets
    callers tear down all books owned by a subscription without enumerating
    tickers — critical for all-markets ``subscribe_orderbook_delta`` where
    the server picks which tickers to forward.

    Usage:
        mgr = OrderbookManager()
        book = mgr.apply_snapshot(snapshot_msg)  # Initialize
        book = mgr.apply_delta(delta_msg)         # Update
        book = mgr.get("TICKER")                   # Read current state
    """

    def __init__(self) -> None:
        self._books: dict[str, _BookState] = {}
        # sid -> set of tickers seeded by snapshots on that sid. Maintained
        # in lockstep with ``_books`` so ``remove_by_sid`` is O(k) in the
        # number of tickers owned by the sid, not O(n) over every book.
        self._sid_tickers: dict[int, set[str]] = {}

    def _install_snapshot(
        self,
        ticker: str,
        sid_val: int | None,
        yes: dict[Decimal, Decimal],
        no: dict[Decimal, Decimal],
    ) -> _BookState:
        """Replace the book for ``ticker`` with a freshly seeded state.

        The provided ``yes`` / ``no`` dicts are adopted by identity into
        the new :class:`_BookState`; the caller is responsible for
        defensive-copying when its input must not alias the manager's
        internal state. See :meth:`apply_snapshot` vs.
        :meth:`_apply_snapshot_inplace` for the two callers.
        """
        # If a prior book existed under a different sid (e.g. server moved
        # the ticker between subs), unindex it from the old sid first so
        # remove_by_sid on the stale id doesn't drop the live book.
        prior = self._books.get(ticker)
        if prior is not None and prior.sid is not None and prior.sid != sid_val:
            old_bucket = self._sid_tickers.get(prior.sid)
            if old_bucket is not None:
                old_bucket.discard(ticker)
                if not old_bucket:
                    self._sid_tickers.pop(prior.sid, None)

        state = _BookState(ticker=ticker, yes=yes, no=no, sid=sid_val)
        self._books[ticker] = state
        if sid_val is not None:
            bucket = self._sid_tickers.get(sid_val)
            if bucket is None:
                bucket = set()
                self._sid_tickers[sid_val] = bucket
            bucket.add(ticker)
        logger.debug(
            "Orderbook snapshot: %s (%d yes, %d no levels, sid=%s)",
            ticker,
            len(yes),
            len(no),
            sid_val,
        )
        return state

    def _apply_snapshot_inplace(
        self, msg: OrderbookSnapshotMessage, sid: int | None = None
    ) -> None:
        """In-place state mutation for a snapshot. No materialization.

        Recv-loop hot path entry point (#199). The public
        :meth:`apply_snapshot` wraps this with a ``to_orderbook()`` call
        for direct callers that still want a fully built ``Orderbook``.

        ``sid`` records which subscription produced this snapshot so the
        ticker can be torn down later via :meth:`remove_by_sid` — required
        for all-markets subscriptions that don't pin tickers up front.
        If omitted, defaults to ``msg.sid`` from the envelope.

        Ownership note: ``msg.msg.yes`` / ``.no`` are adopted by identity
        into the new ``_BookState``; callers must treat them as consumed.
        """
        sid_val = sid if sid is not None else msg.sid
        self._install_snapshot(
            msg.msg.market_ticker, sid_val, msg.msg.yes, msg.msg.no
        )

    def _apply_delta_inplace(self, msg: OrderbookDeltaMessage) -> bool:
        """In-place state mutation for a delta. No materialization.

        Returns True if the mutation was applied, False if no book exists
        for the ticker yet (delta arrived before snapshot — caller may
        choose to skip materializing in that case).
        """
        ticker = msg.msg.market_ticker
        state = self._books.get(ticker)
        if state is None:
            logger.warning("Delta for unknown ticker %s (no snapshot yet)", ticker)
            return False

        price = msg.msg.price  # Decimal via DollarDecimal
        delta = msg.msg.delta  # Decimal via FixedPointCount
        side = msg.msg.side

        levels = state.yes if side == "yes" else state.no
        existing_qty = levels.get(price)

        if existing_qty is not None:
            new_qty = existing_qty + delta
            if new_qty <= 0:
                del levels[price]
                # #244: a side mutated; drop the cached Orderbook view so
                # the next `to_orderbook`/`get` rebuilds with the new side.
                state.invalidate()
            elif new_qty != existing_qty:
                levels[price] = new_qty
                state.invalidate()
            # #347: ``delta == 0`` (or otherwise nets to no change) leaves
            # the price-level dict identical; preserve the #244 cache so
            # consumers polling ``get()`` keep getting the same instance.
        elif delta > 0:
            levels[price] = delta
            state.invalidate()
        # #347: ``delta <= 0`` at a non-existent level is a no-op too —
        # the original code already skipped invalidation here; keep it so.

        return True

    def apply_snapshot(self, msg: OrderbookSnapshotMessage, sid: int | None = None) -> Orderbook:
        """Initialize (or reset) a book from a full snapshot.

        Public wrapper: seeds the book with a defensive single-copy of the
        caller's ``msg.msg.yes`` / ``.no`` dicts and materializes a fresh
        :class:`Orderbook`. The recv loop bypasses this and calls
        :meth:`_apply_snapshot_inplace` directly to avoid both the
        defensive copy and the O(n log n) materialization (#199, #296).

        ``msg`` is safe to reuse after this call: the manager owns the
        copied dicts, so subsequent delta mutations cannot leak back
        through ``msg.msg.yes`` / ``.no``.

        #344: previously this routed through ``_apply_snapshot_inplace``
        (which identity-adopts) and then overwrote ``state.yes`` / ``.no``
        with a ``dict(...)`` copy — two assignments per side for one
        useful copy. We now install the copies directly via
        :meth:`_install_snapshot`, so each side is materialized into the
        ``_BookState`` exactly once.
        """
        sid_val = sid if sid is not None else msg.sid
        state = self._install_snapshot(
            msg.msg.market_ticker,
            sid_val,
            dict(msg.msg.yes),
            dict(msg.msg.no),
        )
        return state.to_orderbook()

    def apply_delta(self, msg: OrderbookDeltaMessage) -> Orderbook | None:
        """Apply an incremental delta to an existing book.

        Public wrapper. Returns the materialized Orderbook on success or
        None if no book exists for the ticker. The recv loop bypasses this
        and calls :meth:`_apply_delta_inplace` directly (#199).
        """
        if not self._apply_delta_inplace(msg):
            return None
        state = self._books.get(msg.msg.market_ticker)
        return state.to_orderbook() if state else None

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
        state = self._books.pop(ticker, None)
        if state is not None and state.sid is not None:
            bucket = self._sid_tickers.get(state.sid)
            if bucket is not None:
                bucket.discard(ticker)
                if not bucket:
                    self._sid_tickers.pop(state.sid, None)

    def tickers_for_sid(self, sid: int) -> set[str]:
        """Return tickers currently tracked under ``sid``.

        Returns a fresh set; mutating the returned value does not affect
        the manager's internal state.
        """
        bucket = self._sid_tickers.get(sid)
        return set(bucket) if bucket is not None else set()

    def remove_by_sid(self, sid: int) -> list[str]:
        """Remove every book associated with ``sid``.

        Returns the tickers that were removed (empty if the sid was
        unknown). Used by the gap-recovery and unsubscribe paths so a
        single call tears down all per-sid local state, including
        all-markets subscriptions where the caller didn't know which
        tickers the server would forward.
        """
        bucket = self._sid_tickers.pop(sid, None)
        if not bucket:
            return []
        removed: list[str] = []
        for ticker in bucket:
            if self._books.pop(ticker, None) is not None:
                removed.append(ticker)
        return removed

    def clear(self) -> None:
        """Remove all books (e.g., on reconnect before resubscribe)."""
        self._books.clear()
        self._sid_tickers.clear()
