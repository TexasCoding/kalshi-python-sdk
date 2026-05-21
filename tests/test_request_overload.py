"""Tests for the model-first request overload across resource methods (#56).

Resource methods with a request body accept either individual kwargs or a
pre-built ``request=Model(...)``. The two forms must produce identical wire
bodies; passing both raises ``TypeError``.

Covers a representative slice of methods rather than every method — the
dispatcher logic is identical across the codebase, so 3-4 methods locks
in the pattern.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.models.api_keys import CreateApiKeyRequest
from kalshi.models.multivariate import (
    CreateMarketInMultivariateEventCollectionRequest,
    TickerPair,
)
from kalshi.models.orders import (
    AmendOrderRequest,
    BatchCreateOrdersRequest,
    CreateOrderRequest,
)
from kalshi.resources.api_keys import ApiKeysResource
from kalshi.resources.multivariate import MultivariateCollectionsResource
from kalshi.resources.orders import OrdersResource
from tests._model_fixtures import order_dict


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def orders(test_auth: KalshiAuth, config: KalshiConfig) -> OrdersResource:
    return OrdersResource(SyncTransport(test_auth, config))


@pytest.fixture
def api_keys(test_auth: KalshiAuth, config: KalshiConfig) -> ApiKeysResource:
    return ApiKeysResource(SyncTransport(test_auth, config))


@pytest.fixture
def multivariate(
    test_auth: KalshiAuth,
    config: KalshiConfig,
) -> MultivariateCollectionsResource:
    return MultivariateCollectionsResource(SyncTransport(test_auth, config))


_AMEND_RESPONSE = {
    "old_order": order_dict(order_id="ord-1", ticker="MKT"),
    "order": order_dict(order_id="ord-1", ticker="MKT"),
}


class TestAmendRequestOverload:
    """`orders.amend` accepts either kwargs or a pre-built AmendOrderRequest."""

    @respx.mock
    def test_request_model_produces_same_body_as_kwargs(
        self,
        orders: OrdersResource,
    ) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-1/amend"
        ).mock(return_value=httpx.Response(200, json=_AMEND_RESPONSE))

        orders.amend(
            "ord-1",
            ticker="MKT",
            side="yes",
            action="buy",
            yes_price="0.55",
            count=3,
            subaccount=2,
        )
        kwarg_body = json.loads(route.calls[0].request.content)

        orders.amend(
            "ord-1",
            request=AmendOrderRequest(
                ticker="MKT",
                side="yes",
                action="buy",
                yes_price="0.55",
                count=3,
                subaccount=2,  # type: ignore[arg-type]
            ),
        )
        model_body = json.loads(route.calls[1].request.content)

        assert kwarg_body == model_body
        assert kwarg_body["yes_price_dollars"] == "0.55"
        assert kwarg_body["count_fp"] == "3"

    @respx.mock
    def test_passing_request_and_kwarg_raises(
        self,
        orders: OrdersResource,
    ) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/ord-1/amend").mock(
            return_value=httpx.Response(200, json=_AMEND_RESPONSE)
        )

        with pytest.raises(TypeError, match=r"Pass either `request=\.\.\.` or"):
            orders.amend(
                "ord-1",
                request=AmendOrderRequest(
                    ticker="MKT",
                    side="yes",
                    action="buy",
                    yes_price="0.55",  # type: ignore[arg-type]
                ),
                yes_price="0.60",
            )


_ORDER_RESPONSE = {"order": order_dict(order_id="ord-x", ticker="MKT", side="yes")}


class TestCreateOrderRequestOverload:
    """`orders.create` accepts either kwargs or a pre-built CreateOrderRequest."""

    @respx.mock
    def test_request_model_produces_same_body_as_kwargs(
        self,
        orders: OrdersResource,
    ) -> None:
        route = respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json=_ORDER_RESPONSE)
        )

        orders.create(
            ticker="MKT",
            side="yes",
            count=2,
            yes_price="0.50",
            action="buy",
        )
        kwarg_body = json.loads(route.calls[0].request.content)

        orders.create(
            request=CreateOrderRequest(
                ticker="MKT",
                side="yes",
                count=2,  # type: ignore[arg-type]
                yes_price="0.50",  # type: ignore[arg-type]
                action="buy",
            ),
        )
        model_body = json.loads(route.calls[1].request.content)

        assert kwarg_body == model_body

    @respx.mock
    def test_passing_request_and_kwarg_raises(
        self,
        orders: OrdersResource,
    ) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(200, json=_ORDER_RESPONSE)
        )

        with pytest.raises(TypeError, match=r"Pass either `request=\.\.\.` or"):
            orders.create(
                request=CreateOrderRequest(ticker="MKT", side="yes", action="buy", count=1),
                ticker="OTHER",
            )


class TestBatchCreateRequestOverload:
    """`orders.batch_create` (nested model wrapper) accepts request= form."""

    @respx.mock
    def test_request_model_produces_same_body_as_kwargs(
        self,
        orders: OrdersResource,
    ) -> None:
        route = respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )

        inner = [
            CreateOrderRequest(ticker="MKT-A", side="yes", action="buy", count=1),
            CreateOrderRequest(ticker="MKT-B", side="no", action="buy", count=1),
        ]
        orders.batch_create(inner)
        kwarg_body = json.loads(route.calls[0].request.content)

        orders.batch_create(request=BatchCreateOrdersRequest(orders=inner))
        model_body = json.loads(route.calls[1].request.content)

        assert kwarg_body == model_body

    @respx.mock
    def test_passing_request_and_kwarg_raises(
        self,
        orders: OrdersResource,
    ) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders/batched").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )

        inner = [CreateOrderRequest(ticker="MKT-A", side="yes", action="buy", count=1)]
        with pytest.raises(TypeError, match=r"Pass either `request=\.\.\.` or"):
            orders.batch_create(
                inner,
                request=BatchCreateOrdersRequest(orders=inner),
            )


class TestCreateApiKeyRequestOverload:
    """`api_keys.create` accepts request= form (simple POST body, no path params)."""

    @respx.mock
    def test_request_model_produces_same_body_as_kwargs(
        self,
        api_keys: ApiKeysResource,
    ) -> None:
        route = respx.post("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(200, json={"api_key_id": "k-id"})
        )

        api_keys.create(name="k", public_key="PK")
        kwarg_body = json.loads(route.calls[0].request.content)

        api_keys.create(request=CreateApiKeyRequest(name="k", public_key="PK"))
        model_body = json.loads(route.calls[1].request.content)

        assert kwarg_body == model_body


class TestMissingRequiredKwargsRaisesTypeError:
    """Calling a dispatcher with no request= and missing required kwargs.

    One test per dispatcher shape (single-required, multi-required,
    list-required) — locks in the runtime guard mypy's overloads enforce
    statically.
    """

    def test_single_required_kwarg_missing(
        self,
        api_keys: ApiKeysResource,
    ) -> None:
        # generate() requires `name` (one required kwarg).
        with pytest.raises(TypeError, match=r"generate\(\) requires `name`"):
            api_keys.generate()

    def test_multi_required_kwargs_missing(
        self,
        orders: OrdersResource,
    ) -> None:
        # create() requires `ticker` and `side`. Passing only one raises.
        with pytest.raises(
            TypeError,
            match=r"create\(\) requires `ticker`, `side`, `count`, and `action`",
        ):
            orders.create(ticker="MKT")

    def test_list_required_kwarg_missing(
        self,
        orders: OrdersResource,
    ) -> None:
        # batch_create() requires `orders` (the list). Zero-args raises.
        with pytest.raises(
            TypeError,
            match=r"batch_create\(\) requires `orders`",
        ):
            orders.batch_create()


class TestCreateMarketRequestOverload:
    """`multivariate.create_market` — nested-list model + positional path param."""

    @respx.mock
    def test_request_model_produces_same_body_as_kwargs(
        self,
        multivariate: MultivariateCollectionsResource,
    ) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/multivariate_event_collections/COL-1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"market_ticker": "M", "event_ticker": "E"},
            )
        )

        selected = [TickerPair(event_ticker="EVT", market_ticker="MKT", side="yes")]

        multivariate.create_market("COL-1", selected_markets=selected)
        kwarg_body = json.loads(route.calls[0].request.content)

        multivariate.create_market(
            "COL-1",
            request=CreateMarketInMultivariateEventCollectionRequest(
                selected_markets=selected,
            ),
        )
        model_body = json.loads(route.calls[1].request.content)

        assert kwarg_body == model_body

    @respx.mock
    def test_passing_request_and_kwarg_raises(
        self,
        multivariate: MultivariateCollectionsResource,
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/multivariate_event_collections/COL-1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"market_ticker": "M", "event_ticker": "E"},
            )
        )

        selected = [TickerPair(event_ticker="EVT", market_ticker="MKT", side="yes")]
        with pytest.raises(TypeError, match=r"Pass either `request=\.\.\.` or"):
            multivariate.create_market(
                "COL-1",
                selected_markets=selected,
                request=CreateMarketInMultivariateEventCollectionRequest(
                    selected_markets=selected,
                ),
            )
