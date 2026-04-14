"""Tests for kalshi.resources.markets — Markets resource."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiNotFoundError
from kalshi.resources.markets import MarketsResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def markets(test_auth: KalshiAuth, config: KalshiConfig) -> MarketsResource:
    return MarketsResource(SyncTransport(test_auth, config))


class TestMarketsList:
    @respx.mock
    def test_returns_page_of_markets(self, markets: MarketsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "markets": [
                        {"ticker": "MKT-A", "title": "Market A", "yes_bid_dollars": "0.4500"},
                        {"ticker": "MKT-B", "title": "Market B", "yes_bid_dollars": "0.6000"},
                    ],
                    "cursor": "page2",
                },
            )
        )
        page = markets.list()
        assert len(page) == 2
        assert page.items[0].ticker == "MKT-A"
        assert page.items[0].yes_bid == Decimal("0.4500")
        assert page.has_next is True
        assert page.cursor == "page2"

    @respx.mock
    def test_with_status_filter(self, markets: MarketsResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": None})
        )
        markets.list(status="open")
        assert route.calls[0].request.url.params["status"] == "open"

    @respx.mock
    def test_with_market_type_filter(self, markets: MarketsResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": None})
        )
        markets.list(market_type="binary")
        assert route.calls[0].request.url.params["market_type"] == "binary"

    @respx.mock
    def test_empty_result(self, markets: MarketsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        page = markets.list()
        assert len(page) == 0
        assert page.has_next is False


class TestMarketsListAll:
    @respx.mock
    def test_auto_paginates(self, markets: MarketsResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "markets": [{"ticker": "A"}, {"ticker": "B"}],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={"markets": [{"ticker": "C"}], "cursor": None},
                ),
            ]
        )
        tickers = [m.ticker for m in markets.list_all()]
        assert tickers == ["A", "B", "C"]
        assert route.call_count == 2


class TestMarketsGet:
    @respx.mock
    def test_returns_market(self, markets: MarketsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/markets/TEST-MKT").mock(
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
        market = markets.get("TEST-MKT")
        assert market.ticker == "TEST-MKT"
        assert market.yes_ask == Decimal("0.7200")

    @respx.mock
    def test_not_found(self, markets: MarketsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/markets/FAKE").mock(
            return_value=httpx.Response(404, json={"message": "market not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            markets.get("FAKE")


class TestMarketsOrderbook:
    @respx.mock
    def test_returns_orderbook(self, markets: MarketsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/markets/TEST-MKT/orderbook").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orderbook_fp": {
                        "yes_dollars": [["0.4500", "100.00"], ["0.5000", "50.00"]],
                        "no_dollars": [["0.5500", "75.00"]],
                    }
                },
            )
        )
        ob = markets.orderbook("TEST-MKT")
        assert ob.ticker == "TEST-MKT"
        assert len(ob.yes) == 2
        assert ob.yes[0].price == Decimal("0.4500")
        assert ob.yes[0].quantity == Decimal("100.00")
        assert len(ob.no) == 1


class TestMarketsCandlesticks:
    @respx.mock
    def test_returns_nested_candlesticks(self, markets: MarketsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/series/SER/markets/MKT/candlesticks"
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
        candles = markets.candlesticks(
            "SER", "MKT", start_ts=1700000000, end_ts=1700100000, period_interval=60
        )
        assert len(candles) == 1
        c = candles[0]
        assert c.end_period_ts == 1700000000
        assert c.yes_bid is not None
        assert c.yes_bid.open == Decimal("0.4000")
        assert c.yes_bid.close == Decimal("0.4500")
        assert c.yes_ask is not None
        assert c.yes_ask.high == Decimal("0.6000")
        assert c.price is not None
        assert c.price.open == Decimal("0.5000")
        assert c.volume == Decimal("1234.50")
        assert c.open_interest == Decimal("5000.00")

    @respx.mock
    def test_empty_candlesticks(self, markets: MarketsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/series/SER/markets/MKT/candlesticks"
        ).mock(
            return_value=httpx.Response(200, json={"candlesticks": []})
        )
        candles = markets.candlesticks(
            "SER", "MKT", start_ts=1700000000, end_ts=1700100000, period_interval=60
        )
        assert candles == []


class TestMarketModel:
    def test_new_fields_from_api(self) -> None:
        """Market model accepts new v0.2 fields from the /markets endpoint."""
        market = Market.model_validate({
            "ticker": "TEST",
            "market_type": "binary",
            "yes_sub_title": "Yes",
            "no_sub_title": "No",
            "volume_fp": "1234.50",
            "volume_24h_fp": "500.00",
            "open_interest_fp": "10000.00",
            "yes_bid_size_fp": "200.00",
            "yes_ask_size_fp": "300.00",
            "settlement_value_dollars": "1.0000",
            "fractional_trading_enabled": True,
            "settlement_timer_seconds": 3600,
        })
        assert market.market_type == "binary"
        assert market.yes_sub_title == "Yes"
        assert market.volume == Decimal("1234.50")
        assert market.volume_24h == Decimal("500.00")
        assert market.open_interest == Decimal("10000.00")
        assert market.yes_bid_size == Decimal("200.00")
        assert market.settlement_value == Decimal("1.0000")
        assert market.fractional_trading_enabled is True
        assert market.settlement_timer_seconds == 3600

    def test_backward_compat_short_names(self) -> None:
        """Market model still accepts short names for price fields."""
        market = Market.model_validate({
            "ticker": "TEST",
            "yes_bid": "0.45",
            "volume": "100",
        })
        assert market.yes_bid == Decimal("0.45")
        assert market.volume == Decimal("100")


# Import here to avoid circular issues at module level
from kalshi.models.markets import Market  # noqa: E402
