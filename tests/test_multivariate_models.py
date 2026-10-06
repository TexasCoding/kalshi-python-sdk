"""Tests for kalshi.models.multivariate — Multivariate model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kalshi.models.multivariate import (
    CreateMarketResponse,
    MultivariateEventCollection,
    TickerPair,
)
from tests._model_fixtures import market_dict, multivariate_event_collection_dict


class TestMultivariateEventCollectionModel:
    def test_parse_full(self) -> None:
        c = MultivariateEventCollection.model_validate(
            {
                **multivariate_event_collection_dict(
                    collection_ticker="MVC-1",
                    series_ticker="SER-1",
                    title="Test Collection",
                    description="A test multivariate collection",
                    open_date="2026-01-01T00:00:00Z",
                    close_date="2026-12-31T23:59:59Z",
                    is_ordered=True,
                    size_min=2,
                    size_max=10,
                    functional_description="Pick 2-10 outcomes",
                ),
                "associated_events": [
                    {
                        "ticker": "EVT-A",
                        "is_yes_only": True,
                        "size_max": 10,
                        "size_min": 2,
                        "active_quoters": ["q1"],
                    },
                    {
                        "ticker": "EVT-B",
                        "is_yes_only": False,
                        "size_max": None,
                        "size_min": None,
                        "active_quoters": [],
                    },
                ],
                "associated_event_tickers": ["EVT-A", "EVT-B"],
                "is_single_market_per_event": True,
                "is_all_yes": False,
            }
        )
        assert c.collection_ticker == "MVC-1"
        assert len(c.associated_events) == 2
        assert c.associated_events[0].ticker == "EVT-A"
        assert c.associated_events[0].is_yes_only is True
        assert c.is_ordered is True
        assert c.size_min == 2
        assert c.price_level_structure == "binary"
        assert c.price_ranges == []

    def test_extra_fields_allowed(self) -> None:
        c = MultivariateEventCollection.model_validate(
            {
                **multivariate_event_collection_dict(
                    collection_ticker="T",
                    series_ticker="T",
                    title="T",
                    description="",
                    open_date="2026-01-01T00:00:00Z",
                    close_date="2026-01-02T00:00:00Z",
                    associated_events=[],
                    is_ordered=False,
                    size_min=1,
                    size_max=1,
                    functional_description="",
                ),
                "brand_new_field": 42,
            }
        )
        assert c.collection_ticker == "T"

    def test_parses_price_level_structure_and_price_ranges(self) -> None:
        c = MultivariateEventCollection.model_validate(
            multivariate_event_collection_dict(
                collection_ticker="MVC-1",
                price_level_structure="linear_cent",
                price_ranges=[
                    {"start": "0.01", "end": "0.99", "step": "0.01"},
                ],
            )
        )
        assert c.price_level_structure == "linear_cent"
        assert c.price_ranges is not None
        assert c.price_ranges[0]["step"] == "0.01"

    def test_missing_price_level_structure_raises(self) -> None:
        payload = multivariate_event_collection_dict()
        del payload["price_level_structure"]
        with pytest.raises(ValidationError):
            MultivariateEventCollection.model_validate(payload)

    def test_missing_price_ranges_raises(self) -> None:
        payload = multivariate_event_collection_dict()
        del payload["price_ranges"]
        with pytest.raises(ValidationError):
            MultivariateEventCollection.model_validate(payload)

    def test_null_price_ranges_coerces_to_empty(self) -> None:
        c = MultivariateEventCollection.model_validate(
            multivariate_event_collection_dict(price_ranges=None)
        )
        assert c.price_ranges == []


class TestTickerPairModel:
    def test_parse_and_serialize(self) -> None:
        tp = TickerPair.model_validate(
            {
                "market_ticker": "MKT-1",
                "event_ticker": "EVT-1",
                "side": "yes",
            }
        )
        assert tp.market_ticker == "MKT-1"
        assert tp.side == "yes"

        d = tp.model_dump()
        assert d["market_ticker"] == "MKT-1"
        assert d["side"] == "yes"


class TestCreateMarketResponseModel:
    def test_with_market(self) -> None:
        r = CreateMarketResponse.model_validate(
            {
                "event_ticker": "EVT-1",
                "market_ticker": "MKT-1",
                "market": market_dict(ticker="MKT-1", status="open"),
            }
        )
        assert r.market_ticker == "MKT-1"
        assert r.market is not None
        assert r.market.ticker == "MKT-1"

    def test_without_market(self) -> None:
        r = CreateMarketResponse.model_validate(
            {
                "event_ticker": "EVT-1",
                "market_ticker": "MKT-1",
            }
        )
        assert r.market is None


