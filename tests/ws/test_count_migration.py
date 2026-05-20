"""Verify REST order count fields use FixedPointCount (Decimal)."""

from __future__ import annotations

from decimal import Decimal

from kalshi.models.orders import CreateOrderRequest, Order
from tests._model_fixtures import order_dict


class TestOrderCountMigration:
    def test_order_count_is_decimal(self) -> None:
        order = Order.model_validate(order_dict(count="100.00"))
        assert isinstance(order.count, Decimal)
        assert order.count == Decimal("100.00")

    def test_order_count_accepts_int(self) -> None:
        order = Order.model_validate(order_dict(count=42))
        assert isinstance(order.count, Decimal)
        assert order.count == Decimal("42")

    def test_order_count_fp_alias(self) -> None:
        order = Order.model_validate(order_dict(count_fp="50.00"))
        assert order.count == Decimal("50.00")

    def test_initial_count_fp_alias(self) -> None:
        order = Order.model_validate(order_dict(initial_count_fp="25.00"))
        assert order.initial_count == Decimal("25.00")

    def test_remaining_count_fp_alias(self) -> None:
        order = Order.model_validate(order_dict(remaining_count_fp="10.00"))
        assert order.remaining_count == Decimal("10.00")

    def test_fill_count_fp_alias(self) -> None:
        order = Order.model_validate(order_dict(fill_count_fp="15.00"))
        assert order.fill_count == Decimal("15.00")

    def test_create_order_count_is_decimal(self) -> None:
        req = CreateOrderRequest(ticker="ECON-GDP", side="yes", count=Decimal("10"), action="buy")
        assert isinstance(req.count, Decimal)

    def test_create_order_count_default(self) -> None:
        req = CreateOrderRequest(ticker="ECON-GDP", side="yes", action="buy")
        assert req.count == Decimal("1")
        assert isinstance(req.count, Decimal)

    def test_create_order_count_serializes(self) -> None:
        req = CreateOrderRequest(ticker="ECON-GDP", side="yes", count=Decimal("10"), action="buy")
        data = req.model_dump(mode="json")
        assert isinstance(data["count"], str)
