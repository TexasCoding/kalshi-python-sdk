"""Tests for kalshi.models.series — Series model validation."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from kalshi.models.series import (
    EventCandlesticks,
    ForecastPercentilesPoint,
    Series,
    SeriesFeeChange,
)


class TestSeriesModel:
    def test_parse_with_volume_fp(self) -> None:
        s = Series.model_validate({
            "ticker": "ECON-GDP",
            "frequency": "quarterly",
            "title": "GDP Report",
            "category": "Economics",
            "tags": ["gdp", "economy"],
            "settlement_sources": [{"name": "BEA", "url": "https://bea.gov"}],
            "contract_url": "https://kalshi.com/contracts/econ-gdp",
            "contract_terms_url": "https://kalshi.com/terms/econ-gdp",
            "fee_type": "quadratic",
            "fee_multiplier": 1.0,
            "additional_prohibitions": [],
            "volume_fp": "123456.00",
        })
        assert s.ticker == "ECON-GDP"
        assert s.volume == Decimal("123456.00")
        assert s.fee_type == "quadratic"

    def test_parse_with_volume_alias(self) -> None:
        s = Series.model_validate({
            "ticker": "T",
            "frequency": "daily",
            "title": "T",
            "category": "T",
            "tags": [],
            "settlement_sources": [],
            "contract_url": "",
            "contract_terms_url": "",
            "fee_type": "flat",
            "fee_multiplier": 0.5,
            "additional_prohibitions": [],
            "volume": "99.00",
        })
        assert s.volume == Decimal("99.00")

    def test_extra_fields_allowed(self) -> None:
        s = Series.model_validate({
            "ticker": "T",
            "frequency": "daily",
            "title": "T",
            "category": "T",
            "tags": [],
            "settlement_sources": [],
            "contract_url": "",
            "contract_terms_url": "",
            "fee_type": "flat",
            "fee_multiplier": 0.5,
            "additional_prohibitions": [],
            "unknown_future_field": "hello",
        })
        assert s.ticker == "T"

    def test_volume_none_when_missing(self) -> None:
        s = Series.model_validate({
            "ticker": "T",
            "frequency": "daily",
            "title": "T",
            "category": "T",
            "tags": [],
            "settlement_sources": [],
            "contract_url": "",
            "contract_terms_url": "",
            "fee_type": "flat",
            "fee_multiplier": 0.5,
            "additional_prohibitions": [],
        })
        assert s.volume is None


class TestSeriesNullableList:
    """Guard the NullableList[T] coercion on Series list fields.

    The Kalshi demo API has been observed returning JSON null for tags,
    settlement_sources, and additional_prohibitions, even though the spec
    declares them as required arrays. NullableList[T] coerces null -> [].
    """

    def _base_payload(self) -> dict[str, Any]:
        return {
            "ticker": "T",
            "frequency": "daily",
            "title": "T",
            "category": "T",
            "contract_url": "",
            "contract_terms_url": "",
            "fee_type": "flat",
            "fee_multiplier": 0.5,
        }

    def test_tags_none_coerced_to_empty_list(self) -> None:
        payload = {**self._base_payload(), "tags": None,
                   "settlement_sources": [], "additional_prohibitions": []}
        s = Series.model_validate(payload)
        assert s.tags == []

    def test_settlement_sources_none_coerced(self) -> None:
        payload = {**self._base_payload(), "tags": [],
                   "settlement_sources": None, "additional_prohibitions": []}
        s = Series.model_validate(payload)
        assert s.settlement_sources == []

    def test_additional_prohibitions_none_coerced(self) -> None:
        payload = {**self._base_payload(), "tags": [],
                   "settlement_sources": [], "additional_prohibitions": None}
        s = Series.model_validate(payload)
        assert s.additional_prohibitions == []

    def test_all_three_none_together(self) -> None:
        payload = {**self._base_payload(), "tags": None,
                   "settlement_sources": None, "additional_prohibitions": None}
        s = Series.model_validate(payload)
        assert s.tags == []
        assert s.settlement_sources == []
        assert s.additional_prohibitions == []

    def test_populated_list_passes_through(self) -> None:
        payload = {**self._base_payload(), "tags": ["a", "b"],
                   "settlement_sources": [{"name": "BEA"}],
                   "additional_prohibitions": ["nope"]}
        s = Series.model_validate(payload)
        assert s.tags == ["a", "b"]
        assert len(s.settlement_sources) == 1
        assert s.additional_prohibitions == ["nope"]


class TestEventCandlesticksNullableList:
    def test_null_market_tickers_coerced(self) -> None:
        ec = EventCandlesticks.model_validate({
            "market_tickers": None,
            "market_candlesticks": [],
            "adjusted_end_ts": 0,
        })
        assert ec.market_tickers == []

    def test_null_market_candlesticks_coerced(self) -> None:
        ec = EventCandlesticks.model_validate({
            "market_tickers": [],
            "market_candlesticks": None,
            "adjusted_end_ts": 0,
        })
        assert ec.market_candlesticks == []


class TestForecastPercentilesPointNullableList:
    def test_null_percentile_points_coerced(self) -> None:
        fp = ForecastPercentilesPoint.model_validate({
            "event_ticker": "EVT-1",
            "end_period_ts": 12345,
            "period_interval": 60,
            "percentile_points": None,
        })
        assert fp.percentile_points == []


class TestSeriesFeeChangeModel:
    def test_parse(self) -> None:
        fc = SeriesFeeChange.model_validate({
            "id": "fc-1",
            "series_ticker": "ECON-GDP",
            "fee_type": "quadratic_with_maker_fees",
            "fee_multiplier": 1.5,
            "scheduled_ts": "2026-05-01T00:00:00Z",
        })
        assert fc.id == "fc-1"
        assert fc.fee_type == "quadratic_with_maker_fees"
        assert fc.scheduled_ts is not None


class TestEventCandlesticksModel:
    def test_parse_nested_arrays(self) -> None:
        ec = EventCandlesticks.model_validate({
            "market_tickers": ["MKT-A", "MKT-B"],
            "market_candlesticks": [
                [{"end_period_ts": 1000, "volume_fp": "50.00"}],
                [{"end_period_ts": 1000, "volume_fp": "30.00"}, {"end_period_ts": 2000}],
            ],
            "adjusted_end_ts": 3000,
        })
        assert ec.market_tickers == ["MKT-A", "MKT-B"]
        assert len(ec.market_candlesticks) == 2
        assert len(ec.market_candlesticks[0]) == 1
        assert len(ec.market_candlesticks[1]) == 2
        assert ec.adjusted_end_ts == 3000

    def test_empty_candlesticks(self) -> None:
        ec = EventCandlesticks.model_validate({
            "market_tickers": [],
            "market_candlesticks": [],
            "adjusted_end_ts": 0,
        })
        assert ec.market_tickers == []
        assert ec.market_candlesticks == []


class TestForecastPercentilesPointModel:
    def test_parse_with_percentile_points(self) -> None:
        fp = ForecastPercentilesPoint.model_validate({
            "event_ticker": "EVT-1",
            "end_period_ts": 12345,
            "period_interval": 60,
            "percentile_points": [
                {
                    "percentile": 2500,
                    "raw_numerical_forecast": 3.14,
                    "numerical_forecast": 3.1,
                    "formatted_forecast": "3.1%",
                },
                {
                    "percentile": 7500,
                    "raw_numerical_forecast": 5.5,
                    "numerical_forecast": 5.5,
                    "formatted_forecast": "5.5%",
                },
            ],
        })
        assert fp.event_ticker == "EVT-1"
        assert len(fp.percentile_points) == 2
        assert fp.percentile_points[0].percentile == 2500
        assert fp.percentile_points[1].formatted_forecast == "5.5%"
