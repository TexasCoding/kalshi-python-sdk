"""Tests for the perps markets resource (#390).

All four endpoints (``list`` / ``get`` / ``orderbook`` / ``candlesticks``) are
public margin market data — the spec marks no ``security`` block on any of them,
so an unauthenticated client must reach the wire (no ``AuthRequiredError``).
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi.errors import KalshiNotFoundError, KalshiServerError
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.models.markets import (
    BidAskDistributionHistorical,
    MarginMarket,
    MarginMarketCandlestick,
    MarginOrderbook,
    PriceDistributionHistorical,
)

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


def _market_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ticker": "BTC-PERP",
        "title": "Bitcoin Perpetual",
        "status": "active",
        "contract_size": "1.000000",
        "tick_size": "0.0100",
        "fractional_trading_enabled": True,
        "leverage_estimate": 2.5,
        "price": "0.5600",
        "bid": "0.5500",
        "ask": "0.5700",
        "volume": "1000.00",
        "volume_24h": "250.00",
        "open_interest": "500.00",
    }
    base.update(overrides)
    return base


def _candle_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "end_period_ts": 1_700_000_060,
        "bid": {"open": "0.5500", "high": "0.5600", "low": "0.5400", "close": "0.5550"},
        "ask": {"open": "0.5700", "high": "0.5800", "low": "0.5600", "close": "0.5750"},
        "price": {
            "open": "0.5600",
            "high": "0.5700",
            "low": "0.5500",
            "close": "0.5650",
            "mean": "0.5620",
            "previous": "0.5580",
        },
        "volume": "100.00",
        "open_interest": "500.00",
    }
    base.update(overrides)
    return base


# ── list ──────────────────────────────────────────────────────────────────────


class TestList:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets").mock(
            return_value=httpx.Response(200, json={"markets": [_market_dict()]})
        )
        markets = perps_client.markets.list()
        assert isinstance(markets, list)
        assert len(markets) == 1
        m = markets[0]
        assert isinstance(m, MarginMarket)
        assert m.ticker == "BTC-PERP"
        assert m.status == "active"
        assert m.contract_size == Decimal("1.000000")
        assert isinstance(m.contract_size, Decimal)
        assert m.tick_size == Decimal("0.0100")
        assert isinstance(m.tick_size, Decimal)
        assert m.leverage_estimate == 2.5
        assert isinstance(m.leverage_estimate, float)
        assert m.volume == Decimal("1000.00")

    @respx.mock
    def test_status_filter(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        perps_client.markets.list(status="active")
        assert route.calls[0].request.url.params["status"] == "active"

    @respx.mock
    def test_null_leverage_and_missing_optionals(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "markets": [
                        {
                            "ticker": "ETH-PERP",
                            "title": "Ether Perpetual",
                            "status": "inactive",
                            "contract_size": "1.000000",
                            "tick_size": "0.0100",
                            "fractional_trading_enabled": False,
                            "leverage_estimate": None,
                        }
                    ]
                },
            )
        )
        m = perps_client.markets.list()[0]
        assert m.leverage_estimate is None
        assert m.price is None
        assert m.bid is None
        assert m.ask is None
        assert m.volume is None
        assert m.volume_24h is None
        assert m.open_interest is None

    @respx.mock
    def test_empty_list(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        assert perps_client.markets.list() == []

    @respx.mock
    def test_missing_markets_key(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets").mock(return_value=httpx.Response(200, json={}))
        assert perps_client.markets.list() == []

    @respx.mock
    def test_server_error_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets").mock(return_value=httpx.Response(500))
        with pytest.raises(KalshiServerError):
            perps_client.markets.list()

    @respx.mock
    def test_public_no_auth_required(self) -> None:
        route = respx.get(f"{BASE}/margin/markets").mock(
            return_value=httpx.Response(200, json={"markets": [_market_dict()]})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        markets = client.markets.list()
        assert len(markets) == 1
        assert route.called
        client.close()

    @respx.mock
    async def test_async(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets").mock(
            return_value=httpx.Response(200, json={"markets": [_market_dict(ticker="SOL-PERP")]})
        )
        markets = await async_perps_client.markets.list()
        assert markets[0].ticker == "SOL-PERP"
        await async_perps_client.close()


# ── get ───────────────────────────────────────────────────────────────────────


class TestGet:
    @respx.mock
    def test_happy_wrapped(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/BTC-PERP").mock(
            return_value=httpx.Response(200, json={"market": _market_dict()})
        )
        m = perps_client.markets.get("BTC-PERP")
        assert m.ticker == "BTC-PERP"
        assert m.price == Decimal("0.5600")
        assert isinstance(m.price, Decimal)

    @respx.mock
    def test_happy_bare_fallback(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/BTC-PERP").mock(
            return_value=httpx.Response(200, json=_market_dict())
        )
        m = perps_client.markets.get("BTC-PERP")
        assert m.ticker == "BTC-PERP"

    @respx.mock
    def test_not_found_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/NOPE").mock(return_value=httpx.Response(404))
        with pytest.raises(KalshiNotFoundError):
            perps_client.markets.get("NOPE")

    @respx.mock
    def test_not_found_single_call(self, perps_client: PerpsClient) -> None:
        # 404 is non-retryable; GET only retries on 429/502/503/504.
        route = respx.get(f"{BASE}/margin/markets/NOPE").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(KalshiNotFoundError):
            perps_client.markets.get("NOPE")
        assert route.call_count == 1

    @respx.mock
    async def test_async(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/BTC-PERP").mock(
            return_value=httpx.Response(200, json={"market": _market_dict()})
        )
        m = await async_perps_client.markets.get("BTC-PERP")
        assert m.ticker == "BTC-PERP"
        await async_perps_client.close()


# ── orderbook ─────────────────────────────────────────────────────────────────


class TestOrderbook:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/BTC-PERP/orderbook").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orderbook": {
                        "bids": [["0.1500", "100.00"], ["0.1400", "200.00"]],
                        "asks": [["0.1600", "50.00"]],
                    }
                },
            )
        )
        ob = perps_client.markets.orderbook("BTC-PERP")
        assert isinstance(ob, MarginOrderbook)
        assert ob.ticker == "BTC-PERP"
        assert ob.bids[0].price == Decimal("0.15")
        assert isinstance(ob.bids[0].price, Decimal)
        assert ob.bids[0].quantity == Decimal("100.00")
        assert ob.asks[0].price == Decimal("0.16")
        assert ob.asks[0].quantity == Decimal("50.00")

    @respx.mock
    def test_params(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/markets/BTC-PERP/orderbook").mock(
            return_value=httpx.Response(200, json={"orderbook": {"bids": [], "asks": []}})
        )
        perps_client.markets.orderbook("BTC-PERP", depth=10, aggregation_tick_size="0.10")
        params = dict(route.calls[0].request.url.params)
        assert params["depth"] == "10"
        assert params["aggregation_tick_size"] == "0.10"

    @respx.mock
    def test_null_bids_asks(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/BTC-PERP/orderbook").mock(
            return_value=httpx.Response(
                200, json={"orderbook": {"bids": None, "asks": None}}
            )
        )
        ob = perps_client.markets.orderbook("BTC-PERP")
        assert ob.bids == []
        assert ob.asks == []

    @respx.mock
    def test_missing_bids_asks(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/BTC-PERP/orderbook").mock(
            return_value=httpx.Response(200, json={"orderbook": {}})
        )
        ob = perps_client.markets.orderbook("BTC-PERP")
        assert ob.bids == []
        assert ob.asks == []

    @respx.mock
    def test_not_found_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/NOPE/orderbook").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(KalshiNotFoundError):
            perps_client.markets.orderbook("NOPE")

    @respx.mock
    async def test_async(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/BTC-PERP/orderbook").mock(
            return_value=httpx.Response(
                200, json={"orderbook": {"bids": [["0.1500", "100.00"]], "asks": []}}
            )
        )
        ob = await async_perps_client.markets.orderbook("BTC-PERP")
        assert ob.bids[0].price == Decimal("0.15")
        await async_perps_client.close()


# ── candlesticks ──────────────────────────────────────────────────────────────


class TestCandlesticks:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/BTC-PERP/candlesticks").mock(
            return_value=httpx.Response(
                200, json={"ticker": "BTC-PERP", "candlesticks": [_candle_dict()]}
            )
        )
        candles = perps_client.markets.candlesticks(
            "BTC-PERP", start_ts=1_700_000_000, end_ts=1_700_003_600, period_interval=1
        )
        assert len(candles) == 1
        c = candles[0]
        assert isinstance(c, MarginMarketCandlestick)
        assert c.end_period_ts == 1_700_000_060
        assert isinstance(c.bid, BidAskDistributionHistorical)
        assert c.bid.open == Decimal("0.5500")
        assert c.bid.close == Decimal("0.5550")
        assert c.ask.high == Decimal("0.5800")
        assert isinstance(c.price, PriceDistributionHistorical)
        assert c.price.open == Decimal("0.5600")
        assert c.price.mean == Decimal("0.5620")
        assert c.volume == Decimal("100.00")
        assert isinstance(c.volume, Decimal)
        assert c.open_interest == Decimal("500.00")

    @respx.mock
    def test_all_null_trade_prices(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/BTC-PERP/candlesticks").mock(
            return_value=httpx.Response(
                200,
                json={
                    "ticker": "BTC-PERP",
                    "candlesticks": [
                        _candle_dict(
                            price={
                                "open": None,
                                "high": None,
                                "low": None,
                                "close": None,
                                "mean": None,
                                "previous": None,
                            }
                        )
                    ],
                },
            )
        )
        c = perps_client.markets.candlesticks(
            "BTC-PERP", start_ts=1, end_ts=2, period_interval=60
        )[0]
        assert c.price.open is None
        assert c.price.close is None
        assert c.price.mean is None
        assert c.price.previous is None
        # bid/ask OHLC are still required + present.
        assert c.bid.open == Decimal("0.5500")

    @respx.mock
    def test_required_and_optional_params(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/markets/BTC-PERP/candlesticks").mock(
            return_value=httpx.Response(200, json={"ticker": "BTC-PERP", "candlesticks": []})
        )
        perps_client.markets.candlesticks(
            "BTC-PERP",
            start_ts=1_700_000_000,
            end_ts=1_700_003_600,
            period_interval=1440,
            include_latest_before_start=True,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["start_ts"] == "1700000000"
        assert params["end_ts"] == "1700003600"
        assert params["period_interval"] == "1440"
        assert params["include_latest_before_start"] == "true"

    @respx.mock
    def test_include_latest_omitted_by_default(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/markets/BTC-PERP/candlesticks").mock(
            return_value=httpx.Response(200, json={"ticker": "BTC-PERP", "candlesticks": []})
        )
        perps_client.markets.candlesticks(
            "BTC-PERP", start_ts=1, end_ts=2, period_interval=1
        )
        assert "include_latest_before_start" not in dict(route.calls[0].request.url.params)

    @respx.mock
    def test_not_found_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/NOPE/candlesticks").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(KalshiNotFoundError):
            perps_client.markets.candlesticks("NOPE", start_ts=1, end_ts=2, period_interval=1)

    @respx.mock
    def test_invalid_period_interval_server_rejected(self, perps_client: PerpsClient) -> None:
        # The client passes period_interval through; the server rejects bad
        # values with a 400 which surfaces as a mapped SDK error.
        respx.get(f"{BASE}/margin/markets/BTC-PERP/candlesticks").mock(
            return_value=httpx.Response(400, json={"error": {"code": "invalid_parameter"}})
        )
        with pytest.raises(Exception):  # noqa: B017 — mapped SDK validation error
            perps_client.markets.candlesticks(
                "BTC-PERP", start_ts=1, end_ts=2, period_interval=5
            )

    @respx.mock
    async def test_async(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/BTC-PERP/candlesticks").mock(
            return_value=httpx.Response(
                200, json={"ticker": "BTC-PERP", "candlesticks": [_candle_dict()]}
            )
        )
        candles = await async_perps_client.markets.candlesticks(
            "BTC-PERP", start_ts=1, end_ts=2, period_interval=1
        )
        assert candles[0].price.mean == Decimal("0.5620")
        await async_perps_client.close()
