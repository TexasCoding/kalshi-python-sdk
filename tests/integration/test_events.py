"""Integration tests for EventsResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.common import Page
from kalshi.models.events import Event, EventMetadata
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register("EventsResource", ["get", "list", "list_all", "metadata"])


@pytest.mark.integration
class TestEventsSync:
    def test_list(self, sync_client: KalshiClient) -> None:
        page = sync_client.events.list(limit=5)
        assert isinstance(page, Page)
        assert isinstance(page.items, list)
        if page.items:
            assert isinstance(page.items[0], Event)
            assert_model_fields(page.items[0])
            assert page.items[0].event_ticker

    def test_get(self, sync_client: KalshiClient, demo_event_ticker: str) -> None:
        event = sync_client.events.get(demo_event_ticker)
        assert isinstance(event, Event)
        assert_model_fields(event)
        assert event.event_ticker == demo_event_ticker

    def test_list_all(self, sync_client: KalshiClient) -> None:
        for count, event in enumerate(sync_client.events.list_all(limit=2)):
            assert isinstance(event, Event)
            assert_model_fields(event)

            if count >= 2:
                break
        assert count > 0

    def test_metadata(self, sync_client: KalshiClient, demo_event_ticker: str) -> None:
        meta = sync_client.events.metadata(demo_event_ticker)
        assert isinstance(meta, EventMetadata)
        assert_model_fields(meta)


@pytest.mark.integration
class TestEventsAsync:
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.events.list(limit=5)
        assert isinstance(page, Page)
        if page.items:
            assert isinstance(page.items[0], Event)
            assert_model_fields(page.items[0])

    async def test_get(self, async_client: AsyncKalshiClient, demo_event_ticker: str) -> None:
        event = await async_client.events.get(demo_event_ticker)
        assert isinstance(event, Event)
        assert_model_fields(event)
        assert event.event_ticker == demo_event_ticker

    async def test_list_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for event in async_client.events.list_all(limit=2):
            assert isinstance(event, Event)
            assert_model_fields(event)
            count += 1
            if count >= 3:
                break
        assert count > 0

    async def test_metadata(self, async_client: AsyncKalshiClient, demo_event_ticker: str) -> None:
        meta = await async_client.events.metadata(demo_event_ticker)
        assert isinstance(meta, EventMetadata)
        assert_model_fields(meta)
