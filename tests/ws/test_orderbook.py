"""Tests for OrderbookManager."""

from __future__ import annotations

from decimal import Decimal

from kalshi.ws.models.orderbook_delta import (
    OrderbookDeltaMessage,
    OrderbookDeltaPayload,
    OrderbookSnapshotMessage,
)
from kalshi.ws.orderbook import OrderbookManager


def make_snapshot(
    ticker: str = "T",
    yes: list[list[str]] | None = None,
    no: list[list[str]] | None = None,
    seq: int = 1,
) -> OrderbookSnapshotMessage:
    # Go through model_validate so Pydantic handles the list→tuple coercion
    # that ``OrderbookSnapshotPayload.yes/no: list[tuple[str, str]]`` expects.
    # Callers pass list-of-list literals for readability; direct constructor
    # arguments would trip mypy strict on the list vs tuple mismatch.
    return OrderbookSnapshotMessage.model_validate(
        {
            "type": "orderbook_snapshot",
            "sid": 1,
            "seq": seq,
            "msg": {
                "market_ticker": ticker,
                "market_id": "id",
                "yes": yes or [],
                "no": no or [],
            },
        }
    )


def make_delta(
    ticker: str = "T",
    price: str = "0.50",
    delta: str = "10",
    side: str = "yes",
    seq: int = 2,
) -> OrderbookDeltaMessage:
    return OrderbookDeltaMessage(
        type="orderbook_delta",
        sid=1,
        seq=seq,
        msg=OrderbookDeltaPayload(
            market_ticker=ticker,
            market_id="id",
            price=Decimal(price),
            delta=Decimal(delta),
            side=side,
        ),
    )


class TestOrderbookManager:
    def test_apply_snapshot(self) -> None:
        mgr = OrderbookManager()
        book = mgr.apply_snapshot(
            make_snapshot(
                yes=[["0.50", "100.00"], ["0.55", "200.00"]],
                no=[["0.45", "150.00"]],
            )
        )
        assert book.ticker == "T"
        assert len(book.yes) == 2
        assert len(book.no) == 1
        assert book.yes[0].price == Decimal("0.50")
        assert book.yes[0].quantity == Decimal("100.00")
        assert book.yes[1].price == Decimal("0.55")

    def test_apply_delta_add_quantity(self) -> None:
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.50", "100"]]))
        book = mgr.apply_delta(make_delta(price="0.50", delta="50", side="yes"))
        assert book is not None
        assert len(book.yes) == 1
        assert book.yes[0].quantity == Decimal("150")

    def test_apply_delta_remove_level(self) -> None:
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.50", "100"]]))
        book = mgr.apply_delta(make_delta(price="0.50", delta="-100", side="yes"))
        assert book is not None
        assert len(book.yes) == 0  # level removed

    def test_apply_delta_new_price_level(self) -> None:
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.50", "100"]]))
        book = mgr.apply_delta(make_delta(price="0.60", delta="200", side="yes"))
        assert book is not None
        assert len(book.yes) == 2
        prices = [level.price for level in book.yes]
        assert prices == [Decimal("0.50"), Decimal("0.60")]  # sorted

    def test_apply_delta_no_side(self) -> None:
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(no=[["0.45", "100"]]))
        book = mgr.apply_delta(make_delta(price="0.45", delta="50", side="no"))
        assert book is not None
        assert book.no[0].quantity == Decimal("150")

    def test_delta_before_snapshot_returns_none(self) -> None:
        mgr = OrderbookManager()
        result = mgr.apply_delta(make_delta(ticker="UNKNOWN"))
        assert result is None

    def test_get_existing_book(self) -> None:
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(ticker="A"))
        assert mgr.get("A") is not None
        assert mgr.get("B") is None

    def test_remove_book(self) -> None:
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(ticker="A"))
        mgr.remove("A")
        assert mgr.get("A") is None

    def test_clear_all(self) -> None:
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(ticker="A"))
        mgr.apply_snapshot(make_snapshot(ticker="B"))
        mgr.clear()
        assert mgr.get("A") is None
        assert mgr.get("B") is None

    def test_snapshot_replaces_existing(self) -> None:
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.50", "100"]]))
        mgr.apply_snapshot(make_snapshot(yes=[["0.60", "200"]]))  # replaces
        book = mgr.get("T")
        assert book is not None
        assert len(book.yes) == 1
        assert book.yes[0].price == Decimal("0.60")

    def test_empty_snapshot(self) -> None:
        mgr = OrderbookManager()
        book = mgr.apply_snapshot(make_snapshot())
        assert book.yes == []
        assert book.no == []

    def test_many_deltas(self) -> None:
        """Apply 100 deltas and verify the book is consistent."""
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.50", "1000"]]))
        for i in range(100):
            mgr.apply_delta(make_delta(price="0.50", delta="1", side="yes", seq=i + 2))
        book = mgr.get("T")
        assert book is not None
        assert book.yes[0].quantity == Decimal("1100")  # 1000 + 100

    def test_negative_delta_partial(self) -> None:
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.50", "100"]]))
        book = mgr.apply_delta(make_delta(price="0.50", delta="-30", side="yes"))
        assert book is not None
        assert book.yes[0].quantity == Decimal("70")  # 100 - 30

    def test_returned_book_is_snapshot_not_live_view(self) -> None:
        """Regression for #85: a book handed to a consumer must not mutate
        when subsequent deltas are applied.

        Post-#244 the materialized view is cached on ``_BookState`` and
        only rebuilt when ``_apply_*_inplace`` invalidates it. The
        mutation-safety invariant is preserved at the *value* level:
        previously-handed-out books are immutable snapshots whose lists
        the manager never touches. Identity between concurrent reads is
        now a side-effect of caching, not a contract.
        """
        mgr = OrderbookManager()
        snap_book = mgr.apply_snapshot(make_snapshot(yes=[["0.50", "100"]]))

        # Apply a delta that would have mutated the level in-place under the
        # old implementation (quantity 100 -> 150).
        delta_book = mgr.apply_delta(make_delta(price="0.50", delta="50", side="yes"))
        assert delta_book is not None

        # Different snapshot generations -> different instances.
        assert snap_book is not delta_book
        # The first-handed-out book is frozen at its emission-time state.
        assert snap_book.yes[0].quantity == Decimal("100")
        assert delta_book.yes[0].quantity == Decimal("150")

        # ``get()`` returns the current cached view (== delta_book here),
        # but a *subsequent* delta must not mutate it in place.
        get_book = mgr.get("T")
        assert get_book is not None
        mgr.apply_delta(make_delta(price="0.50", delta="25", side="yes"))
        assert get_book.yes[0].quantity == Decimal("150")  # unchanged
        # And the next get re-materializes with the new state.
        fresh = mgr.get("T")
        assert fresh is not None
        assert fresh is not get_book
        assert fresh.yes[0].quantity == Decimal("175")

    def test_apply_delta_is_constant_time_in_book_depth(self) -> None:
        """Regression for #87: apply_delta must touch at most a constant
        number of levels per delta, not scan the whole book.

        We swap the internal price->qty mapping for a counting dict that
        records every key access (``get`` / ``__getitem__`` /
        ``__setitem__`` / ``__delitem__`` / ``__contains__``). The old
        list-scan implementation iterated the level container once per
        level (O(n) accesses); the new dict-backed implementation does
        O(1) accesses regardless of book depth.

        This is an *invariant* test (access count grows like O(1), not
        O(n)), not a wall-clock budget -- stable on slow CI.
        """
        from kalshi.ws.orderbook import _BookState

        class CountingDict(dict[Decimal, Decimal]):
            def __init__(self, *a: object, **kw: object) -> None:
                super().__init__(*a, **kw)  # type: ignore[arg-type]
                self.accesses = 0

            def get(self, key: object, default: object = None) -> object:  # type: ignore[override]
                self.accesses += 1
                return super().get(key, default)  # type: ignore[arg-type]

            def __getitem__(self, key: Decimal) -> Decimal:
                self.accesses += 1
                return super().__getitem__(key)

            def __setitem__(self, key: Decimal, value: Decimal) -> None:
                self.accesses += 1
                super().__setitem__(key, value)

            def __delitem__(self, key: Decimal) -> None:
                self.accesses += 1
                super().__delitem__(key)

            def __contains__(self, key: object) -> bool:
                self.accesses += 1
                return super().__contains__(key)

        # Two probe sizes -- a small book and a large book. If the
        # implementation is O(n), the second number is ~50x the first.
        # If O(1), they're identical.
        def measure(n: int) -> int:
            mgr = OrderbookManager()
            mgr.apply_snapshot(make_snapshot(yes=[[f"0.{i:04d}", "100"] for i in range(1, n + 1)]))
            counting = CountingDict(mgr._books["T"].yes)
            mgr._books["T"] = _BookState(ticker="T", yes=counting, no=mgr._books["T"].no)
            mgr.apply_delta(make_delta(price=f"0.{n // 2:04d}", delta="1", side="yes"))
            return counting.accesses

        small = measure(10)
        large = measure(500)

        # Allow generous slack but reject anything that scales with n.
        # O(1) -> equal counts; O(n) -> large is ~50x small.
        assert large <= small + 2, (
            f"apply_delta access count grew from {small} (n=10) to "
            f"{large} (n=500) -- expected O(1), looks O(n)"
        )

    def test_fractional_delta_matches_wire_format(self) -> None:
        """Live capture on demo shows delta_fp arrives as ``"1.00"`` (with
        trailing .00), not bare ``"1"``. Lock in that Decimal arithmetic
        handles the mixed-precision case cleanly.
        """
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.0100", "0.00"]]))
        book = mgr.apply_delta(make_delta(price="0.0100", delta="1.00", side="yes"))
        assert book is not None
        # Decimal("0.00") + Decimal("1.00") == Decimal("1.00"), not Decimal("1")
        assert book.yes[0].quantity == Decimal("1.00")
        assert book.yes[0].price == Decimal("0.0100")


class TestOrderbookManagerInplace:
    """#199: in-place variants used by the recv loop to avoid the
    O(n log n) sort + 2N OrderbookLevel allocation that the public
    ``apply_*`` wrappers perform.
    """

    def test_apply_snapshot_inplace_returns_none_and_mutates(self) -> None:
        mgr = OrderbookManager()
        snap = make_snapshot(
            yes=[["0.50", "100.00"], ["0.55", "200.00"]],
            no=[["0.45", "50.00"]],
        )
        result = mgr._apply_snapshot_inplace(snap)
        assert result is None
        # State should be mutated; ``get`` materializes on demand.
        book = mgr.get("T")
        assert book is not None
        assert len(book.yes) == 2
        assert len(book.no) == 1

    def test_apply_snapshot_inplace_records_sid(self) -> None:
        mgr = OrderbookManager()
        snap = make_snapshot(yes=[["0.50", "100.00"]])
        mgr._apply_snapshot_inplace(snap, sid=snap.sid)
        assert mgr.tickers_for_sid(snap.sid) == {"T"}

    def test_apply_delta_inplace_returns_true_on_known_ticker(self) -> None:
        mgr = OrderbookManager()
        mgr._apply_snapshot_inplace(make_snapshot(yes=[["0.50", "10.00"]]))
        ok = mgr._apply_delta_inplace(make_delta(price="0.50", delta="5.00", side="yes"))
        assert ok is True
        book = mgr.get("T")
        assert book is not None
        assert book.yes[0].quantity == Decimal("15.00")

    def test_apply_delta_inplace_returns_false_for_unknown_ticker(self) -> None:
        mgr = OrderbookManager()
        ok = mgr._apply_delta_inplace(make_delta(ticker="OTHER", price="0.50", delta="5.00"))
        assert ok is False

    def test_apply_delta_inplace_does_not_call_to_orderbook(
        self,
        monkeypatch: object,
    ) -> None:
        """Hot-path invariant: the in-place variant MUST NOT materialize
        an Orderbook. Spy on ``_BookState.to_orderbook`` and assert zero
        calls during a snapshot+delta cycle through the in-place API.
        """
        from kalshi.ws import orderbook as ob_mod

        calls: list[str] = []
        orig = ob_mod._BookState.to_orderbook

        def spy(self):  # type: ignore[no-untyped-def]
            calls.append(self.ticker)
            return orig(self)

        monkeypatch.setattr(ob_mod._BookState, "to_orderbook", spy)  # type: ignore[attr-defined]

        mgr = OrderbookManager()
        mgr._apply_snapshot_inplace(make_snapshot(yes=[["0.50", "10.00"]]))
        for _ in range(5):
            mgr._apply_delta_inplace(make_delta(price="0.50", delta="1.00", side="yes"))
        assert calls == []

    def test_public_apply_delta_still_returns_orderbook(self) -> None:
        """Back-compat: direct callers of the public ``apply_delta`` still
        get a fully materialized Orderbook.
        """
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.50", "10.00"]]))
        book = mgr.apply_delta(make_delta(price="0.50", delta="1.00", side="yes"))
        assert book is not None
        assert book.yes[0].quantity == Decimal("11.00")

    def test_public_apply_delta_returns_none_for_unknown_ticker(self) -> None:
        mgr = OrderbookManager()
        result = mgr.apply_delta(make_delta(ticker="UNK"))
        assert result is None

    def test_public_apply_snapshot_returns_orderbook(self) -> None:
        mgr = OrderbookManager()
        book = mgr.apply_snapshot(make_snapshot(yes=[["0.10", "5.00"]], no=[["0.90", "5.00"]]))
        assert book is not None
        assert book.ticker == "T"
        assert len(book.yes) == 1
        assert len(book.no) == 1
