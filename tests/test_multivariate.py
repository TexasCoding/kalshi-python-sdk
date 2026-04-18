"""Tests for kalshi.resources.multivariate — Multivariate collections resource."""

from __future__ import annotations

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import AuthRequiredError
from kalshi.models.multivariate import (
    TickerPair,
)
from kalshi.resources.multivariate import (
    AsyncMultivariateCollectionsResource,
    MultivariateCollectionsResource,
)

BASE = "https://test.kalshi.com/trade-api/v2"

COLLECTION_PAYLOAD = {
    "collection_ticker": "MVC-1",
    "series_ticker": "SER-1",
    "title": "Test",
    "description": "",
    "open_date": "2026-01-01T00:00:00Z",
    "close_date": "2026-12-31T00:00:00Z",
    "associated_events": [],
    "is_ordered": False,
    "size_min": 2,
    "size_max": 5,
    "functional_description": "",
}


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(base_url=BASE, timeout=5.0, max_retries=0)


@pytest.fixture
def mv(test_auth: KalshiAuth, config: KalshiConfig) -> MultivariateCollectionsResource:
    return MultivariateCollectionsResource(SyncTransport(test_auth, config))


@pytest.fixture
def unauth_mv(config: KalshiConfig) -> MultivariateCollectionsResource:
    return MultivariateCollectionsResource(SyncTransport(None, config))


class TestMultivariateList:
    @respx.mock
    def test_list_returns_page(self, mv: MultivariateCollectionsResource) -> None:
        respx.get(f"{BASE}/multivariate_event_collections").mock(
            return_value=httpx.Response(200, json={
                "multivariate_contracts": [COLLECTION_PAYLOAD],
                "cursor": "next-page",
            })
        )
        page = mv.list()
        assert len(page.items) == 1
        assert page.cursor == "next-page"
        assert page.items[0].collection_ticker == "MVC-1"

    @respx.mock
    def test_list_with_filters(self, mv: MultivariateCollectionsResource) -> None:
        route = respx.get(f"{BASE}/multivariate_event_collections").mock(
            return_value=httpx.Response(200, json={"multivariate_contracts": [], "cursor": ""})
        )
        mv.list(status="open", series_ticker="SER-1", limit=50)
        params = dict(route.calls[0].request.url.params)
        assert params["status"] == "open"
        assert params["series_ticker"] == "SER-1"
        assert params["limit"] == "50"

    @respx.mock
    def test_list_all_auto_paginates(self, mv: MultivariateCollectionsResource) -> None:
        respx.get(f"{BASE}/multivariate_event_collections").mock(
            side_effect=[
                httpx.Response(200, json={
                    "multivariate_contracts": [COLLECTION_PAYLOAD],
                    "cursor": "page2",
                }),
                httpx.Response(200, json={
                    "multivariate_contracts": [
                        {**COLLECTION_PAYLOAD, "collection_ticker": "MVC-2"},
                    ],
                    "cursor": "",
                }),
            ]
        )
        items = list(mv.list_all())
        assert len(items) == 2
        assert items[0].collection_ticker == "MVC-1"
        assert items[1].collection_ticker == "MVC-2"


class TestMultivariateGet:
    @respx.mock
    def test_get_by_ticker(self, mv: MultivariateCollectionsResource) -> None:
        respx.get(f"{BASE}/multivariate_event_collections/MVC-1").mock(
            return_value=httpx.Response(200, json={"multivariate_contract": COLLECTION_PAYLOAD})
        )
        c = mv.get("MVC-1")
        assert c.collection_ticker == "MVC-1"


class TestMultivariateCreateMarket:
    @respx.mock
    def test_create_market(self, mv: MultivariateCollectionsResource) -> None:
        route = respx.post(f"{BASE}/multivariate_event_collections/MVC-1").mock(
            return_value=httpx.Response(200, json={
                "event_ticker": "EVT-1",
                "market_ticker": "MKT-1",
            })
        )
        pairs = [TickerPair(market_ticker="M-A", event_ticker="E-A", side="yes")]
        result = mv.create_market("MVC-1", selected_markets=pairs)
        assert result.market_ticker == "MKT-1"
        assert route.called

    def test_create_market_auth_guard(self, unauth_mv: MultivariateCollectionsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_mv.create_market("MVC-1", selected_markets=[])


class TestMultivariateLookupTickers:
    @respx.mock
    def test_lookup_tickers(self, mv: MultivariateCollectionsResource) -> None:
        respx.put(f"{BASE}/multivariate_event_collections/MVC-1/lookup").mock(
            return_value=httpx.Response(200, json={
                "event_ticker": "EVT-1",
                "market_ticker": "MKT-1",
            })
        )
        pairs = [TickerPair(market_ticker="M-A", event_ticker="E-A", side="yes")]
        result = mv.lookup_tickers("MVC-1", selected_markets=pairs)
        assert result.event_ticker == "EVT-1"

    def test_lookup_tickers_auth_guard(self, unauth_mv: MultivariateCollectionsResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_mv.lookup_tickers("MVC-1", selected_markets=[])


class TestMultivariateLookupHistory:
    @respx.mock
    def test_lookup_history(self, mv: MultivariateCollectionsResource) -> None:
        respx.get(f"{BASE}/multivariate_event_collections/MVC-1/lookup").mock(
            return_value=httpx.Response(200, json={
                "lookup_points": [{
                    "event_ticker": "EVT-1",
                    "market_ticker": "MKT-1",
                    "selected_markets": [],
                    "last_queried_ts": "2026-04-16T10:00:00Z",
                }]
            })
        )
        result = mv.lookup_history("MVC-1", lookback_seconds=60)
        assert len(result) == 1
        assert result[0].event_ticker == "EVT-1"


class TestAsyncMultivariateCollectionsResource:
    @pytest.fixture
    def async_mv(
        self, test_auth: KalshiAuth, config: KalshiConfig,
    ) -> AsyncMultivariateCollectionsResource:
        return AsyncMultivariateCollectionsResource(
            AsyncTransport(test_auth, config),
        )

    @pytest.fixture
    def unauth_async_mv(self, config: KalshiConfig) -> AsyncMultivariateCollectionsResource:
        return AsyncMultivariateCollectionsResource(AsyncTransport(None, config))

    @respx.mock
    @pytest.mark.asyncio
    async def test_list(self, async_mv: AsyncMultivariateCollectionsResource) -> None:
        respx.get(f"{BASE}/multivariate_event_collections").mock(
            return_value=httpx.Response(200, json={
                "multivariate_contracts": [COLLECTION_PAYLOAD], "cursor": "",
            })
        )
        page = await async_mv.list()
        assert len(page.items) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_get(self, async_mv: AsyncMultivariateCollectionsResource) -> None:
        respx.get(f"{BASE}/multivariate_event_collections/MVC-1").mock(
            return_value=httpx.Response(200, json={"multivariate_contract": COLLECTION_PAYLOAD})
        )
        c = await async_mv.get("MVC-1")
        assert c.collection_ticker == "MVC-1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_market(self, async_mv: AsyncMultivariateCollectionsResource) -> None:
        respx.post(f"{BASE}/multivariate_event_collections/MVC-1").mock(
            return_value=httpx.Response(200, json={"event_ticker": "E", "market_ticker": "M"})
        )
        result = await async_mv.create_market("MVC-1", selected_markets=[])
        assert result.market_ticker == "M"

    @pytest.mark.asyncio
    async def test_create_market_auth_guard(
        self, unauth_async_mv: AsyncMultivariateCollectionsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_mv.create_market("MVC-1", selected_markets=[])

    @respx.mock
    @pytest.mark.asyncio
    async def test_lookup_tickers(self, async_mv: AsyncMultivariateCollectionsResource) -> None:
        respx.put(f"{BASE}/multivariate_event_collections/MVC-1/lookup").mock(
            return_value=httpx.Response(200, json={"event_ticker": "E", "market_ticker": "M"})
        )
        result = await async_mv.lookup_tickers("MVC-1", selected_markets=[])
        assert result.event_ticker == "E"

    @pytest.mark.asyncio
    async def test_lookup_tickers_auth_guard(
        self, unauth_async_mv: AsyncMultivariateCollectionsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_mv.lookup_tickers("MVC-1", selected_markets=[])

    @respx.mock
    @pytest.mark.asyncio
    async def test_lookup_history(self, async_mv: AsyncMultivariateCollectionsResource) -> None:
        respx.get(f"{BASE}/multivariate_event_collections/MVC-1/lookup").mock(
            return_value=httpx.Response(200, json={"lookup_points": []})
        )
        result = await async_mv.lookup_history("MVC-1", lookback_seconds=300)
        assert result == []


class TestCreateMarketWireShape:
    """v0.8.0: create_market() builds CreateMarketInMultivariateEventCollectionRequest
    internally and serializes via model_dump."""

    @respx.mock
    def test_selected_markets_in_body(
        self, mv: MultivariateCollectionsResource
    ) -> None:
        import json

        route = respx.post(f"{BASE}/multivariate_event_collections/MVC-1").mock(
            return_value=httpx.Response(200, json={"event_ticker": "E", "market_ticker": "M"})
        )
        pairs = [TickerPair(market_ticker="M-A", event_ticker="E-A", side="yes")]
        mv.create_market("MVC-1", selected_markets=pairs)

        body = json.loads(route.calls[0].request.content)
        assert "selected_markets" in body
        assert len(body["selected_markets"]) == 1
        item = body["selected_markets"][0]
        assert item["market_ticker"] == "M-A"
        assert item["event_ticker"] == "E-A"
        assert item["side"] == "yes"

    @respx.mock
    def test_with_market_payload_included_when_true(
        self, mv: MultivariateCollectionsResource
    ) -> None:
        import json

        route = respx.post(f"{BASE}/multivariate_event_collections/MVC-1").mock(
            return_value=httpx.Response(200, json={"event_ticker": "E", "market_ticker": "M"})
        )
        mv.create_market("MVC-1", selected_markets=[], with_market_payload=True)

        body = json.loads(route.calls[0].request.content)
        assert body["with_market_payload"] is True

    @respx.mock
    def test_with_market_payload_absent_when_not_passed(
        self, mv: MultivariateCollectionsResource
    ) -> None:
        import json

        route = respx.post(f"{BASE}/multivariate_event_collections/MVC-1").mock(
            return_value=httpx.Response(200, json={"event_ticker": "E", "market_ticker": "M"})
        )
        mv.create_market("MVC-1", selected_markets=[])

        body = json.loads(route.calls[0].request.content)
        assert "with_market_payload" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_selected_markets_in_body(
        self,
        test_auth: KalshiAuth,
        config: KalshiConfig,
    ) -> None:
        import json

        from kalshi._base_client import AsyncTransport

        async_mv = AsyncMultivariateCollectionsResource(AsyncTransport(test_auth, config))
        route = respx.post(f"{BASE}/multivariate_event_collections/MVC-1").mock(
            return_value=httpx.Response(200, json={"event_ticker": "E", "market_ticker": "M"})
        )
        pairs = [TickerPair(market_ticker="M-A", event_ticker="E-A", side="yes")]
        await async_mv.create_market("MVC-1", selected_markets=pairs)

        body = json.loads(route.calls[0].request.content)
        assert "selected_markets" in body
        assert body["selected_markets"][0]["market_ticker"] == "M-A"
        assert "with_market_payload" not in body


class TestLookupTickersWireShape:
    """v0.8.0: lookup_tickers() builds LookupTickersForMarketInMultivariateEventCollectionRequest
    internally and serializes via model_dump."""

    @respx.mock
    def test_only_selected_markets_in_body(
        self, mv: MultivariateCollectionsResource
    ) -> None:
        import json

        route = respx.put(f"{BASE}/multivariate_event_collections/MVC-1/lookup").mock(
            return_value=httpx.Response(200, json={"event_ticker": "E", "market_ticker": "M"})
        )
        pairs = [TickerPair(market_ticker="M-A", event_ticker="E-A", side="yes")]
        mv.lookup_tickers("MVC-1", selected_markets=pairs)

        body = json.loads(route.calls[0].request.content)
        assert set(body.keys()) == {"selected_markets"}
        assert len(body["selected_markets"]) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_only_selected_markets_in_body(
        self,
        test_auth: KalshiAuth,
        config: KalshiConfig,
    ) -> None:
        import json

        from kalshi._base_client import AsyncTransport

        async_mv = AsyncMultivariateCollectionsResource(AsyncTransport(test_auth, config))
        route = respx.put(f"{BASE}/multivariate_event_collections/MVC-1/lookup").mock(
            return_value=httpx.Response(200, json={"event_ticker": "E", "market_ticker": "M"})
        )
        pairs = [TickerPair(market_ticker="M-A", event_ticker="E-A", side="yes")]
        await async_mv.lookup_tickers("MVC-1", selected_markets=pairs)

        body = json.loads(route.calls[0].request.content)
        assert set(body.keys()) == {"selected_markets"}
        assert len(body["selected_markets"]) == 1
