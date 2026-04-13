"""Tests for kalshi._base_client — HTTP transport, retry, error mapping."""

from __future__ import annotations

import httpx
import pytest
import respx

from kalshi._base_client import SyncTransport, _map_error
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import (
    KalshiAuthError,
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
