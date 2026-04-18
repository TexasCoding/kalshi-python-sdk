"""Tests for kalshi.resources.communications — RFQ + Quote resource."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.async_client import AsyncKalshiClient
from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import DEMO_BASE_URL, KalshiConfig
from kalshi.errors import (
    AuthRequiredError,
    KalshiNotFoundError,
    KalshiValidationError,
)
from kalshi.models.communications import (
    RFQ,
    AcceptQuoteRequest,
    CreateQuoteRequest,
    CreateQuoteResponse,
    CreateRFQRequest,
    CreateRFQResponse,
    GetCommunicationsIDResponse,
    GetQuoteResponse,
    GetRFQResponse,
    Quote,
)
from kalshi.resources.communications import (
    AsyncCommunicationsResource,
    CommunicationsResource,
)


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def comms(test_auth: KalshiAuth, config: KalshiConfig) -> CommunicationsResource:
    return CommunicationsResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_comms(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> AsyncCommunicationsResource:
    return AsyncCommunicationsResource(AsyncTransport(test_auth, config))


@pytest.fixture
def client(test_auth: KalshiAuth) -> KalshiClient:
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, timeout=5.0, max_retries=0)
    return KalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def async_client(test_auth: KalshiAuth) -> AsyncKalshiClient:
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, timeout=5.0, max_retries=0)
    return AsyncKalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def unauth_comms(config: KalshiConfig) -> CommunicationsResource:
    return CommunicationsResource(SyncTransport(None, config))


_MINIMAL_RFQ = {
    "id": "rfq-1",
    "creator_id": "comm-42",
    "market_ticker": "MKT-1",
    "contracts_fp": "100",
    "status": "open",
    "created_ts": "2026-04-18T12:00:00Z",
}

_MINIMAL_QUOTE = {
    "id": "q-1",
    "rfq_id": "rfq-1",
    "creator_id": "comm-99",
    "rfq_creator_id": "comm-42",
    "market_ticker": "MKT-1",
    "contracts_fp": "100",
    "yes_bid_dollars": "0.5600",
    "no_bid_dollars": "0.4400",
    "created_ts": "2026-04-18T12:01:00Z",
    "updated_ts": "2026-04-18T12:01:00Z",
    "status": "open",
}


class TestCommunicationsResponseModels:
    def test_rfq_accepts_fp_and_dollars_aliases(self) -> None:
        rfq = RFQ.model_validate(
            {**_MINIMAL_RFQ, "target_cost_dollars": "50.0000"}
        )
        assert rfq.id == "rfq-1"
        assert rfq.contracts == Decimal("100")
        assert rfq.target_cost == Decimal("50.0000")
        assert rfq.status == "open"

    def test_rfq_accepts_short_name_aliases(self) -> None:
        rfq = RFQ.model_validate(
            {
                "id": "rfq-1",
                "creator_id": "comm-42",
                "market_ticker": "MKT-1",
                "contracts": "100",
                "status": "closed",
                "created_ts": "2026-04-18T12:00:00Z",
                "target_cost": "25.00",
            }
        )
        assert rfq.contracts == Decimal("100")
        assert rfq.target_cost == Decimal("25.00")

    def test_quote_parses_all_aliases(self) -> None:
        q = Quote.model_validate(_MINIMAL_QUOTE)
        assert q.id == "q-1"
        assert q.yes_bid == Decimal("0.5600")
        assert q.no_bid == Decimal("0.4400")
        assert q.contracts == Decimal("100")
        assert q.status == "open"

    def test_get_communications_id_parses(self) -> None:
        resp = GetCommunicationsIDResponse.model_validate(
            {"communications_id": "comm-abc"},
        )
        assert resp.communications_id == "comm-abc"

    def test_get_rfq_response_wraps_rfq(self) -> None:
        resp = GetRFQResponse.model_validate({"rfq": _MINIMAL_RFQ})
        assert isinstance(resp.rfq, RFQ)

    def test_get_quote_response_wraps_quote(self) -> None:
        resp = GetQuoteResponse.model_validate({"quote": _MINIMAL_QUOTE})
        assert isinstance(resp.quote, Quote)

    def test_create_rfq_response(self) -> None:
        resp = CreateRFQResponse.model_validate({"id": "rfq-new"})
        assert resp.id == "rfq-new"

    def test_create_quote_response(self) -> None:
        resp = CreateQuoteResponse.model_validate({"id": "q-new"})
        assert resp.id == "q-new"


class TestCommunicationsRequestModels:
    def test_create_rfq_request_serializes_target_cost_as_dollars(self) -> None:
        req = CreateRFQRequest(
            market_ticker="MKT-1",
            rest_remainder=True,
            contracts=100,
            target_cost=Decimal("50.00"),
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {
            "market_ticker": "MKT-1",
            "rest_remainder": True,
            "contracts": 100,
            "target_cost_dollars": "50.00",
        }

    def test_create_rfq_request_omits_optional_fields(self) -> None:
        req = CreateRFQRequest(market_ticker="MKT-1", rest_remainder=False)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"market_ticker": "MKT-1", "rest_remainder": False}

    def test_create_rfq_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateRFQRequest(  # type: ignore[call-arg]
                market_ticker="MKT-1", rest_remainder=True, phantom=1,
            )

    def test_create_rfq_rejects_zero_contracts(self) -> None:
        with pytest.raises(ValidationError):
            CreateRFQRequest(market_ticker="MKT-1", rest_remainder=True, contracts=0)

    def test_create_quote_request_serializes_bids_without_dollars_suffix(self) -> None:
        # Unlike CreateOrderRequest, spec wire uses yes_bid / no_bid for this one.
        req = CreateQuoteRequest(
            rfq_id="rfq-1",
            yes_bid=Decimal("0.56"),
            no_bid=Decimal("0.44"),
            rest_remainder=True,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {
            "rfq_id": "rfq-1",
            "yes_bid": "0.56",
            "no_bid": "0.44",
            "rest_remainder": True,
        }

    def test_create_quote_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateQuoteRequest(  # type: ignore[call-arg]
                rfq_id="rfq-1",
                yes_bid=Decimal("0.5"),
                no_bid=Decimal("0.5"),
                rest_remainder=True,
                phantom=True,
            )

    def test_accept_quote_request_serializes(self) -> None:
        req = AcceptQuoteRequest(accepted_side="yes")
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"accepted_side": "yes"}

    def test_accept_quote_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            AcceptQuoteRequest(accepted_side="yes", phantom=1)  # type: ignore[call-arg]


class TestGetCommunicationsID:
    @respx.mock
    def test_returns_id(self, comms: CommunicationsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/id",
        ).mock(
            return_value=httpx.Response(200, json={"communications_id": "comm-42"}),
        )
        resp = comms.get_id()
        assert resp.communications_id == "comm-42"

    @respx.mock
    def test_500_raises(self, comms: CommunicationsResource) -> None:
        from kalshi.errors import KalshiServerError

        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/id",
        ).mock(return_value=httpx.Response(500, json={"message": "boom"}))
        with pytest.raises(KalshiServerError):
            comms.get_id()


class TestListRfqs:
    @respx.mock
    def test_returns_paged_rfqs(self, comms: CommunicationsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(
            return_value=httpx.Response(
                200, json={"rfqs": [_MINIMAL_RFQ], "cursor": "next"},
            ),
        )
        page = comms.list_rfqs(limit=10)
        assert len(page.items) == 1
        assert isinstance(page.items[0], RFQ)
        assert page.cursor == "next"

    @respx.mock
    def test_passes_filter_params(self, comms: CommunicationsResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(200, json={"rfqs": []}))
        comms.list_rfqs(
            limit=50,
            market_ticker="MKT-1",
            status="open",
            subaccount=3,
            creator_user_id="u-1",
        )
        params = route.calls[0].request.url.params
        assert params["limit"] == "50"
        assert params["market_ticker"] == "MKT-1"
        assert params["status"] == "open"
        assert params["subaccount"] == "3"
        assert params["creator_user_id"] == "u-1"

    @respx.mock
    def test_list_all_rfqs_auto_paginates(
        self, comms: CommunicationsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "rfqs": [_MINIMAL_RFQ, {**_MINIMAL_RFQ, "id": "rfq-2"}],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200, json={"rfqs": [{**_MINIMAL_RFQ, "id": "rfq-3"}]},
                ),
            ],
        )
        items = list(comms.list_all_rfqs())
        assert [r.id for r in items] == ["rfq-1", "rfq-2", "rfq-3"]


class TestGetRfq:
    @respx.mock
    def test_returns_rfq(self, comms: CommunicationsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/rfq-1",
        ).mock(return_value=httpx.Response(200, json={"rfq": _MINIMAL_RFQ}))
        resp = comms.get_rfq("rfq-1")
        assert resp.rfq.id == "rfq-1"

    @respx.mock
    def test_404_maps_to_not_found(self, comms: CommunicationsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/missing",
        ).mock(return_value=httpx.Response(404, json={"message": "missing"}))
        with pytest.raises(KalshiNotFoundError):
            comms.get_rfq("missing")


class TestCreateRfq:
    @respx.mock
    def test_sends_correct_body(self, comms: CommunicationsResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(201, json={"id": "rfq-new"}))
        resp = comms.create_rfq(
            market_ticker="MKT-1",
            rest_remainder=True,
            contracts=10,
            target_cost=Decimal("5.00"),
            subaccount=2,
        )
        assert resp.id == "rfq-new"
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "market_ticker": "MKT-1",
            "rest_remainder": True,
            "contracts": 10,
            "target_cost_dollars": "5.00",
            "subaccount": 2,
        }

    @respx.mock
    def test_omits_optional_fields(self, comms: CommunicationsResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(201, json={"id": "rfq-new"}))
        comms.create_rfq(market_ticker="MKT-1", rest_remainder=False)
        body = json.loads(route.calls[0].request.content)
        assert body == {"market_ticker": "MKT-1", "rest_remainder": False}

    @respx.mock
    def test_400_maps_to_validation_error(
        self, comms: CommunicationsResource,
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(400, json={"message": "bad"}))
        with pytest.raises(KalshiValidationError):
            comms.create_rfq(market_ticker="MKT-1", rest_remainder=True)


class TestDeleteRfq:
    @respx.mock
    def test_sends_delete(self, comms: CommunicationsResource) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/rfq-1",
        ).mock(return_value=httpx.Response(204))
        comms.delete_rfq("rfq-1")
        assert route.called

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/gone",
        ).mock(return_value=httpx.Response(404, json={"message": "missing"}))
        with pytest.raises(KalshiNotFoundError):
            comms.delete_rfq("gone")


class TestListQuotes:
    @respx.mock
    def test_returns_paged_quotes(self, comms: CommunicationsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": [_MINIMAL_QUOTE]}))
        page = comms.list_quotes()
        assert len(page.items) == 1
        assert isinstance(page.items[0], Quote)

    @respx.mock
    def test_passes_rfq_id_filter(self, comms: CommunicationsResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": []}))
        comms.list_quotes(rfq_id="rfq-1", status="accepted")
        params = route.calls[0].request.url.params
        assert params["rfq_id"] == "rfq-1"
        assert params["status"] == "accepted"

    @respx.mock
    def test_list_all_quotes_auto_paginates(
        self, comms: CommunicationsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"quotes": [_MINIMAL_QUOTE], "cursor": "page2"},
                ),
                httpx.Response(
                    200, json={"quotes": [{**_MINIMAL_QUOTE, "id": "q-2"}]},
                ),
            ],
        )
        items = list(comms.list_all_quotes())
        assert [q.id for q in items] == ["q-1", "q-2"]


class TestGetQuote:
    @respx.mock
    def test_returns_quote(self, comms: CommunicationsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1",
        ).mock(return_value=httpx.Response(200, json={"quote": _MINIMAL_QUOTE}))
        resp = comms.get_quote("q-1")
        assert resp.quote.id == "q-1"

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/gone",
        ).mock(return_value=httpx.Response(404, json={"message": "missing"}))
        with pytest.raises(KalshiNotFoundError):
            comms.get_quote("gone")


class TestCreateQuote:
    @respx.mock
    def test_sends_correct_body(self, comms: CommunicationsResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(201, json={"id": "q-new"}))
        resp = comms.create_quote(
            rfq_id="rfq-1",
            yes_bid=Decimal("0.56"),
            no_bid=Decimal("0.44"),
            rest_remainder=True,
        )
        assert resp.id == "q-new"
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "rfq_id": "rfq-1",
            "yes_bid": "0.56",
            "no_bid": "0.44",
            "rest_remainder": True,
        }

    @respx.mock
    def test_400(self, comms: CommunicationsResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(400, json={"message": "bad"}))
        with pytest.raises(KalshiValidationError):
            comms.create_quote(
                rfq_id="rfq-1",
                yes_bid=Decimal("0.5"),
                no_bid=Decimal("0.5"),
                rest_remainder=True,
            )


class TestDeleteQuote:
    @respx.mock
    def test_sends_delete(self, comms: CommunicationsResource) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1",
        ).mock(return_value=httpx.Response(204))
        comms.delete_quote("q-1")
        assert route.called


class TestAcceptQuote:
    @respx.mock
    def test_sends_put_with_body(self, comms: CommunicationsResource) -> None:
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1/accept",
        ).mock(return_value=httpx.Response(204))
        comms.accept_quote("q-1", accepted_side="yes")
        assert route.called
        body = json.loads(route.calls[0].request.content)
        assert body == {"accepted_side": "yes"}

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/gone/accept",
        ).mock(return_value=httpx.Response(404, json={"message": "missing"}))
        with pytest.raises(KalshiNotFoundError):
            comms.accept_quote("gone", accepted_side="no")


class TestConfirmQuote:
    @respx.mock
    def test_sends_put_with_empty_body(self, comms: CommunicationsResource) -> None:
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1/confirm",
        ).mock(return_value=httpx.Response(204))
        comms.confirm_quote("q-1")
        assert route.called
        # json={} forces Content-Type: application/json — demo rejects empty PUTs.
        assert route.calls[0].request.content == b"{}"

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/gone/confirm",
        ).mock(return_value=httpx.Response(404, json={"message": "missing"}))
        with pytest.raises(KalshiNotFoundError):
            comms.confirm_quote("gone")


@pytest.mark.asyncio
class TestAsyncCommunications:
    async def test_get_id(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/id",
        ).mock(
            return_value=httpx.Response(200, json={"communications_id": "comm-7"}),
        )
        resp = await async_comms.get_id()
        assert resp.communications_id == "comm-7"

    async def test_list_rfqs(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(200, json={"rfqs": [_MINIMAL_RFQ]}))
        page = await async_comms.list_rfqs()
        assert len(page.items) == 1
        assert isinstance(page.items[0], RFQ)

    async def test_create_rfq(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(201, json={"id": "rfq-9"}))
        resp = await async_comms.create_rfq(
            market_ticker="MKT-1", rest_remainder=True, contracts=5,
        )
        assert resp.id == "rfq-9"
        assert route.called

    async def test_list_all_rfqs_async(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"rfqs": [_MINIMAL_RFQ], "cursor": "page2"},
                ),
                httpx.Response(
                    200, json={"rfqs": [{**_MINIMAL_RFQ, "id": "rfq-2"}]},
                ),
            ],
        )
        ids = [rfq.id async for rfq in async_comms.list_all_rfqs()]
        assert ids == ["rfq-1", "rfq-2"]

    async def test_create_quote(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(201, json={"id": "q-9"}))
        resp = await async_comms.create_quote(
            rfq_id="rfq-1",
            yes_bid=Decimal("0.5"),
            no_bid=Decimal("0.5"),
            rest_remainder=True,
        )
        assert resp.id == "q-9"
        assert route.called

    async def test_accept_quote(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1/accept",
        ).mock(return_value=httpx.Response(204))
        await async_comms.accept_quote("q-1", accepted_side="yes")
        body = json.loads(route.calls[0].request.content)
        assert body == {"accepted_side": "yes"}

    async def test_confirm_quote(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1/confirm",
        ).mock(return_value=httpx.Response(204))
        await async_comms.confirm_quote("q-1")
        assert route.calls[0].request.content == b"{}"

    async def test_delete_rfq(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.delete(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/rfq-1",
        ).mock(return_value=httpx.Response(204))
        await async_comms.delete_rfq("rfq-1")
        assert route.called

    async def test_delete_quote(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.delete(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1",
        ).mock(return_value=httpx.Response(204))
        await async_comms.delete_quote("q-1")
        assert route.called


class TestCommunicationsAuthGuard:
    def test_get_id_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.get_id()

    def test_list_rfqs_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.list_rfqs()

    def test_list_all_rfqs_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_comms.list_all_rfqs())

    def test_get_rfq_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.get_rfq("rfq-1")

    def test_create_rfq_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.create_rfq(market_ticker="MKT-1", rest_remainder=True)

    def test_delete_rfq_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.delete_rfq("rfq-1")

    def test_list_quotes_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.list_quotes()

    def test_list_all_quotes_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_comms.list_all_quotes())

    def test_get_quote_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.get_quote("q-1")

    def test_create_quote_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.create_quote(
                rfq_id="rfq-1",
                yes_bid=Decimal("0.5"),
                no_bid=Decimal("0.5"),
                rest_remainder=True,
            )

    def test_delete_quote_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.delete_quote("q-1")

    def test_accept_quote_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.accept_quote("q-1", accepted_side="yes")

    def test_confirm_quote_requires_auth(
        self, unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.confirm_quote("q-1")


class TestClientWiring:
    def test_sync_client_exposes_communications(
        self, client: KalshiClient,
    ) -> None:
        assert isinstance(client.communications, CommunicationsResource)

    def test_async_client_exposes_communications(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        assert isinstance(
            async_client.communications, AsyncCommunicationsResource,
        )
