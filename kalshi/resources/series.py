"""Series resource — list, get, fee changes, event candlesticks, forecast."""

from __future__ import annotations

import builtins

from kalshi.models.series import (
    EventCandlesticks,
    ForecastPercentilesPoint,
    Series,
    SeriesFeeChange,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


class SeriesResource(SyncResource):
    """Sync series API."""

    def list(
        self,
        *,
        category: str | None = None,
        tags: str | None = None,
        include_product_metadata: bool | None = None,
        include_volume: bool | None = None,
        min_updated_ts: int | None = None,
    ) -> builtins.list[Series]:
        params = _params(
            category=category,
            tags=tags,
            include_product_metadata="true" if include_product_metadata else None,
            include_volume="true" if include_volume else None,
            min_updated_ts=min_updated_ts,
        )
        data = self._get("/series", params=params)
        raw = data.get("series", [])
        return [Series.model_validate(item) for item in raw]

    def get(
        self,
        series_ticker: str,
        *,
        include_volume: bool | None = None,
    ) -> Series:
        params = _params(
            include_volume="true" if include_volume else None,
        )
        data = self._get(f"/series/{series_ticker}", params=params)
        return Series.model_validate(data.get("series", data))

    def fee_changes(
        self,
        *,
        series_ticker: str | None = None,
        show_historical: bool | None = None,
    ) -> builtins.list[SeriesFeeChange]:
        params = _params(
            series_ticker=series_ticker,
            show_historical="true" if show_historical else None,
        )
        data = self._get("/series/fee_changes", params=params)
        raw = data.get("series_fee_change_arr", [])
        return [SeriesFeeChange.model_validate(item) for item in raw]

    def event_candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> EventCandlesticks:
        params = _params(
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
        )
        data = self._get(
            f"/series/{series_ticker}/events/{ticker}/candlesticks",
            params=params,
        )
        return EventCandlesticks.model_validate(data)

    def forecast_percentile_history(
        self,
        series_ticker: str,
        ticker: str,
        *,
        percentiles: builtins.list[int],
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> builtins.list[ForecastPercentilesPoint]:
        self._require_auth()
        params = _params(
            percentiles=percentiles,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
        )
        data = self._get(
            f"/series/{series_ticker}/events/{ticker}/forecast_percentile_history",
            params=params,
        )
        raw = data.get("forecast_history", [])
        return [ForecastPercentilesPoint.model_validate(item) for item in raw]


class AsyncSeriesResource(AsyncResource):
    """Async series API."""

    async def list(
        self,
        *,
        category: str | None = None,
        tags: str | None = None,
        include_product_metadata: bool | None = None,
        include_volume: bool | None = None,
        min_updated_ts: int | None = None,
    ) -> builtins.list[Series]:
        params = _params(
            category=category,
            tags=tags,
            include_product_metadata="true" if include_product_metadata else None,
            include_volume="true" if include_volume else None,
            min_updated_ts=min_updated_ts,
        )
        data = await self._get("/series", params=params)
        raw = data.get("series", [])
        return [Series.model_validate(item) for item in raw]

    async def get(
        self,
        series_ticker: str,
        *,
        include_volume: bool | None = None,
    ) -> Series:
        params = _params(
            include_volume="true" if include_volume else None,
        )
        data = await self._get(f"/series/{series_ticker}", params=params)
        return Series.model_validate(data.get("series", data))

    async def fee_changes(
        self,
        *,
        series_ticker: str | None = None,
        show_historical: bool | None = None,
    ) -> builtins.list[SeriesFeeChange]:
        params = _params(
            series_ticker=series_ticker,
            show_historical="true" if show_historical else None,
        )
        data = await self._get("/series/fee_changes", params=params)
        raw = data.get("series_fee_change_arr", [])
        return [SeriesFeeChange.model_validate(item) for item in raw]

    async def event_candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> EventCandlesticks:
        params = _params(
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
        )
        data = await self._get(
            f"/series/{series_ticker}/events/{ticker}/candlesticks",
            params=params,
        )
        return EventCandlesticks.model_validate(data)

    async def forecast_percentile_history(
        self,
        series_ticker: str,
        ticker: str,
        *,
        percentiles: builtins.list[int],
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> builtins.list[ForecastPercentilesPoint]:
        self._require_auth()
        params = _params(
            percentiles=percentiles,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
        )
        data = await self._get(
            f"/series/{series_ticker}/events/{ticker}/forecast_percentile_history",
            params=params,
        )
        raw = data.get("forecast_history", [])
        return [ForecastPercentilesPoint.model_validate(item) for item in raw]
