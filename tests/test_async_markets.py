"""Tests for async markets resource — mirrors test_markets.py."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiNotFoundError
from kalshi.resources.markets import AsyncMarketsResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def markets(
    test_auth: KalshiAuth, config: KalshiConfig
) -> AsyncMarketsResource:
    return AsyncMarketsResource(AsyncTransport(test_auth, config))


class TestAsyncMarketsList:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page_of_markets(
        self, markets: AsyncMarketsResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/events"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "ticker": "MKT-A",
                            "title": "Market A",
                            "yes_bid_dollars": "0.4500",
                        },
                        {
                            "ticker": "MKT-B",
                            "title": "Market B",
                            "yes_bid_dollars": "0.6000",
                        },
                    ],
                    "cursor": "page2",
                },
            )
        )
        page = await markets.list()
        assert len(page) == 2
        assert page.items[0].ticker == "MKT-A"
        assert page.items[0].yes_bid == Decimal("0.4500")
        assert page.has_next is True
        assert page.cursor == "page2"

    @respx.mock
    @pytest.mark.asyncio
    async def test_with_status_filter(
        self, markets: AsyncMarketsResource
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/events"
        ).mock(
            return_value=httpx.Response(
                200, json={"events": [], "cursor": None}
            )
        )
        await markets.list(status="open")
        assert route.calls[0].request.url.params["status"] == "open"

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_result(
        self, markets: AsyncMarketsResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/events"
        ).mock(
            return_value=httpx.Response(
                200, json={"events": []}
            )
        )
        page = await markets.list()
        assert len(page) == 0
        assert page.has_next is False


class TestAsyncMarketsListAll:
    @respx.mock
    @pytest.mark.asyncio
    async def test_auto_paginates(
        self, markets: AsyncMarketsResource
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/events"
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "events": [
                            {"ticker": "A"},
                            {"ticker": "B"},
                        ],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "events": [{"ticker": "C"}],
                        "cursor": None,
                    },
                ),
            ]
        )
        tickers = [m.ticker async for m in markets.list_all()]
        assert tickers == ["A", "B", "C"]
        assert route.call_count == 2


class TestAsyncMarketsGet:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_market(
        self, markets: AsyncMarketsResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/events/TEST-MKT"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "event": {
                        "ticker": "TEST-MKT",
                        "title": "Test Market",
                        "yes_ask_dollars": "0.7200",
                    }
                },
            )
        )
        market = await markets.get("TEST-MKT")
        assert market.ticker == "TEST-MKT"
        assert market.yes_ask == Decimal("0.7200")

    @respx.mock
    @pytest.mark.asyncio
    async def test_not_found(
        self, markets: AsyncMarketsResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/events/FAKE"
        ).mock(
            return_value=httpx.Response(
                404, json={"message": "event not found"}
            )
        )
        with pytest.raises(KalshiNotFoundError):
            await markets.get("FAKE")


class TestAsyncMarketsOrderbook:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_orderbook(
        self, markets: AsyncMarketsResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/TEST-MKT/orderbook"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "orderbook_fp": {
                        "yes_dollars": [
                            ["0.4500", "100.00"],
                            ["0.5000", "50.00"],
                        ],
                        "no_dollars": [["0.5500", "75.00"]],
                    }
                },
            )
        )
        ob = await markets.orderbook("TEST-MKT")
        assert ob.ticker == "TEST-MKT"
        assert len(ob.yes) == 2
        assert ob.yes[0].price == Decimal("0.4500")
        assert ob.yes[0].quantity == Decimal("100.00")
        assert len(ob.no) == 1


class TestAsyncMarketsCandlesticks:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_candlesticks(
        self, markets: AsyncMarketsResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2"
            "/series/SER/markets/MKT/candlesticks"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "candlesticks": [
                        {
                            "ticker": "MKT",
                            "open_dollars": "0.5000",
                            "close_dollars": "0.5500",
                            "volume": 100,
                        }
                    ]
                },
            )
        )
        candles = await markets.candlesticks("SER", "MKT")
        assert len(candles) == 1
        assert candles[0].open == Decimal("0.5000")
        assert candles[0].volume == 100
