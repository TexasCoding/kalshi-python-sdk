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

class TestSnapshotIdentityAdoption:
    """Regression for #296: ``_apply_snapshot_inplace`` must adopt the
    validator-built ``dict[Decimal, Decimal]`` by identity (no rebuild).

    The CHANGELOG v2.5.0 #263 claim is "snapshot apply collapses to a single
    dict walk"; if a future refactor reintroduces a ``dict(...)`` copy, this
    test fails immediately rather than silently regressing recv-loop perf.
    """

    def test_snapshot_adopts_validated_dicts_by_identity(self) -> None:
        mgr = OrderbookManager()
        # Build with Decimal-keyed dicts directly so the validator's
        # identity fast-path engages (see ``_levels_to_dict``).
        yes_in: dict[Decimal, Decimal] = {Decimal("0.50"): Decimal("100.00")}
        no_in: dict[Decimal, Decimal] = {Decimal("0.45"): Decimal("150.00")}
        msg = OrderbookSnapshotMessage.model_validate(
            {
                "type": "orderbook_snapshot",
                "sid": 1,
                "seq": 1,
                "msg": {
                    "market_ticker": "T",
                    "market_id": "id",
                    "yes": yes_in,
                    "no": no_in,
                },
            }
        )
        # We don't assert state.yes is yes_in (Pydantic may copy the input during
        # field binding), but we DO assert state.yes is msg.msg.yes: the SDK must
        # adopt the already-validated dict without adding another dict() copy.
        mgr._apply_snapshot_inplace(msg)
        state = mgr._books["T"]
        assert state.yes is msg.msg.yes
        assert state.no is msg.msg.no

    def test_delta_mutates_in_place_and_invalidates_cache(self) -> None:
        mgr = OrderbookManager()
        yes_in: dict[Decimal, Decimal] = {Decimal("0.50"): Decimal("100.00")}
        msg = OrderbookSnapshotMessage.model_validate(
            {
                "type": "orderbook_snapshot",
                "sid": 1,
                "seq": 1,
                "msg": {
                    "market_ticker": "T",
                    "market_id": "id",
                    "yes": yes_in,
                    "no": {},
                },
            }
        )
        mgr._apply_snapshot_inplace(msg)
        state = mgr._books["T"]
        adopted_yes = state.yes
        # Materialize once to populate the #244 cache.
        cached = state.to_orderbook()
        assert state._cached is cached

        applied = mgr._apply_delta_inplace(
            make_delta(price="0.50", delta="25", side="yes")
        )
        assert applied is True
        # In-place mutation: the dict instance is unchanged, the value moved.
        assert state.yes is adopted_yes
        assert state.yes[Decimal("0.50")] == Decimal("125.00")
        # The cache was invalidated so the next read re-materializes.
        assert state._cached is None

    def test_subscriber_held_snapshot_dict_mutates_on_delta(self) -> None:
        """Documents the live-dict contract for raw ``subscribe_orderbook_delta`` consumers."""
        mgr = OrderbookManager()
        yes_in: dict[Decimal, Decimal] = {Decimal("0.50"): Decimal("100.00")}
        no_in: dict[Decimal, Decimal] = {Decimal("0.45"): Decimal("150.00")}
        msg = OrderbookSnapshotMessage.model_validate(
            {
                "type": "orderbook_snapshot",
                "sid": 1,
                "seq": 1,
                "msg": {
                    "market_ticker": "T",
                    "market_id": "id",
                    "yes": yes_in,
                    "no": no_in,
                },
            }
        )
        mgr._apply_snapshot_inplace(msg)
        # A raw subscriber who stored ``msg.msg.yes`` after receiving the snapshot
        # frame is holding the live ``_BookState`` dict; the next delta mutates it.
        held_yes = msg.msg.yes
        applied = mgr._apply_delta_inplace(
            make_delta(price="0.60", delta="25", side="yes")
        )
        assert applied is True
        assert Decimal("0.60") in held_yes
        assert held_yes[Decimal("0.60")] == Decimal("25.00")
        assert held_yes is mgr._books["T"].yes

    def test_public_apply_snapshot_does_not_alias_input_msg(self) -> None:
        """Public apply_snapshot must defensively copy so the caller's msg is not aliased."""
        snapshot_payload = {
            "type": "orderbook_snapshot",
            "sid": 7,
            "seq": 1,
            "msg": {
                "market_ticker": "PUB-T",
                "market_id": "id",
                "yes": {Decimal("0.30"): Decimal("5")},
                "no": {Decimal("0.70"): Decimal("3")},
            },
        }
        msg = OrderbookSnapshotMessage.model_validate(snapshot_payload)
        held_yes = msg.msg.yes

        mgr = OrderbookManager()
        mgr.apply_snapshot(msg)

        # Public path: state must NOT share identity with the caller's msg.
        state = mgr._books["PUB-T"]
        assert state.yes is not held_yes
        assert state.no is not msg.msg.no
        assert state.yes == {Decimal("0.30"): Decimal("5")}

        # A subsequent delta mutates state but leaves the caller's msg dict untouched.
        delta = OrderbookDeltaMessage.model_validate({
            "type": "orderbook_delta",
            "sid": 7,
            "seq": 2,
            "msg": {
                "market_ticker": "PUB-T",
                "market_id": "id",
                "price": Decimal("0.30"),
                "delta": Decimal("4"),
                "side": "yes",
            },
        })
        mgr.apply_delta(delta)
        assert state.yes[Decimal("0.30")] == Decimal("9")
        # Caller's held reference is untouched — the public-API safety contract.
        assert held_yes[Decimal("0.30")] == Decimal("5")


class TestWave2CorrectnessRegressions:
    """Round-3 W2 perf-correctness regressions for #327, #344, #347."""

    def test_issue_327_to_orderbook_no_revalidation(
        self, monkeypatch: object
    ) -> None:
        """``_BookState.to_orderbook`` materializes via ``model_construct``.

        The validating constructors (``OrderbookLevel(...)`` /
        ``Orderbook(...)``) re-run the per-level ``DollarDecimal`` /
        ``FixedPointCount`` validators on data that is already SDK-canonical
        — wasted work on the high-frequency ``subscribe_book`` path that
        the #244 cache exists to protect.

        We spy on the validating ``__init__`` methods (which Pydantic's
        ``model_construct`` bypasses) and assert zero calls during a
        ``apply_snapshot`` + ``apply_delta`` cycle.
        """
        import pytest

        from kalshi.models.markets import Orderbook, OrderbookLevel
        from kalshi.ws import orderbook as ob_mod

        calls = {"level": 0, "ob": 0}
        orig_level_init = OrderbookLevel.__init__
        orig_ob_init = Orderbook.__init__

        def spy_level_init(self: object, **kw: object) -> None:
            calls["level"] += 1
            orig_level_init(self, **kw)  # type: ignore[arg-type]

        def spy_ob_init(self: object, **kw: object) -> None:
            calls["ob"] += 1
            orig_ob_init(self, **kw)  # type: ignore[arg-type]

        mp = pytest.MonkeyPatch()
        mp.setattr(OrderbookLevel, "__init__", spy_level_init)
        mp.setattr(Orderbook, "__init__", spy_ob_init)
        try:
            mgr = ob_mod.OrderbookManager()
            book = mgr.apply_snapshot(
                make_snapshot(
                    yes=[["0.50", "100"], ["0.55", "200"], ["0.60", "300"]],
                    no=[["0.40", "150"], ["0.35", "75"]],
                )
            )
            assert len(book.yes) == 3 and len(book.no) == 2
            # Force re-materialization by invalidating and reading again.
            delta_book = mgr.apply_delta(
                make_delta(price="0.50", delta="50", side="yes")
            )
            assert delta_book is not None
        finally:
            mp.undo()

        assert (
            calls["level"] == 0
        ), f"OrderbookLevel validating __init__ ran {calls['level']} times"
        assert (
            calls["ob"] == 0
        ), f"Orderbook validating __init__ ran {calls['ob']} times"

    def test_issue_344_apply_snapshot_public_single_copy(self) -> None:
        """Public ``apply_snapshot`` assigns each side dict exactly once.

        Pre-fix the public path identity-adopted ``msg.msg.yes`` / ``.no``
        via :meth:`_apply_snapshot_inplace` and then overwrote with
        ``dict(msg.msg.yes)`` / ``dict(msg.msg.no)`` — two assignments
        per side for one useful copy. We spy on ``_BookState.__setattr__``
        and assert exactly one ``yes`` and one ``no`` assignment.
        """
        import pytest

        from kalshi.ws import orderbook as ob_mod

        side_assignments: list[tuple[str, int]] = []
        orig_setattr = ob_mod._BookState.__setattr__

        def spy_setattr(self: object, name: str, value: object) -> None:
            if name in ("yes", "no"):
                side_assignments.append((name, id(value)))
            orig_setattr(self, name, value)  # type: ignore[arg-type]

        mp = pytest.MonkeyPatch()
        mp.setattr(ob_mod._BookState, "__setattr__", spy_setattr)
        try:
            msg = make_snapshot(
                yes=[["0.50", "100"], ["0.55", "200"]],
                no=[["0.45", "150"]],
            )
            mgr = ob_mod.OrderbookManager()
            book = mgr.apply_snapshot(msg)
            assert book.ticker == "T"
        finally:
            mp.undo()

        yes_assigns = [a for a in side_assignments if a[0] == "yes"]
        no_assigns = [a for a in side_assignments if a[0] == "no"]
        assert (
            len(yes_assigns) == 1
        ), f"expected 1 yes assignment, got {len(yes_assigns)}: {yes_assigns}"
        assert (
            len(no_assigns) == 1
        ), f"expected 1 no assignment, got {len(no_assigns)}: {no_assigns}"

        # And the defensive-copy contract still holds.
        state = mgr._books["T"]
        assert state.yes is not msg.msg.yes
        assert state.no is not msg.msg.no
        assert state.yes == {Decimal("0.50"): Decimal("100"), Decimal("0.55"): Decimal("200")}

    def test_issue_347_zero_delta_preserves_cache(self) -> None:
        """A delta that nets to no change must not invalidate the #244 cache.

        ``_apply_delta_inplace`` previously called ``state.invalidate()``
        unconditionally when the level already existed, even when ``delta``
        was zero (``new_qty == existing_qty``). Cache-identity for a
        no-op delta is preserved by post-fix.
        """
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.50", "100"]]))
        state = mgr._books["T"]

        # Populate the #244 cache.
        first = mgr.get("T")
        assert first is not None
        cached = state._cached
        assert cached is first

        # Apply a zero delta: the dict must be byte-identical afterward.
        before_snapshot = dict(state.yes)
        result = mgr.apply_delta(make_delta(price="0.50", delta="0", side="yes"))
        assert result is not None
        assert state.yes == before_snapshot

        # Cache MUST be preserved across the zero-delta and identity-stable
        # on subsequent reads.
        assert state._cached is cached, "zero delta should not invalidate cache"
        assert result is cached
        again = mgr.get("T")
        assert again is cached

        # A non-zero delta still invalidates (control case).
        mgr.apply_delta(make_delta(price="0.50", delta="5", side="yes"))
        fresh = mgr.get("T")
        assert fresh is not None
        assert fresh is not cached
        assert fresh.yes[0].quantity == Decimal("105")

    def test_issue_347_zero_delta_at_missing_level_preserves_cache(self) -> None:
        """A non-positive delta at a missing price level is also a no-op."""
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.50", "100"]]))
        state = mgr._books["T"]
        first = mgr.get("T")
        assert first is not None
        cached = state._cached
        assert cached is first

        # Delta of 0 at a price we don't track: previously already a no-op,
        # codify that the cache continues to ride through.
        mgr.apply_delta(make_delta(price="0.99", delta="0", side="yes"))
        assert state._cached is cached
        again = mgr.get("T")
        assert again is cached
