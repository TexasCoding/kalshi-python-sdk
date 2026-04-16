"""Tests for kalshi.resources.series — Series resource."""

from __future__ import annotations

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import AuthRequiredError
from kalshi.resources.series import AsyncSeriesResource, SeriesResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def series_resource(test_auth: KalshiAuth, config: KalshiConfig) -> SeriesResource:
    return SeriesResource(SyncTransport(test_auth, config))


@pytest.fixture
def unauth_series(config: KalshiConfig) -> SeriesResource:
    return SeriesResource(SyncTransport(None, config))


BASE = "https://test.kalshi.com/trade-api/v2"

SERIES_PAYLOAD = {
    "ticker": "ECON-GDP",
    "frequency": "quarterly",
    "title": "GDP Report",
    "category": "Economics",
    "tags": ["gdp"],
    "settlement_sources": [],
    "contract_url": "",
    "contract_terms_url": "",
    "fee_type": "quadratic",
    "fee_multiplier": 1.0,
    "additional_prohibitions": [],
    "volume_fp": "500.00",
}


class TestSeriesList:
    @respx.mock
    def test_list_returns_series(self, series_resource: SeriesResource) -> None:
        respx.get(f"{BASE}/series").mock(
            return_value=httpx.Response(200, json={"series": [SERIES_PAYLOAD]})
        )
        result = series_resource.list()
        assert len(result) == 1
        assert result[0].ticker == "ECON-GDP"

    @respx.mock
    def test_list_empty(self, series_resource: SeriesResource) -> None:
        respx.get(f"{BASE}/series").mock(
            return_value=httpx.Response(200, json={"series": []})
        )
        result = series_resource.list()
        assert result == []

    @respx.mock
    def test_list_passes_filters(self, series_resource: SeriesResource) -> None:
        route = respx.get(f"{BASE}/series").mock(
            return_value=httpx.Response(200, json={"series": []})
        )
        series_resource.list(category="Economics", include_volume=True, min_updated_ts=1000)
        params = dict(route.calls[0].request.url.params)
        assert params["category"] == "Economics"
        assert params["include_volume"] == "true"
        assert params["min_updated_ts"] == "1000"


class TestSeriesGet:
    @respx.mock
    def test_get_by_ticker(self, series_resource: SeriesResource) -> None:
        respx.get(f"{BASE}/series/ECON-GDP").mock(
            return_value=httpx.Response(200, json={"series": SERIES_PAYLOAD})
        )
        s = series_resource.get("ECON-GDP")
        assert s.ticker == "ECON-GDP"

    @respx.mock
    def test_get_with_include_volume(self, series_resource: SeriesResource) -> None:
        route = respx.get(f"{BASE}/series/ECON-GDP").mock(
            return_value=httpx.Response(200, json={"series": SERIES_PAYLOAD})
        )
        series_resource.get("ECON-GDP", include_volume=True)
        params = dict(route.calls[0].request.url.params)
        assert params["include_volume"] == "true"


class TestSeriesFeeChanges:
    @respx.mock
    def test_fee_changes(self, series_resource: SeriesResource) -> None:
        respx.get(f"{BASE}/series/fee_changes").mock(
            return_value=httpx.Response(200, json={
                "series_fee_change_arr": [{
                    "id": "fc-1",
                    "series_ticker": "ECON-GDP",
                    "fee_type": "flat",
                    "fee_multiplier": 0.5,
                    "scheduled_ts": "2026-05-01T00:00:00Z",
                }]
            })
        )
        result = series_resource.fee_changes()
        assert len(result) == 1
        assert result[0].id == "fc-1"

    @respx.mock
    def test_fee_changes_with_filters(self, series_resource: SeriesResource) -> None:
        route = respx.get(f"{BASE}/series/fee_changes").mock(
            return_value=httpx.Response(200, json={"series_fee_change_arr": []})
        )
        series_resource.fee_changes(series_ticker="ECON-GDP", show_historical=True)
        params = dict(route.calls[0].request.url.params)
        assert params["series_ticker"] == "ECON-GDP"
        assert params["show_historical"] == "true"


class TestSeriesEventCandlesticks:
    @respx.mock
    def test_event_candlesticks(self, series_resource: SeriesResource) -> None:
        respx.get(f"{BASE}/series/SER/events/EVT/candlesticks").mock(
            return_value=httpx.Response(200, json={
                "market_tickers": ["MKT-A"],
                "market_candlesticks": [[{"end_period_ts": 1000, "volume_fp": "10.00"}]],
                "adjusted_end_ts": 2000,
            })
        )
        ec = series_resource.event_candlesticks(
            "SER", "EVT", start_ts=100, end_ts=200, period_interval=60,
        )
        assert ec.market_tickers == ["MKT-A"]
        assert len(ec.market_candlesticks) == 1


class TestSeriesForecastPercentileHistory:
    @respx.mock
    def test_happy_path(self, series_resource: SeriesResource) -> None:
        respx.get(f"{BASE}/series/SER/events/EVT/forecast_percentile_history").mock(
            return_value=httpx.Response(200, json={
                "forecast_history": [{
                    "event_ticker": "EVT",
                    "end_period_ts": 12345,
                    "period_interval": 60,
                    "percentile_points": [{
                        "percentile": 5000,
                        "raw_numerical_forecast": 3.0,
                        "numerical_forecast": 3.0,
                        "formatted_forecast": "3.0%",
                    }],
                }]
            })
        )
        result = series_resource.forecast_percentile_history(
            "SER", "EVT", percentiles=[5000], start_ts=100, end_ts=200, period_interval=60,
        )
        assert len(result) == 1
        assert result[0].percentile_points[0].percentile == 5000

    def test_auth_guard(self, unauth_series: SeriesResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_series.forecast_percentile_history(
                "SER", "EVT", percentiles=[5000], start_ts=100, end_ts=200, period_interval=60,
            )


class TestAsyncSeriesResource:
    @pytest.fixture
    def async_series(self, test_auth: KalshiAuth, config: KalshiConfig) -> AsyncSeriesResource:
        return AsyncSeriesResource(AsyncTransport(test_auth, config))

    @pytest.fixture
    def unauth_async_series(self, config: KalshiConfig) -> AsyncSeriesResource:
        return AsyncSeriesResource(AsyncTransport(None, config))

    @respx.mock
    @pytest.mark.asyncio
    async def test_list(self, async_series: AsyncSeriesResource) -> None:
        respx.get(f"{BASE}/series").mock(
            return_value=httpx.Response(200, json={"series": [SERIES_PAYLOAD]})
        )
        result = await async_series.list()
        assert len(result) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_get(self, async_series: AsyncSeriesResource) -> None:
        respx.get(f"{BASE}/series/ECON-GDP").mock(
            return_value=httpx.Response(200, json={"series": SERIES_PAYLOAD})
        )
        s = await async_series.get("ECON-GDP")
        assert s.ticker == "ECON-GDP"

    @respx.mock
    @pytest.mark.asyncio
    async def test_fee_changes(self, async_series: AsyncSeriesResource) -> None:
        respx.get(f"{BASE}/series/fee_changes").mock(
            return_value=httpx.Response(200, json={"series_fee_change_arr": []})
        )
        result = await async_series.fee_changes()
        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_event_candlesticks(self, async_series: AsyncSeriesResource) -> None:
        respx.get(f"{BASE}/series/SER/events/EVT/candlesticks").mock(
            return_value=httpx.Response(200, json={
                "market_tickers": [],
                "market_candlesticks": [],
                "adjusted_end_ts": 0,
            })
        )
        ec = await async_series.event_candlesticks(
            "SER", "EVT", start_ts=0, end_ts=1, period_interval=1,
        )
        assert ec.market_tickers == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_forecast_percentile_history(self, async_series: AsyncSeriesResource) -> None:
        respx.get(f"{BASE}/series/SER/events/EVT/forecast_percentile_history").mock(
            return_value=httpx.Response(200, json={"forecast_history": []})
        )
        result = await async_series.forecast_percentile_history(
            "SER", "EVT", percentiles=[5000], start_ts=0, end_ts=1, period_interval=60,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_forecast_auth_guard(self, unauth_async_series: AsyncSeriesResource) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_series.forecast_percentile_history(
                "SER", "EVT", percentiles=[5000], start_ts=0, end_ts=1, period_interval=60,
            )
