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
    AuthRequiredError,
    KalshiAuthError,
    KalshiConflictError,
    KalshiError,
    KalshiPoolExhaustedError,
    KalshiServerError,
    KalshiTimeoutError,
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
    async def test_429_retry_after_zero_is_honored_end_to_end(
        self, transport: AsyncTransport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Async counterpart of the sync regression: `is not None` keeps Retry-After: 0.
        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        # _base_client imports asyncio inside the method, so patch the module attr directly.
        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "rl"}),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert sleeps == [0.0], (
            f"Expected one sleep of 0.0s honoring Retry-After: 0, got {sleeps!r}"
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_retries_on_500(self, transport: AsyncTransport) -> None:
        """Async counterpart of the sync 500-retry test."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/markets",
        ).mock(
            side_effect=[
                httpx.Response(500, json={"message": "internal error"}),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_post_not_retried_on_500(
        self, transport: AsyncTransport,
    ) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders",
        ).mock(return_value=httpx.Response(500, json={"message": "internal"}))
        with pytest.raises(KalshiServerError):
            await transport.request(
                "POST", "/portfolio/orders", json={"ticker": "T"},
            )
        assert route.call_count == 1

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

    @respx.mock
    @pytest.mark.asyncio
    async def test_429_retry_after_caps_at_retry_max_delay(
        self, transport: AsyncTransport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Async cap: Retry-After: 9999 must clamp to retry_max_delay=0.1."""
        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "9999"}, json={"message": "rl"}),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert sleeps == [0.1], (
            f"Expected sleep clamped to retry_max_delay=0.1, got {sleeps!r}"
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_429_retry_after_http_date_falls_back_to_backoff(
        self, transport: AsyncTransport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Async: HTTP-date unparseable; transport retries via computed backoff."""
        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            side_effect=[
                httpx.Response(
                    429,
                    headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
                    json={"message": "rl"},
                ),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert route.call_count == 2
        assert len(sleeps) == 1
        assert 0.0 <= sleeps[0] <= 0.01, (
            f"Expected backoff sleep in [0, 0.01], got {sleeps[0]!r}"
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_retries_on_timeout(
        self, transport: AsyncTransport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Async GET retries on httpx.TimeoutException."""
        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            side_effect=[
                httpx.TimeoutException("read timed out"),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert route.call_count == 2
        # Confirm a backoff delay happened between attempts — without this
        # assertion, removing the asyncio.sleep(delay) line would still pass.
        assert len(sleeps) == 1
        assert sleeps[0] >= 0.0

    @respx.mock
    @pytest.mark.asyncio
    async def test_post_not_retried_on_timeout(
        self, transport: AsyncTransport
    ) -> None:
        """Async POST timeout raises immediately; no retry."""
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(side_effect=httpx.TimeoutException("read timed out"))
        with pytest.raises(KalshiError, match="timed out"):
            await transport.request(
                "POST", "/portfolio/orders", json={"ticker": "T"}
            )
        assert route.call_count == 1


class TestAsyncTransportContextManager:
    @pytest.mark.asyncio
    async def test_close(
        self, test_auth: KalshiAuth, config: KalshiConfig
    ) -> None:
        transport = AsyncTransport(test_auth, config)
        await transport.close()  # should not raise


class TestAsyncTransportUnauthenticated:
    """Tests for AsyncTransport with auth=None (unauthenticated mode)."""

    @pytest.fixture
    def unauth_config(self) -> KalshiConfig:
        return KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )

    def test_transport_accepts_none_auth(self, unauth_config: KalshiConfig) -> None:
        transport = AsyncTransport(None, unauth_config)
        assert transport.is_authenticated is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_unauthenticated_request_sends_no_auth_headers(
        self, unauth_config: KalshiConfig
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        transport = AsyncTransport(None, unauth_config)
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200

        # Verify no auth headers were sent
        request = route.calls[0].request
        assert "KALSHI-ACCESS-KEY" not in request.headers
        assert "KALSHI-ACCESS-SIGNATURE" not in request.headers
        assert "KALSHI-ACCESS-TIMESTAMP" not in request.headers
        await transport.close()


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

    def test_no_auth_constructs_unauthenticated(self) -> None:
        client = AsyncKalshiClient()
        assert client._auth is None

    def test_is_authenticated_true_with_auth(self, test_auth: KalshiAuth) -> None:
        client = AsyncKalshiClient(auth=test_auth)
        assert client.is_authenticated is True

    def test_is_authenticated_false_without_auth(self) -> None:
        client = AsyncKalshiClient()
        assert client.is_authenticated is False

    def test_demo_flag(self, test_auth: KalshiAuth) -> None:
        client = AsyncKalshiClient(auth=test_auth, demo=True)
        assert client._config.base_url == DEMO_BASE_URL

    def test_base_url_override(self, test_auth: KalshiAuth) -> None:
        custom = "https://custom.api.com/trade-api/v2"
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
        assert hasattr(client, "series")
        assert hasattr(client, "multivariate_collections")
        assert hasattr(client, "api_keys")
        assert hasattr(client, "milestones")
        assert hasattr(client, "live_data")


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
        custom = "https://custom.api.com/trade-api/v2"
        monkeypatch.setenv("KALSHI_KEY_ID", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.setenv("KALSHI_API_BASE_URL", custom)
        client = AsyncKalshiClient.from_env()
        assert client._config.base_url == custom

    def test_from_env_missing_key_id_returns_unauthenticated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = AsyncKalshiClient.from_env()
        assert client._auth is None

    def test_from_env_missing_keys_returns_unauthenticated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "test")
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = AsyncKalshiClient.from_env()
        assert client._auth is None


class TestAsyncUnauthenticatedResourceGuards:
    @pytest.mark.asyncio
    async def test_orders_create_raises_auth_required(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = AsyncTransport(None, config)
        from kalshi.resources.orders import AsyncOrdersResource
        resource = AsyncOrdersResource(transport)
        with pytest.raises(AuthRequiredError):
            await resource.create(ticker="TEST", side="yes")

    @pytest.mark.asyncio
    async def test_portfolio_balance_raises_auth_required(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = AsyncTransport(None, config)
        from kalshi.resources.portfolio import AsyncPortfolioResource
        resource = AsyncPortfolioResource(transport)
        with pytest.raises(AuthRequiredError):
            await resource.balance()

    def test_ws_property_raises_auth_required(self) -> None:
        client = AsyncKalshiClient.__new__(AsyncKalshiClient)
        client._auth = None
        client._config = KalshiConfig(base_url="https://test.kalshi.com/trade-api/v2", timeout=5.0)
        with pytest.raises(AuthRequiredError):
            _ = client.ws


class TestAsyncKalshiClientUnauthenticated:
    def test_no_auth_constructs(self) -> None:
        client = AsyncKalshiClient()
        assert client._auth is None

    def test_demo_no_auth(self) -> None:
        client = AsyncKalshiClient(demo=True)
        assert client._auth is None
        assert client._config.base_url == DEMO_BASE_URL

    @pytest.mark.asyncio
    async def test_private_endpoint_raises(self) -> None:
        client = AsyncKalshiClient(demo=True)
        with pytest.raises(AuthRequiredError):
            await client.orders.list()

    def test_ws_raises_without_auth(self) -> None:
        client = AsyncKalshiClient(demo=True)
        with pytest.raises(AuthRequiredError):
            _ = client.ws

class TestAsyncWidenedRetrySet:
    """#192: async mirror of widened retryable status set."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_includes_cloudflare_5xx_521_on_get(
        self, transport: AsyncTransport
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            side_effect=[
                httpx.Response(521, text="Web Server Is Down"),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_post_521_not_retried(self, transport: AsyncTransport) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(521, text="down"))
        with pytest.raises(KalshiServerError):
            await transport.request("POST", "/portfolio/orders", json={"ticker": "T"})
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_408_retried_on_get(self, transport: AsyncTransport) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            side_effect=[
                httpx.Response(408, json={"message": "request timeout"}),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert route.call_count == 2


class TestAsyncStatusToTypedException:
    """#201: async hits _map_error too."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_422_maps_to_KalshiValidationError(  # noqa: N802
        self, transport: AsyncTransport
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(422, json={"message": "unprocessable"})
        )
        with pytest.raises(KalshiValidationError):
            await transport.request("GET", "/markets")

    @respx.mock
    @pytest.mark.asyncio
    async def test_409_maps_to_KalshiConflictError(  # noqa: N802
        self, transport: AsyncTransport
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(
            return_value=httpx.Response(409, json={"message": "duplicate"})
        )
        with pytest.raises(KalshiConflictError):
            await transport.request(
                "POST", "/portfolio/orders", json={"ticker": "T"}
            )


class TestAsyncPoolTimeout:
    """#204: async pool exhaustion → KalshiPoolExhaustedError, always retried."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_pool_timeout_retried_on_post(
        self, transport: AsyncTransport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_sleep(d: float) -> None:
            pass

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(
            side_effect=[
                httpx.PoolTimeout("pool full"),
                httpx.Response(200, json={"order_id": "abc"}),
            ]
        )
        resp = await transport.request(
            "POST", "/portfolio/orders", json={"ticker": "T"}
        )
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_pool_timeout_raises_KalshiPoolExhaustedError(  # noqa: N802
        self, transport: AsyncTransport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_sleep(d: float) -> None:
            pass

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(side_effect=httpx.PoolTimeout("pool full"))
        with pytest.raises(KalshiPoolExhaustedError, match="pool exhausted"):
            await transport.request(
                "POST", "/portfolio/orders", json={"ticker": "T"}
            )


class TestAsyncTypedTimeoutException:
    """#204: async POST read-timeout → KalshiTimeoutError, no retry."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_read_timeout_on_post_raises_KalshiTimeoutError_no_retry(  # noqa: N802
        self, transport: AsyncTransport
    ) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/orders"
        ).mock(side_effect=httpx.ReadTimeout("read timed out"))
        with pytest.raises(KalshiTimeoutError, match="timed out"):
            await transport.request(
                "POST", "/portfolio/orders", json={"ticker": "T"}
            )
        assert route.call_count == 1


class TestAsyncTotalTimeoutBudget:
    """#193: async wall-clock budget."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_total_timeout_short_circuits_retries(
        self, test_auth: KalshiAuth, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=5,
            retry_base_delay=0.01,
            retry_max_delay=0.1,
            total_timeout=0.05,
        )
        transport = AsyncTransport(test_auth, cfg)
        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        clock = {"t": 0.0}

        def fake_monotonic() -> float:
            t = clock["t"]
            clock["t"] += 1.0
            return t

        monkeypatch.setattr(
            "kalshi._base_client.time.monotonic", fake_monotonic
        )
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(502, text="bad gateway")
        )
        with pytest.raises(KalshiServerError):
            await transport.request("GET", "/markets")
        assert route.call_count == 1
        assert sleeps == []
        await transport.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_total_timeout_None_preserves_legacy_behavior(  # noqa: N802
        self, test_auth: KalshiAuth, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=2,
            retry_base_delay=0.001,
            retry_max_delay=0.01,
            total_timeout=None,
        )
        transport = AsyncTransport(test_auth, cfg)

        async def fake_sleep(d: float) -> None:
            pass

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(502, text="bad gateway")
        )
        with pytest.raises(KalshiServerError):
            await transport.request("GET", "/markets")
        assert route.call_count == 3
        await transport.close()


class TestAsyncCloseOwnership:
    """#210: async close() must not shut down a caller-owned KalshiAuth."""

    @pytest.mark.asyncio
    async def test_close_does_not_shut_externally_provided_auth(
        self, test_auth: KalshiAuth
    ) -> None:
        client_a = AsyncKalshiClient(auth=test_auth)
        client_b = AsyncKalshiClient(auth=test_auth)
        assert client_a._auth_owned is False
        assert client_b._auth_owned is False
        await client_a.close()
        headers = test_auth.sign_request("GET", "/trade-api/v2/markets")
        assert "KALSHI-ACCESS-KEY" in headers
        await client_b.close()

    @pytest.mark.asyncio
    async def test_close_shuts_locally_constructed_auth(
        self, pem_string: str
    ) -> None:
        client = AsyncKalshiClient(key_id="test-key", private_key=pem_string)
        assert client._auth_owned is True
        await client.close()
        await client.close()  # idempotent

    @pytest.mark.asyncio
    async def test_from_env_owns_auth(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = AsyncKalshiClient.from_env()
        assert client._auth_owned is True
        await client.close()
