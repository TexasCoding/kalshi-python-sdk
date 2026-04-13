"""Tests for AsyncTransport and AsyncKalshiClient.

Mirrors sync tests in test_client.py for async code paths.
"""

from __future__ import annotations

import os
import tempfile

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport
from kalshi.async_client import AsyncKalshiClient
from kalshi.auth import KalshiAuth
from kalshi.config import DEMO_BASE_URL, PRODUCTION_BASE_URL, KalshiConfig
from kalshi.errors import (
    KalshiAuthError,
    KalshiServerError,
    KalshiValidationError,
)


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=2,
        retry_base_delay=0.01,
        retry_max_delay=0.1,
    )


@pytest.fixture
def transport(test_auth: KalshiAuth, config: KalshiConfig) -> AsyncTransport:
    return AsyncTransport(test_auth, config)


class TestAsyncTransportRetry:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_retries_on_502(self, transport: AsyncTransport) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets"
        ).mock(
            side_effect=[
                httpx.Response(502, text="Bad Gateway"),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_retries_on_429(self, transport: AsyncTransport) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets"
        ).mock(
            side_effect=[
                httpx.Response(429, json={"message": "rate limited"}),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_post_not_retried(self, transport: AsyncTransport) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(502, text="Bad Gateway"))
        with pytest.raises(KalshiServerError):
            await transport.request(
                "POST", "/portfolio/orders", json={"ticker": "TEST"}
            )
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_not_retried(self, transport: AsyncTransport) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders/abc"
        ).mock(return_value=httpx.Response(503, text="Unavailable"))
        with pytest.raises(KalshiServerError):
            await transport.request("DELETE", "/portfolio/orders/abc")
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_max_retries_exhausted(
        self, transport: AsyncTransport
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/markets"
        ).mock(return_value=httpx.Response(502, text="Bad Gateway"))
        with pytest.raises(KalshiServerError):
            await transport.request("GET", "/markets")

    @respx.mock
    @pytest.mark.asyncio
    async def test_400_not_retried(self, transport: AsyncTransport) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets"
        ).mock(
            return_value=httpx.Response(
                400, json={"message": "bad request"}
            )
        )
        with pytest.raises(KalshiValidationError):
            await transport.request("GET", "/markets")
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_401_not_retried(self, transport: AsyncTransport) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets"
        ).mock(
            return_value=httpx.Response(
                401, json={"message": "unauthorized"}
            )
        )
        with pytest.raises(KalshiAuthError):
            await transport.request("GET", "/markets")
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_successful_request(
        self, transport: AsyncTransport
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/markets"
        ).mock(
            return_value=httpx.Response(
                200, json={"markets": [{"ticker": "TEST"}]}
            )
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert resp.json()["markets"][0]["ticker"] == "TEST"


class TestAsyncTransportContextManager:
    @pytest.mark.asyncio
    async def test_close(
        self, test_auth: KalshiAuth, config: KalshiConfig
    ) -> None:
        transport = AsyncTransport(test_auth, config)
        await transport.close()  # should not raise


class TestAsyncKalshiClientConstructor:
    def test_auth_passthrough(self, test_auth: KalshiAuth) -> None:
        client = AsyncKalshiClient(auth=test_auth)
        assert client._auth is test_auth

    def test_key_id_and_pem(self, pem_string: str) -> None:
        client = AsyncKalshiClient(
            key_id="test-key", private_key=pem_string
        )
        assert client._auth.key_id == "test-key"

    def test_key_id_and_path(self, pem_bytes: bytes) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False
        ) as f:
            f.write(pem_bytes)
            f.flush()
            client = AsyncKalshiClient(
                key_id="test-key", private_key_path=f.name
            )
            assert client._auth.key_id == "test-key"
        os.unlink(f.name)

    def test_raises_without_auth(self) -> None:
        with pytest.raises(ValueError, match="Provide auth"):
            AsyncKalshiClient()

    def test_demo_flag(self, test_auth: KalshiAuth) -> None:
        client = AsyncKalshiClient(auth=test_auth, demo=True)
        assert client._config.base_url == DEMO_BASE_URL

    def test_base_url_override(self, test_auth: KalshiAuth) -> None:
        custom = "https://custom.api.com/v2"
        client = AsyncKalshiClient(auth=test_auth, base_url=custom)
        assert client._config.base_url == custom

    def test_default_production_url(self, test_auth: KalshiAuth) -> None:
        client = AsyncKalshiClient(auth=test_auth)
        assert client._config.base_url == PRODUCTION_BASE_URL

    @pytest.mark.asyncio
    async def test_async_context_manager(
        self, test_auth: KalshiAuth
    ) -> None:
        async with AsyncKalshiClient(auth=test_auth) as client:
            assert client.markets is not None
            assert client.orders is not None

    def test_has_resources(self, test_auth: KalshiAuth) -> None:
        client = AsyncKalshiClient(auth=test_auth)
        assert hasattr(client, "markets")
        assert hasattr(client, "orders")


class TestAsyncKalshiClientFromEnv:
    def test_from_env_with_pem_string(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = AsyncKalshiClient.from_env()
        assert client._auth.key_id == "env-key"
        assert client._config.base_url == PRODUCTION_BASE_URL

    def test_from_env_demo_flag(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.setenv("KALSHI_DEMO", "true")
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = AsyncKalshiClient.from_env()
        assert client._config.base_url == DEMO_BASE_URL

    def test_from_env_base_url_override(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        custom = "https://custom.api.com/v2"
        monkeypatch.setenv("KALSHI_KEY_ID", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.setenv("KALSHI_API_BASE_URL", custom)
        client = AsyncKalshiClient.from_env()
        assert client._config.base_url == custom

    def test_from_env_missing_key_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        with pytest.raises(KalshiAuthError, match="KALSHI_KEY_ID"):
            AsyncKalshiClient.from_env()

    def test_from_env_missing_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "test")
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        with pytest.raises(KalshiAuthError, match="KALSHI_PRIVATE_KEY"):
            AsyncKalshiClient.from_env()
