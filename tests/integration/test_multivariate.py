"""Integration tests for MultivariateCollectionsResource."""

from __future__ import annotations

import pytest

from kalshi.client import KalshiClient
from kalshi.errors import (
    KalshiNotFoundError,
    KalshiValidationError,
)
from kalshi.models.common import Page
from kalshi.models.multivariate import (
    CreateMarketResponse,
    MultivariateEventCollection,
    TickerPair,
)
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register(
    "MultivariateCollectionsResource",
    [
        "list",
        "list_all",
        "get",
        "create_market",
    ],
)


@pytest.fixture(scope="session")
def demo_collection(sync_client: KalshiClient) -> MultivariateEventCollection:
    """Return an active multivariate collection from the demo server."""
    page = sync_client.multivariate_collections.list(limit=10)
    if not page.items:
        pytest.skip("No multivariate collections available on demo server")
    return page.items[0]


@pytest.fixture(scope="session")
def demo_collection_ticker(demo_collection: MultivariateEventCollection) -> str:
    return demo_collection.collection_ticker


def _build_ticker_pairs(
    collection: MultivariateEventCollection, sync_client: KalshiClient
) -> list[TickerPair]:
    """Construct TickerPairs from the collection's first two associated events.

    Returns an empty list if the collection cannot yield a valid pair —
    callers should skip in that case.
    """
    events = collection.associated_events[:2]
    if not events:
        return []
    pairs: list[TickerPair] = []
    for assoc in events:
        try:
            event = sync_client.events.get(assoc.ticker, with_nested_markets=True)
        except KalshiNotFoundError:
            continue
        if not event.markets:
            continue
        pairs.append(
            TickerPair(
                market_ticker=event.markets[0].ticker,
                event_ticker=event.event_ticker,
                side="yes",
            )
        )
    return pairs


@pytest.mark.integration
class TestMultivariateSync:
    def test_list(self, sync_client: KalshiClient) -> None:
        page = sync_client.multivariate_collections.list(limit=5)
        assert isinstance(page, Page)
        assert isinstance(page.items, list)
        if page.items:
            assert isinstance(page.items[0], MultivariateEventCollection)
            assert_model_fields(page.items[0])
            assert page.items[0].collection_ticker

    def test_list_all(self, sync_client: KalshiClient) -> None:
        count = 0
        for collection in sync_client.multivariate_collections.list_all(limit=2):
            assert isinstance(collection, MultivariateEventCollection)
            assert_model_fields(collection)
            count += 1  # noqa: SIM113
            if count >= 2:
                break

    def test_get(
        self, sync_client: KalshiClient, demo_collection_ticker: str
    ) -> None:
        collection = sync_client.multivariate_collections.get(demo_collection_ticker)
        assert isinstance(collection, MultivariateEventCollection)
        assert_model_fields(collection)
        assert collection.collection_ticker == demo_collection_ticker

    def test_create_market(
        self,
        sync_client: KalshiClient,
        demo_collection: MultivariateEventCollection,
    ) -> None:
        """POST endpoint — idempotent in practice (canonicalizes a combo)."""
        pairs = _build_ticker_pairs(demo_collection, sync_client)
        if not pairs:
            pytest.skip("Demo collection has no associated events with markets")
        try:
            resp = sync_client.multivariate_collections.create_market(
                demo_collection.collection_ticker,
                selected_markets=pairs,
            )
        except (KalshiValidationError, KalshiNotFoundError) as e:
            pytest.skip(f"Demo rejected create_market for this collection: {e}")
        assert isinstance(resp, CreateMarketResponse)
        assert resp.event_ticker
        assert resp.market_ticker

