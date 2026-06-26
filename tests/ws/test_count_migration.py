"""Verify REST order count fields use FixedPointCount (Decimal)."""

from __future__ import annotations

from decimal import Decimal

from kalshi.models.orders import CreateOrderV2Request, Order
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
        req = CreateOrderV2Request(
            ticker="ECON-GDP",
            client_order_id="cli-1",
            side="bid",
            count=Decimal("10"),
            price=Decimal("0.50"),
            time_in_force="good_till_canceled",
            self_trade_prevention_type="taker_at_cross",
        )
        assert isinstance(req.count, Decimal)

    def test_create_order_count_serializes(self) -> None:
        req = CreateOrderV2Request(
            ticker="ECON-GDP",
            client_order_id="cli-1",
            side="bid",
            count=Decimal("10"),
            price=Decimal("0.50"),
            time_in_force="good_till_canceled",
            self_trade_prevention_type="taker_at_cross",
        )
        data = req.model_dump(mode="json")
        assert isinstance(data["count"], str)
