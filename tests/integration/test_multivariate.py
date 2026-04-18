"""Integration tests for MultivariateCollectionsResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import (
    KalshiNotFoundError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.models.common import Page
from kalshi.models.multivariate import (
    CreateMarketResponse,
    LookupPoint,
    LookupTickersResponse,
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
        "lookup_tickers",
        "lookup_history",
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
    if len(events) < 1:
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
        for count, collection in enumerate(
            sync_client.multivariate_collections.list_all(limit=2)
        ):
            assert isinstance(collection, MultivariateEventCollection)
            assert_model_fields(collection)
            if count >= 1:
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
        except (KalshiValidationError, KalshiNotFoundError, KalshiServerError) as e:
            pytest.skip(f"Demo rejected create_market for this collection: {e}")
        assert isinstance(resp, CreateMarketResponse)
        assert resp.event_ticker
        assert resp.market_ticker

    def test_lookup_tickers(
        self,
        sync_client: KalshiClient,
        demo_collection: MultivariateEventCollection,
    ) -> None:
        """PUT lookup — resolves a TickerPair set to a canonical combo ticker."""
        pairs = _build_ticker_pairs(demo_collection, sync_client)
        if not pairs:
            pytest.skip("Demo collection has no associated events with markets")
        try:
            resp = sync_client.multivariate_collections.lookup_tickers(
                demo_collection.collection_ticker,
                selected_markets=pairs,
            )
        except (KalshiValidationError, KalshiNotFoundError, KalshiServerError) as e:
            pytest.skip(f"Demo rejected lookup_tickers for this collection: {e}")
        assert isinstance(resp, LookupTickersResponse)
        assert resp.event_ticker
        assert resp.market_ticker

    def test_lookup_history(
        self, sync_client: KalshiClient, demo_collection_ticker: str
    ) -> None:
        try:
            points = sync_client.multivariate_collections.lookup_history(
                demo_collection_ticker,
                lookback_seconds=3600,
            )
        except KalshiNotFoundError:
            pytest.skip("Demo collection has no lookup history")
        assert isinstance(points, list)
        for point in points:
            assert isinstance(point, LookupPoint)
            assert_model_fields(point)


@pytest.mark.integration
class TestMultivariateAsync:
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.multivariate_collections.list(limit=5)
        assert isinstance(page, Page)
        if page.items:
            assert isinstance(page.items[0], MultivariateEventCollection)
            assert_model_fields(page.items[0])

    async def test_list_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for collection in async_client.multivariate_collections.list_all(limit=2):
            assert isinstance(collection, MultivariateEventCollection)
            assert_model_fields(collection)
            count += 1
            if count >= 2:
                break

    async def test_get(
        self, async_client: AsyncKalshiClient, demo_collection_ticker: str
    ) -> None:
        collection = await async_client.multivariate_collections.get(
            demo_collection_ticker
        )
        assert isinstance(collection, MultivariateEventCollection)
        assert_model_fields(collection)
        assert collection.collection_ticker == demo_collection_ticker

    async def test_create_market(
        self,
        async_client: AsyncKalshiClient,
        sync_client: KalshiClient,
        demo_collection: MultivariateEventCollection,
    ) -> None:
        pairs = _build_ticker_pairs(demo_collection, sync_client)
        if not pairs:
            pytest.skip("Demo collection has no associated events with markets")
        try:
            resp = await async_client.multivariate_collections.create_market(
                demo_collection.collection_ticker,
                selected_markets=pairs,
            )
        except (KalshiValidationError, KalshiNotFoundError, KalshiServerError) as e:
            pytest.skip(f"Demo rejected create_market for this collection: {e}")
        assert isinstance(resp, CreateMarketResponse)
        assert resp.event_ticker
        assert resp.market_ticker

    async def test_lookup_tickers(
        self,
        async_client: AsyncKalshiClient,
        sync_client: KalshiClient,
        demo_collection: MultivariateEventCollection,
    ) -> None:
        pairs = _build_ticker_pairs(demo_collection, sync_client)
        if not pairs:
            pytest.skip("Demo collection has no associated events with markets")
        try:
            resp = await async_client.multivariate_collections.lookup_tickers(
                demo_collection.collection_ticker,
                selected_markets=pairs,
            )
        except (KalshiValidationError, KalshiNotFoundError, KalshiServerError) as e:
            pytest.skip(f"Demo rejected lookup_tickers for this collection: {e}")
        assert isinstance(resp, LookupTickersResponse)
        assert resp.event_ticker
        assert resp.market_ticker

    async def test_lookup_history(
        self, async_client: AsyncKalshiClient, demo_collection_ticker: str
    ) -> None:
        try:
            points = await async_client.multivariate_collections.lookup_history(
                demo_collection_ticker,
                lookback_seconds=3600,
            )
        except KalshiNotFoundError:
            pytest.skip("Demo collection has no lookup history")
        assert isinstance(points, list)
        for point in points:
            assert isinstance(point, LookupPoint)
            assert_model_fields(point)
