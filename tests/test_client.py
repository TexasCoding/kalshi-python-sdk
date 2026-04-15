"""Tests for kalshi._base_client and kalshi.client.

Covers HTTP transport, retry, error mapping, and client constructors.
"""

from __future__ import annotations

import os
import tempfile

import httpx
import pytest
import respx

from kalshi._base_client import SyncTransport, _map_error
from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import DEMO_BASE_URL, PRODUCTION_BASE_URL, KalshiConfig
from kalshi.errors import (
    AuthRequiredError,
    KalshiAuthError,
    KalshiError,
    KalshiNotFoundError,
    KalshiRateLimitError,
    KalshiServerError,
    KalshiValidationError,
)


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=2,
        retry_base_delay=0.01,  # fast retries for tests
        retry_max_delay=0.1,
    )


@pytest.fixture
def transport(test_auth: KalshiAuth, config: KalshiConfig) -> SyncTransport:
    return SyncTransport(test_auth, config)


class TestErrorMapping:
    def test_400_validation_error(self) -> None:
        resp = httpx.Response(400, json={"message": "invalid ticker"})
        err = _map_error(resp)
        assert isinstance(err, KalshiValidationError)
        assert err.status_code == 400

    def test_401_auth_error(self) -> None:
        resp = httpx.Response(401, json={"message": "unauthorized"})
        err = _map_error(resp)
        assert isinstance(err, KalshiAuthError)

    def test_403_auth_error(self) -> None:
        resp = httpx.Response(403, json={"message": "forbidden"})
        err = _map_error(resp)
        assert isinstance(err, KalshiAuthError)

    def test_404_not_found(self) -> None:
        resp = httpx.Response(404, json={"message": "not found"})
        err = _map_error(resp)
        assert isinstance(err, KalshiNotFoundError)

    def test_429_rate_limit(self) -> None:
        resp = httpx.Response(
            429, json={"message": "rate limited"}, headers={"Retry-After": "2.5"}
        )
        err = _map_error(resp)
        assert isinstance(err, KalshiRateLimitError)
        assert err.retry_after == 2.5

    def test_429_no_retry_after(self) -> None:
        resp = httpx.Response(429, json={"message": "slow down"})
        err = _map_error(resp)
        assert isinstance(err, KalshiRateLimitError)
        assert err.retry_after is None

    def test_500_server_error(self) -> None:
        resp = httpx.Response(500, json={"message": "internal error"})
        err = _map_error(resp)
        assert isinstance(err, KalshiServerError)

    def test_502_server_error(self) -> None:
        resp = httpx.Response(502, text="Bad Gateway")
        err = _map_error(resp)
        assert isinstance(err, KalshiServerError)

    def test_503_server_error(self) -> None:
        resp = httpx.Response(503, json={"message": "unavailable"})
        err = _map_error(resp)
        assert isinstance(err, KalshiServerError)

    def test_validation_error_with_details(self) -> None:
        resp = httpx.Response(
            400, json={"message": "validation failed", "details": {"ticker": "required"}}
        )
        err = _map_error(resp)
        assert isinstance(err, KalshiValidationError)
        assert err.details == {"ticker": "required"}


class TestSyncTransportRetry:
    @respx.mock
    def test_get_retries_on_502(self, transport: SyncTransport) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            side_effect=[
                httpx.Response(502, text="Bad Gateway"),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    def test_get_retries_on_429(self, transport: SyncTransport) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            side_effect=[
                httpx.Response(429, json={"message": "rate limited"}),
                httpx.Response(200, json={"markets": []}),
            ]
        )
        resp = transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    def test_post_not_retried(self, transport: SyncTransport) -> None:
        route = respx.post("https://test.kalshi.com/trade-api/v2/portfolio/orders").mock(
            return_value=httpx.Response(502, text="Bad Gateway")
        )
        with pytest.raises(KalshiServerError):
            transport.request("POST", "/portfolio/orders", json={"ticker": "TEST"})
        assert route.call_count == 1

    @respx.mock
    def test_delete_not_retried(self, transport: SyncTransport) -> None:
        """DELETE is not retried (cancel operations are not safely idempotent)."""
        route = respx.delete("https://test.kalshi.com/trade-api/v2/portfolio/orders/abc").mock(
            return_value=httpx.Response(503, text="Unavailable"),
        )
        with pytest.raises(KalshiServerError):
            transport.request("DELETE", "/portfolio/orders/abc")
        assert route.call_count == 1

    @respx.mock
    def test_max_retries_exhausted(self, transport: SyncTransport) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(502, text="Bad Gateway")
        )
        with pytest.raises(KalshiServerError):
            transport.request("GET", "/markets")

    @respx.mock
    def test_400_not_retried(self, transport: SyncTransport) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(400, json={"message": "bad request"})
        )
        with pytest.raises(KalshiValidationError):
            transport.request("GET", "/markets")
        assert route.call_count == 1

    @respx.mock
    def test_401_not_retried(self, transport: SyncTransport) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(401, json={"message": "unauthorized"})
        )
        with pytest.raises(KalshiAuthError):
            transport.request("GET", "/markets")
        assert route.call_count == 1

    @respx.mock
    def test_successful_request(self, transport: SyncTransport) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": [{"ticker": "TEST"}]})
        )
        resp = transport.request("GET", "/markets")
        assert resp.status_code == 200
        assert resp.json()["markets"][0]["ticker"] == "TEST"


class TestSyncTransportContextManager:
    def test_close(self, test_auth: KalshiAuth, config: KalshiConfig) -> None:
        transport = SyncTransport(test_auth, config)
        transport.close()  # should not raise


class TestKalshiClientConstructor:
    """Tests for KalshiClient constructor branches and from_env()."""

    def test_auth_passthrough(self, test_auth: KalshiAuth) -> None:
        client = KalshiClient(auth=test_auth)
        assert client._auth is test_auth
        client.close()

    def test_key_id_and_path(self, pem_bytes: bytes) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_bytes)
            f.flush()
            client = KalshiClient(key_id="test-key", private_key_path=f.name)
            assert client._auth.key_id == "test-key"
            client.close()
        os.unlink(f.name)

    def test_key_id_and_pem(self, pem_string: str) -> None:
        client = KalshiClient(key_id="test-key", private_key=pem_string)
        assert client._auth.key_id == "test-key"
        client.close()

    def test_no_auth_constructs_unauthenticated(self) -> None:
        client = KalshiClient()
        assert client._auth is None
        client.close()

    def test_demo_flag(self, test_auth: KalshiAuth) -> None:
        client = KalshiClient(auth=test_auth, demo=True)
        assert client._config.base_url == DEMO_BASE_URL
        client.close()

    def test_base_url_override(self, test_auth: KalshiAuth) -> None:
        custom = "https://custom.api.com/v2"
        client = KalshiClient(auth=test_auth, base_url=custom)
        assert client._config.base_url == custom
        client.close()

    def test_base_url_takes_precedence_over_demo(self, test_auth: KalshiAuth) -> None:
        custom = "https://custom.api.com/v2"
        client = KalshiClient(auth=test_auth, base_url=custom, demo=True)
        assert client._config.base_url == custom
        client.close()

    def test_default_production_url(self, test_auth: KalshiAuth) -> None:
        client = KalshiClient(auth=test_auth)
        assert client._config.base_url == PRODUCTION_BASE_URL
        client.close()

    def test_context_manager(self, test_auth: KalshiAuth) -> None:
        with KalshiClient(auth=test_auth) as client:
            assert client.markets is not None
            assert client.orders is not None

    def test_has_resources(self, test_auth: KalshiAuth) -> None:
        client = KalshiClient(auth=test_auth)
        assert hasattr(client, "markets")
        assert hasattr(client, "orders")
        client.close()


class TestSyncTransportUnauthenticated:
    """Tests for SyncTransport with auth=None (unauthenticated mode)."""

    @pytest.fixture
    def unauth_config(self) -> KalshiConfig:
        return KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )

    def test_transport_accepts_none_auth(self, unauth_config: KalshiConfig) -> None:
        transport = SyncTransport(None, unauth_config)
        assert transport.is_authenticated is False
        transport.close()

    def test_transport_is_authenticated_true(
        self, test_auth: KalshiAuth, unauth_config: KalshiConfig
    ) -> None:
        transport = SyncTransport(test_auth, unauth_config)
        assert transport.is_authenticated is True
        transport.close()

    @respx.mock
    def test_unauthenticated_request_sends_no_auth_headers(
        self, unauth_config: KalshiConfig
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        transport = SyncTransport(None, unauth_config)
        resp = transport.request("GET", "/markets")
        assert resp.status_code == 200

        # Verify no auth headers were sent
        request = route.calls[0].request
        assert "KALSHI-ACCESS-KEY" not in request.headers
        assert "KALSHI-ACCESS-SIGNATURE" not in request.headers
        assert "KALSHI-ACCESS-TIMESTAMP" not in request.headers
        transport.close()


class TestKalshiClientFromEnv:
    """Tests for KalshiClient.from_env() with various env var combinations."""

    def test_from_env_with_pem_string(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = KalshiClient.from_env()
        assert client._auth.key_id == "env-key"
        assert client._config.base_url == PRODUCTION_BASE_URL
        client.close()

    def test_from_env_with_key_path(
        self, monkeypatch: pytest.MonkeyPatch, pem_bytes: bytes
    ) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_bytes)
            f.flush()
            monkeypatch.setenv("KALSHI_KEY_ID", "path-key")
            monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
            monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", f.name)
            monkeypatch.delenv("KALSHI_DEMO", raising=False)
            monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
            client = KalshiClient.from_env()
            assert client._auth.key_id == "path-key"
            client.close()
        os.unlink(f.name)

    def test_from_env_demo_flag(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.setenv("KALSHI_DEMO", "true")
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = KalshiClient.from_env()
        assert client._config.base_url == DEMO_BASE_URL
        client.close()

    def test_from_env_base_url_override(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        custom = "https://custom.api.com/v2"
        monkeypatch.setenv("KALSHI_KEY_ID", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.setenv("KALSHI_API_BASE_URL", custom)
        client = KalshiClient.from_env()
        assert client._config.base_url == custom
        client.close()

    def test_from_env_missing_key_id_returns_unauthenticated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = KalshiClient.from_env()
        assert client._auth is None
        client.close()

    def test_from_env_missing_keys_returns_unauthenticated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "test")
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = KalshiClient.from_env()
        assert client._auth is None
        client.close()


class TestAuthRequiredError:
    def test_is_kalshi_auth_error(self) -> None:
        err = AuthRequiredError("auth required")
        assert isinstance(err, KalshiAuthError)
        assert isinstance(err, KalshiError)

    def test_default_message(self) -> None:
        err = AuthRequiredError()
        assert "authentication" in str(err).lower()

    def test_custom_message(self) -> None:
        err = AuthRequiredError("custom msg")
        assert str(err) == "custom msg"


class TestUnauthenticatedResourceGuards:
    def test_orders_create_raises_auth_required(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(None, config)
        from kalshi.resources.orders import OrdersResource
        resource = OrdersResource(transport)
        with pytest.raises(AuthRequiredError):
            resource.create(ticker="TEST", side="yes")

    def test_orders_list_raises_auth_required(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(None, config)
        from kalshi.resources.orders import OrdersResource
        resource = OrdersResource(transport)
        with pytest.raises(AuthRequiredError):
            resource.list()

    def test_portfolio_balance_raises_auth_required(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(None, config)
        from kalshi.resources.portfolio import PortfolioResource
        resource = PortfolioResource(transport)
        with pytest.raises(AuthRequiredError):
            resource.balance()

    def test_markets_list_does_not_raise_auth_required(self) -> None:
        """Public resources should NOT have auth guards."""
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(None, config)
        from kalshi.resources.markets import MarketsResource
        resource = MarketsResource(transport)
        # Should not raise AuthRequiredError (will fail with network/connection error)
        with pytest.raises(Exception) as exc_info:
            resource.list()
        assert not isinstance(exc_info.value, AuthRequiredError)


class TestKalshiClientUnauthenticated:
    def test_no_auth_constructs(self) -> None:
        client = KalshiClient()
        assert client._auth is None
        client.close()

    def test_demo_no_auth(self) -> None:
        client = KalshiClient(demo=True)
        assert client._auth is None
        assert client._config.base_url == DEMO_BASE_URL
        client.close()

    def test_has_all_resources(self) -> None:
        client = KalshiClient(demo=True)
        assert hasattr(client, "markets")
        assert hasattr(client, "orders")
        assert hasattr(client, "exchange")
        assert hasattr(client, "events")
        assert hasattr(client, "historical")
        assert hasattr(client, "portfolio")
        client.close()

    @respx.mock
    def test_public_endpoint_works(self) -> None:
        respx.get("https://demo-api.kalshi.co/trade-api/v2/exchange/status").mock(
            return_value=httpx.Response(200, json={
                "exchange_active": True,
                "trading_active": True,
            })
        )
        client = KalshiClient(demo=True)
        status = client.exchange.status()
        assert status.exchange_active is True
        client.close()

    def test_private_endpoint_raises(self) -> None:
        client = KalshiClient(demo=True)
        with pytest.raises(AuthRequiredError):
            client.orders.list()
        client.close()


class TestKalshiClientFromEnvUnauthenticated:
    def test_from_env_no_credentials_returns_unauthenticated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = KalshiClient.from_env()
        assert client._auth is None
        client.close()
