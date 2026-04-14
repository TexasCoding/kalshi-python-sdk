"""Verify REST order count fields use FixedPointCount (Decimal)."""
from __future__ import annotations

from decimal import Decimal

from kalshi.models.orders import CreateOrderRequest, Order


class TestOrderCountMigration:
    def test_order_count_is_decimal(self) -> None:
        order = Order.model_validate({"order_id": "abc", "count": "100.00"})
        assert isinstance(order.count, Decimal)
        assert order.count == Decimal("100.00")

    def test_order_count_accepts_int(self) -> None:
        order = Order.model_validate({"order_id": "abc", "count": 42})
        assert isinstance(order.count, Decimal)
        assert order.count == Decimal("42")

    def test_order_count_fp_alias(self) -> None:
        order = Order.model_validate({"order_id": "abc", "count_fp": "50.00"})
        assert order.count == Decimal("50.00")

    def test_initial_count_fp_alias(self) -> None:
        order = Order.model_validate({"order_id": "abc", "initial_count_fp": "25.00"})
        assert order.initial_count == Decimal("25.00")

    def test_remaining_count_fp_alias(self) -> None:
        order = Order.model_validate({"order_id": "abc", "remaining_count_fp": "10.00"})
        assert order.remaining_count == Decimal("10.00")

    def test_fill_count_fp_alias(self) -> None:
        order = Order.model_validate({"order_id": "abc", "fill_count_fp": "15.00"})
        assert order.fill_count == Decimal("15.00")

    def test_create_order_count_is_decimal(self) -> None:
        req = CreateOrderRequest(ticker="ECON-GDP", side="yes", count=Decimal("10"))
        assert isinstance(req.count, Decimal)

    def test_create_order_count_default(self) -> None:
        req = CreateOrderRequest(ticker="ECON-GDP", side="yes")
        assert req.count == Decimal("1")
        assert isinstance(req.count, Decimal)

    def test_create_order_count_serializes(self) -> None:
        req = CreateOrderRequest(ticker="ECON-GDP", side="yes", count=Decimal("10"))
        data = req.model_dump(mode="json")
        assert isinstance(data["count"], str)
