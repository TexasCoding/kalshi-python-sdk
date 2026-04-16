"""Tests for kalshi.models.multivariate — Multivariate model validation."""

from __future__ import annotations

from kalshi.models.multivariate import (
    CreateMarketResponse,
    LookupPoint,
    LookupTickersResponse,
    MultivariateEventCollection,
    TickerPair,
)


class TestMultivariateEventCollectionModel:
    def test_parse_full(self) -> None:
        c = MultivariateEventCollection.model_validate({
            "collection_ticker": "MVC-1",
            "series_ticker": "SER-1",
            "title": "Test Collection",
            "description": "A test multivariate collection",
            "open_date": "2026-01-01T00:00:00Z",
            "close_date": "2026-12-31T23:59:59Z",
            "associated_events": [
                {
                    "ticker": "EVT-A", "is_yes_only": True,
                    "size_max": 10, "size_min": 2, "active_quoters": ["q1"],
                },
                {
                    "ticker": "EVT-B", "is_yes_only": False,
                    "size_max": None, "size_min": None, "active_quoters": [],
                },
            ],
            "associated_event_tickers": ["EVT-A", "EVT-B"],
            "is_ordered": True,
            "is_single_market_per_event": True,
            "is_all_yes": False,
            "size_min": 2,
            "size_max": 10,
            "functional_description": "Pick 2-10 outcomes",
        })
        assert c.collection_ticker == "MVC-1"
        assert len(c.associated_events) == 2
        assert c.associated_events[0].ticker == "EVT-A"
        assert c.associated_events[0].is_yes_only is True
        assert c.is_ordered is True
        assert c.size_min == 2

    def test_extra_fields_allowed(self) -> None:
        c = MultivariateEventCollection.model_validate({
            "collection_ticker": "T",
            "series_ticker": "T",
            "title": "T",
            "description": "",
            "open_date": "2026-01-01T00:00:00Z",
            "close_date": "2026-01-02T00:00:00Z",
            "associated_events": [],
            "is_ordered": False,
            "size_min": 1,
            "size_max": 1,
            "functional_description": "",
            "brand_new_field": 42,
        })
        assert c.collection_ticker == "T"


class TestTickerPairModel:
    def test_parse_and_serialize(self) -> None:
        tp = TickerPair.model_validate({
            "market_ticker": "MKT-1",
            "event_ticker": "EVT-1",
            "side": "yes",
        })
        assert tp.market_ticker == "MKT-1"
        assert tp.side == "yes"

        d = tp.model_dump()
        assert d["market_ticker"] == "MKT-1"
        assert d["side"] == "yes"


class TestCreateMarketResponseModel:
    def test_with_market(self) -> None:
        r = CreateMarketResponse.model_validate({
            "event_ticker": "EVT-1",
            "market_ticker": "MKT-1",
            "market": {"ticker": "MKT-1", "status": "open"},
        })
        assert r.market_ticker == "MKT-1"
        assert r.market is not None
        assert r.market.ticker == "MKT-1"

    def test_without_market(self) -> None:
        r = CreateMarketResponse.model_validate({
            "event_ticker": "EVT-1",
            "market_ticker": "MKT-1",
        })
        assert r.market is None


class TestLookupTickersResponseModel:
    def test_parse(self) -> None:
        r = LookupTickersResponse.model_validate({
            "event_ticker": "EVT-1",
            "market_ticker": "MKT-1",
        })
        assert r.event_ticker == "EVT-1"


class TestLookupPointModel:
    def test_parse_with_selected_markets(self) -> None:
        lp = LookupPoint.model_validate({
            "event_ticker": "EVT-1",
            "market_ticker": "MKT-1",
            "selected_markets": [
                {"market_ticker": "M-A", "event_ticker": "E-A", "side": "yes"},
                {"market_ticker": "M-B", "event_ticker": "E-B", "side": "no"},
            ],
            "last_queried_ts": "2026-04-16T10:00:00Z",
        })
        assert len(lp.selected_markets) == 2
        assert lp.selected_markets[0].side == "yes"
        assert lp.last_queried_ts is not None
