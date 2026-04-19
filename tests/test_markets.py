"""Tests for kalshi.resources.markets — Markets resource."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import AuthRequiredError, KalshiError, KalshiNotFoundError
from kalshi.models.historical import Trade
from kalshi.models.markets import MarketCandlesticks, Orderbook
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

    def test_market_type_kwarg_removed(self, markets: MarketsResource) -> None:
        """Regression: v0.7.0 dropped phantom `market_type` kwarg (not in spec).

        Replaced the prior `test_with_market_type_filter` which asserted the
        opposite. Migration: drop the kwarg from caller code.
        """
        with pytest.raises(TypeError, match="market_type"):
            markets.list(market_type="binary")  # type: ignore[call-arg]

    @respx.mock
    def test_list_with_all_new_filters(self, markets: MarketsResource) -> None:
        """v0.7.0 ADDs: tickers, mve_filter, 7 *_ts filters."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": None})
        )
        markets.list(
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
    def test_tickers_serialized_as_comma_join_list(self, markets: MarketsResource) -> None:
        """Spec says tickers is type:string (comma-separated), NOT explode:true.

        Asserts wire is ?tickers=A,B (NOT ?tickers=A&tickers=B). Prevents future
        regression if someone refactors `_join_tickers` to a pass-through.
        """
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        markets.list(tickers=["A", "B", "C"])
        # raw query string should have a single tickers= entry
        url = str(route.calls[0].request.url)
        assert "tickers=A%2CB%2CC" in url or "tickers=A,B,C" in url
        assert url.count("tickers=") == 1

    @respx.mock
    def test_tickers_serialized_as_comma_join_string(self, markets: MarketsResource) -> None:
        """Pre-joined string passes through unchanged."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        markets.list(tickers="A,B,C")
        params = dict(route.calls[0].request.url.params)
        assert params["tickers"] == "A,B,C"

    @respx.mock
    def test_tickers_empty_list_drops_param(self, markets: MarketsResource) -> None:
        """Regression: tickers=[] must drop the param (sending ?tickers= is undefined)."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        markets.list(tickers=[])
        params = dict(route.calls[0].request.url.params)
        assert "tickers" not in params

    @respx.mock
    def test_tickers_empty_string_drops_param(self, markets: MarketsResource) -> None:
        """Regression: tickers='' must drop the param."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        markets.list(tickers="")
        params = dict(route.calls[0].request.url.params)
        assert "tickers" not in params

    @respx.mock
    def test_tickers_tuple_input_joins_correctly(self, markets: MarketsResource) -> None:
        """Tuples (a natural Python sequence type) must be joined the same as lists.

        Regression: pre-fix, isinstance(value, list) check let tuples bypass the
        join, getting passed to httpx as a tuple and serialized explode-style
        (?tickers=A&tickers=B), which is the wrong wire format.
        """
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        markets.list(tickers=("A", "B"))  # type: ignore[arg-type]
        url = str(route.calls[0].request.url)
        assert url.count("tickers=") == 1
        assert "tickers=A%2CB" in url or "tickers=A,B" in url

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

    @respx.mock
    def test_list_all_with_all_new_filters(self, markets: MarketsResource) -> None:
        """v0.7.0 ADDs on list_all match list (no cursor)."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": [{"ticker": "A"}], "cursor": ""})
        )
        list(
            markets.list_all(
                status="open",
                tickers=["MKT-A", "MKT-B"],
                mve_filter="some_filter",
                min_created_ts=1000,
                max_close_ts=4000,
                limit=50,
            )
        )
        params = dict(route.calls[0].request.url.params)
        assert params["status"] == "open"
        assert params["tickers"] == "MKT-A,MKT-B"
        assert params["mve_filter"] == "some_filter"
        assert params["min_created_ts"] == "1000"
        assert params["max_close_ts"] == "4000"
        assert params["limit"] == "50"


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

    @respx.mock
    def test_orderbook_with_depth(self, markets: MarketsResource) -> None:
        """v0.7.0 ADD: depth kwarg reaches the wire."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/TEST-MKT/orderbook"
        ).mock(
            return_value=httpx.Response(
                200, json={"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}
            )
        )
        markets.orderbook("TEST-MKT", depth=10)
        assert route.calls[0].request.url.params["depth"] == "10"


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

    @respx.mock
    def test_candlesticks_with_include_latest_before_start_true(
        self, markets: MarketsResource
    ) -> None:
        """v0.7.0 ADD: include_latest_before_start=True sends 'true' on wire."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/series/SER/markets/MKT/candlesticks"
        ).mock(return_value=httpx.Response(200, json={"candlesticks": []}))
        markets.candlesticks(
            "SER",
            "MKT",
            start_ts=1700000000,
            end_ts=1700100000,
            period_interval=60,
            include_latest_before_start=True,
        )
        assert route.calls[0].request.url.params["include_latest_before_start"] == "true"

    @respx.mock
    def test_candlesticks_sends_explicit_false(
        self, markets: MarketsResource
    ) -> None:
        """Tri-state bool: False must send 'false' (opt-out survives server default flips)."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/series/SER/markets/MKT/candlesticks"
        ).mock(return_value=httpx.Response(200, json={"candlesticks": []}))
        markets.candlesticks(
            "SER",
            "MKT",
            start_ts=1700000000,
            end_ts=1700100000,
            period_interval=60,
            include_latest_before_start=False,
        )
        assert route.calls[0].request.url.params["include_latest_before_start"] == "false"

    @respx.mock
    def test_candlesticks_omits_include_latest_when_none(
        self, markets: MarketsResource
    ) -> None:
        """Tri-state bool: None drops the param entirely."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/series/SER/markets/MKT/candlesticks"
        ).mock(return_value=httpx.Response(200, json={"candlesticks": []}))
        markets.candlesticks(
            "SER",
            "MKT",
            start_ts=1700000000,
            end_ts=1700100000,
            period_interval=60,
        )
        assert "include_latest_before_start" not in dict(
            route.calls[0].request.url.params
        )


class TestMarketsListTrades:
    @respx.mock
    def test_returns_page_of_trades(self, markets: MarketsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/markets/trades").mock(
            return_value=httpx.Response(
                200,
                json={
                    "trades": [
                        {
                            "trade_id": "t-1",
                            "ticker": "MKT-A",
                            "count_fp": "50.00",
                            "yes_price_dollars": "0.4500",
                            "no_price_dollars": "0.5500",
                            "taker_side": "yes",
                            "created_time": "2026-04-18T12:00:00Z",
                        },
                    ],
                    "cursor": "next",
                },
            ),
        )
        page = markets.list_trades(ticker="MKT-A", limit=10)
        assert len(page.items) == 1
        assert isinstance(page.items[0], Trade)
        assert page.items[0].count == Decimal("50.00")
        assert page.items[0].yes_price == Decimal("0.4500")
        assert page.cursor == "next"

    @respx.mock
    def test_list_trades_all_paginates(self, markets: MarketsResource) -> None:
        base_trade = {
            "trade_id": "t-1",
            "ticker": "MKT-A",
            "count_fp": "1.00",
            "yes_price_dollars": "0.50",
            "no_price_dollars": "0.50",
            "taker_side": "yes",
            "created_time": "2026-04-18T12:00:00Z",
        }
        page1 = {"trades": [base_trade], "cursor": "p2"}
        page2 = {
            "trades": [{**base_trade, "trade_id": "t-2"}],
            "cursor": "",
        }
        respx.get("https://test.kalshi.com/trade-api/v2/markets/trades").mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ],
        )
        items = list(markets.list_trades_all(limit=1))
        assert [t.trade_id for t in items] == ["t-1", "t-2"]


class TestMarketsBulkCandlesticks:
    @respx.mock
    def test_returns_per_market_bundles(self, markets: MarketsResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/candlesticks",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "markets": [
                        {
                            "market_ticker": "MKT-A",
                            "candlesticks": [
                                {"end_period_ts": 1, "volume_fp": "0"},
                            ],
                        },
                        {"market_ticker": "MKT-B", "candlesticks": []},
                    ],
                },
            ),
        )
        result = markets.bulk_candlesticks(
            market_tickers=["MKT-A", "MKT-B"],
            start_ts=1700000000,
            end_ts=1700100000,
            period_interval=60,
        )
        assert len(result) == 2
        assert all(isinstance(r, MarketCandlesticks) for r in result)
        assert result[0].market_ticker == "MKT-A"
        # Spec: comma-joined, not exploded.
        q = dict(route.calls[0].request.url.params)
        assert q["market_tickers"] == "MKT-A,MKT-B"

    @respx.mock
    def test_bulk_candlesticks_handles_null_candlesticks(
        self, markets: MarketsResource,
    ) -> None:
        """NullableList[Candlestick]: server-sent ``null`` coerces to ``[]``."""
        respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/candlesticks",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "markets": [
                        {"market_ticker": "MKT-A", "candlesticks": None},
                    ],
                },
            ),
        )
        result = markets.bulk_candlesticks(
            market_tickers=["MKT-A"],
            start_ts=1700000000,
            end_ts=1700100000,
            period_interval=60,
        )
        assert result[0].candlesticks == []

    @respx.mock
    def test_bulk_candlesticks_include_flag(
        self, markets: MarketsResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/candlesticks",
        ).mock(return_value=httpx.Response(200, json={"markets": []}))
        markets.bulk_candlesticks(
            market_tickers="MKT-A",
            start_ts=1700000000,
            end_ts=1700100000,
            period_interval=60,
            include_latest_before_start=True,
        )
        q = dict(route.calls[0].request.url.params)
        assert q["include_latest_before_start"] == "true"

    @respx.mock
    def test_bulk_candlesticks_include_flag_false(
        self, markets: MarketsResource,
    ) -> None:
        """Tri-state bool: explicit False must send 'false' on the wire."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/candlesticks",
        ).mock(return_value=httpx.Response(200, json={"markets": []}))
        markets.bulk_candlesticks(
            market_tickers="MKT-A",
            start_ts=1700000000,
            end_ts=1700100000,
            period_interval=60,
            include_latest_before_start=False,
        )
        q = dict(route.calls[0].request.url.params)
        assert q["include_latest_before_start"] == "false"

    @respx.mock
    def test_bulk_candlesticks_omits_include_flag_when_none(
        self, markets: MarketsResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/candlesticks",
        ).mock(return_value=httpx.Response(200, json={"markets": []}))
        markets.bulk_candlesticks(
            market_tickers="MKT-A",
            start_ts=1700000000,
            end_ts=1700100000,
            period_interval=60,
        )
        q = dict(route.calls[0].request.url.params)
        assert "include_latest_before_start" not in q


class TestMarketsBulkEmptyValidation:
    def test_bulk_candlesticks_rejects_empty_list(
        self, markets: MarketsResource,
    ) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            markets.bulk_candlesticks(
                market_tickers=[],
                start_ts=1, end_ts=2, period_interval=60,
            )

    def test_bulk_candlesticks_rejects_empty_string(
        self, markets: MarketsResource,
    ) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            markets.bulk_candlesticks(
                market_tickers="",
                start_ts=1, end_ts=2, period_interval=60,
            )

    def test_bulk_candlesticks_rejects_over_100_list(
        self, markets: MarketsResource,
    ) -> None:
        with pytest.raises(ValueError, match="at most 100"):
            markets.bulk_candlesticks(
                market_tickers=[f"MKT-{i}" for i in range(101)],
                start_ts=1, end_ts=2, period_interval=60,
            )

    def test_bulk_candlesticks_rejects_over_100_string(
        self, markets: MarketsResource,
    ) -> None:
        """Pre-joined string input must hit the same upper-bound guard as list input."""
        joined = ",".join(f"MKT-{i}" for i in range(101))
        with pytest.raises(ValueError, match="at most 100"):
            markets.bulk_candlesticks(
                market_tickers=joined,
                start_ts=1, end_ts=2, period_interval=60,
            )

    def test_bulk_orderbooks_rejects_empty_list(
        self, markets: MarketsResource,
    ) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            markets.bulk_orderbooks(tickers=[])

    def test_bulk_orderbooks_rejects_over_100(
        self, markets: MarketsResource,
    ) -> None:
        with pytest.raises(ValueError, match="at most 100"):
            markets.bulk_orderbooks(tickers=[f"MKT-{i}" for i in range(101)])


class TestMarketsBulkOrderbooks:
    @respx.mock
    def test_returns_list_of_orderbooks(self, markets: MarketsResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/orderbooks",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "orderbooks": [
                        {
                            "ticker": "MKT-A",
                            "orderbook_fp": {
                                "yes_dollars": [["0.45", "100"]],
                                "no_dollars": [["0.55", "50"]],
                            },
                        },
                        {
                            "ticker": "MKT-B",
                            "orderbook_fp": {
                                "yes_dollars": [],
                                "no_dollars": [],
                            },
                        },
                    ],
                },
            ),
        )
        books = markets.bulk_orderbooks(tickers=["MKT-A", "MKT-B"])
        assert len(books) == 2
        assert all(isinstance(b, Orderbook) for b in books)
        assert books[0].ticker == "MKT-A"
        assert books[0].yes[0].price == Decimal("0.45")
        assert books[0].yes[0].quantity == Decimal("100")
        # Spec: explode:true — httpx sends each ticker as a separate param.
        raw = str(route.calls[0].request.url.query)
        assert "tickers=MKT-A" in raw
        assert "tickers=MKT-B" in raw

    def test_bulk_orderbooks_requires_auth(self, config: KalshiConfig) -> None:
        unauth = MarketsResource(SyncTransport(None, config))
        with pytest.raises(AuthRequiredError):
            unauth.bulk_orderbooks(tickers=["MKT-A"])

    @respx.mock
    def test_bulk_orderbooks_handles_missing_sides(
        self, markets: MarketsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/orderbooks",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"orderbooks": [{"ticker": "MKT-X", "orderbook_fp": {}}]},
            ),
        )
        books = markets.bulk_orderbooks(tickers=["MKT-X"])
        assert books[0].yes == []
        assert books[0].no == []

    @respx.mock
    def test_bulk_orderbooks_rejects_item_with_missing_ticker(
        self, markets: MarketsResource,
    ) -> None:
        """Server omitting per-item ticker must raise, not silently return ``ticker=''``."""
        respx.get(
            "https://test.kalshi.com/trade-api/v2/markets/orderbooks",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"orderbooks": [{"orderbook_fp": {}}]},
            ),
        )
        with pytest.raises(KalshiError, match="empty or missing 'ticker'"):
            markets.bulk_orderbooks(tickers=["MKT-X"])


class TestOrderbookFromItem:
    """Direct unit tests for the bulk-orderbook per-item parser."""

    def test_missing_ticker_raises_kalshi_error(self) -> None:
        from kalshi.resources.markets import _orderbook_from_item
        with pytest.raises(KalshiError, match="empty or missing 'ticker'"):
            _orderbook_from_item({"orderbook_fp": {}})

    def test_empty_string_ticker_raises(self) -> None:
        from kalshi.resources.markets import _orderbook_from_item
        with pytest.raises(KalshiError, match="empty or missing 'ticker'"):
            _orderbook_from_item({"ticker": "", "orderbook_fp": {}})

    def test_parses_new_shape(self) -> None:
        from kalshi.resources.markets import _orderbook_from_item
        ob = _orderbook_from_item({
            "ticker": "MKT-A",
            "orderbook_fp": {
                "yes_dollars": [["0.42", "100"]],
                "no_dollars": [["0.58", "50"]],
            },
        })
        assert ob.ticker == "MKT-A"
        assert ob.yes[0].price == Decimal("0.42")
        assert ob.no[0].price == Decimal("0.58")


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
