"""Tests for kalshi.resources.structured_targets."""

from __future__ import annotations

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiNotFoundError
from kalshi.resources.structured_targets import (
    AsyncStructuredTargetsResource,
    StructuredTargetsResource,
)


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def resource(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> StructuredTargetsResource:
    return StructuredTargetsResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_resource(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> AsyncStructuredTargetsResource:
    return AsyncStructuredTargetsResource(AsyncTransport(test_auth, config))


class TestList:
    @respx.mock
    def test_returns_page(self, resource: StructuredTargetsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/structured_targets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "structured_targets": [
                        {
                            "id": "uuid-1",
                            "name": "LeBron James",
                            "type": "basketball_player",
                            "details": {"team": "LAL"},
                        },
                    ],
                    "cursor": "next-page",
                },
            )
        )
        page = resource.list()
        assert len(page.items) == 1
        assert page.items[0].id == "uuid-1"
        assert page.items[0].name == "LeBron James"
        assert page.items[0].details == {"team": "LAL"}
        assert page.cursor == "next-page"

    @respx.mock
    def test_filters_serialize(self, resource: StructuredTargetsResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/structured_targets",
        ).mock(
            return_value=httpx.Response(
                200, json={"structured_targets": []},
            )
        )
        resource.list(
            ids=["uuid-1", "uuid-2"],
            target_type="basketball_player",
            competition="NBA",
            page_size=50,
        )
        assert route.called
        call = route.calls.last
        # ids as explode:true → repeated ?ids=...
        assert call.request.url.params.get_list("ids") == ["uuid-1", "uuid-2"]
        assert call.request.url.params["type"] == "basketball_player"
        assert call.request.url.params["competition"] == "NBA"
        assert call.request.url.params["page_size"] == "50"

    @respx.mock
    def test_empty(self, resource: StructuredTargetsResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/structured_targets").mock(
            return_value=httpx.Response(200, json={"structured_targets": []})
        )
        page = resource.list()
        assert page.items == []
        assert page.cursor is None

class TestGet:
    @respx.mock
    def test_returns_target(self, resource: StructuredTargetsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/structured_targets/uuid-1",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "structured_target": {
                        "id": "uuid-1",
                        "name": "LeBron James",
                        "type": "basketball_player",
                        "last_updated_ts": "2026-04-19T12:00:00Z",
                    }
                },
            )
        )
        target = resource.get("uuid-1")
        assert target is not None
        assert target.id == "uuid-1"
        assert target.last_updated_ts is not None

    @respx.mock
    def test_not_found(self, resource: StructuredTargetsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/structured_targets/bad-id",
        ).mock(return_value=httpx.Response(404, json={"error": "not found"}))
        with pytest.raises(KalshiNotFoundError):
            resource.get("bad-id")


class TestAsyncList:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(
        self, async_resource: AsyncStructuredTargetsResource,
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/structured_targets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "structured_targets": [
                        {"id": "uuid-1", "type": "basketball_player"},
                    ],
                },
            )
        )
        page = await async_resource.list()
        assert len(page.items) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_get(
        self, async_resource: AsyncStructuredTargetsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/structured_targets/uuid-1",
        ).mock(
            return_value=httpx.Response(
                200, json={"structured_target": {"id": "uuid-1"}},
            )
        )
        target = await async_resource.get("uuid-1")
        assert target is not None
        assert target.id == "uuid-1"
