"""Tests for kalshi.models.series — Series model validation."""

from __future__ import annotations

from decimal import Decimal

from kalshi.models.series import (
    EventCandlesticks,
    ForecastPercentilesPoint,
    PercentilePoint,
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
