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
    return OrderbookSnapshotMessage.model_validate({
        "type": "orderbook_snapshot",
        "sid": 1,
        "seq": seq,
        "msg": {
            "market_ticker": ticker,
            "market_id": "id",
            "yes": yes or [],
            "no": no or [],
        },
    })


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

    def test_fractional_delta_matches_wire_format(self) -> None:
        """Live capture on demo shows delta_fp arrives as ``"1.00"`` (with
        trailing .00), not bare ``"1"``. Lock in that Decimal arithmetic
        handles the mixed-precision case cleanly.
        """
        mgr = OrderbookManager()
        mgr.apply_snapshot(make_snapshot(yes=[["0.0100", "0.00"]]))
        book = mgr.apply_delta(
            make_delta(price="0.0100", delta="1.00", side="yes")
        )
        assert book is not None
        # Decimal("0.00") + Decimal("1.00") == Decimal("1.00"), not Decimal("1")
        assert book.yes[0].quantity == Decimal("1.00")
        assert book.yes[0].price == Decimal("0.0100")
