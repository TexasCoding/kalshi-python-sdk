"""Series resource — list, get, fee changes, event candlesticks, forecast."""

from __future__ import annotations

import builtins
from typing import Any

from kalshi.models.series import (
    EventCandlesticks,
    ForecastPercentilesPoint,
    Series,
    SeriesFeeChange,
)
from kalshi.resources._base import AsyncResource, SyncResource, _bool_param, _params

# Shared param builders (issue #46).


def _list_series_params(
    *,
    category: str | None,
    tags: str | None,
    include_product_metadata: bool | None,
    include_volume: bool | None,
    min_updated_ts: int | None,
) -> dict[str, Any]:
    return _params(
        category=category,
        tags=tags,
        include_product_metadata=_bool_param(include_product_metadata),
        include_volume=_bool_param(include_volume),
        min_updated_ts=min_updated_ts,
    )


def _fee_changes_params(
    *,
    series_ticker: str | None,
    show_historical: bool | None,
) -> dict[str, Any]:
    return _params(
        series_ticker=series_ticker,
        show_historical=_bool_param(show_historical),
    )


def _event_candlesticks_params(
    *, start_ts: int, end_ts: int, period_interval: int,
) -> dict[str, Any]:
    return _params(
        start_ts=start_ts,
        end_ts=end_ts,
        period_interval=period_interval,
    )


def _forecast_history_params(
    *,
    percentiles: builtins.list[int],
    start_ts: int,
    end_ts: int,
    period_interval: int,
) -> dict[str, Any]:
    return _params(
        percentiles=percentiles,
        start_ts=start_ts,
        end_ts=end_ts,
        period_interval=period_interval,
    )


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
        params = _list_series_params(
            category=category, tags=tags,
            include_product_metadata=include_product_metadata,
            include_volume=include_volume,
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
            include_volume=_bool_param(include_volume),
        )
        data = self._get(f"/series/{series_ticker}", params=params)
        return Series.model_validate(data.get("series", data))

    def fee_changes(
        self,
        *,
        series_ticker: str | None = None,
        show_historical: bool | None = None,
    ) -> builtins.list[SeriesFeeChange]:
        params = _fee_changes_params(
            series_ticker=series_ticker, show_historical=show_historical,
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
        params = _event_candlesticks_params(
            start_ts=start_ts, end_ts=end_ts,
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
        params = _forecast_history_params(
            percentiles=percentiles,
            start_ts=start_ts, end_ts=end_ts,
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
        params = _list_series_params(
            category=category, tags=tags,
            include_product_metadata=include_product_metadata,
            include_volume=include_volume,
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
            include_volume=_bool_param(include_volume),
        )
        data = await self._get(f"/series/{series_ticker}", params=params)
        return Series.model_validate(data.get("series", data))

    async def fee_changes(
        self,
        *,
        series_ticker: str | None = None,
        show_historical: bool | None = None,
    ) -> builtins.list[SeriesFeeChange]:
        params = _fee_changes_params(
            series_ticker=series_ticker, show_historical=show_historical,
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
        params = _event_candlesticks_params(
            start_ts=start_ts, end_ts=end_ts,
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
        params = _forecast_history_params(
            percentiles=percentiles,
            start_ts=start_ts, end_ts=end_ts,
            period_interval=period_interval,
        )
        data = await self._get(
            f"/series/{series_ticker}/events/{ticker}/forecast_percentile_history",
            params=params,
        )
        raw = data.get("forecast_history", [])
        return [ForecastPercentilesPoint.model_validate(item) for item in raw]
