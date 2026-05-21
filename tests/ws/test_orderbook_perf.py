"""Regression tests for #244 — OrderbookManager.get caches materialized view.

#244: every ``orderbook_delta`` consumed via the high-level
``subscribe_book`` iterator previously paid an O(n log n) sort + 2N
``OrderbookLevel`` validations + 1 ``Orderbook`` validation per delta.
``_BookState.to_orderbook`` now memoizes the result and only rebuilds
when ``_apply_*_inplace`` invalidates the cache.

Smoke tests, not microbenches: assert object identity to prove no
re-validation happens between mutations, and assert identity-bust
across mutations so stale data is never served.
"""
from __future__ import annotations

from decimal import Decimal

from kalshi.ws.orderbook import OrderbookManager
from tests.ws.test_orderbook import make_delta, make_snapshot


class TestOrderbookCaching:
    def test_consecutive_get_returns_same_object_identity(self) -> None:
        mgr = OrderbookManager()
        mgr._apply_snapshot_inplace(
            make_snapshot(yes=[["0.50", "100"]], no=[["0.50", "50"]])
        )
        first = mgr.get("T")
        second = mgr.get("T")
        third = mgr.get("T")
        assert first is not None
        # #244: identity-stable — no re-materialization without mutation.
        assert first is second
        assert second is third

    def test_delta_invalidates_cache(self) -> None:
        mgr = OrderbookManager()
        mgr._apply_snapshot_inplace(
            make_snapshot(yes=[["0.50", "100"]])
        )
        before = mgr.get("T")
        # Apply a delta that mutates the yes side.
        mgr._apply_delta_inplace(
            make_delta(price="0.51", delta="10", side="yes")
        )
        after = mgr.get("T")
        # Identity MUST differ — cache was invalidated.
        assert before is not after
        # And the new view sees the new level.
        assert any(lvl.price == Decimal("0.51") for lvl in after.yes)  # type: ignore[union-attr]

    def test_snapshot_resets_cache(self) -> None:
        mgr = OrderbookManager()
        mgr._apply_snapshot_inplace(make_snapshot(yes=[["0.50", "100"]]))
        first = mgr.get("T")
        # Re-snapshot replaces state entirely; new state has fresh cache.
        mgr._apply_snapshot_inplace(make_snapshot(yes=[["0.60", "200"]], seq=2))
        second = mgr.get("T")
        assert first is not second
        assert any(lvl.price == Decimal("0.60") for lvl in second.yes)  # type: ignore[union-attr]

    def test_public_apply_delta_returns_cached_view(self) -> None:
        """``apply_delta`` is identity-stable with subsequent ``get`` calls."""
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.50", "100"]]))
        after_delta = mgr.apply_delta(
            make_delta(price="0.51", delta="10", side="yes")
        )
        from_get = mgr.get("T")
        assert after_delta is from_get
