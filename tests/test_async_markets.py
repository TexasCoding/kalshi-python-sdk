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
            "https://test.kalshi.com/trade-api/v2/markets"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "markets": [
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
            "https://test.kalshi.com/trade-api/v2/markets"
        ).mock(
            return_value=httpx.Response(
                200, json={"markets": [], "cursor": None}
            )
        )
        await markets.list(status="open")
        assert route.calls[0].request.url.params["status"] == "open"

    @pytest.mark.asyncio
    async def test_market_type_kwarg_removed(
        self, markets: AsyncMarketsResource
    ) -> None:
        """Regression: v0.7.0 dropped phantom market_type kwarg (not in spec)."""
        with pytest.raises(TypeError, match="market_type"):
            await markets.list(market_type="binary")  # type: ignore[call-arg]

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_with_all_new_filters(
        self, markets: AsyncMarketsResource
    ) -> None:
        """v0.7.0 ADDs: tickers, mve_filter, 7 *_ts filters."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": None})
        )
        await markets.list(
            status="open",
            series_ticker="SER-X",
            event_ticker="EVT-Y",
            tickers=["MKT-A", "MKT-B"],
            mve_filter="some_filter",
            min_created_ts=1000,
            max_created_ts=2000,
            min_updated_ts=1500,
            min_close_ts=3000,
            max_close_ts=4000,
            min_settled_ts=5000,
            max_settled_ts=6000,
            limit=50,
            cursor="abc",
        )
        params = dict(route.calls[0].request.url.params)
        assert params["status"] == "open"
        assert params["series_ticker"] == "SER-X"
        assert params["event_ticker"] == "EVT-Y"
        assert params["tickers"] == "MKT-A,MKT-B"
        assert params["mve_filter"] == "some_filter"
        assert params["min_created_ts"] == "1000"
        assert params["max_created_ts"] == "2000"
        assert params["min_updated_ts"] == "1500"
        assert params["min_close_ts"] == "3000"
        assert params["max_close_ts"] == "4000"
        assert params["min_settled_ts"] == "5000"
        assert params["max_settled_ts"] == "6000"
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"

    @respx.mock
    @pytest.mark.asyncio
    async def test_tickers_serialized_as_comma_join_list(
        self, markets: AsyncMarketsResource
    ) -> None:
        """Spec says tickers is type:string (comma-separated), NOT explode:true."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        await markets.list(tickers=["A", "B", "C"])
        url = str(route.calls[0].request.url)
        assert "tickers=A%2CB%2CC" in url or "tickers=A,B,C" in url
        assert url.count("tickers=") == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_tickers_serialized_as_comma_join_string(
        self, markets: AsyncMarketsResource
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        await markets.list(tickers="A,B,C")
        params = dict(route.calls[0].request.url.params)
        assert params["tickers"] == "A,B,C"

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_result(
        self, markets: AsyncMarketsResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/markets"
        ).mock(
            return_value=httpx.Response(
                200, json={"markets": []}
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
            "https://test.kalshi.com/trade-api/v2/markets"
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "markets": [
                            {"ticker": "A"},
                            {"ticker": "B"},
                        ],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "markets": [{"ticker": "C"}],
                        "cursor": None,
                    },
                ),
            ]
        )
        tickers = [m.ticker async for m in markets.list_all()]
        assert tickers == ["A", "B", "C"]
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_all_with_all_new_filters(
        self, markets: AsyncMarketsResource
    ) -> None:
        """v0.7.0 ADDs on list_all match list (no cursor)."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": [{"ticker": "A"}], "cursor": ""})
        )
        _ = [m async for m in markets.list_all(
            status="open",
            tickers=["MKT-A", "MKT-B"],
            mve_filter="some_filter",
            min_created_ts=1000,
            max_close_ts=4000,
            limit=50,
        )]
        params = dict(route.calls[0].request.url.params)
        assert params["status"] == "open"
        assert params["tickers"] == "MKT-A,MKT-B"
        assert params["mve_filter"] == "some_filter"
        assert params["min_created_ts"] == "1000"
        assert params["max_close_ts"] == "4000"
        assert params["limit"] == "50"


class TestAsyncMarketsGet:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_market(
        self, markets: AsyncMarketsResource
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/TEST-MKT"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "market": {
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
            "https://test.kalshi.com/trade-api/v2/markets/FAKE"
        ).mock(
            return_value=httpx.Response(
                404, json={"message": "market not found"}
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

    @respx.mock
    @pytest.mark.asyncio
    async def test_orderbook_with_depth(
        self, markets: AsyncMarketsResource
    ) -> None:
        """v0.7.0 ADD: depth kwarg reaches the wire."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/TEST-MKT/orderbook"
        ).mock(
            return_value=httpx.Response(
                200, json={"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}
            )
        )
        await markets.orderbook("TEST-MKT", depth=10)
        assert route.calls[0].request.url.params["depth"] == "10"


class TestAsyncMarketsCandlesticks:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_nested_candlesticks(
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
                            "end_period_ts": 1700000000,
                            "yes_bid": {
                                "open_dollars": "0.4000",
                                "high_dollars": "0.5000",
                                "low_dollars": "0.3500",
                                "close_dollars": "0.4500",
                            },
                            "yes_ask": {
                                "open_dollars": "0.5500",
                                "high_dollars": "0.6000",
                                "low_dollars": "0.5000",
                                "close_dollars": "0.5500",
                            },
                            "price": {
                                "open_dollars": "0.5000",
                                "high_dollars": "0.5500",
                                "low_dollars": "0.4500",
                                "close_dollars": "0.5000",
                            },
                            "volume_fp": "1234.50",
                            "open_interest_fp": "5000.00",
                        }
                    ]
                },
            )
        )
        candles = await markets.candlesticks(
            "SER", "MKT", start_ts=1700000000, end_ts=1700100000, period_interval=60
        )
        assert len(candles) == 1
        c = candles[0]
        assert c.end_period_ts == 1700000000
        assert c.yes_bid is not None
        assert c.yes_bid.open == Decimal("0.4000")
        assert c.price is not None
        assert c.price.close == Decimal("0.5000")
        assert c.volume == Decimal("1234.50")
        assert c.open_interest == Decimal("5000.00")

    @respx.mock
    @pytest.mark.asyncio
    async def test_candlesticks_with_include_latest_before_start_true(
        self, markets: AsyncMarketsResource
    ) -> None:
        """v0.7.0 ADD: include_latest_before_start=True sends 'true' on wire."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/series/SER/markets/MKT/candlesticks"
        ).mock(return_value=httpx.Response(200, json={"candlesticks": []}))
        await markets.candlesticks(
            "SER",
            "MKT",
            start_ts=1700000000,
            end_ts=1700100000,
            period_interval=60,
            include_latest_before_start=True,
        )
        assert route.calls[0].request.url.params["include_latest_before_start"] == "true"

    @respx.mock
    @pytest.mark.asyncio
    async def test_candlesticks_omits_include_latest_when_false(
        self, markets: AsyncMarketsResource
    ) -> None:
        """Bool 'true or omit' rule: False/None drop the param."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/series/SER/markets/MKT/candlesticks"
        ).mock(return_value=httpx.Response(200, json={"candlesticks": []}))
        await markets.candlesticks(
            "SER",
            "MKT",
            start_ts=1700000000,
            end_ts=1700100000,
            period_interval=60,
            include_latest_before_start=False,
        )
        assert "include_latest_before_start" not in dict(
            route.calls[0].request.url.params
        )
