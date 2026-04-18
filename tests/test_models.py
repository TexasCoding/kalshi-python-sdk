"""Tests for kalshi.types and model Decimal handling."""

from __future__ import annotations

from decimal import Decimal

import pytest

from kalshi.models.markets import Market
from kalshi.models.orders import Order
from kalshi.types import to_decimal


class TestToDecimal:
    def test_float_to_decimal(self) -> None:
        result = to_decimal(0.65)
        assert result == Decimal("0.65")
        assert isinstance(result, Decimal)

    def test_float_precision(self) -> None:
        """0.65 as float has representation issues. to_decimal avoids them."""
        result = to_decimal(0.65)
        # Decimal(0.65) would give 0.6499999999...
        # Decimal(str(0.65)) gives exactly 0.65
        assert str(result) == "0.65"

    def test_string_to_decimal(self) -> None:
        result = to_decimal("0.72")
        assert result == Decimal("0.72")

    def test_int_to_decimal(self) -> None:
        result = to_decimal(1)
        assert result == Decimal("1")

    def test_decimal_passthrough(self) -> None:
        d = Decimal("0.50")
        result = to_decimal(d)
        assert result is d


class TestDollarDecimalField:
    def test_market_parses_string_price(self) -> None:
        m = Market(ticker="T", yes_ask="0.65")
        assert m.yes_ask == Decimal("0.65")
        assert isinstance(m.yes_ask, Decimal)

    def test_market_parses_float_price(self) -> None:
        m = Market(ticker="T", yes_bid=0.45)
        assert m.yes_bid == Decimal("0.45")

    def test_market_parses_int_price(self) -> None:
        m = Market(ticker="T", last_price=1)
        assert m.last_price == Decimal("1")

    def test_market_model_dump_serializes(self) -> None:
        m = Market(ticker="T", yes_ask="0.72")
        data = m.model_dump()
        assert data["yes_ask"] == "0.72"

    def test_order_decimal_fields(self) -> None:
        o = Order(order_id="x", yes_price="0.65", no_price="0.35")
        assert o.yes_price == Decimal("0.65")
        assert o.no_price == Decimal("0.35")


class TestDollarsAliasFields:
    """Verify models accept _dollars-suffixed field names from the API.

    The Kalshi API returns price fields with a '_dollars' suffix
    (e.g. 'yes_bid_dollars') as FixedPointDollars strings. The SDK
    uses shorter Python field names (e.g. 'yes_bid') with validation
    aliases to accept both formats.
    """

    def test_market_accepts_dollars_suffix(self) -> None:
        m = Market.model_validate({
            "ticker": "T",
            "yes_bid_dollars": "0.4500",
            "yes_ask_dollars": "0.5500",
            "no_bid_dollars": "0.3000",
            "no_ask_dollars": "0.7000",
            "last_price_dollars": "0.5000",
        })
        assert m.yes_bid == Decimal("0.4500")
        assert m.yes_ask == Decimal("0.5500")
        assert m.no_bid == Decimal("0.3000")
        assert m.no_ask == Decimal("0.7000")
        assert m.last_price == Decimal("0.5000")

    def test_market_accepts_bare_names(self) -> None:
        m = Market(ticker="T", yes_bid="0.45")
        assert m.yes_bid == Decimal("0.45")

    def test_order_accepts_dollars_suffix(self) -> None:
        o = Order.model_validate({
            "order_id": "x",
            "yes_price_dollars": "0.6500",
            "no_price_dollars": "0.3500",
            "taker_fill_cost_dollars": "6.5000",
            "maker_fill_cost_dollars": "0.0000",
            "taker_fees_dollars": "0.0650",
            "maker_fees_dollars": "0.0000",
        })
        assert o.yes_price == Decimal("0.6500")
        assert o.no_price == Decimal("0.3500")
        assert o.taker_fill_cost == Decimal("6.5000")
        assert o.taker_fees == Decimal("0.0650")

    def test_fill_accepts_dollars_suffix(self) -> None:
        from kalshi.models.orders import Fill

        f = Fill.model_validate({
            "trade_id": "t1",
            "yes_price_dollars": "0.5000",
            "no_price_dollars": "0.5000",
        })
        assert f.yes_price == Decimal("0.5000")
        assert f.no_price == Decimal("0.5000")

    def test_candlestick_nested_structure(self) -> None:
        from kalshi.models.markets import Candlestick

        c = Candlestick.model_validate({
            "end_period_ts": 1700000000,
            "yes_bid": {
                "open_dollars": "0.4000",
                "high_dollars": "0.5000",
                "low_dollars": "0.3500",
                "close_dollars": "0.4500",
            },
            "price": {
                "open_dollars": "0.5000",
                "close_dollars": "0.5500",
            },
            "volume_fp": "100.00",
        })
        assert c.yes_bid is not None
        assert c.yes_bid.open == Decimal("0.4000")
        assert c.yes_bid.high == Decimal("0.5000")
        assert c.price is not None
        assert c.price.open == Decimal("0.5000")
        assert c.price.close == Decimal("0.5500")
        assert c.volume == Decimal("100.00")

    def test_create_order_serializes_with_dollars_alias(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="T",
            side="yes",
            yes_price=Decimal("0.65"),
        )
        data = req.model_dump(exclude_none=True, by_alias=True)
        assert "yes_price_dollars" in data
        assert data["yes_price_dollars"] == "0.65"
        assert "yes_price" not in data


class TestErrorHierarchy:
    def test_all_errors_inherit_base(self) -> None:
        from kalshi.errors import (
            KalshiAuthError,
            KalshiError,
            KalshiNotFoundError,
            KalshiRateLimitError,
            KalshiServerError,
            KalshiValidationError,
        )

        assert issubclass(KalshiAuthError, KalshiError)
        assert issubclass(KalshiNotFoundError, KalshiError)
        assert issubclass(KalshiRateLimitError, KalshiError)
        assert issubclass(KalshiValidationError, KalshiError)
        assert issubclass(KalshiServerError, KalshiError)

    def test_rate_limit_has_retry_after(self) -> None:
        from kalshi.errors import KalshiRateLimitError

        err = KalshiRateLimitError("too fast", retry_after=2.5)
        assert err.retry_after == 2.5

    def test_validation_has_details(self) -> None:
        from kalshi.errors import KalshiValidationError

        err = KalshiValidationError("bad input", details={"field": "required"})
        assert err.details == {"field": "required"}


class TestAmendOrderResponse:
    def test_parses_old_and_new_order(self) -> None:
        from kalshi.models.orders import AmendOrderResponse

        data = {
            "old_order": {
                "order_id": "ord-old",
                "ticker": "MKT-A",
                "yes_price_dollars": "0.5000",
                "count": 5,
            },
            "order": {
                "order_id": "ord-new",
                "ticker": "MKT-A",
                "yes_price_dollars": "0.6500",
                "count": 5,
            },
        }
        result = AmendOrderResponse.model_validate(data)
        assert result.old_order.order_id == "ord-old"
        assert result.order.order_id == "ord-new"
        assert result.old_order.yes_price == Decimal("0.5000")
        assert result.order.yes_price == Decimal("0.6500")


class TestOrderQueuePosition:
    def test_parses_queue_position(self) -> None:
        from kalshi.models.orders import OrderQueuePosition

        data = {
            "order_id": "ord-123",
            "market_ticker": "MKT-A",
            "queue_position_fp": "42.00",
        }
        result = OrderQueuePosition.model_validate(data)
        assert result.order_id == "ord-123"
        assert result.market_ticker == "MKT-A"
        assert result.queue_position == Decimal("42.00")


class TestCreateOrderRequestExtended:
    def test_accepts_time_in_force(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT", side="yes", action="buy",
            time_in_force="fill_or_kill",
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["time_in_force"] == "fill_or_kill"

    def test_accepts_post_only_and_reduce_only(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT", side="yes", action="buy",
            post_only=True, reduce_only=False,
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["post_only"] is True
        assert body["reduce_only"] is False

    def test_accepts_self_trade_prevention_and_order_group(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT", side="yes", action="buy",
            self_trade_prevention_type="maker",
            order_group_id="grp-123",
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["self_trade_prevention_type"] == "maker"
        assert body["order_group_id"] == "grp-123"

    def test_accepts_cancel_on_pause_and_subaccount(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT", side="yes", action="buy",
            cancel_order_on_pause=True, subaccount=5,
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["cancel_order_on_pause"] is True
        assert body["subaccount"] == 5

    def test_buy_max_cost_is_int_cents(self) -> None:
        """Spec says integer cents; SDK must send int on the wire."""
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT", side="yes", action="buy",
            buy_max_cost=500,
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["buy_max_cost"] == 500
        assert isinstance(body["buy_max_cost"], int)

    def test_buy_max_cost_rejects_fractional_value(self) -> None:
        """A caller passing a fractional string like '5.5' must raise.

        Pydantic v2 int coercion rejects strings that are not whole numbers
        (e.g. '5.5'), but accepts whole-number strings like '500' and even
        '5.00' (coerced to 5). The field is int cents, so fractional values
        are always invalid.
        """
        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT", side="yes", action="buy",
                buy_max_cost="5.5",  # type: ignore[arg-type]
            )

    def test_buy_max_cost_rejects_decimal(self) -> None:
        """Migration-hazard guard: Decimal inputs raise clearly, not silently coerce."""
        from decimal import Decimal

        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        # Both whole and fractional Decimal values must raise — the hazard is
        # silent coercion to cents regardless of the numeric value.
        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT", side="yes", action="buy",
                buy_max_cost=Decimal("500"),  # type: ignore[arg-type]
            )
        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT", side="yes", action="buy",
                buy_max_cost=Decimal("5.00"),  # type: ignore[arg-type]
            )

    def test_buy_max_cost_rejects_float(self) -> None:
        """Float inputs (even whole-valued) must raise to prevent unit confusion."""
        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT", side="yes", action="buy",
                buy_max_cost=5.0,  # type: ignore[arg-type]
            )

    def test_buy_max_cost_accepts_int_string(self) -> None:
        """Int-shaped strings are coerced normally (e.g., loading from env/config)."""
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT", side="yes", action="buy",
            buy_max_cost="500",  # type: ignore[arg-type]
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["buy_max_cost"] == 500

    def test_omits_none_fields_from_wire(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(ticker="MKT", side="yes", action="buy")
        body = req.model_dump(exclude_none=True, by_alias=True)
        # Core fields present
        assert body["ticker"] == "MKT"
        # Optional fields absent (defaults to None, stripped by exclude_none)
        assert "time_in_force" not in body
        assert "post_only" not in body
        assert "buy_max_cost" not in body
        assert "subaccount" not in body

    def test_phantom_type_field_removed(self) -> None:
        """v0.8.0 removed the phantom `type` field (spec has no such field)."""
        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT", side="yes", action="buy",
                type="limit",  # type: ignore[call-arg]
            )

    def test_forbid_extra_rejects_unknown_kwarg(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import CreateOrderRequest

        with pytest.raises(ValidationError):
            CreateOrderRequest(
                ticker="MKT", side="yes", action="buy",
                bogus_field="x",  # type: ignore[call-arg]
            )

    def test_serializes_count_fp_not_count(self) -> None:
        from kalshi.models.orders import CreateOrderRequest

        req = CreateOrderRequest(
            ticker="MKT", side="yes", action="buy",
            count=Decimal("7"),
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert "count_fp" in body
        assert "count" not in body


class TestAmendOrderRequest:
    def test_required_fields(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import AmendOrderRequest

        with pytest.raises(ValidationError):
            AmendOrderRequest()  # type: ignore[call-arg]

        # ticker/side/action required per spec
        req = AmendOrderRequest(ticker="MKT", side="yes", action="buy")
        assert req.ticker == "MKT"

    def test_serializes_yes_price_dollars(self) -> None:
        from decimal import Decimal

        from kalshi.models.orders import AmendOrderRequest

        req = AmendOrderRequest(
            ticker="MKT", side="yes", action="buy",
            yes_price=Decimal("0.55"),
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["yes_price_dollars"] == "0.55"
        assert "yes_price" not in body  # int cent form excluded

    def test_serializes_no_price_dollars(self) -> None:
        from decimal import Decimal

        from kalshi.models.orders import AmendOrderRequest

        req = AmendOrderRequest(
            ticker="MKT", side="no", action="sell",
            no_price=Decimal("0.75"),
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["no_price_dollars"] == "0.75"
        assert "no_price" not in body

    def test_serializes_count_fp(self) -> None:
        from decimal import Decimal

        from kalshi.models.orders import AmendOrderRequest

        req = AmendOrderRequest(
            ticker="MKT", side="yes", action="buy",
            count=Decimal("3"),
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert "count_fp" in body
        assert body["count_fp"] == "3"
        assert "count" not in body

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import AmendOrderRequest

        with pytest.raises(ValidationError):
            AmendOrderRequest(
                ticker="MKT", side="yes", action="buy",
                bogus_field="x",  # type: ignore[call-arg]
            )

    def test_accepts_client_order_ids(self) -> None:
        from kalshi.models.orders import AmendOrderRequest

        req = AmendOrderRequest(
            ticker="MKT", side="yes", action="buy",
            client_order_id="old-id",
            updated_client_order_id="new-id",
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["client_order_id"] == "old-id"
        assert body["updated_client_order_id"] == "new-id"

    def test_accepts_subaccount(self) -> None:
        from kalshi.models.orders import AmendOrderRequest

        req = AmendOrderRequest(
            ticker="MKT", side="yes", action="buy", subaccount=3,
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["subaccount"] == 3


class TestDecreaseOrderRequest:
    def test_accepts_reduce_by(self) -> None:
        from kalshi.models.orders import DecreaseOrderRequest

        req = DecreaseOrderRequest(reduce_by=3)
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body == {"reduce_by": 3}

    def test_accepts_reduce_to(self) -> None:
        from kalshi.models.orders import DecreaseOrderRequest

        req = DecreaseOrderRequest(reduce_to=2)
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body == {"reduce_to": 2}

    def test_accepts_subaccount(self) -> None:
        from kalshi.models.orders import DecreaseOrderRequest

        req = DecreaseOrderRequest(reduce_by=1, subaccount=4)
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["subaccount"] == 4

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import DecreaseOrderRequest

        with pytest.raises(ValidationError):
            DecreaseOrderRequest(
                reduce_by=1,
                bogus_field=5,  # type: ignore[call-arg]
            )

    def test_all_optional(self) -> None:
        """Spec has no required fields on this schema."""
        from kalshi.models.orders import DecreaseOrderRequest

        req = DecreaseOrderRequest()
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body == {}


class TestBatchCreateOrdersRequest:
    def test_wraps_order_list(self) -> None:
        from kalshi.models.orders import (
            BatchCreateOrdersRequest,
            CreateOrderRequest,
        )

        orders = [
            CreateOrderRequest(ticker="MKT-A", side="yes", action="buy"),
            CreateOrderRequest(ticker="MKT-B", side="no", action="sell"),
        ]
        req = BatchCreateOrdersRequest(orders=orders)
        body = req.model_dump(exclude_none=True, by_alias=True)

        assert "orders" in body
        assert len(body["orders"]) == 2
        assert body["orders"][0]["ticker"] == "MKT-A"
        assert body["orders"][1]["ticker"] == "MKT-B"

    def test_empty_list_allowed(self) -> None:
        from kalshi.models.orders import BatchCreateOrdersRequest

        req = BatchCreateOrdersRequest(orders=[])
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body == {"orders": []}

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.orders import BatchCreateOrdersRequest

        with pytest.raises(ValidationError):
            BatchCreateOrdersRequest(
                orders=[],
                bogus=1,  # type: ignore[call-arg]
            )

    def test_nested_create_order_phantom_rejected(self) -> None:
        """Phantom key in a raw-dict nested order rejected via BatchCreateOrdersRequest.

        Constructs BatchCreateOrdersRequest with a raw dict item — Pydantic
        coerces into CreateOrderRequest and its extra='forbid' fires on the
        phantom. This exercises the BatchCreateOrdersRequest -> nested item
        path, not CreateOrderRequest's forbid in isolation (already covered
        by TestCreateOrderRequestExtended.test_forbid_extra).
        """
        from pydantic import ValidationError

        from kalshi.models.orders import BatchCreateOrdersRequest

        with pytest.raises(ValidationError):
            BatchCreateOrdersRequest(
                orders=[
                    {
                        "ticker": "MKT",
                        "side": "yes",
                        "action": "buy",
                        "type": "limit",  # phantom
                    },  # type: ignore[list-item]
                ],
            )


class TestCreateMarketInMultivariateRequest:
    def test_requires_selected_markets(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.multivariate import (
            CreateMarketInMultivariateEventCollectionRequest,
        )

        with pytest.raises(ValidationError):
            CreateMarketInMultivariateEventCollectionRequest()  # type: ignore[call-arg]

    def test_accepts_ticker_pair_items(self) -> None:
        from kalshi.models.multivariate import (
            CreateMarketInMultivariateEventCollectionRequest,
            TickerPair,
        )

        pair = TickerPair(event_ticker="E1", market_ticker="M1", side="yes")
        req = CreateMarketInMultivariateEventCollectionRequest(
            selected_markets=[pair],
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["selected_markets"][0]["event_ticker"] == "E1"

    def test_with_market_payload_optional(self) -> None:
        from kalshi.models.multivariate import (
            CreateMarketInMultivariateEventCollectionRequest,
            TickerPair,
        )

        pair = TickerPair(event_ticker="E1", market_ticker="M1", side="yes")
        req = CreateMarketInMultivariateEventCollectionRequest(
            selected_markets=[pair],
            with_market_payload=True,
        )
        body = req.model_dump(exclude_none=True, by_alias=True)
        assert body["with_market_payload"] is True

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.multivariate import (
            CreateMarketInMultivariateEventCollectionRequest,
            TickerPair,
        )

        pair = TickerPair(event_ticker="E1", market_ticker="M1", side="yes")
        with pytest.raises(ValidationError):
            CreateMarketInMultivariateEventCollectionRequest(
                selected_markets=[pair],
                bogus=1,  # type: ignore[call-arg]
            )


class TestLookupTickersRequest:
    def test_requires_selected_markets(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.multivariate import (
            LookupTickersForMarketInMultivariateEventCollectionRequest,
        )

        with pytest.raises(ValidationError):
            LookupTickersForMarketInMultivariateEventCollectionRequest()  # type: ignore[call-arg]

    def test_forbid_extra(self) -> None:
        from pydantic import ValidationError

        from kalshi.models.multivariate import (
            LookupTickersForMarketInMultivariateEventCollectionRequest,
            TickerPair,
        )

        pair = TickerPair(event_ticker="E1", market_ticker="M1", side="yes")
        with pytest.raises(ValidationError):
            LookupTickersForMarketInMultivariateEventCollectionRequest(
                selected_markets=[pair],
                bogus=1,  # type: ignore[call-arg]
            )
