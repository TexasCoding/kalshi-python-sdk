"""Integration tests for StructuredTargetsResource."""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import KalshiNotFoundError
from kalshi.models.structured_targets import StructuredTarget
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register("StructuredTargetsResource", ["get", "list", "list_all"])


@pytest.mark.integration
class TestStructuredTargetsSync:
    def test_list(self, sync_client: KalshiClient) -> None:
        page = sync_client.structured_targets.list(page_size=5)
        assert isinstance(page.items, list)
        for item in page.items:
            assert isinstance(item, StructuredTarget)
            assert_model_fields(item)

    def test_list_all(self, sync_client: KalshiClient) -> None:
        for count, item in enumerate(
            sync_client.structured_targets.list_all(page_size=5),
        ):
            assert isinstance(item, StructuredTarget)
            if count >= 9:
                break

    def test_get_roundtrip(self, sync_client: KalshiClient) -> None:
        page = sync_client.structured_targets.list(page_size=1)
        if not page.items or not page.items[0].id:
            pytest.skip("No structured targets on demo to fetch")
        target_id = page.items[0].id
        fetched = sync_client.structured_targets.get(target_id)
        assert fetched is not None
        assert fetched.id == target_id

    def test_get_not_found(self, sync_client: KalshiClient) -> None:
        with pytest.raises(KalshiNotFoundError):
            sync_client.structured_targets.get(
                "00000000-0000-0000-0000-000000000000",
            )


@pytest.mark.integration
class TestStructuredTargetsAsync:
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.structured_targets.list(page_size=5)
        assert isinstance(page.items, list)
        for item in page.items:
            assert isinstance(item, StructuredTarget)
            assert_model_fields(item)

    async def test_list_all(self, async_client: AsyncKalshiClient) -> None:
        count = 0
        async for item in async_client.structured_targets.list_all(page_size=5):
            assert isinstance(item, StructuredTarget)
            count += 1
            if count >= 10:
                break

    async def test_get_roundtrip(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.structured_targets.list(page_size=1)
        if not page.items or not page.items[0].id:
            pytest.skip("No structured targets on demo to fetch")
        target_id = page.items[0].id
        fetched = await async_client.structured_targets.get(target_id)
        assert fetched is not None
        assert fetched.id == target_id
