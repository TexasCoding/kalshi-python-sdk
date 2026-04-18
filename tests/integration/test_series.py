"""Integration tests for SeriesResource."""

from __future__ import annotations

import time

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import KalshiNotFoundError, KalshiValidationError
from kalshi.models.series import (
    EventCandlesticks,
    ForecastPercentilesPoint,
    Series,
    SeriesFeeChange,
)
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register(
    "SeriesResource",
    [
        "list",
        "get",
        "fee_changes",
        "event_candlesticks",
        "forecast_percentile_history",
    ],
)


@pytest.fixture(scope="session")
def demo_series_ticker(sync_client: KalshiClient) -> str:
    """Return a series ticker that exists on the demo server."""
    items = sync_client.series.list()
    if not items:
        pytest.skip("No series available on demo server")
    return items[0].ticker


@pytest.mark.integration
class TestSeriesSync:
    def test_list(self, sync_client: KalshiClient) -> None:
        items = sync_client.series.list()
        assert isinstance(items, list)
        if items:
            assert isinstance(items[0], Series)
            assert_model_fields(items[0])
            assert items[0].ticker

    def test_get(self, sync_client: KalshiClient, demo_series_ticker: str) -> None:
        series = sync_client.series.get(demo_series_ticker)
        assert isinstance(series, Series)
        assert_model_fields(series)
        assert series.ticker == demo_series_ticker

    def test_fee_changes(self, sync_client: KalshiClient) -> None:
        changes = sync_client.series.fee_changes()
        assert isinstance(changes, list)
        for change in changes:
            assert isinstance(change, SeriesFeeChange)
            assert_model_fields(change)

    def test_event_candlesticks(
        self, sync_client: KalshiClient, demo_event_ticker: str
    ) -> None:
        event = sync_client.events.get(demo_event_ticker)
        if not event.series_ticker:
            pytest.skip("Demo event has no series_ticker")
        now = int(time.time())
        result = sync_client.series.event_candlesticks(
            event.series_ticker,
            demo_event_ticker,
            start_ts=now - 86400 * 7,
            end_ts=now,
            period_interval=60,
        )
        assert isinstance(result, EventCandlesticks)
        assert_model_fields(result)

    def test_forecast_percentile_history(
        self, sync_client: KalshiClient, demo_event_ticker: str
    ) -> None:
        """Auth-required. May return empty history for events without forecasts."""
        event = sync_client.events.get(demo_event_ticker)
        if not event.series_ticker:
            pytest.skip("Demo event has no series_ticker")
        now = int(time.time())
        try:
            points = sync_client.series.forecast_percentile_history(
                event.series_ticker,
                demo_event_ticker,
                percentiles=[10, 50, 90],
                start_ts=now - 86400 * 7,
                end_ts=now,
                period_interval=3600,
            )
        except (KalshiNotFoundError, KalshiValidationError) as e:
            pytest.skip(f"No forecast history for demo event: {e}")
        assert isinstance(points, list)
        for point in points:
            assert isinstance(point, ForecastPercentilesPoint)
            assert_model_fields(point)


@pytest.mark.integration
class TestSeriesAsync:
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        items = await async_client.series.list()
        assert isinstance(items, list)
        if items:
            assert isinstance(items[0], Series)
            assert_model_fields(items[0])

    async def test_get(
        self, async_client: AsyncKalshiClient, demo_series_ticker: str
    ) -> None:
        series = await async_client.series.get(demo_series_ticker)
        assert isinstance(series, Series)
        assert_model_fields(series)
        assert series.ticker == demo_series_ticker

    async def test_fee_changes(self, async_client: AsyncKalshiClient) -> None:
        changes = await async_client.series.fee_changes()
        assert isinstance(changes, list)
        for change in changes:
            assert isinstance(change, SeriesFeeChange)
            assert_model_fields(change)

    async def test_event_candlesticks(
        self, async_client: AsyncKalshiClient, demo_event_ticker: str
    ) -> None:
        event = await async_client.events.get(demo_event_ticker)
        if not event.series_ticker:
            pytest.skip("Demo event has no series_ticker")
        now = int(time.time())
        result = await async_client.series.event_candlesticks(
            event.series_ticker,
            demo_event_ticker,
            start_ts=now - 86400 * 7,
            end_ts=now,
            period_interval=60,
        )
        assert isinstance(result, EventCandlesticks)
        assert_model_fields(result)

    async def test_forecast_percentile_history(
        self, async_client: AsyncKalshiClient, demo_event_ticker: str
    ) -> None:
        event = await async_client.events.get(demo_event_ticker)
        if not event.series_ticker:
            pytest.skip("Demo event has no series_ticker")
        now = int(time.time())
        try:
            points = await async_client.series.forecast_percentile_history(
                event.series_ticker,
                demo_event_ticker,
                percentiles=[10, 50, 90],
                start_ts=now - 86400 * 7,
                end_ts=now,
                period_interval=3600,
            )
        except (KalshiNotFoundError, KalshiValidationError) as e:
            pytest.skip(f"No forecast history for demo event: {e}")
        assert isinstance(points, list)
        for point in points:
            assert isinstance(point, ForecastPercentilesPoint)
            assert_model_fields(point)
