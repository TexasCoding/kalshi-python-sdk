"""Tests for kalshi.resources.incentive_programs."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.resources.incentive_programs import (
    AsyncIncentiveProgramsResource,
    IncentiveProgramsResource,
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
) -> IncentiveProgramsResource:
    return IncentiveProgramsResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_resource(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> AsyncIncentiveProgramsResource:
    return AsyncIncentiveProgramsResource(AsyncTransport(test_auth, config))


_SAMPLE_PROGRAM = {
    "id": "prog-1",
    "market_id": "mkt-abc",
    "market_ticker": "TEST-MKT",
    "incentive_type": "liquidity",
    "start_date": "2026-04-01T00:00:00Z",
    "end_date": "2026-04-30T23:59:59Z",
    "period_reward": 1_000_000,  # centi-cents
    "paid_out": False,
    "discount_factor_bps": 25,
    "target_size_fp": "100.5000",
}


class TestList:
    @respx.mock
    def test_returns_page(self, resource: IncentiveProgramsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "incentive_programs": [_SAMPLE_PROGRAM],
                    "next_cursor": "page-2",
                },
            )
        )
        page = resource.list()
        assert len(page.items) == 1
        prog = page.items[0]
        assert prog.id == "prog-1"
        assert prog.incentive_type == "liquidity"
        assert prog.period_reward == 1_000_000
        assert prog.paid_out is False
        assert prog.target_size_fp == Decimal("100.5000")
        assert page.cursor == "page-2"
        assert page.has_next

    @respx.mock
    def test_no_next_cursor(self, resource: IncentiveProgramsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200, json={"incentive_programs": [_SAMPLE_PROGRAM]},
            )
        )
        page = resource.list()
        assert page.cursor is None
        assert not page.has_next

    @respx.mock
    def test_forwards_filters(self, resource: IncentiveProgramsResource) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200, json={"incentive_programs": []},
            )
        )
        resource.list(status="active", incentive_type="volume", limit=50)
        assert route.called
        url = route.calls.last.request.url
        assert url.params["status"] == "active"
        # Wire key is `type`, SDK kwarg is `incentive_type`
        assert url.params["type"] == "volume"
        assert url.params["limit"] == "50"

    @respx.mock
    def test_null_target_size_fp(
        self, resource: IncentiveProgramsResource,
    ) -> None:
        prog = {**_SAMPLE_PROGRAM, "target_size_fp": None, "discount_factor_bps": None}
        respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200, json={"incentive_programs": [prog]},
            )
        )
        page = resource.list()
        assert page.items[0].target_size_fp is None
        assert page.items[0].discount_factor_bps is None


class TestListAll:
    @respx.mock
    def test_paginates_next_cursor(
        self, resource: IncentiveProgramsResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "incentive_programs": [_SAMPLE_PROGRAM],
                        "next_cursor": "page-2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "incentive_programs": [
                            {**_SAMPLE_PROGRAM, "id": "prog-2"},
                        ],
                    },
                ),
            ],
        )
        items = list(resource.list_all(limit=1))
        assert len(items) == 2
        assert items[0].id == "prog-1"
        assert items[1].id == "prog-2"
        assert route.call_count == 2
        # Second call must send cursor=page-2
        assert route.calls[1].request.url.params["cursor"] == "page-2"


class TestAsync:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list(
        self, async_resource: AsyncIncentiveProgramsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200, json={"incentive_programs": [_SAMPLE_PROGRAM]},
            )
        )
        page = await async_resource.list()
        assert page.items[0].id == "prog-1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_forwards_filters(
        self, async_resource: AsyncIncentiveProgramsResource,
    ) -> None:
        """Regression guard: SDK kwarg `incentive_type` must serialize to wire `type`."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200, json={"incentive_programs": []},
            )
        )
        await async_resource.list(
            status="active", incentive_type="volume", limit=50,
        )
        assert route.called
        url = route.calls.last.request.url
        assert url.params["type"] == "volume"
        assert url.params["status"] == "active"
        assert url.params["limit"] == "50"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_all(
        self, async_resource: AsyncIncentiveProgramsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            return_value=httpx.Response(
                200, json={"incentive_programs": [_SAMPLE_PROGRAM]},
            )
        )
        items = [item async for item in async_resource.list_all()]
        assert len(items) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_paginates_next_cursor(
        self, async_resource: AsyncIncentiveProgramsResource,
    ) -> None:
        """next_cursor (not cursor) drives async pagination for this endpoint."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/incentive_programs",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "incentive_programs": [_SAMPLE_PROGRAM],
                        "next_cursor": "page-2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "incentive_programs": [
                            {**_SAMPLE_PROGRAM, "id": "prog-2"},
                        ],
                    },
                ),
            ],
        )
        items = [item async for item in async_resource.list_all(limit=1)]
        assert len(items) == 2
        assert items[0].id == "prog-1"
        assert items[1].id == "prog-2"
        assert route.call_count == 2
        assert route.calls[1].request.url.params["cursor"] == "page-2"
