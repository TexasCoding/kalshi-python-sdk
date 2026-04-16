"""Tests for _put() helper on base resource classes."""

from __future__ import annotations

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


class TestSyncPut:
    @respx.mock
    def test_put_sends_json_body(self, test_auth: KalshiAuth, config: KalshiConfig) -> None:
        from kalshi.resources._base import SyncResource

        route = respx.put("https://test.kalshi.com/trade-api/v2/test/path").mock(
            return_value=httpx.Response(200, json={"result": "ok"})
        )
        resource = SyncResource(SyncTransport(test_auth, config))
        result = resource._put("/test/path", json={"key": "value"})

        assert result == {"result": "ok"}
        assert route.called
        assert route.calls[0].request.content == b'{"key":"value"}'


class TestAsyncPut:
    @respx.mock
    @pytest.mark.asyncio
    async def test_put_sends_json_body(self, test_auth: KalshiAuth, config: KalshiConfig) -> None:
        from kalshi.resources._base import AsyncResource

        route = respx.put("https://test.kalshi.com/trade-api/v2/test/path").mock(
            return_value=httpx.Response(200, json={"result": "ok"})
        )
        resource = AsyncResource(AsyncTransport(test_auth, config))
        result = await resource._put("/test/path", json={"key": "value"})

        assert result == {"result": "ok"}
        assert route.called
