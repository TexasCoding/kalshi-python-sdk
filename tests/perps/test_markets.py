"""Tests for the perps markets resource (#390).

All five endpoints (``list`` / ``get`` / ``orderbook`` / ``bulk_orderbooks`` /
``candlesticks``) are public margin market data — the spec marks no
``security`` block on any of them, so an unauthenticated client must reach
the wire (no ``AuthRequiredError``).
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi.errors import KalshiError, KalshiNotFoundError, KalshiServerError
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.models.markets import (
    BidAskDistributionHistorical,
    MarginMarket,
    MarginMarketCandlestick,
    MarginMarketSchedule,
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
        "underlying_multiplier": "1",
        "tick_size": "0.0100",
        "fractional_trading_enabled": True,
        # Spec requires schedule; null means 24/7. Populated object used as the
        # happy-path default so nested field parsing is exercised.
        "schedule": {
            "is_open": True,
            "next_close_ts": 1_700_000_000,
            "next_open_ts": None,
        },
        "exchange_index": 0,
        "market_version": 1,
        "funding_deadband": 0.0,
        "funding_cap": 1.0,
        "funding_limit_unit": "percentage",
        "funding_invalid_premium_handling": "dampen",
        "halt_sources": [],
        "leverage_estimate": 2.5,
        "leverage_estimates": {"1000": 2.5, "10000": 2.0, "100000": 1.5},
        "long_leverage_estimates": {"1000": 2.4, "10000": 1.9},
        "short_leverage_estimates": {"1000": 2.6, "10000": 2.1},
        "price": "0.5600",
        "bid": "0.5500",
        "ask": "0.5700",
        "volume": "1000.00",
        "volume_notional_value_dollars": "560.0000",
        "volume_24h": "250.00",
        "volume_24h_notional_value_dollars": "140.0000",
        "open_interest": "500.00",
        "open_interest_notional_value_dollars": "280.0000",
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
        "volume_notional_value_dollars": "56.0000",
        "open_interest": "500.00",
        "open_interest_notional_value_dollars": "280.0000",
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
        assert m.underlying_multiplier == "1"
        assert m.tick_size == Decimal("0.0100")
        assert isinstance(m.tick_size, Decimal)
        assert m.leverage_estimate == Decimal("2.5")
        assert isinstance(m.leverage_estimate, Decimal)
        assert m.leverage_estimates == {
            "1000": Decimal("2.5"),
            "10000": Decimal("2.0"),
            "100000": Decimal("1.5"),
        }
        assert m.long_leverage_estimates == {
            "1000": Decimal("2.4"),
            "10000": Decimal("1.9"),
        }
        assert m.short_leverage_estimates == {
            "1000": Decimal("2.6"),
            "10000": Decimal("2.1"),
        }
        assert m.volume == Decimal("1000.00")
        assert m.bid_size is None
        assert m.ask_size is None
        assert m.volume_notional_value == Decimal("560.0000")
        assert m.volume_24h_notional_value == Decimal("140.0000")
        assert m.open_interest_notional_value == Decimal("280.0000")
        assert isinstance(m.volume_notional_value, Decimal)
        assert isinstance(m.schedule, MarginMarketSchedule)
        assert m.schedule.is_open is True
        assert m.schedule.next_close_ts == 1_700_000_000
        assert m.schedule.next_open_ts is None
        assert m.exchange_index == 0
        assert m.market_version == 1
        assert m.funding_deadband == Decimal("0.0")
        assert m.funding_cap == Decimal("1.0")
        assert m.funding_limit_unit == "percentage"
        assert m.funding_invalid_premium_handling == "dampen"
        assert m.halt_sources == []
        assert isinstance(m.funding_deadband, Decimal)
        assert isinstance(m.funding_cap, Decimal)

    @respx.mock
    def test_bid_ask_size_fp_parsed(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets").mock(
            return_value=httpx.Response(
                200,
                json={"markets": [_market_dict(bid_size_fp="10.00", ask_size_fp="12.50")]},
            )
        )
        m = perps_client.markets.list()[0]
        assert m.bid_size == Decimal("10.00")
        assert m.ask_size == Decimal("12.50")
        assert isinstance(m.bid_size, Decimal)
        assert isinstance(m.ask_size, Decimal)

    def test_bid_ask_size_accepts_bare_alias(self) -> None:
        m = MarginMarket.model_validate(_market_dict(bid_size="3.00", ask_size="4.00"))
        assert m.bid_size == Decimal("3.00")
        assert m.ask_size == Decimal("4.00")

    def test_bid_ask_size_omitted_when_missing(self) -> None:
        m = MarginMarket.model_validate(_market_dict())
        assert m.bid_size is None
        assert m.ask_size is None

    def test_funding_fields_required(self) -> None:
        for key in (
            "funding_deadband",
            "funding_cap",
            "funding_limit_unit",
            "funding_invalid_premium_handling",
        ):
            payload = _market_dict()
            del payload[key]
            with pytest.raises(ValidationError):
                MarginMarket.model_validate(payload)

    def test_funding_invalid_premium_handling_parse(self) -> None:
        m = MarginMarket.model_validate(
            _market_dict(funding_invalid_premium_handling="exclude")
        )
        assert m.funding_invalid_premium_handling == "exclude"

    def test_funding_invalid_premium_handling_rejects_unknown(self) -> None:
        with pytest.raises(ValidationError):
            MarginMarket.model_validate(_market_dict(funding_invalid_premium_handling="skip"))

    def test_funding_limit_unit_dollar(self) -> None:
        m = MarginMarket.model_validate(
            _market_dict(funding_deadband=0.25, funding_cap=5.0, funding_limit_unit="dollar")
        )
        assert m.funding_deadband == Decimal("0.25")
        assert m.funding_cap == Decimal("5.0")
        assert m.funding_limit_unit == "dollar"

    def test_funding_limit_unit_rejects_unknown(self) -> None:
        with pytest.raises(ValidationError):
            MarginMarket.model_validate(_market_dict(funding_limit_unit="bps"))

    def test_halt_sources_optional(self) -> None:
        payload = _market_dict()
        del payload["halt_sources"]
        assert MarginMarket.model_validate(payload).halt_sources is None

    def test_halt_sources_parses(self) -> None:
        m = MarginMarket.model_validate(_market_dict(halt_sources=["corporate_action"]))
        assert m.halt_sources == ["corporate_action"]

    def test_halt_sources_empty_is_valid(self) -> None:
        m = MarginMarket.model_validate(_market_dict(halt_sources=[]))
        assert m.halt_sources == []

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
                            "underlying_multiplier": "1",
                            "tick_size": "0.0100",
                            "fractional_trading_enabled": False,
                            # required key present, null value = 24/7 market
                            "schedule": None,
                            "exchange_index": 0,
                            "market_version": 1,
                            "funding_deadband": 0.0,
                            "funding_cap": 1.0,
                            "funding_limit_unit": "percentage",
                            "funding_invalid_premium_handling": "dampen",
                            "halt_sources": ["initial_setup"],
                            "leverage_estimate": None,
                        }
                    ]
                },
            )
        )
        m = perps_client.markets.list()[0]
        assert m.schedule is None
        assert m.leverage_estimate is None
        assert m.price is None
        assert m.bid is None
        assert m.bid_size is None
        assert m.ask is None
        assert m.ask_size is None
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
    def test_missing_markets_raises_but_null_tolerated(self, perps_client: PerpsClient) -> None:
        # `markets` is spec-required: a MISSING key hard-fails (surfacing drift),
        # while a NULL array coerces to [] via NullableList (Kalshi's
        # empty-as-null convention; matches the prediction-API envelopes).
        route = respx.get(f"{BASE}/margin/markets")
        route.mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValidationError):
            perps_client.markets.list()
        route.mock(return_value=httpx.Response(200, json={"markets": None}))
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
        route = respx.get(f"{BASE}/margin/markets/NOPE").mock(return_value=httpx.Response(404))
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
            return_value=httpx.Response(200, json={"orderbook": {"bids": None, "asks": None}})
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
        respx.get(f"{BASE}/margin/markets/NOPE/orderbook").mock(return_value=httpx.Response(404))
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


# ── bulk orderbooks ───────────────────────────────────────────────────────────


_UNSET: object = object()


def _bulk_orderbook_item(
    ticker: str,
    *,
    bids: object = _UNSET,
    asks: object = _UNSET,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "orderbook": {
            "bids": [["0.1500", "100.00"]] if bids is _UNSET else bids,
            "asks": [["0.1600", "50.00"]] if asks is _UNSET else asks,
        },
    }


class TestBulkOrderbooks:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/markets/orderbooks").mock(
            return_value=httpx.Response(
                200,
                json={
                    "orderbooks": [
                        _bulk_orderbook_item("BTC-PERP"),
                        _bulk_orderbook_item(
                            "ETH-PERP",
                            bids=[["0.2500", "10.00"]],
                            asks=[],
                        ),
                    ]
                },
            )
        )
        books = perps_client.markets.bulk_orderbooks(tickers=["BTC-PERP", "ETH-PERP"])
        assert len(books) == 2
        assert all(isinstance(b, MarginOrderbook) for b in books)
        assert books[0].ticker == "BTC-PERP"
        assert books[0].bids[0].price == Decimal("0.15")
        assert books[0].bids[0].quantity == Decimal("100.00")
        assert books[0].asks[0].price == Decimal("0.16")
        assert books[1].ticker == "ETH-PERP"
        assert books[1].bids[0].price == Decimal("0.25")
        assert books[1].asks == []
        assert dict(route.calls[0].request.url.params)["tickers"] == "BTC-PERP,ETH-PERP"

    @respx.mock
    def test_not_found_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/orderbooks").mock(return_value=httpx.Response(404))
        with pytest.raises(KalshiNotFoundError):
            perps_client.markets.bulk_orderbooks(tickers=["NOPE"])

    def test_rejects_empty_list(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            perps_client.markets.bulk_orderbooks(tickers=[])

    def test_rejects_over_100(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValueError, match="at most 100"):
            perps_client.markets.bulk_orderbooks(tickers=[f"T-{i}" for i in range(101)])

    @respx.mock
    def test_missing_orderbooks_raises_but_null_tolerated(
        self, perps_client: PerpsClient
    ) -> None:
        route = respx.get(f"{BASE}/margin/markets/orderbooks")
        route.mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValidationError):
            perps_client.markets.bulk_orderbooks(tickers=["BTC-PERP"])
        route.mock(return_value=httpx.Response(200, json={"orderbooks": None}))
        assert perps_client.markets.bulk_orderbooks(tickers=["BTC-PERP"]) == []

    @respx.mock
    def test_item_missing_ticker_raises(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/orderbooks").mock(
            return_value=httpx.Response(
                200,
                json={"orderbooks": [{"orderbook": {"bids": [], "asks": []}}]},
            )
        )
        with pytest.raises(KalshiError, match="empty or missing 'ticker'"):
            perps_client.markets.bulk_orderbooks(tickers=["BTC-PERP"])

    @respx.mock
    def test_null_bids_asks(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/orderbooks").mock(
            return_value=httpx.Response(
                200,
                json={"orderbooks": [_bulk_orderbook_item("BTC-PERP", bids=None, asks=None)]},
            )
        )
        ob = perps_client.markets.bulk_orderbooks(tickers=["BTC-PERP"])[0]
        assert ob.bids == []
        assert ob.asks == []

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/orderbooks").mock(
            return_value=httpx.Response(
                200, json={"orderbooks": [_bulk_orderbook_item("BTC-PERP")]}
            )
        )
        books = await async_perps_client.markets.bulk_orderbooks(tickers=["BTC-PERP"])
        assert books[0].ticker == "BTC-PERP"
        assert books[0].bids[0].price == Decimal("0.15")
        await async_perps_client.close()

    @respx.mock
    async def test_async_not_found(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/orderbooks").mock(return_value=httpx.Response(404))
        with pytest.raises(KalshiNotFoundError):
            await async_perps_client.markets.bulk_orderbooks(tickers=["NOPE"])
        await async_perps_client.close()

    @respx.mock
    async def test_async_rejects_empty(self, async_perps_client: AsyncPerpsClient) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            await async_perps_client.markets.bulk_orderbooks(tickers=[])
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
        assert c.volume_notional_value == Decimal("56.0000")
        assert c.open_interest == Decimal("500.00")
        assert c.open_interest_notional_value == Decimal("280.0000")

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
        c = perps_client.markets.candlesticks("BTC-PERP", start_ts=1, end_ts=2, period_interval=60)[
            0
        ]
        assert c.price.open is None
        assert c.price.close is None
        assert c.price.mean is None
        assert c.price.previous is None
        # bid/ask OHLC are still required + present.
        assert c.bid.open == Decimal("0.5500")

    def test_notional_value_required_on_candlestick(self) -> None:
        # Spec lists both notional fields under `required`; the model enforces it
        # (unlike the live MarginTickerPayload, where they are optional).
        for missing in ("volume_notional_value_dollars", "open_interest_notional_value_dollars"):
            frame = _candle_dict()
            del frame[missing]
            with pytest.raises(ValidationError):
                MarginMarketCandlestick.model_validate(frame)

    @respx.mock
    def test_missing_ticker_or_candlesticks_raises(self, perps_client: PerpsClient) -> None:
        # #404: both `ticker` and `candlesticks` are spec-required on this
        # response — the envelope validates the previously-discarded `ticker`.
        route = respx.get(f"{BASE}/margin/markets/BTC-PERP/candlesticks")
        route.mock(return_value=httpx.Response(200, json={"candlesticks": []}))  # no ticker
        with pytest.raises(ValidationError):
            perps_client.markets.candlesticks("BTC-PERP", start_ts=1, end_ts=2, period_interval=1)
        route.mock(return_value=httpx.Response(200, json={"ticker": "BTC-PERP"}))  # no array
        with pytest.raises(ValidationError):
            perps_client.markets.candlesticks("BTC-PERP", start_ts=1, end_ts=2, period_interval=1)
        # A null candlesticks array coerces to [] (NullableList).
        route.mock(
            return_value=httpx.Response(200, json={"ticker": "BTC-PERP", "candlesticks": None})
        )
        assert (
            perps_client.markets.candlesticks("BTC-PERP", start_ts=1, end_ts=2, period_interval=1)
            == []
        )

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
        perps_client.markets.candlesticks("BTC-PERP", start_ts=1, end_ts=2, period_interval=1)
        assert "include_latest_before_start" not in dict(route.calls[0].request.url.params)

    @respx.mock
    def test_not_found_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/markets/NOPE/candlesticks").mock(return_value=httpx.Response(404))
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
            perps_client.markets.candlesticks("BTC-PERP", start_ts=1, end_ts=2, period_interval=5)

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
