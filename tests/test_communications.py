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
from kalshi.config import DEMO_BASE_URL, DEMO_WS_URL, KalshiConfig
from kalshi.errors import (
    AuthRequiredError,
    KalshiNotFoundError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.models.communications import (
    RFQ,
    AcceptBlockTradeProposalRequest,
    AcceptQuoteRequest,
    AcceptRFQBatchRequest,
    BlockTradeProposal,
    CreateQuoteRequest,
    CreateQuoteResponse,
    CreateRFQBatchChild,
    CreateRFQBatchQuoteRequest,
    CreateRFQBatchRequest,
    CreateRFQRequest,
    CreateRFQResponse,
    GetBlockTradeProposalsResponse,
    GetCommunicationsIDResponse,
    GetQuoteResponse,
    GetRFQBatchBestQuotesResponse,
    GetRFQBatchQuotesResponse,
    GetRFQBatchResponse,
    GetRFQResponse,
    ProposeBlockTradeRequest,
    Quote,
    RFQBatch,
    RFQBatchAcceptLimit,
    RFQBatchBestQuote,
    RFQBatchQuote,
    RFQBatchQuoteEntry,
)
from kalshi.resources.communications import (
    AsyncCommunicationsResource,
    AsyncQuotesResource,
    AsyncRFQsResource,
    CommunicationsResource,
    QuotesResource,
    RFQBatchesResource,
    RFQBatchQuotesResource,
    RFQsResource,
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
    test_auth: KalshiAuth,
    config: KalshiConfig,
) -> AsyncCommunicationsResource:
    return AsyncCommunicationsResource(AsyncTransport(test_auth, config))


@pytest.fixture
def client(test_auth: KalshiAuth) -> KalshiClient:
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, ws_base_url=DEMO_WS_URL, timeout=5.0, max_retries=0)
    return KalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def async_client(test_auth: KalshiAuth) -> AsyncKalshiClient:
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, ws_base_url=DEMO_WS_URL, timeout=5.0, max_retries=0)
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
        rfq = RFQ.model_validate({**_MINIMAL_RFQ, "target_cost_dollars": "50.0000"})
        assert rfq.id == "rfq-1"
        assert rfq.contracts == Decimal("100")
        assert rfq.target_cost == Decimal("50.0000")
        assert rfq.status == "open"

    def test_rfq_and_quote_target_cost_excludes_fees(self) -> None:
        rfq = RFQ.model_validate({**_MINIMAL_RFQ, "target_cost_excludes_fees": True})
        quote = Quote.model_validate({**_MINIMAL_QUOTE, "target_cost_excludes_fees": True})
        assert rfq.target_cost_excludes_fees is True
        assert quote.target_cost_excludes_fees is True

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

    def test_create_rfq_request_serializes_obscure_creator_id(self) -> None:
        req = CreateRFQRequest(
            market_ticker="MKT-1",
            rest_remainder=True,
            obscure_creator_id=True,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["obscure_creator_id"] is True

    def test_create_rfq_request_omits_obscure_creator_id_when_none(self) -> None:
        req = CreateRFQRequest(
            market_ticker="MKT-1",
            rest_remainder=True,
            obscure_creator_id=None,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert "obscure_creator_id" not in body

    def test_create_rfq_request_serializes_target_cost_excludes_fees(self) -> None:
        req = CreateRFQRequest(
            market_ticker="MKT-1",
            rest_remainder=True,
            target_cost_excludes_fees=True,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["target_cost_excludes_fees"] is True

    def test_create_rfq_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateRFQRequest(  # type: ignore[call-arg]
                market_ticker="MKT-1",
                rest_remainder=True,
                phantom=1,
            )

    def test_create_rfq_rejects_zero_contracts(self) -> None:
        with pytest.raises(ValidationError):
            CreateRFQRequest(market_ticker="MKT-1", rest_remainder=True, contracts=0)

    def test_create_quote_request_serializes_bids_without_dollars_suffix(self) -> None:
        # Spec wire uses yes_bid / no_bid (no _dollars suffix) for this one.
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
                200,
                json={"rfqs": [_MINIMAL_RFQ], "cursor": "next"},
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
        self,
        comms: CommunicationsResource,
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
                    200,
                    json={"rfqs": [{**_MINIMAL_RFQ, "id": "rfq-3"}]},
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
    def test_sends_obscure_creator_id(self, comms: CommunicationsResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(201, json={"id": "rfq-new"}))
        comms.rfqs.create(
            market_ticker="MKT-1",
            rest_remainder=True,
            obscure_creator_id=True,
        )
        with pytest.warns(DeprecationWarning):
            comms.create_rfq(
                market_ticker="MKT-1",
                rest_remainder=True,
                obscure_creator_id=True,
            )
        for call in route.calls:
            body = json.loads(call.request.content)
            assert body["obscure_creator_id"] is True

    @respx.mock
    def test_sends_target_cost_excludes_fees(self, comms: CommunicationsResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(201, json={"id": "rfq-new"}))
        comms.create_rfq(
            market_ticker="MKT-1",
            rest_remainder=True,
            target_cost_excludes_fees=True,
        )
        body = json.loads(route.calls[0].request.content)
        assert body["target_cost_excludes_fees"] is True

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
        self,
        comms: CommunicationsResource,
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
        page = comms.list_quotes(quote_creator_user_id="u1")
        assert len(page.items) == 1
        assert isinstance(page.items[0], Quote)

    @respx.mock
    def test_passes_filters(self, comms: CommunicationsResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": []}))
        comms.list_quotes(
            rfq_id="rfq-1",
            status="accepted",
            quote_creator_user_id="u1",
        )
        params = route.calls[0].request.url.params
        assert params["rfq_id"] == "rfq-1"
        assert params["status"] == "accepted"
        assert params["quote_creator_user_id"] == "u1"

    @respx.mock
    def test_list_all_quotes_auto_paginates(
        self,
        comms: CommunicationsResource,
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
                    200,
                    json={"quotes": [{**_MINIMAL_QUOTE, "id": "q-2"}]},
                ),
            ],
        )
        items = list(comms.list_all_quotes(quote_creator_user_id="u1"))
        assert [q.id for q in items] == ["q-1", "q-2"]

    def test_raises_without_creator_filter(
        self,
        comms: CommunicationsResource,
    ) -> None:
        """Spec + demo require creator_user_id or rfq_creator_user_id.

        Fail fast locally instead of paying a network round trip for a 400.
        """
        with pytest.raises(
            ValueError,
            match=r"quote_creator_user_id.*rfq_creator_user_id",
        ):
            comms.list_quotes()

    def test_raises_without_creator_filter_even_with_rfq_id(
        self,
        comms: CommunicationsResource,
    ) -> None:
        """rfq_id alone is not enough — v0.11.0 integration audit confirmed."""
        with pytest.raises(ValueError):
            comms.list_quotes(rfq_id="rfq-1")

    @respx.mock
    def test_rfq_creator_user_id_alone_is_sufficient(
        self,
        comms: CommunicationsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": []}))
        page = comms.list_quotes(rfq_creator_user_id="u1")
        assert page.items == []

    def test_list_all_quotes_raises_without_creator_filter(
        self,
        comms: CommunicationsResource,
    ) -> None:
        """Generator-returning variant must raise eagerly, not on first yield."""
        with pytest.raises(ValueError):
            comms.list_all_quotes()

    @respx.mock
    def test_user_filter_alone_is_sufficient(
        self,
        comms: CommunicationsResource,
    ) -> None:
        """Spec v3.18.0 added user_filter='self' as a server-side shorthand
        for the caller's user-id, so it satisfies the filter requirement.
        """
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": []}))
        page = comms.list_quotes(user_filter="self")
        assert page.items == []

    @respx.mock
    def test_rfq_user_filter_alone_is_sufficient(
        self,
        comms: CommunicationsResource,
    ) -> None:
        """rfq_user_filter='self' (filter to quotes responding to the caller's
        own RFQs) is also a valid standalone satisfier.
        """
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": []}))
        page = comms.list_quotes(rfq_user_filter="self")
        assert page.items == []

    def test_raises_lists_all_four_satisfiers(
        self,
        comms: CommunicationsResource,
    ) -> None:
        """The updated error message must enumerate all four valid filters
        so callers know about the user_filter / rfq_user_filter shortcuts.
        """
        with pytest.raises(ValueError) as excinfo:
            comms.list_quotes()
        msg = str(excinfo.value)
        assert "quote_creator_user_id" in msg
        assert "rfq_creator_user_id" in msg
        assert "user_filter" in msg
        assert "rfq_user_filter" in msg


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


class TestRFQScopedQuoteActions:
    """RFQ-scoped quote actions (spec v3.22.0):
    ``/communications/rfqs/{rfq_id}/quotes/{quote_id}[/accept|/confirm]``."""

    @respx.mock
    def test_get_for_rfq_returns_quote(self, comms: CommunicationsResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/r-1/quotes/q-1",
        ).mock(return_value=httpx.Response(200, json={"quote": _MINIMAL_QUOTE}))
        resp = comms.quotes.get_for_rfq("r-1", "q-1")
        assert isinstance(resp, GetQuoteResponse)
        assert route.called

    @respx.mock
    def test_delete_for_rfq_sends_delete(self, comms: CommunicationsResource) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/r-1/quotes/q-1",
        ).mock(return_value=httpx.Response(204))
        comms.quotes.delete_for_rfq("r-1", "q-1")
        assert route.called

    @respx.mock
    def test_accept_for_rfq_sends_put_with_body(self, comms: CommunicationsResource) -> None:
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/r-1/quotes/q-1/accept",
        ).mock(return_value=httpx.Response(204))
        comms.quotes.accept_for_rfq("r-1", "q-1", accepted_side="yes")
        assert route.called
        body = json.loads(route.calls[0].request.content)
        assert body == {"accepted_side": "yes"}

    @respx.mock
    def test_confirm_for_rfq_sends_put_with_empty_body(self, comms: CommunicationsResource) -> None:
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/r-1/quotes/q-1/confirm",
        ).mock(return_value=httpx.Response(204))
        comms.quotes.confirm_for_rfq("r-1", "q-1")
        assert route.called
        # json={} forces Content-Type: application/json — demo rejects empty PUTs.
        assert route.calls[0].request.content == b"{}"

    @respx.mock
    def test_accept_for_rfq_404(self, comms: CommunicationsResource) -> None:
        respx.put(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/r-1/quotes/gone/accept",
        ).mock(return_value=httpx.Response(404, json={"message": "missing"}))
        with pytest.raises(KalshiNotFoundError):
            comms.quotes.accept_for_rfq("r-1", "gone", accepted_side="no")


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
            market_ticker="MKT-1",
            rest_remainder=True,
            contracts=5,
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
                    200,
                    json={"rfqs": [{**_MINIMAL_RFQ, "id": "rfq-2"}]},
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

    async def test_accept_for_rfq(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/r-1/quotes/q-1/accept",
        ).mock(return_value=httpx.Response(204))
        await async_comms.quotes.accept_for_rfq("r-1", "q-1", accepted_side="yes")
        body = json.loads(route.calls[0].request.content)
        assert body == {"accepted_side": "yes"}

    async def test_confirm_for_rfq(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/r-1/quotes/q-1/confirm",
        ).mock(return_value=httpx.Response(204))
        await async_comms.quotes.confirm_for_rfq("r-1", "q-1")
        assert route.calls[0].request.content == b"{}"

    async def test_get_for_rfq(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/r-1/quotes/q-1",
        ).mock(return_value=httpx.Response(200, json={"quote": _MINIMAL_QUOTE}))
        resp = await async_comms.quotes.get_for_rfq("r-1", "q-1")
        assert isinstance(resp, GetQuoteResponse)
        assert route.called

    async def test_delete_for_rfq(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.delete(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/r-1/quotes/q-1",
        ).mock(return_value=httpx.Response(204))
        await async_comms.quotes.delete_for_rfq("r-1", "q-1")
        assert route.called

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

    async def test_list_quotes_raises_without_creator_filter(
        self,
        async_comms: AsyncCommunicationsResource,
    ) -> None:
        with pytest.raises(
            ValueError,
            match=r"quote_creator_user_id.*rfq_creator_user_id",
        ):
            await async_comms.list_quotes()

    async def test_list_all_quotes_raises_without_creator_filter(
        self,
        async_comms: AsyncCommunicationsResource,
    ) -> None:
        """Must raise at call time, not on first iteration."""
        with pytest.raises(ValueError):
            async_comms.list_all_quotes()

    async def test_list_quotes_user_filter_alone_is_sufficient(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Spec v3.18.0: user_filter='self' satisfies the filter requirement."""
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": []}))
        page = await async_comms.list_quotes(user_filter="self")
        assert page.items == []

    async def test_list_quotes_rfq_user_filter_alone_is_sufficient(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": []}))
        page = await async_comms.list_quotes(rfq_user_filter="self")
        assert page.items == []


class TestCommunicationsAuthGuard:
    def test_get_id_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.get_id()

    def test_list_rfqs_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.list_rfqs()

    def test_list_all_rfqs_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_comms.list_all_rfqs())

    def test_get_rfq_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.get_rfq("rfq-1")

    def test_create_rfq_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.create_rfq(market_ticker="MKT-1", rest_remainder=True)

    def test_delete_rfq_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.delete_rfq("rfq-1")

    def test_list_quotes_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.list_quotes()

    def test_list_all_quotes_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_comms.list_all_quotes())

    def test_get_quote_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.get_quote("q-1")

    def test_create_quote_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.create_quote(
                rfq_id="rfq-1",
                yes_bid=Decimal("0.5"),
                no_bid=Decimal("0.5"),
                rest_remainder=True,
            )

    def test_delete_quote_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.delete_quote("q-1")

    def test_accept_quote_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.accept_quote("q-1", accepted_side="yes")

    def test_confirm_quote_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.confirm_quote("q-1")

    def test_get_for_rfq_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.quotes.get_for_rfq("r-1", "q-1")

    def test_delete_for_rfq_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.quotes.delete_for_rfq("r-1", "q-1")

    def test_accept_for_rfq_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.quotes.accept_for_rfq("r-1", "q-1", accepted_side="yes")

    def test_confirm_for_rfq_requires_auth(
        self,
        unauth_comms: CommunicationsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.quotes.confirm_for_rfq("r-1", "q-1")


class TestClientWiring:
    def test_sync_client_exposes_communications(
        self,
        client: KalshiClient,
    ) -> None:
        assert isinstance(client.communications, CommunicationsResource)

    def test_async_client_exposes_communications(
        self,
        async_client: AsyncKalshiClient,
    ) -> None:
        assert isinstance(
            async_client.communications,
            AsyncCommunicationsResource,
        )


class TestIssue324CommunicationsStatusLiteralNarrowing:
    """``status`` on list_rfqs / list_quotes is narrowed to a closed Literal
    matching the spec's RFQ.status and Quote.status enums (#324). The values
    are stable: tightening the type later would be a breaking change, so we
    pin them here. Static checking (mypy) is what fences typos at the call
    site; we mirror the static contract at runtime via ``typing.get_args``.
    """

    def test_issue_324_communications_status_literal_narrowing(self) -> None:
        from typing import get_args

        from kalshi.models.communications import (
            QuoteStatusLiteral,
            RfqStatusLiteral,
        )

        # Pin the closed set of values against the OpenAPI spec. Adding a new
        # status is a non-breaking expansion; removing one is breaking.
        assert set(get_args(RfqStatusLiteral)) == {"open", "closed"}
        assert set(get_args(QuoteStatusLiteral)) == {
            "open",
            "accepted",
            "confirmed",
            "executed",
            "cancelled",
        }

    def test_issue_324_status_literals_reexported_from_models_and_root(self) -> None:
        import kalshi
        import kalshi.models

        assert kalshi.RfqStatusLiteral is kalshi.models.RfqStatusLiteral
        assert kalshi.QuoteStatusLiteral is kalshi.models.QuoteStatusLiteral
        assert "RfqStatusLiteral" in kalshi.__all__
        assert "QuoteStatusLiteral" in kalshi.__all__

    @respx.mock
    def test_issue_324_valid_rfq_status_flows_through_to_query(
        self,
        comms: CommunicationsResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(200, json={"rfqs": []}))
        comms.list_rfqs(status="closed")
        assert route.calls[0].request.url.params["status"] == "closed"

    @respx.mock
    def test_issue_324_valid_quote_status_flows_through_to_query(
        self,
        comms: CommunicationsResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": []}))
        comms.list_quotes(status="executed", quote_creator_user_id="u1")
        assert route.calls[0].request.url.params["status"] == "executed"

    @pytest.mark.asyncio
    async def test_issue_324_valid_rfq_status_flows_through_to_query_async(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(200, json={"rfqs": []}))
        await async_comms.list_rfqs(status="closed")
        assert route.calls[0].request.url.params["status"] == "closed"

    @pytest.mark.asyncio
    async def test_issue_324_valid_quote_status_flows_through_to_query_async(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": []}))
        await async_comms.list_quotes(status="executed", quote_creator_user_id="u1")
        assert route.calls[0].request.url.params["status"] == "executed"


class TestV3DeprecationAliases:
    """v3.0.0 sub-namespace migration (#348).

    ``client.communications.{rfqs,quotes}.<verb>`` is the new shape. The flat
    ``list_rfqs`` / ``get_rfq`` / ``create_rfq`` / ``delete_rfq`` /
    ``list_all_rfqs`` / ``list_quotes`` / ``get_quote`` / ``create_quote`` /
    ``delete_quote`` / ``list_all_quotes`` / ``accept_quote`` /
    ``confirm_quote`` methods are kept as deprecated forwarders for one
    release. Each call emits ``DeprecationWarning`` and delegates to the
    sub-namespace equivalent.
    """

    @respx.mock
    def test_issue_348_rfqs_sub_namespace_works(
        self,
        comms: CommunicationsResource,
    ) -> None:
        assert isinstance(comms.rfqs, RFQsResource)
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(200, json={"rfqs": [_MINIMAL_RFQ]}))
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/rfq-1",
        ).mock(return_value=httpx.Response(200, json={"rfq": _MINIMAL_RFQ}))
        respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(201, json={"id": "rfq-new"}))

        page = comms.rfqs.list(limit=10)
        assert isinstance(page.items[0], RFQ)

        got = comms.rfqs.get("rfq-1")
        assert got.rfq.id == "rfq-1"

        created = comms.rfqs.create(market_ticker="MKT-1", rest_remainder=True)
        assert created.id == "rfq-new"

    @respx.mock
    def test_issue_348_quotes_sub_namespace_works(
        self,
        comms: CommunicationsResource,
    ) -> None:
        assert isinstance(comms.quotes, QuotesResource)
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": [_MINIMAL_QUOTE]}))
        respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(201, json={"id": "q-new"}))
        respx.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1/accept",
        ).mock(return_value=httpx.Response(204))

        page = comms.quotes.list(quote_creator_user_id="u1")
        assert isinstance(page.items[0], Quote)

        created = comms.quotes.create(
            rfq_id="rfq-1",
            yes_bid=Decimal("0.56"),
            no_bid=Decimal("0.44"),
            rest_remainder=True,
        )
        assert created.id == "q-new"

        comms.quotes.accept("q-1", accepted_side="yes")

    def test_issue_348_async_rfqs_sub_namespace_class(
        self,
        async_comms: AsyncCommunicationsResource,
    ) -> None:
        # Wiring check — full async I/O is exercised in TestAsyncCommunications
        # via the deprecated forwarders, which delegate here.
        assert isinstance(async_comms.rfqs, AsyncRFQsResource)
        assert isinstance(async_comms.quotes, AsyncQuotesResource)

    @respx.mock
    def test_issue_348_flat_names_still_work_emit_deprecation_warning(
        self,
        comms: CommunicationsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(200, json={"rfqs": [_MINIMAL_RFQ]}))
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/rfq-1",
        ).mock(return_value=httpx.Response(200, json={"rfq": _MINIMAL_RFQ}))
        respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(201, json={"id": "rfq-new"}))
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/rfq-1",
        ).mock(return_value=httpx.Response(204))

        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": [_MINIMAL_QUOTE]}))
        respx.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1",
        ).mock(return_value=httpx.Response(200, json={"quote": _MINIMAL_QUOTE}))
        respx.post(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(201, json={"id": "q-new"}))
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1",
        ).mock(return_value=httpx.Response(204))
        respx.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1/accept",
        ).mock(return_value=httpx.Response(204))
        respx.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1/confirm",
        ).mock(return_value=httpx.Response(204))

        # Each old flat method emits exactly one DeprecationWarning per call
        # and produces a response shape matching the sub-namespace method.
        with pytest.warns(DeprecationWarning, match=r"rfqs\.list"):
            page_rfqs = comms.list_rfqs(limit=10)
        assert isinstance(page_rfqs.items[0], RFQ)

        with pytest.warns(DeprecationWarning, match=r"rfqs\.list_all"):
            rfqs_all = list(comms.list_all_rfqs())
        assert isinstance(rfqs_all[0], RFQ)

        with pytest.warns(DeprecationWarning, match=r"rfqs\.get"):
            got_rfq = comms.get_rfq("rfq-1")
        assert got_rfq.rfq.id == "rfq-1"

        with pytest.warns(DeprecationWarning, match=r"rfqs\.create"):
            new_rfq = comms.create_rfq(market_ticker="MKT-1", rest_remainder=True)
        assert new_rfq.id == "rfq-new"

        with pytest.warns(DeprecationWarning, match=r"rfqs\.delete"):
            comms.delete_rfq("rfq-1")

        with pytest.warns(DeprecationWarning, match=r"quotes\.list"):
            page_quotes = comms.list_quotes(quote_creator_user_id="u1")
        assert isinstance(page_quotes.items[0], Quote)

        with pytest.warns(DeprecationWarning, match=r"quotes\.list_all"):
            quotes_all = list(comms.list_all_quotes(quote_creator_user_id="u1"))
        assert isinstance(quotes_all[0], Quote)

        with pytest.warns(DeprecationWarning, match=r"quotes\.get"):
            got_quote = comms.get_quote("q-1")
        assert got_quote.quote.id == "q-1"

        with pytest.warns(DeprecationWarning, match=r"quotes\.create"):
            new_quote = comms.create_quote(
                rfq_id="rfq-1",
                yes_bid=Decimal("0.5"),
                no_bid=Decimal("0.5"),
                rest_remainder=True,
            )
        assert new_quote.id == "q-new"

        with pytest.warns(DeprecationWarning, match=r"quotes\.delete"):
            comms.delete_quote("q-1")

        with pytest.warns(DeprecationWarning, match=r"quotes\.accept"):
            comms.accept_quote("q-1", accepted_side="yes")

        with pytest.warns(DeprecationWarning, match=r"quotes\.confirm"):
            comms.confirm_quote("q-1")

    @pytest.mark.asyncio
    async def test_issue_348_async_flat_names_emit_deprecation_warning(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(200, json={"rfqs": [_MINIMAL_RFQ]}))
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/rfq-1",
        ).mock(return_value=httpx.Response(200, json={"rfq": _MINIMAL_RFQ}))
        respx_mock.post(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs",
        ).mock(return_value=httpx.Response(201, json={"id": "rfq-new"}))
        respx_mock.delete(
            "https://test.kalshi.com/trade-api/v2/communications/rfqs/rfq-1",
        ).mock(return_value=httpx.Response(204))

        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(200, json={"quotes": [_MINIMAL_QUOTE]}))
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1",
        ).mock(return_value=httpx.Response(200, json={"quote": _MINIMAL_QUOTE}))
        respx_mock.post(
            "https://test.kalshi.com/trade-api/v2/communications/quotes",
        ).mock(return_value=httpx.Response(201, json={"id": "q-new"}))
        respx_mock.delete(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1",
        ).mock(return_value=httpx.Response(204))
        respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1/accept",
        ).mock(return_value=httpx.Response(204))
        respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/communications/quotes/q-1/confirm",
        ).mock(return_value=httpx.Response(204))

        with pytest.warns(DeprecationWarning, match=r"rfqs\.list"):
            page_rfqs = await async_comms.list_rfqs(limit=10)
        assert isinstance(page_rfqs.items[0], RFQ)

        with pytest.warns(DeprecationWarning, match=r"rfqs\.list_all"):
            rfqs_all = [r async for r in async_comms.list_all_rfqs()]
        assert isinstance(rfqs_all[0], RFQ)

        with pytest.warns(DeprecationWarning, match=r"rfqs\.get"):
            got_rfq = await async_comms.get_rfq("rfq-1")
        assert got_rfq.rfq.id == "rfq-1"

        with pytest.warns(DeprecationWarning, match=r"rfqs\.create"):
            new_rfq = await async_comms.create_rfq(
                market_ticker="MKT-1",
                rest_remainder=True,
            )
        assert new_rfq.id == "rfq-new"

        with pytest.warns(DeprecationWarning, match=r"rfqs\.delete"):
            await async_comms.delete_rfq("rfq-1")

        with pytest.warns(DeprecationWarning, match=r"quotes\.list"):
            page_quotes = await async_comms.list_quotes(quote_creator_user_id="u1")
        assert isinstance(page_quotes.items[0], Quote)

        with pytest.warns(DeprecationWarning, match=r"quotes\.list_all"):
            quotes_all = [q async for q in async_comms.list_all_quotes(quote_creator_user_id="u1")]
        assert isinstance(quotes_all[0], Quote)

        with pytest.warns(DeprecationWarning, match=r"quotes\.get"):
            got_quote = await async_comms.get_quote("q-1")
        assert got_quote.quote.id == "q-1"

        with pytest.warns(DeprecationWarning, match=r"quotes\.create"):
            new_quote = await async_comms.create_quote(
                rfq_id="rfq-1",
                yes_bid=Decimal("0.5"),
                no_bid=Decimal("0.5"),
                rest_remainder=True,
            )
        assert new_quote.id == "q-new"

        with pytest.warns(DeprecationWarning, match=r"quotes\.delete"):
            await async_comms.delete_quote("q-1")

        with pytest.warns(DeprecationWarning, match=r"quotes\.accept"):
            await async_comms.accept_quote("q-1", accepted_side="yes")

        with pytest.warns(DeprecationWarning, match=r"quotes\.confirm"):
            await async_comms.confirm_quote("q-1")


# ── block trade proposals (openapi 3.21.0) ─────────────────────────────────


_MINIMAL_BTP = {
    "id": "btp-1",
    "proposer_user_id": "u-prop",
    "buyer_user_id": "u-buy",
    "seller_user_id": "u-sell",
    "market_ticker": "MKT-1",
    "price_centi_cents": 5600,
    "centicount": 10000,
    "maker_side": "yes",
    "expiration_ts": "2026-04-18T13:00:00Z",
    "status": "open",
    "created_ts": "2026-04-18T12:00:00Z",
    "updated_ts": "2026-04-18T12:00:00Z",
    "buyer_accepted": False,
    "seller_accepted": False,
}


class TestBlockTradeProposalModels:
    def test_block_trade_proposal_parses(self) -> None:
        btp = BlockTradeProposal.model_validate(_MINIMAL_BTP)
        assert btp.id == "btp-1"
        assert btp.price_centi_cents == 5600
        assert btp.centicount == 10000
        assert btp.maker_side == "yes"
        assert btp.buyer_accepted is False

    def test_get_block_trade_proposals_response_wraps_list(self) -> None:
        resp = GetBlockTradeProposalsResponse.model_validate(
            {"block_trade_proposals": [_MINIMAL_BTP], "cursor": "next"}
        )
        assert len(resp.block_trade_proposals) == 1
        assert resp.cursor == "next"

    def test_propose_block_trade_request_serializes(self) -> None:
        req = ProposeBlockTradeRequest(
            buyer_user_id="u-buy",
            seller_user_id="u-sell",
            market_ticker="MKT-1",
            price_centi_cents=5600,
            centicount=10000,
            maker_side="yes",
            expiration_ts="2026-04-18T13:00:00Z",
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["price_centi_cents"] == 5600
        assert body["centicount"] == 10000
        assert "buyer_subtrader_id" not in body  # exclude_none drops it

    def test_propose_block_trade_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            ProposeBlockTradeRequest(
                buyer_user_id="u-buy",
                seller_user_id="u-sell",
                market_ticker="MKT-1",
                price_centi_cents=5600,
                centicount=10000,
                maker_side="yes",
                expiration_ts="2026-04-18T13:00:00Z",
                bogus="x",  # type: ignore[call-arg]
            )

    def test_propose_block_trade_request_rejects_zero_price(self) -> None:
        with pytest.raises(ValidationError):
            ProposeBlockTradeRequest(
                buyer_user_id="u-buy",
                seller_user_id="u-sell",
                market_ticker="MKT-1",
                price_centi_cents=0,
                centicount=10000,
                maker_side="yes",
                expiration_ts="2026-04-18T13:00:00Z",
            )

    def test_propose_block_trade_request_requires_market_ticker(self) -> None:
        with pytest.raises(ValidationError):
            ProposeBlockTradeRequest(  # type: ignore[call-arg]  # market_ticker omitted
                buyer_user_id="u-buy",
                seller_user_id="u-sell",
                price_centi_cents=5600,
                centicount=10000,
                maker_side="yes",
                expiration_ts="2026-04-18T13:00:00Z",
            )

    def test_accept_block_trade_proposal_request_allows_empty(self) -> None:
        req = AcceptBlockTradeProposalRequest()
        assert req.model_dump(exclude_none=True, by_alias=True, mode="json") == {}

    def test_accept_block_trade_proposal_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            AcceptBlockTradeProposalRequest(bogus="x")  # type: ignore[call-arg]


_BTP_URL = "https://test.kalshi.com/trade-api/v2/communications/block-trade-proposals"


class TestListBlockTradeProposals:
    @respx.mock
    def test_returns_paged_proposals(self, comms: CommunicationsResource) -> None:
        respx.get(_BTP_URL).mock(
            return_value=httpx.Response(200, json={"block_trade_proposals": [_MINIMAL_BTP]})
        )
        page = comms.block_trade_proposals.list()
        assert len(page.items) == 1
        assert isinstance(page.items[0], BlockTradeProposal)
        assert page.items[0].id == "btp-1"

    @respx.mock
    def test_passes_filter_params(self, comms: CommunicationsResource) -> None:
        route = respx.get(_BTP_URL).mock(
            return_value=httpx.Response(200, json={"block_trade_proposals": []})
        )
        comms.block_trade_proposals.list(market_ticker="MKT-1", status="open", limit=50)
        req = route.calls[0].request
        assert req.url.params["market_ticker"] == "MKT-1"
        assert req.url.params["status"] == "open"
        assert req.url.params["limit"] == "50"

    @respx.mock
    def test_list_all_auto_paginates(self, comms: CommunicationsResource) -> None:
        respx.get(_BTP_URL).mock(
            side_effect=[
                httpx.Response(
                    200, json={"block_trade_proposals": [_MINIMAL_BTP], "cursor": "page2"}
                ),
                httpx.Response(
                    200, json={"block_trade_proposals": [{**_MINIMAL_BTP, "id": "btp-2"}]}
                ),
            ]
        )
        ids = [p.id for p in comms.block_trade_proposals.list_all()]
        assert ids == ["btp-1", "btp-2"]

    @respx.mock
    def test_500_raises(self, comms: CommunicationsResource) -> None:
        respx.get(_BTP_URL).mock(return_value=httpx.Response(500, json={"message": "boom"}))
        with pytest.raises(KalshiServerError):
            comms.block_trade_proposals.list()


class TestProposeBlockTrade:
    @respx.mock
    def test_sends_correct_body(self, comms: CommunicationsResource) -> None:
        route = respx.post(_BTP_URL).mock(
            return_value=httpx.Response(201, json={"block_trade_proposal_id": "btp-new"})
        )
        resp = comms.block_trade_proposals.create(
            buyer_user_id="u-buy",
            seller_user_id="u-sell",
            market_ticker="MKT-1",
            price_centi_cents=5600,
            centicount=10000,
            maker_side="yes",
            expiration_ts="2026-04-18T13:00:00Z",
        )
        assert resp.block_trade_proposal_id == "btp-new"
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "buyer_user_id": "u-buy",
            "seller_user_id": "u-sell",
            "market_ticker": "MKT-1",
            "price_centi_cents": 5600,
            "centicount": 10000,
            "maker_side": "yes",
            "expiration_ts": "2026-04-18T13:00:00Z",
        }

    @respx.mock
    def test_accepts_request_model(self, comms: CommunicationsResource) -> None:
        route = respx.post(_BTP_URL).mock(
            return_value=httpx.Response(201, json={"block_trade_proposal_id": "btp-r"})
        )
        req = ProposeBlockTradeRequest(
            buyer_user_id="u-buy",
            seller_user_id="u-sell",
            market_ticker="MKT-1",
            price_centi_cents=4400,
            centicount=5000,
            maker_side="no",
            expiration_ts="2026-04-18T13:00:00Z",
            buyer_subaccount=3,
        )
        resp = comms.block_trade_proposals.create(request=req)
        assert resp.block_trade_proposal_id == "btp-r"
        body = json.loads(route.calls[0].request.content)
        assert body["buyer_subaccount"] == 3
        assert body["maker_side"] == "no"

    def test_create_rejects_request_with_kwargs(self, comms: CommunicationsResource) -> None:
        req = ProposeBlockTradeRequest(
            buyer_user_id="u-buy",
            seller_user_id="u-sell",
            market_ticker="MKT-1",
            price_centi_cents=5600,
            centicount=10000,
            maker_side="yes",
            expiration_ts="2026-04-18T13:00:00Z",
        )
        with pytest.raises(TypeError):
            comms.block_trade_proposals.create(request=req, buyer_user_id="x")

    @respx.mock
    def test_400_maps_to_validation_error(self, comms: CommunicationsResource) -> None:
        respx.post(_BTP_URL).mock(return_value=httpx.Response(400, json={"message": "bad"}))
        with pytest.raises(KalshiValidationError):
            comms.block_trade_proposals.create(
                buyer_user_id="u-buy",
                seller_user_id="u-sell",
                market_ticker="MKT-1",
                price_centi_cents=5600,
                centicount=10000,
                maker_side="yes",
                expiration_ts="2026-04-18T13:00:00Z",
            )


class TestAcceptBlockTradeProposal:
    @respx.mock
    def test_sends_post_with_empty_body(self, comms: CommunicationsResource) -> None:
        route = respx.post(f"{_BTP_URL}/btp-1/accept").mock(return_value=httpx.Response(204))
        comms.block_trade_proposals.accept("btp-1")
        assert route.called
        # empty AcceptBlockTradeProposalRequest serializes to {}
        assert route.calls[0].request.content == b"{}"

    @respx.mock
    def test_sends_post_with_subaccount(self, comms: CommunicationsResource) -> None:
        route = respx.post(f"{_BTP_URL}/btp-1/accept").mock(return_value=httpx.Response(204))
        comms.block_trade_proposals.accept("btp-1", subaccount=2)
        body = json.loads(route.calls[0].request.content)
        assert body == {"subaccount": 2}

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.post(f"{_BTP_URL}/gone/accept").mock(
            return_value=httpx.Response(404, json={"message": "missing"})
        )
        with pytest.raises(KalshiNotFoundError):
            comms.block_trade_proposals.accept("gone")


class TestAsyncBlockTradeProposals:
    async def test_list(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(_BTP_URL).mock(
            return_value=httpx.Response(200, json={"block_trade_proposals": [_MINIMAL_BTP]})
        )
        page = await async_comms.block_trade_proposals.list()
        assert len(page.items) == 1
        assert isinstance(page.items[0], BlockTradeProposal)

    async def test_list_all(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(_BTP_URL).mock(
            side_effect=[
                httpx.Response(
                    200, json={"block_trade_proposals": [_MINIMAL_BTP], "cursor": "page2"}
                ),
                httpx.Response(
                    200, json={"block_trade_proposals": [{**_MINIMAL_BTP, "id": "btp-2"}]}
                ),
            ]
        )
        ids = [p.id async for p in async_comms.block_trade_proposals.list_all()]
        assert ids == ["btp-1", "btp-2"]

    async def test_create(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(_BTP_URL).mock(
            return_value=httpx.Response(201, json={"block_trade_proposal_id": "btp-9"})
        )
        resp = await async_comms.block_trade_proposals.create(
            buyer_user_id="u-buy",
            seller_user_id="u-sell",
            market_ticker="MKT-1",
            price_centi_cents=5600,
            centicount=10000,
            maker_side="yes",
            expiration_ts="2026-04-18T13:00:00Z",
        )
        assert resp.block_trade_proposal_id == "btp-9"
        assert route.called

    async def test_accept(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(f"{_BTP_URL}/btp-1/accept").mock(return_value=httpx.Response(204))
        await async_comms.block_trade_proposals.accept("btp-1", subtrader_id="st-1")
        body = json.loads(route.calls[0].request.content)
        assert body == {"subtrader_id": "st-1"}


class TestBlockTradeProposalsAuthGuard:
    def test_list_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.block_trade_proposals.list()

    def test_list_all_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_comms.block_trade_proposals.list_all())

    def test_create_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.block_trade_proposals.create(
                buyer_user_id="u-buy",
                seller_user_id="u-sell",
                market_ticker="MKT-1",
                price_centi_cents=5600,
                centicount=10000,
                maker_side="yes",
                expiration_ts="2026-04-18T13:00:00Z",
            )

    def test_accept_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.block_trade_proposals.accept("btp-1")


# ── RFQ batches ─────────────────────────────────────────────────────────────


_MINIMAL_RFQ_BATCH = {
    "id": "batch-1",
    "creator_id": "comm-42",
    "status": "open",
    "created_ts": "2026-04-18T12:00:00Z",
    "rfqs": [_MINIMAL_RFQ, {**_MINIMAL_RFQ, "id": "rfq-2", "market_ticker": "MKT-2"}],
}

_MINIMAL_BATCH_QUOTE = {
    "id": "bq-1",
    "rfq_batch_id": "batch-1",
    "creator_id": "comm-99",
    "rfq_creator_id": "comm-42",
    "status": "open",
    "created_ts": "2026-04-18T12:01:00Z",
    "updated_ts": "2026-04-18T12:01:00Z",
    "quotes": [_MINIMAL_QUOTE],
}

_MINIMAL_BEST_QUOTES = {
    "rfq_batch_id": "batch-1",
    "status": "open",
    "version": 3,
    "yes_complete": True,
    "no_complete": False,
    "rfqs": [
        {
            "rfq_id": "rfq-1",
            "market_ticker": "MKT-1",
            "yes_bid_dollars": "0.5600",
            "no_bid_dollars": "0.4400",
            "yes_contracts_offered_fp": "10.00",
            "no_contracts_offered_fp": "10.00",
        },
        {"rfq_id": "rfq-2", "market_ticker": "MKT-2"},
    ],
}

_BATCH_URL = "https://test.kalshi.com/trade-api/v2/communications/rfq_batches"

_CHILDREN = [
    CreateRFQBatchChild(market_ticker="MKT-1"),
    CreateRFQBatchChild(market_ticker="MKT-2"),
]


class TestRFQBatchModels:
    def test_rfq_batch_parses(self) -> None:
        batch = RFQBatch.model_validate(_MINIMAL_RFQ_BATCH)
        assert batch.id == "batch-1"
        assert len(batch.rfqs) == 2
        assert isinstance(batch.rfqs[0], RFQ)

    def test_get_rfq_batch_response_wraps(self) -> None:
        resp = GetRFQBatchResponse.model_validate({"rfq_batch": _MINIMAL_RFQ_BATCH})
        assert resp.rfq_batch.id == "batch-1"

    def test_batch_quote_parses(self) -> None:
        q = RFQBatchQuote.model_validate(_MINIMAL_BATCH_QUOTE)
        assert q.id == "bq-1"
        assert isinstance(q.quotes[0], Quote)

    def test_best_quote_accepts_dollars_and_fp_aliases(self) -> None:
        bq = RFQBatchBestQuote.model_validate(
            {
                "rfq_id": "rfq-1",
                "market_ticker": "MKT-1",
                "yes_bid_dollars": "0.5600",
                "yes_contracts_offered_fp": "10.00",
            }
        )
        assert bq.yes_bid == Decimal("0.5600")
        assert bq.yes_contracts_offered == Decimal("10.00")

    def test_best_quote_accepts_short_names(self) -> None:
        bq = RFQBatchBestQuote.model_validate(
            {
                "rfq_id": "rfq-1",
                "market_ticker": "MKT-1",
                "yes_bid": "0.50",
                "yes_contracts_offered": "5",
            }
        )
        assert bq.yes_bid == Decimal("0.50")
        assert bq.yes_contracts_offered == Decimal("5")

    def test_create_rfq_batch_request_serializes_fp_and_dollars(self) -> None:
        req = CreateRFQBatchRequest(
            children=_CHILDREN,
            contracts=Decimal("10.00"),
            target_cost=Decimal("5.00"),
            rest_remainder=True,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["contracts_fp"] == "10.00"
        assert body["target_cost_dollars"] == "5.00"
        assert "contracts" not in body
        assert "target_cost" not in body
        assert body["rest_remainder"] is True

    def test_create_rfq_batch_request_omits_optional(self) -> None:
        req = CreateRFQBatchRequest(children=_CHILDREN)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {
            "children": [{"market_ticker": "MKT-1"}, {"market_ticker": "MKT-2"}],
        }

    def test_create_rfq_batch_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateRFQBatchRequest(children=_CHILDREN, phantom=1)  # type: ignore[call-arg]

    def test_create_rfq_batch_child_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateRFQBatchChild(market_ticker="MKT-1", phantom=1)  # type: ignore[call-arg]

    def test_create_rfq_batch_child_serializes_fp_and_dollars(self) -> None:
        child = CreateRFQBatchChild(
            market_ticker="MKT-1",
            contracts=Decimal("10.00"),
            target_cost=Decimal("5.00"),
        )
        body = child.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["contracts_fp"] == "10.00"
        assert body["target_cost_dollars"] == "5.00"
        assert "contracts" not in body
        assert "target_cost" not in body

    def test_create_rfq_batch_child_accepts_wire_aliases(self) -> None:
        child = CreateRFQBatchChild.model_validate(
            {
                "market_ticker": "MKT-1",
                "contracts_fp": "10.00",
                "target_cost_dollars": "5.00",
            }
        )
        assert child.contracts == Decimal("10.00")
        assert child.target_cost == Decimal("5.00")

    def test_create_rfq_batch_child_accepts_python_names(self) -> None:
        child = CreateRFQBatchChild(market_ticker="MKT-1", contracts=Decimal("10.00"))
        assert child.contracts == Decimal("10.00")
        assert child.target_cost is None

    def test_create_rfq_batch_child_omits_optional_size(self) -> None:
        child = CreateRFQBatchChild(market_ticker="MKT-1")
        body = child.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"market_ticker": "MKT-1"}

    def test_create_rfq_batch_quote_request_serializes_bids_without_suffix(self) -> None:
        req = CreateRFQBatchQuoteRequest(
            quotes=[
                RFQBatchQuoteEntry(
                    rfq_id="rfq-1", yes_bid=Decimal("0.56"), no_bid=Decimal("0.44")
                ),
                RFQBatchQuoteEntry(
                    rfq_id="rfq-2", yes_bid=Decimal("0.50"), no_bid=Decimal("0.50")
                ),
            ],
            rest_remainder=True,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["quotes"][0] == {
            "rfq_id": "rfq-1",
            "yes_bid": "0.56",
            "no_bid": "0.44",
        }
        assert "yes_bid_dollars" not in body["quotes"][0]

    def test_create_rfq_batch_quote_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateRFQBatchQuoteRequest(  # type: ignore[call-arg]
                quotes=[
                    RFQBatchQuoteEntry(
                        rfq_id="rfq-1", yes_bid=Decimal("0.5"), no_bid=Decimal("0.5")
                    ),
                    RFQBatchQuoteEntry(
                        rfq_id="rfq-2", yes_bid=Decimal("0.5"), no_bid=Decimal("0.5")
                    ),
                ],
                rest_remainder=True,
                phantom=True,
            )

    def test_accept_rfq_batch_request_serializes_bid_dollars(self) -> None:
        req = AcceptRFQBatchRequest(
            accepted_side="yes",
            min_bids=[
                RFQBatchAcceptLimit(rfq_id="rfq-1", bid=Decimal("0.56")),
                RFQBatchAcceptLimit(rfq_id="rfq-2", bid=Decimal("0.44")),
            ],
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {
            "accepted_side": "yes",
            "min_bids": [
                {"rfq_id": "rfq-1", "bid_dollars": "0.56"},
                {"rfq_id": "rfq-2", "bid_dollars": "0.44"},
            ],
        }

    def test_accept_rfq_batch_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            AcceptRFQBatchRequest(  # type: ignore[call-arg]
                accepted_side="yes",
                min_bids=[
                    RFQBatchAcceptLimit(rfq_id="rfq-1", bid=Decimal("0.5")),
                    RFQBatchAcceptLimit(rfq_id="rfq-2", bid=Decimal("0.5")),
                ],
                phantom=1,
            )

    def test_rfq_batch_accept_limit_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            RFQBatchAcceptLimit(rfq_id="rfq-1", bid=Decimal("0.5"), phantom=1)  # type: ignore[call-arg]


class TestListRFQBatches:
    @respx.mock
    def test_returns_paged_batches(self, comms: CommunicationsResource) -> None:
        respx.get(_BATCH_URL).mock(
            return_value=httpx.Response(200, json={"rfq_batches": [_MINIMAL_RFQ_BATCH]})
        )
        page = comms.rfq_batches.list()
        assert len(page.items) == 1
        assert isinstance(page.items[0], RFQBatch)
        assert page.items[0].id == "batch-1"
        assert isinstance(comms.rfq_batches, RFQBatchesResource)

    @respx.mock
    def test_passes_filter_params(self, comms: CommunicationsResource) -> None:
        route = respx.get(_BATCH_URL).mock(
            return_value=httpx.Response(200, json={"rfq_batches": []})
        )
        comms.rfq_batches.list(status="open", subaccount=3, user_filter="self", limit=10)
        params = route.calls[0].request.url.params
        assert params["status"] == "open"
        assert params["subaccount"] == "3"
        assert params["user_filter"] == "self"
        assert params["limit"] == "10"

    def test_limit_out_of_range(self, comms: CommunicationsResource) -> None:
        with pytest.raises(ValueError, match="limit"):
            comms.rfq_batches.list(limit=21)

    @respx.mock
    def test_list_all_auto_paginates(self, comms: CommunicationsResource) -> None:
        respx.get(_BATCH_URL).mock(
            side_effect=[
                httpx.Response(
                    200, json={"rfq_batches": [_MINIMAL_RFQ_BATCH], "cursor": "page2"}
                ),
                httpx.Response(
                    200, json={"rfq_batches": [{**_MINIMAL_RFQ_BATCH, "id": "batch-2"}]}
                ),
            ]
        )
        ids = [b.id for b in comms.rfq_batches.list_all()]
        assert ids == ["batch-1", "batch-2"]

    @respx.mock
    def test_500_raises(self, comms: CommunicationsResource) -> None:
        respx.get(_BATCH_URL).mock(return_value=httpx.Response(500, json={"message": "boom"}))
        with pytest.raises(KalshiServerError):
            comms.rfq_batches.list()


class TestGetRFQBatch:
    @respx.mock
    def test_returns_batch(self, comms: CommunicationsResource) -> None:
        respx.get(f"{_BATCH_URL}/batch-1").mock(
            return_value=httpx.Response(200, json={"rfq_batch": _MINIMAL_RFQ_BATCH})
        )
        resp = comms.rfq_batches.get("batch-1")
        assert resp.rfq_batch.id == "batch-1"

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.get(f"{_BATCH_URL}/missing").mock(
            return_value=httpx.Response(404, json={"message": "missing"})
        )
        with pytest.raises(KalshiNotFoundError):
            comms.rfq_batches.get("missing")

    def test_empty_id_rejected(self, comms: CommunicationsResource) -> None:
        with pytest.raises(ValueError, match="rfq_batch_id"):
            comms.rfq_batches.get("")


class TestCreateRFQBatch:
    @respx.mock
    def test_sends_correct_body(self, comms: CommunicationsResource) -> None:
        route = respx.post(_BATCH_URL).mock(
            return_value=httpx.Response(201, json={"rfq_batch": _MINIMAL_RFQ_BATCH})
        )
        resp = comms.rfq_batches.create(
            children=_CHILDREN,
            contracts=Decimal("10"),
            rest_remainder=True,
            subaccount=2,
        )
        assert resp.rfq_batch.id == "batch-1"
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "children": [{"market_ticker": "MKT-1"}, {"market_ticker": "MKT-2"}],
            "contracts_fp": "10",
            "rest_remainder": True,
            "subaccount": 2,
        }

    @respx.mock
    def test_sends_per_child_size(self, comms: CommunicationsResource) -> None:
        route = respx.post(_BATCH_URL).mock(
            return_value=httpx.Response(201, json={"rfq_batch": _MINIMAL_RFQ_BATCH})
        )
        comms.rfq_batches.create(
            children=[
                CreateRFQBatchChild(market_ticker="MKT-1", contracts=Decimal("10.00")),
                CreateRFQBatchChild(market_ticker="MKT-2", target_cost=Decimal("5.00")),
            ],
        )
        body = json.loads(route.calls[0].request.content)
        assert body["children"][0] == {"market_ticker": "MKT-1", "contracts_fp": "10.00"}
        assert body["children"][1] == {
            "market_ticker": "MKT-2",
            "target_cost_dollars": "5.00",
        }

    @respx.mock
    def test_accepts_request_model(self, comms: CommunicationsResource) -> None:
        route = respx.post(_BATCH_URL).mock(
            return_value=httpx.Response(201, json={"rfq_batch": _MINIMAL_RFQ_BATCH})
        )
        req = CreateRFQBatchRequest(
            children=_CHILDREN,
            target_cost=Decimal("5.00"),
            client_batch_id="cli-batch",
        )
        comms.rfq_batches.create(request=req)
        body = json.loads(route.calls[0].request.content)
        assert body["target_cost_dollars"] == "5.00"
        assert body["client_batch_id"] == "cli-batch"

    def test_create_rejects_request_with_kwargs(self, comms: CommunicationsResource) -> None:
        req = CreateRFQBatchRequest(children=_CHILDREN)
        with pytest.raises(TypeError):
            comms.rfq_batches.create(request=req, children=_CHILDREN)

    def test_create_requires_children(self, comms: CommunicationsResource) -> None:
        with pytest.raises(TypeError, match="children"):
            comms.rfq_batches.create()

    @respx.mock
    def test_400_maps_to_validation_error(self, comms: CommunicationsResource) -> None:
        respx.post(_BATCH_URL).mock(return_value=httpx.Response(400, json={"message": "bad"}))
        with pytest.raises(KalshiValidationError):
            comms.rfq_batches.create(children=_CHILDREN)


class TestDeleteRFQBatch:
    @respx.mock
    def test_sends_delete(self, comms: CommunicationsResource) -> None:
        route = respx.delete(f"{_BATCH_URL}/batch-1").mock(return_value=httpx.Response(204))
        comms.rfq_batches.delete("batch-1")
        assert route.called

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.delete(f"{_BATCH_URL}/gone").mock(
            return_value=httpx.Response(404, json={"message": "missing"})
        )
        with pytest.raises(KalshiNotFoundError):
            comms.rfq_batches.delete("gone")


class TestAcceptRFQBatch:
    @respx.mock
    def test_sends_put_with_body(self, comms: CommunicationsResource) -> None:
        route = respx.put(f"{_BATCH_URL}/batch-1/accept").mock(
            return_value=httpx.Response(
                200,
                json={"accepted_side": "yes", "quotes": [_MINIMAL_QUOTE, _MINIMAL_QUOTE]},
            )
        )
        resp = comms.rfq_batches.accept(
            "batch-1",
            accepted_side="yes",
            min_bids=[
                RFQBatchAcceptLimit(rfq_id="rfq-1", bid=Decimal("0.56")),
                RFQBatchAcceptLimit(rfq_id="rfq-2", bid=Decimal("0.44")),
            ],
        )
        assert resp.accepted_side == "yes"
        assert len(resp.quotes) == 2
        body = json.loads(route.calls[0].request.content)
        assert body["accepted_side"] == "yes"
        assert body["min_bids"][0]["bid_dollars"] == "0.56"

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.put(f"{_BATCH_URL}/gone/accept").mock(
            return_value=httpx.Response(404, json={"message": "missing"})
        )
        with pytest.raises(KalshiNotFoundError):
            comms.rfq_batches.accept(
                "gone",
                accepted_side="no",
                min_bids=[
                    RFQBatchAcceptLimit(rfq_id="rfq-1", bid=Decimal("0.5")),
                    RFQBatchAcceptLimit(rfq_id="rfq-2", bid=Decimal("0.5")),
                ],
            )

    def test_accept_requires_min_bids(self, comms: CommunicationsResource) -> None:
        with pytest.raises(TypeError, match="min_bids"):
            comms.rfq_batches.accept("batch-1", accepted_side="yes")


class TestBestQuotesRFQBatch:
    @respx.mock
    def test_returns_best_quotes(self, comms: CommunicationsResource) -> None:
        respx.get(f"{_BATCH_URL}/batch-1/best_quotes").mock(
            return_value=httpx.Response(200, json={"best_quotes": _MINIMAL_BEST_QUOTES})
        )
        resp = comms.rfq_batches.best_quotes("batch-1")
        assert isinstance(resp, GetRFQBatchBestQuotesResponse)
        assert resp.best_quotes.version == 3
        assert resp.best_quotes.rfqs[0].yes_bid == Decimal("0.5600")
        assert resp.best_quotes.rfqs[1].yes_bid is None

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.get(f"{_BATCH_URL}/gone/best_quotes").mock(
            return_value=httpx.Response(404, json={"message": "missing"})
        )
        with pytest.raises(KalshiNotFoundError):
            comms.rfq_batches.best_quotes("gone")


class TestListRFQBatchQuotes:
    @respx.mock
    def test_returns_quotes(self, comms: CommunicationsResource) -> None:
        respx.get(f"{_BATCH_URL}/batch-1/quotes").mock(
            return_value=httpx.Response(200, json={"batch_quotes": [_MINIMAL_BATCH_QUOTE]})
        )
        resp = comms.rfq_batches.quotes.list("batch-1")
        assert isinstance(resp, GetRFQBatchQuotesResponse)
        assert isinstance(comms.rfq_batches.quotes, RFQBatchQuotesResource)
        assert len(resp.batch_quotes) == 1
        assert resp.batch_quotes[0].id == "bq-1"

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.get(f"{_BATCH_URL}/gone/quotes").mock(
            return_value=httpx.Response(404, json={"message": "missing"})
        )
        with pytest.raises(KalshiNotFoundError):
            comms.rfq_batches.quotes.list("gone")

    @respx.mock
    def test_empty_list(self, comms: CommunicationsResource) -> None:
        respx.get(f"{_BATCH_URL}/batch-1/quotes").mock(
            return_value=httpx.Response(200, json={"batch_quotes": []})
        )
        resp = comms.rfq_batches.quotes.list("batch-1")
        assert resp.batch_quotes == []


class TestCreateRFQBatchQuote:
    @respx.mock
    def test_sends_correct_body(self, comms: CommunicationsResource) -> None:
        route = respx.post(f"{_BATCH_URL}/batch-1/quotes").mock(
            return_value=httpx.Response(201, json={"id": "bq-new"})
        )
        resp = comms.rfq_batches.quotes.create(
            "batch-1",
            quotes=[
                RFQBatchQuoteEntry(
                    rfq_id="rfq-1", yes_bid=Decimal("0.56"), no_bid=Decimal("0.44")
                ),
                RFQBatchQuoteEntry(
                    rfq_id="rfq-2", yes_bid=Decimal("0.50"), no_bid=Decimal("0.50")
                ),
            ],
            rest_remainder=True,
            post_only=True,
        )
        assert resp.id == "bq-new"
        body = json.loads(route.calls[0].request.content)
        assert body["rest_remainder"] is True
        assert body["post_only"] is True
        assert body["quotes"][0]["yes_bid"] == "0.56"

    @respx.mock
    def test_400(self, comms: CommunicationsResource) -> None:
        respx.post(f"{_BATCH_URL}/batch-1/quotes").mock(
            return_value=httpx.Response(400, json={"message": "bad"})
        )
        with pytest.raises(KalshiValidationError):
            comms.rfq_batches.quotes.create(
                "batch-1",
                quotes=[
                    RFQBatchQuoteEntry(
                        rfq_id="rfq-1", yes_bid=Decimal("0.5"), no_bid=Decimal("0.5")
                    ),
                    RFQBatchQuoteEntry(
                        rfq_id="rfq-2", yes_bid=Decimal("0.5"), no_bid=Decimal("0.5")
                    ),
                ],
                rest_remainder=False,
            )

    def test_create_requires_quotes(self, comms: CommunicationsResource) -> None:
        with pytest.raises(TypeError, match="quotes"):
            comms.rfq_batches.quotes.create("batch-1", rest_remainder=True)


class TestDeleteRFQBatchQuote:
    @respx.mock
    def test_sends_delete(self, comms: CommunicationsResource) -> None:
        route = respx.delete(f"{_BATCH_URL}/batch-1/quotes/bq-1").mock(
            return_value=httpx.Response(204)
        )
        comms.rfq_batches.quotes.delete("batch-1", "bq-1")
        assert route.called

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.delete(f"{_BATCH_URL}/batch-1/quotes/gone").mock(
            return_value=httpx.Response(404, json={"message": "missing"})
        )
        with pytest.raises(KalshiNotFoundError):
            comms.rfq_batches.quotes.delete("batch-1", "gone")


class TestConfirmRFQBatchQuote:
    @respx.mock
    def test_sends_put_with_empty_body(self, comms: CommunicationsResource) -> None:
        route = respx.put(f"{_BATCH_URL}/batch-1/quotes/bq-1/confirm").mock(
            return_value=httpx.Response(204)
        )
        comms.rfq_batches.quotes.confirm("batch-1", "bq-1")
        assert route.called
        assert route.calls[0].request.content == b"{}"

    @respx.mock
    def test_404(self, comms: CommunicationsResource) -> None:
        respx.put(f"{_BATCH_URL}/batch-1/quotes/gone/confirm").mock(
            return_value=httpx.Response(404, json={"message": "missing"})
        )
        with pytest.raises(KalshiNotFoundError):
            comms.rfq_batches.quotes.confirm("batch-1", "gone")


class TestAsyncRFQBatches:
    async def test_list(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(_BATCH_URL).mock(
            return_value=httpx.Response(200, json={"rfq_batches": [_MINIMAL_RFQ_BATCH]})
        )
        page = await async_comms.rfq_batches.list()
        assert len(page.items) == 1
        assert isinstance(page.items[0], RFQBatch)

    async def test_list_all(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(_BATCH_URL).mock(
            side_effect=[
                httpx.Response(
                    200, json={"rfq_batches": [_MINIMAL_RFQ_BATCH], "cursor": "page2"}
                ),
                httpx.Response(
                    200, json={"rfq_batches": [{**_MINIMAL_RFQ_BATCH, "id": "batch-2"}]}
                ),
            ]
        )
        ids = [b.id async for b in async_comms.rfq_batches.list_all()]
        assert ids == ["batch-1", "batch-2"]

    async def test_get(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(f"{_BATCH_URL}/batch-1").mock(
            return_value=httpx.Response(200, json={"rfq_batch": _MINIMAL_RFQ_BATCH})
        )
        resp = await async_comms.rfq_batches.get("batch-1")
        assert resp.rfq_batch.id == "batch-1"

    async def test_create(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(_BATCH_URL).mock(
            return_value=httpx.Response(201, json={"rfq_batch": _MINIMAL_RFQ_BATCH})
        )
        resp = await async_comms.rfq_batches.create(children=_CHILDREN)
        assert resp.rfq_batch.id == "batch-1"
        assert route.called

    async def test_delete(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.delete(f"{_BATCH_URL}/batch-1").mock(
            return_value=httpx.Response(204)
        )
        await async_comms.rfq_batches.delete("batch-1")
        assert route.called

    async def test_accept(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.put(f"{_BATCH_URL}/batch-1/accept").mock(
            return_value=httpx.Response(
                200, json={"accepted_side": "yes", "quotes": [_MINIMAL_QUOTE]}
            )
        )
        resp = await async_comms.rfq_batches.accept(
            "batch-1",
            accepted_side="yes",
            min_bids=[
                RFQBatchAcceptLimit(rfq_id="rfq-1", bid=Decimal("0.56")),
                RFQBatchAcceptLimit(rfq_id="rfq-2", bid=Decimal("0.44")),
            ],
        )
        assert resp.accepted_side == "yes"

    async def test_best_quotes(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(f"{_BATCH_URL}/batch-1/best_quotes").mock(
            return_value=httpx.Response(200, json={"best_quotes": _MINIMAL_BEST_QUOTES})
        )
        resp = await async_comms.rfq_batches.best_quotes("batch-1")
        assert resp.best_quotes.yes_complete is True

    async def test_list_quotes(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(f"{_BATCH_URL}/batch-1/quotes").mock(
            return_value=httpx.Response(200, json={"batch_quotes": [_MINIMAL_BATCH_QUOTE]})
        )
        resp = await async_comms.rfq_batches.quotes.list("batch-1")
        assert resp.batch_quotes[0].id == "bq-1"

    async def test_create_quote(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(f"{_BATCH_URL}/batch-1/quotes").mock(
            return_value=httpx.Response(201, json={"id": "bq-9"})
        )
        resp = await async_comms.rfq_batches.quotes.create(
            "batch-1",
            quotes=[
                RFQBatchQuoteEntry(
                    rfq_id="rfq-1", yes_bid=Decimal("0.5"), no_bid=Decimal("0.5")
                ),
                RFQBatchQuoteEntry(
                    rfq_id="rfq-2", yes_bid=Decimal("0.5"), no_bid=Decimal("0.5")
                ),
            ],
            rest_remainder=False,
        )
        assert resp.id == "bq-9"
        assert route.called

    async def test_delete_quote(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.delete(f"{_BATCH_URL}/batch-1/quotes/bq-1").mock(
            return_value=httpx.Response(204)
        )
        await async_comms.rfq_batches.quotes.delete("batch-1", "bq-1")
        assert route.called

    async def test_confirm_quote(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.put(f"{_BATCH_URL}/batch-1/quotes/bq-1/confirm").mock(
            return_value=httpx.Response(204)
        )
        await async_comms.rfq_batches.quotes.confirm("batch-1", "bq-1")
        assert route.calls[0].request.content == b"{}"

    async def test_list_500(
        self,
        async_comms: AsyncCommunicationsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(_BATCH_URL).mock(
            return_value=httpx.Response(500, json={"message": "boom"})
        )
        with pytest.raises(KalshiServerError):
            await async_comms.rfq_batches.list()


class TestRFQBatchesAuthGuard:
    def test_list_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.rfq_batches.list()

    def test_list_all_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_comms.rfq_batches.list_all())

    def test_get_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.rfq_batches.get("batch-1")

    def test_create_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.rfq_batches.create(children=_CHILDREN)

    def test_delete_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.rfq_batches.delete("batch-1")

    def test_accept_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.rfq_batches.accept(
                "batch-1",
                accepted_side="yes",
                min_bids=[
                    RFQBatchAcceptLimit(rfq_id="rfq-1", bid=Decimal("0.5")),
                    RFQBatchAcceptLimit(rfq_id="rfq-2", bid=Decimal("0.5")),
                ],
            )

    def test_best_quotes_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.rfq_batches.best_quotes("batch-1")

    def test_list_quotes_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.rfq_batches.quotes.list("batch-1")

    def test_create_quote_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.rfq_batches.quotes.create(
                "batch-1",
                quotes=[
                    RFQBatchQuoteEntry(
                        rfq_id="rfq-1", yes_bid=Decimal("0.5"), no_bid=Decimal("0.5")
                    ),
                    RFQBatchQuoteEntry(
                        rfq_id="rfq-2", yes_bid=Decimal("0.5"), no_bid=Decimal("0.5")
                    ),
                ],
                rest_remainder=True,
            )

    def test_delete_quote_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.rfq_batches.quotes.delete("batch-1", "bq-1")

    def test_confirm_quote_requires_auth(self, unauth_comms: CommunicationsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_comms.rfq_batches.quotes.confirm("batch-1", "bq-1")
