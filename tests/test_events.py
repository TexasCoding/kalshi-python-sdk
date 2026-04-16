"""Tests for kalshi.resources.events — Events resource."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiNotFoundError
from kalshi.resources.events import AsyncEventsResource, EventsResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def events(test_auth: KalshiAuth, config: KalshiConfig) -> EventsResource:
    return EventsResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_events(
    test_auth: KalshiAuth, config: KalshiConfig
) -> AsyncEventsResource:
    return AsyncEventsResource(AsyncTransport(test_auth, config))


# ── Sync tests ──────────────────────────────────────────────


class TestEventsList:
    @respx.mock
    def test_returns_page_of_events(self, events: EventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events").mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "event_ticker": "EVT-A",
                            "title": "Event A",
                            "series_ticker": "SER-1",
                            "mutually_exclusive": True,
                        },
                        {
                            "event_ticker": "EVT-B",
                            "title": "Event B",
                            "series_ticker": "SER-2",
                        },
                    ],
                    "cursor": "page2",
                },
            )
        )
        page = events.list()
        assert len(page) == 2
        assert page.items[0].event_ticker == "EVT-A"
        assert page.items[0].mutually_exclusive is True
        assert page.has_next is True

    @respx.mock
    def test_with_filters(self, events: EventsResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/events").mock(
            return_value=httpx.Response(200, json={"events": [], "cursor": ""})
        )
        events.list(status="open", series_ticker="SER-1")
        assert route.calls[0].request.url.params["status"] == "open"
        assert route.calls[0].request.url.params["series_ticker"] == "SER-1"

    @respx.mock
    def test_empty_events(self, events: EventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events").mock(
            return_value=httpx.Response(200, json={"events": []})
        )
        page = events.list()
        assert len(page) == 0
        assert page.has_next is False


class TestEventsListAll:
    @respx.mock
    def test_auto_paginates(self, events: EventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "events": [{"event_ticker": "A"}, {"event_ticker": "B"}],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={"events": [{"event_ticker": "C"}], "cursor": ""},
                ),
            ]
        )
        tickers = [e.event_ticker for e in events.list_all()]
        assert tickers == ["A", "B", "C"]


class TestEventsGet:
    @respx.mock
    def test_returns_event(self, events: EventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/EVT-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "event": {
                        "event_ticker": "EVT-1",
                        "title": "Test Event",
                        "series_ticker": "SER-1",
                        "mutually_exclusive": False,
                    },
                    "markets": [],
                },
            )
        )
        event = events.get("EVT-1")
        assert event.event_ticker == "EVT-1"
        assert event.title == "Test Event"
        assert event.mutually_exclusive is False

    @respx.mock
    def test_with_nested_markets(self, events: EventsResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/events/EVT-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "event": {
                        "event_ticker": "EVT-1",
                        "title": "Test Event",
                        "markets": [
                            {"ticker": "MKT-1", "yes_bid_dollars": "0.45"},
                            {"ticker": "MKT-2", "yes_bid_dollars": "0.55"},
                        ],
                    },
                    "markets": [],
                },
            )
        )
        event = events.get("EVT-1", with_nested_markets=True)
        assert route.calls[0].request.url.params["with_nested_markets"] == "true"
        assert event.markets is not None
        assert len(event.markets) == 2
        assert event.markets[0].ticker == "MKT-1"
        assert event.markets[0].yes_bid == Decimal("0.45")

    @respx.mock
    def test_not_found(self, events: EventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/FAKE").mock(
            return_value=httpx.Response(404, json={"message": "event not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            events.get("FAKE")


class TestEventsMetadata:
    @respx.mock
    def test_returns_metadata(self, events: EventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/EVT-1/metadata").mock(
            return_value=httpx.Response(
                200,
                json={
                    "image_url": "https://example.com/event.png",
                    "featured_image_url": "https://example.com/featured.png",
                    "market_details": [
                        {
                            "market_ticker": "MKT-1",
                            "image_url": "https://example.com/mkt.png",
                            "color_code": "#FF0000",
                        }
                    ],
                    "settlement_sources": [
                        {"url": "https://example.com/source", "name": "Source 1"}
                    ],
                },
            )
        )
        meta = events.metadata("EVT-1")
        assert meta.image_url == "https://example.com/event.png"
        assert meta.market_details is not None
        assert len(meta.market_details) == 1
        assert meta.market_details[0].market_ticker == "MKT-1"
        assert meta.settlement_sources is not None
        assert meta.settlement_sources[0].name == "Source 1"

    @respx.mock
    def test_not_found(self, events: EventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/FAKE/metadata").mock(
            return_value=httpx.Response(404, json={"message": "not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            events.metadata("FAKE")


class TestEventsListMultivariate:
    @respx.mock
    def test_list_multivariate(self, events: EventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/multivariate").mock(
            return_value=httpx.Response(200, json={
                "events": [{"event_ticker": "MVE-1", "series_ticker": "SER-1"}],
                "cursor": "next",
            })
        )
        page = events.list_multivariate()
        assert len(page.items) == 1
        assert page.items[0].event_ticker == "MVE-1"
        assert page.cursor == "next"

    @respx.mock
    def test_list_multivariate_filters(self, events: EventsResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/events/multivariate").mock(
            return_value=httpx.Response(200, json={"events": [], "cursor": ""})
        )
        events.list_multivariate(
            collection_ticker="MVC-1",
            with_nested_markets=True,
            limit=50,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["collection_ticker"] == "MVC-1"
        assert params["with_nested_markets"] == "true"
        assert params["limit"] == "50"

    @respx.mock
    def test_list_all_multivariate(self, events: EventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/multivariate").mock(
            side_effect=[
                httpx.Response(200, json={
                    "events": [{"event_ticker": "MVE-1"}],
                    "cursor": "page2",
                }),
                httpx.Response(200, json={
                    "events": [{"event_ticker": "MVE-2"}],
                    "cursor": "",
                }),
            ]
        )
        items = list(events.list_all_multivariate())
        assert len(items) == 2


class TestEventsListDriftFix:
    @respx.mock
    def test_list_passes_new_params(self, events: EventsResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/events").mock(
            return_value=httpx.Response(200, json={"events": [], "cursor": ""})
        )
        events.list(with_milestones=True, min_close_ts=1000, min_updated_ts=2000)
        params = dict(route.calls[0].request.url.params)
        assert params["with_milestones"] == "true"
        assert params["min_close_ts"] == "1000"
        assert params["min_updated_ts"] == "2000"


# ── Async tests ─────────────────────────────────────────────


class TestAsyncEventsList:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(self, async_events: AsyncEventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events").mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [{"event_ticker": "EVT-A", "title": "Event A"}],
                    "cursor": "p2",
                },
            )
        )
        page = await async_events.list()
        assert len(page) == 1
        assert page.items[0].event_ticker == "EVT-A"
        assert page.has_next is True


class TestAsyncEventsListAll:
    @respx.mock
    @pytest.mark.asyncio
    async def test_auto_paginates(self, async_events: AsyncEventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "events": [{"event_ticker": "A"}],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={"events": [{"event_ticker": "B"}], "cursor": ""},
                ),
            ]
        )
        tickers = [e.event_ticker async for e in async_events.list_all()]
        assert tickers == ["A", "B"]


class TestAsyncEventsGet:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_event(self, async_events: AsyncEventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/EVT-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "event": {
                        "event_ticker": "EVT-1",
                        "title": "Async Event",
                    },
                    "markets": [],
                },
            )
        )
        event = await async_events.get("EVT-1")
        assert event.event_ticker == "EVT-1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_not_found(self, async_events: AsyncEventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/FAKE").mock(
            return_value=httpx.Response(404, json={"message": "not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            await async_events.get("FAKE")


class TestAsyncEventsMetadata:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_metadata(self, async_events: AsyncEventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/EVT-1/metadata").mock(
            return_value=httpx.Response(
                200,
                json={
                    "image_url": "https://example.com/event.png",
                    "market_details": [],
                    "settlement_sources": [],
                },
            )
        )
        meta = await async_events.metadata("EVT-1")
        assert meta.image_url == "https://example.com/event.png"


class TestAsyncEventsListMultivariate:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_multivariate(self, async_events: AsyncEventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/multivariate").mock(
            return_value=httpx.Response(200, json={
                "events": [{"event_ticker": "MVE-1"}],
                "cursor": "",
            })
        )
        page = await async_events.list_multivariate()
        assert len(page.items) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_all_multivariate(self, async_events: AsyncEventsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/events/multivariate").mock(
            side_effect=[
                httpx.Response(200, json={"events": [{"event_ticker": "A"}], "cursor": "p2"}),
                httpx.Response(200, json={"events": [{"event_ticker": "B"}], "cursor": ""}),
            ]
        )
        tickers = [e.event_ticker async for e in async_events.list_all_multivariate()]
        assert tickers == ["A", "B"]
