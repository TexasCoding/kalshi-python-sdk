"""Tests for kalshi.resources.historical — Historical resource."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import AuthRequiredError, KalshiNotFoundError
from kalshi.resources.historical import AsyncHistoricalResource, HistoricalResource
from tests._model_fixtures import (
    candlestick_dict,
    event_position_dict,
    fill_dict,
    market_dict,
    market_position_dict,
    order_dict,
    trade_dict,
)


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def historical(test_auth: KalshiAuth, config: KalshiConfig) -> HistoricalResource:
    return HistoricalResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_historical(test_auth: KalshiAuth, config: KalshiConfig) -> AsyncHistoricalResource:
    return AsyncHistoricalResource(AsyncTransport(test_auth, config))


@pytest.fixture
def unauth_historical(config: KalshiConfig) -> HistoricalResource:
    return HistoricalResource(SyncTransport(None, config))


@pytest.fixture
def unauth_async_historical(config: KalshiConfig) -> AsyncHistoricalResource:
    return AsyncHistoricalResource(AsyncTransport(None, config))


BASE = "https://test.kalshi.com/trade-api/v2"


# ── Sync tests ──────────────────────────────────────────────


class TestHistoricalCutoff:
    @respx.mock
    def test_returns_cutoff(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/cutoff").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_settled_ts": "2026-04-01T00:00:00Z",
                    "trades_created_ts": "2026-04-01T00:00:00Z",
                    "orders_updated_ts": "2026-04-01T00:00:00Z",
                },
            )
        )
        cutoff = historical.cutoff()
        assert cutoff.market_settled_ts is not None
        assert cutoff.trades_created_ts is not None
        assert cutoff.orders_updated_ts is not None
        assert cutoff.market_positions_last_updated_ts is None

    @respx.mock
    def test_returns_cutoff_with_market_positions_ts(
        self, historical: HistoricalResource
    ) -> None:
        """Spec v3.26.0: optional market_positions_last_updated_ts archival boundary."""
        respx.get(f"{BASE}/historical/cutoff").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_settled_ts": "2026-04-01T00:00:00Z",
                    "trades_created_ts": "2026-04-01T00:00:00Z",
                    "orders_updated_ts": "2026-04-01T00:00:00Z",
                    "market_positions_last_updated_ts": "2026-03-15T12:00:00Z",
                },
            )
        )
        cutoff = historical.cutoff()
        assert cutoff.market_positions_last_updated_ts is not None
        assert cutoff.market_positions_last_updated_ts.year == 2026


class TestHistoricalMarkets:
    @respx.mock
    def test_returns_page(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/markets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "markets": [
                        market_dict(ticker="HIST-A", yes_bid_dollars="0.9000"),
                        market_dict(ticker="HIST-B", yes_bid_dollars="0.1000"),
                    ],
                    "cursor": "page2",
                },
            )
        )
        page = historical.markets()
        assert len(page) == 2
        assert page.items[0].ticker == "HIST-A"
        assert page.items[0].yes_bid == Decimal("0.9000")
        assert page.has_next is True

    @respx.mock
    def test_markets_all_paginates(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/markets").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "markets": [market_dict(ticker="A")],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={"markets": [market_dict(ticker="B")], "cursor": ""},
                ),
            ]
        )
        tickers = [m.ticker for m in historical.markets_all()]
        assert tickers == ["A", "B"]

    @respx.mock
    def test_empty_markets(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": ""})
        )
        page = historical.markets()
        assert len(page) == 0

    def test_ticker_kwarg_removed(self, historical: HistoricalResource) -> None:
        """Regression: v0.7.0 renamed `ticker` -> `tickers` (BREAKING).

        Spec uses plural `tickers` (TickersQuery, comma-separated string).
        Migration: historical.markets(ticker="X") -> historical.markets(tickers="X")
        OR historical.markets(tickers=["X", "Y"]).
        """
        with pytest.raises(TypeError, match="ticker"):
            historical.markets(ticker="X")  # type: ignore[call-arg]

    @respx.mock
    def test_markets_with_all_new_filters(self, historical: HistoricalResource) -> None:
        """v0.7.0: tickers RENAME (list form) + mve_filter ADD."""
        route = respx.get(f"{BASE}/historical/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": ""})
        )
        historical.markets(
            limit=50,
            cursor="abc",
            tickers=["MKT-A", "MKT-B"],
            event_ticker="EVT-X",
            series_ticker="SER-Y",
            mve_filter="filter-z",
        )
        params = dict(route.calls[0].request.url.params)
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["tickers"] == "MKT-A,MKT-B"
        assert params["event_ticker"] == "EVT-X"
        assert params["series_ticker"] == "SER-Y"
        assert params["mve_filter"] == "filter-z"

    @respx.mock
    def test_tickers_serialized_as_comma_join_list(self, historical: HistoricalResource) -> None:
        """Spec says tickers is type:string (comma-separated), NOT explode:true."""
        route = respx.get(f"{BASE}/historical/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        historical.markets(tickers=["A", "B", "C"])
        url = str(route.calls[0].request.url)
        assert "tickers=A%2CB%2CC" in url or "tickers=A,B,C" in url
        assert url.count("tickers=") == 1

    @respx.mock
    def test_tickers_serialized_as_comma_join_string(self, historical: HistoricalResource) -> None:
        """Pre-joined string passes through unchanged."""
        route = respx.get(f"{BASE}/historical/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        historical.markets(tickers="A,B,C")
        params = dict(route.calls[0].request.url.params)
        assert params["tickers"] == "A,B,C"


class TestHistoricalMarket:
    @respx.mock
    def test_returns_market(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/markets/HIST-MKT").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market": market_dict(
                        ticker="HIST-MKT", result="yes", yes_bid_dollars="1.0000"
                    ),
                },
            )
        )
        market = historical.market("HIST-MKT")
        assert market.ticker == "HIST-MKT"
        assert market.result == "yes"

    @respx.mock
    def test_not_found(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/markets/FAKE").mock(
            return_value=httpx.Response(404, json={"message": "not found"})
        )
        with pytest.raises(KalshiNotFoundError):
            historical.market("FAKE")


class TestHistoricalCandlesticks:
    @respx.mock
    def test_returns_candlesticks(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/markets/MKT/candlesticks").mock(
            return_value=httpx.Response(
                200,
                json={
                    "candlesticks": [
                        candlestick_dict(
                            end_period_ts=1700000000,
                            yes_bid={
                                "open_dollars": "0.40",
                                "high_dollars": "0.50",
                                "low_dollars": "0.35",
                                "close_dollars": "0.45",
                            },
                            price={"open_dollars": "0.45", "close_dollars": "0.50"},
                            volume_fp="500.00",
                            open_interest_fp="1000.00",
                        )
                    ]
                },
            )
        )
        candles = historical.candlesticks(
            "MKT", start_ts=1700000000, end_ts=1700100000, period_interval=60
        )
        assert len(candles) == 1
        assert candles[0].yes_bid.open == Decimal("0.40")
        assert candles[0].volume == Decimal("500.00")

    @respx.mock
    def test_with_params(self, historical: HistoricalResource) -> None:
        route = respx.get(f"{BASE}/historical/markets/MKT/candlesticks").mock(
            return_value=httpx.Response(200, json={"candlesticks": []})
        )
        historical.candlesticks("MKT", period_interval=60, start_ts=100, end_ts=200)
        assert route.calls[0].request.url.params["period_interval"] == "60"
        assert route.calls[0].request.url.params["start_ts"] == "100"
        assert route.calls[0].request.url.params["end_ts"] == "200"


class TestHistoricalFills:
    @respx.mock
    def test_returns_page(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/fills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fills": [
                        fill_dict(
                            trade_id="f1",
                            fill_id="f1",
                            order_id="o1",
                            ticker="MKT-A",
                            side="yes",
                            action="buy",
                            count_fp="10.00",
                            yes_price_dollars="0.5000",
                            no_price_dollars="0.5000",
                            is_taker=True,
                            fee_cost_dollars="0.0500",
                        )
                    ],
                    "cursor": "p2",
                },
            )
        )
        page = historical.fills()
        assert len(page) == 1
        f = page.items[0]
        assert f.trade_id == "f1"
        assert f.fill_id == "f1"
        assert f.count == Decimal("10.00")
        assert f.yes_price == Decimal("0.5000")
        assert f.fee_cost == Decimal("0.0500")
        assert f.is_taker is True
        assert page.has_next is True

    @respx.mock
    def test_fills_all_paginates(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/fills").mock(
            side_effect=[
                httpx.Response(
                    200, json={"fills": [fill_dict(trade_id="a", count_fp="1")], "cursor": "p2"}
                ),
                httpx.Response(
                    200, json={"fills": [fill_dict(trade_id="b", count_fp="2")], "cursor": ""}
                ),
            ]
        )
        ids = [f.trade_id for f in historical.fills_all()]
        assert ids == ["a", "b"]

    @respx.mock
    def test_fills_with_max_ts(self, historical: HistoricalResource) -> None:
        """v0.7.0 ADD: max_ts kwarg reaches the wire."""
        route = respx.get(f"{BASE}/historical/fills").mock(
            return_value=httpx.Response(200, json={"fills": []})
        )
        historical.fills(ticker="MKT-A", max_ts=1700099999)
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["max_ts"] == "1700099999"


class TestHistoricalOrders:
    @respx.mock
    def test_returns_page(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/orders").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orders": [
                        order_dict(order_id="o1", ticker="MKT-A", status="executed"),
                    ],
                    "cursor": "",
                },
            )
        )
        page = historical.orders()
        assert len(page) == 1
        assert page.items[0].order_id == "o1"

    @respx.mock
    def test_orders_all_paginates(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/orders").mock(
            side_effect=[
                httpx.Response(200, json={"orders": [order_dict(order_id="a")], "cursor": "p2"}),
                httpx.Response(200, json={"orders": [order_dict(order_id="b")], "cursor": ""}),
            ]
        )
        ids = [o.order_id for o in historical.orders_all()]
        assert ids == ["a", "b"]

    @respx.mock
    def test_orders_with_max_ts(self, historical: HistoricalResource) -> None:
        """v0.7.0 ADD: max_ts kwarg reaches the wire."""
        route = respx.get(f"{BASE}/historical/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        historical.orders(ticker="MKT-A", max_ts=1700099999)
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["max_ts"] == "1700099999"


class TestHistoricalTrades:
    @respx.mock
    def test_returns_page(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/trades").mock(
            return_value=httpx.Response(
                200,
                json={
                    "trades": [
                        trade_dict(
                            trade_id="t1",
                            ticker="MKT-A",
                            count_fp="5.00",
                            yes_price_dollars="0.6000",
                            no_price_dollars="0.4000",
                            taker_side="yes",
                            created_time="2026-04-12T12:00:00Z",
                        )
                    ],
                    "cursor": "",
                },
            )
        )
        page = historical.trades()
        assert len(page) == 1
        t = page.items[0]
        assert t.trade_id == "t1"
        assert t.count == Decimal("5.00")
        assert t.yes_price == Decimal("0.6000")
        assert t.taker_side == "yes"

    @respx.mock
    def test_trades_all_paginates(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/trades").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "trades": [
                            trade_dict(
                                trade_id="a",
                                count_fp="1",
                                yes_price_dollars="0.5",
                                no_price_dollars="0.5",
                                taker_side="yes",
                            )
                        ],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "trades": [
                            trade_dict(
                                trade_id="b",
                                count_fp="2",
                                yes_price_dollars="0.6",
                                no_price_dollars="0.4",
                                taker_side="no",
                            )
                        ],
                        "cursor": "",
                    },
                ),
            ]
        )
        ids = [t.trade_id for t in historical.trades_all()]
        assert ids == ["a", "b"]

    @respx.mock
    def test_trades_with_min_max_ts(self, historical: HistoricalResource) -> None:
        """v0.7.0 ADDs: min_ts AND max_ts kwargs reach the wire."""
        route = respx.get(f"{BASE}/historical/trades").mock(
            return_value=httpx.Response(200, json={"trades": []})
        )
        historical.trades(ticker="MKT-A", min_ts=1700000000, max_ts=1700099999)
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"


# ── Async tests ─────────────────────────────────────────────


class TestAsyncHistoricalCutoff:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_cutoff(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/cutoff").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_settled_ts": "2026-04-01T00:00:00Z",
                    "trades_created_ts": "2026-04-01T00:00:00Z",
                    "orders_updated_ts": "2026-04-01T00:00:00Z",
                },
            )
        )
        cutoff = await async_historical.cutoff()
        assert cutoff.market_settled_ts is not None


class TestAsyncHistoricalMarkets:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/markets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "markets": [market_dict(ticker="HIST-A", yes_bid_dollars="0.90")],
                    "cursor": "p2",
                },
            )
        )
        page = await async_historical.markets()
        assert len(page) == 1
        assert page.items[0].yes_bid == Decimal("0.90")

    @respx.mock
    @pytest.mark.asyncio
    async def test_markets_all(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/markets").mock(
            side_effect=[
                httpx.Response(200, json={"markets": [market_dict(ticker="A")], "cursor": "p2"}),
                httpx.Response(200, json={"markets": [market_dict(ticker="B")], "cursor": ""}),
            ]
        )
        tickers = [m.ticker async for m in async_historical.markets_all()]
        assert tickers == ["A", "B"]

    @pytest.mark.asyncio
    async def test_ticker_kwarg_removed(self, async_historical: AsyncHistoricalResource) -> None:
        """Regression: v0.7.0 renamed `ticker` -> `tickers` (BREAKING)."""
        with pytest.raises(TypeError, match="ticker"):
            await async_historical.markets(ticker="X")  # type: ignore[call-arg]

    @respx.mock
    @pytest.mark.asyncio
    async def test_markets_with_all_new_filters(
        self, async_historical: AsyncHistoricalResource
    ) -> None:
        """v0.7.0: tickers RENAME (list form) + mve_filter ADD."""
        route = respx.get(f"{BASE}/historical/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": ""})
        )
        await async_historical.markets(
            limit=50,
            cursor="abc",
            tickers=["MKT-A", "MKT-B"],
            event_ticker="EVT-X",
            series_ticker="SER-Y",
            mve_filter="filter-z",
        )
        params = dict(route.calls[0].request.url.params)
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["tickers"] == "MKT-A,MKT-B"
        assert params["event_ticker"] == "EVT-X"
        assert params["series_ticker"] == "SER-Y"
        assert params["mve_filter"] == "filter-z"

    @respx.mock
    @pytest.mark.asyncio
    async def test_tickers_serialized_as_comma_join_list(
        self, async_historical: AsyncHistoricalResource
    ) -> None:
        """Spec says tickers is type:string (comma-separated), NOT explode:true."""
        route = respx.get(f"{BASE}/historical/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        await async_historical.markets(tickers=["A", "B", "C"])
        url = str(route.calls[0].request.url)
        assert "tickers=A%2CB%2CC" in url or "tickers=A,B,C" in url
        assert url.count("tickers=") == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_tickers_serialized_as_comma_join_string(
        self, async_historical: AsyncHistoricalResource
    ) -> None:
        """Pre-joined string passes through unchanged."""
        route = respx.get(f"{BASE}/historical/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        await async_historical.markets(tickers="A,B,C")
        params = dict(route.calls[0].request.url.params)
        assert params["tickers"] == "A,B,C"


class TestAsyncHistoricalTrades:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/trades").mock(
            return_value=httpx.Response(
                200,
                json={
                    "trades": [
                        trade_dict(
                            trade_id="t1",
                            ticker="MKT",
                            count_fp="5.00",
                            yes_price_dollars="0.60",
                            no_price_dollars="0.40",
                            taker_side="yes",
                        )
                    ],
                    "cursor": "",
                },
            )
        )
        page = await async_historical.trades()
        assert len(page) == 1
        assert page.items[0].count == Decimal("5.00")

    @respx.mock
    @pytest.mark.asyncio
    async def test_trades_all(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/trades").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "trades": [
                            trade_dict(
                                trade_id="a",
                                count_fp="1",
                                yes_price_dollars="0.5",
                                no_price_dollars="0.5",
                                taker_side="yes",
                            )
                        ],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "trades": [
                            trade_dict(
                                trade_id="b",
                                count_fp="2",
                                yes_price_dollars="0.6",
                                no_price_dollars="0.4",
                                taker_side="no",
                            )
                        ],
                        "cursor": "",
                    },
                ),
            ]
        )
        ids = [t.trade_id async for t in async_historical.trades_all()]
        assert ids == ["a", "b"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_trades_with_min_max_ts(self, async_historical: AsyncHistoricalResource) -> None:
        """v0.7.0 ADDs: min_ts AND max_ts kwargs reach the wire."""
        route = respx.get(f"{BASE}/historical/trades").mock(
            return_value=httpx.Response(200, json={"trades": []})
        )
        await async_historical.trades(ticker="MKT-A", min_ts=1700000000, max_ts=1700099999)
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"


class TestAsyncHistoricalFills:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/fills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fills": [
                        fill_dict(
                            trade_id="f1",
                            count_fp="10",
                            yes_price_dollars="0.50",
                            no_price_dollars="0.50",
                            fee_cost_dollars="0.05",
                        ),
                    ],
                    "cursor": "",
                },
            )
        )
        page = await async_historical.fills()
        assert len(page) == 1
        assert page.items[0].fee_cost == Decimal("0.05")

    @respx.mock
    @pytest.mark.asyncio
    async def test_fills_all(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/fills").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "fills": [fill_dict(trade_id="a", count_fp="1")],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "fills": [fill_dict(trade_id="b", count_fp="2")],
                        "cursor": "",
                    },
                ),
            ]
        )
        ids = [f.trade_id async for f in async_historical.fills_all()]
        assert ids == ["a", "b"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_fills_with_max_ts(self, async_historical: AsyncHistoricalResource) -> None:
        """v0.7.0 ADD: max_ts kwarg reaches the wire."""
        route = respx.get(f"{BASE}/historical/fills").mock(
            return_value=httpx.Response(200, json={"fills": []})
        )
        await async_historical.fills(ticker="MKT-A", max_ts=1700099999)
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["max_ts"] == "1700099999"


class TestAsyncHistoricalMarket:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_market(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/markets/HIST-MKT").mock(
            return_value=httpx.Response(
                200,
                json={"market": market_dict(ticker="HIST-MKT", result="yes")},
            )
        )
        market = await async_historical.market("HIST-MKT")
        assert market.ticker == "HIST-MKT"
        assert market.result == "yes"


class TestAsyncHistoricalCandlesticks:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_candlesticks(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/markets/MKT/candlesticks").mock(
            return_value=httpx.Response(
                200,
                json={
                    "candlesticks": [
                        candlestick_dict(
                            end_period_ts=1700000000,
                            yes_bid={
                                "open_dollars": "0.40",
                                "high_dollars": "0.50",
                                "low_dollars": "0.35",
                                "close_dollars": "0.45",
                            },
                            volume_fp="500.00",
                        )
                    ]
                },
            )
        )
        candles = await async_historical.candlesticks(
            "MKT", start_ts=1700000000, end_ts=1700100000, period_interval=60
        )
        assert len(candles) == 1
        assert candles[0].yes_bid.open == Decimal("0.40")


class TestAsyncHistoricalOrders:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/orders").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orders": [order_dict(order_id="o1", status="executed")],
                    "cursor": "",
                },
            )
        )
        page = await async_historical.orders()
        assert len(page) == 1
        assert page.items[0].order_id == "o1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_orders_all(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/orders").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "orders": [order_dict(order_id="a")],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "orders": [order_dict(order_id="b")],
                        "cursor": "",
                    },
                ),
            ]
        )
        ids = [o.order_id async for o in async_historical.orders_all()]
        assert ids == ["a", "b"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_orders_with_max_ts(self, async_historical: AsyncHistoricalResource) -> None:
        """v0.7.0 ADD: max_ts kwarg reaches the wire."""
        route = respx.get(f"{BASE}/historical/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        await async_historical.orders(ticker="MKT-A", max_ts=1700099999)
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["max_ts"] == "1700099999"


# ── Historical positions (spec v3.26.0 / #484) ─────────────────────────────


class TestHistoricalPositions:
    @respx.mock
    def test_returns_positions(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/positions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_positions": [
                        market_position_dict(
                            ticker="MKT-A",
                            total_traded_dollars="100.0000",
                            position_fp="50.00",
                            market_exposure_dollars="25.0000",
                            realized_pnl_dollars="10.0000",
                            fees_paid_dollars="1.5000",
                            resting_orders_count=0,
                        )
                    ],
                    "event_positions": [
                        event_position_dict(
                            event_ticker="EVT-1",
                            total_cost_dollars="200.0000",
                            total_cost_shares_fp="100.00",
                            event_exposure_dollars="50.0000",
                            realized_pnl_dollars="20.0000",
                            fees_paid_dollars="3.0000",
                        )
                    ],
                    "cursor": "next-page",
                },
            )
        )
        resp = historical.positions()
        assert len(resp.market_positions) == 1
        assert resp.market_positions[0].ticker == "MKT-A"
        assert resp.market_positions[0].position == Decimal("50.00")
        assert resp.market_positions[0].total_traded == Decimal("100.0000")
        assert len(resp.event_positions) == 1
        assert resp.event_positions[0].event_ticker == "EVT-1"
        assert resp.has_next is True
        assert resp.cursor == "next-page"

    @respx.mock
    def test_empty_positions(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/positions").mock(
            return_value=httpx.Response(
                200,
                json={"market_positions": [], "event_positions": []},
            )
        )
        resp = historical.positions()
        assert resp.market_positions == []
        assert resp.event_positions == []
        assert resp.has_next is False

    @respx.mock
    def test_positions_with_filters(self, historical: HistoricalResource) -> None:
        route = respx.get(f"{BASE}/historical/positions").mock(
            return_value=httpx.Response(
                200, json={"market_positions": [], "event_positions": [], "cursor": ""}
            )
        )
        historical.positions(
            limit=50,
            cursor="abc",
            ticker="MKT-A",
            event_ticker="EVT-X",
            subaccount=3,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["subaccount"] == "3"
        # Historical positions do not accept portfolio-only count_filter.
        assert "count_filter" not in params

    def test_positions_requires_auth(self, unauth_historical: HistoricalResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_historical.positions()

    def test_count_filter_kwarg_rejected(self, historical: HistoricalResource) -> None:
        """Historical positions is a subset of portfolio positions — no count_filter."""
        with pytest.raises(TypeError, match="count_filter"):
            historical.positions(count_filter="position")  # type: ignore[call-arg]


class TestHistoricalPositionsAll:
    @respx.mock
    def test_positions_all_paginates(self, historical: HistoricalResource) -> None:
        respx.get(f"{BASE}/historical/positions").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "market_positions": [
                            market_position_dict(ticker="A"),
                            market_position_dict(ticker="B"),
                        ],
                        "event_positions": [],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "market_positions": [market_position_dict(ticker="C")],
                        "event_positions": [],
                        "cursor": "",
                    },
                ),
            ]
        )
        tickers = [p.ticker for p in historical.positions_all()]
        assert tickers == ["A", "B", "C"]

    @respx.mock
    def test_positions_all_forwards_filters_and_omits_cursor(
        self, historical: HistoricalResource
    ) -> None:
        route = respx.get(f"{BASE}/historical/positions").mock(
            return_value=httpx.Response(
                200, json={"market_positions": [], "event_positions": [], "cursor": ""}
            )
        )
        list(
            historical.positions_all(
                limit=100,
                ticker="MKT-A",
                event_ticker="EVT-X",
            )
        )
        params = dict(route.calls[0].request.url.params)
        assert params["limit"] == "100"
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert "cursor" not in params

    def test_positions_all_requires_auth(self, unauth_historical: HistoricalResource) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_historical.positions_all())

    def test_positions_all_rejects_zero_max_pages(self, historical: HistoricalResource) -> None:
        with pytest.raises(ValueError, match="max_pages must be positive"):
            list(historical.positions_all(max_pages=0))


class TestAsyncHistoricalPositions:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_positions(self, async_historical: AsyncHistoricalResource) -> None:
        respx.get(f"{BASE}/historical/positions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_positions": [market_position_dict(ticker="MKT-A", position_fp="10.00")],
                    "event_positions": [],
                    "cursor": "",
                },
            )
        )
        resp = await async_historical.positions()
        assert len(resp.market_positions) == 1
        assert resp.market_positions[0].ticker == "MKT-A"
        assert resp.market_positions[0].position == Decimal("10.00")

    @respx.mock
    @pytest.mark.asyncio
    async def test_positions_with_filters(self, async_historical: AsyncHistoricalResource) -> None:
        route = respx.get(f"{BASE}/historical/positions").mock(
            return_value=httpx.Response(
                200, json={"market_positions": [], "event_positions": [], "cursor": ""}
            )
        )
        await async_historical.positions(limit=25, ticker="MKT-B", event_ticker="EVT-Y")
        params = dict(route.calls[0].request.url.params)
        assert params["limit"] == "25"
        assert params["ticker"] == "MKT-B"
        assert params["event_ticker"] == "EVT-Y"

    @pytest.mark.asyncio
    async def test_positions_requires_auth(
        self, unauth_async_historical: AsyncHistoricalResource
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_historical.positions()

    @respx.mock
    @pytest.mark.asyncio
    async def test_positions_all_paginates(
        self, async_historical: AsyncHistoricalResource
    ) -> None:
        respx.get(f"{BASE}/historical/positions").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "market_positions": [market_position_dict(ticker="A")],
                        "event_positions": [],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "market_positions": [market_position_dict(ticker="B")],
                        "event_positions": [],
                        "cursor": "",
                    },
                ),
            ]
        )
        tickers = [p.ticker async for p in async_historical.positions_all()]
        assert tickers == ["A", "B"]

    @pytest.mark.asyncio
    async def test_positions_all_requires_auth(
        self, unauth_async_historical: AsyncHistoricalResource
    ) -> None:
        with pytest.raises(AuthRequiredError):
            async for _ in unauth_async_historical.positions_all():
                pass
