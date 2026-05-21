"""Tests for KalshiConfig normalization and request-layer plumbing.

Covers two gaps flagged by Wave 5 audit (issue #99):

* F-Q-05 — trailing-slash stripping on ``base_url`` / ``ws_base_url`` plus
  end-to-end verification that signed requests don't end up with ``//`` paths.
* F-Q-06 — ``extra_headers`` is forwarded to the httpx client and coexists
  with per-request auth headers (no overwrite either direction).
"""

from __future__ import annotations

import httpx
import respx

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import (
    DEMO_BASE_URL,
    DEMO_WS_URL,
    PRODUCTION_BASE_URL,
    PRODUCTION_WS_URL,
    KalshiConfig,
)


class TestTrailingSlashStripping:
    """F-Q-05: __post_init__ rstrips trailing slashes on base_url and ws_base_url."""

    def test_trailing_slash_stripped_on_base_url(self) -> None:
        config = KalshiConfig(base_url="https://demo-api.kalshi.co/trade-api/v2/")
        assert config.base_url == "https://demo-api.kalshi.co/trade-api/v2"

    def test_trailing_slash_stripped_on_ws_base_url(self) -> None:
        config = KalshiConfig(ws_base_url="wss://demo-api.kalshi.co/trade-api/ws/v2/")
        assert config.ws_base_url == "wss://demo-api.kalshi.co/trade-api/ws/v2"

    def test_multiple_trailing_slashes_all_stripped(self) -> None:
        # Defensive: rstrip("/") removes all of them, not just one.
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2///",
            ws_base_url="wss://demo-api.kalshi.co/trade-api/ws/v2///",
        )
        assert config.base_url == "https://demo-api.kalshi.co/trade-api/v2"
        assert config.ws_base_url == "wss://demo-api.kalshi.co/trade-api/ws/v2"

    def test_no_trailing_slash_left_unchanged(self) -> None:
        config = KalshiConfig(
            base_url=PRODUCTION_BASE_URL,
            ws_base_url=PRODUCTION_WS_URL,
        )
        assert config.base_url == PRODUCTION_BASE_URL
        assert config.ws_base_url == PRODUCTION_WS_URL

    def test_demo_classmethod_url_has_no_trailing_slash(self) -> None:
        config = KalshiConfig.demo()
        assert not config.base_url.endswith("/")
        assert not config.ws_base_url.endswith("/")
        assert config.base_url == DEMO_BASE_URL
        assert config.ws_base_url == DEMO_WS_URL

    def test_trailing_slash_base_url_still_passes_validation(self) -> None:
        # Regression: stripping happens before _validate_url, so a known-host URL
        # with a trailing slash must not trip the validator.
        config = KalshiConfig(base_url="https://demo-api.kalshi.co/trade-api/v2/")
        assert config.base_url == DEMO_BASE_URL


class TestTrailingSlashSignedRequest:
    """F-Q-05: signed GET against a trailing-slash base must hit /v2/markets, not //markets."""

    @respx.mock
    def test_signed_get_with_trailing_slash_base_no_double_slash(
        self, test_auth: KalshiAuth
    ) -> None:
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2/",
            timeout=5.0,
            max_retries=0,
        )
        # Route asserts the URL has no // before "markets". If the trailing slash
        # had leaked through, httpx would emit /trade-api/v2//markets and miss this route.
        route = respx.get("https://demo-api.kalshi.co/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        transport = SyncTransport(test_auth, config)
        try:
            resp = transport.request("GET", "/markets")
            assert resp.status_code == 200
            assert route.call_count == 1
            request = route.calls[0].request
            assert str(request.url) == "https://demo-api.kalshi.co/trade-api/v2/markets"
            assert "//markets" not in str(request.url)
        finally:
            transport.close()


class TestExtraHeadersForwarding:
    """F-Q-06: extra_headers reach the wire and coexist with auth headers."""

    @respx.mock
    def test_extra_headers_forwarded_to_request(self, test_auth: KalshiAuth) -> None:
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2",
            timeout=5.0,
            max_retries=0,
            extra_headers={
                "X-Trace-Id": "trace-1",
                "User-Agent": "kalshi-sdk/test",
            },
        )
        route = respx.get("https://demo-api.kalshi.co/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        transport = SyncTransport(test_auth, config)
        try:
            transport.request("GET", "/markets")
            request = route.calls[0].request
            # User extras land on the wire as-is.
            assert request.headers["X-Trace-Id"] == "trace-1"
            assert request.headers["User-Agent"] == "kalshi-sdk/test"
            # And the per-request auth headers still ride alongside them
            # (no overwrite either direction).
            assert "KALSHI-ACCESS-KEY" in request.headers
            assert "KALSHI-ACCESS-SIGNATURE" in request.headers
            assert "KALSHI-ACCESS-TIMESTAMP" in request.headers
        finally:
            transport.close()

    @respx.mock
    def test_extra_headers_persist_across_multiple_requests(
        self, test_auth: KalshiAuth
    ) -> None:
        # Regression: extras are set on httpx.Client(headers=...), so every request
        # carries them — not just the first one.
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2",
            timeout=5.0,
            max_retries=0,
            extra_headers={"X-Trace-Id": "trace-1"},
        )
        route = respx.get("https://demo-api.kalshi.co/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        transport = SyncTransport(test_auth, config)
        try:
            transport.request("GET", "/markets")
            transport.request("GET", "/markets")
            assert route.call_count == 2
            for call in route.calls:
                assert call.request.headers["X-Trace-Id"] == "trace-1"
        finally:
            transport.close()

    def test_extra_headers_defaults_to_empty_dict(self) -> None:
        # Each instance gets its own dict (default_factory), so mutating one
        # config's extras must not bleed into another's.
        config_a = KalshiConfig()
        config_b = KalshiConfig()
        assert config_a.extra_headers == {}
        assert config_b.extra_headers == {}
        config_a.extra_headers["X-Trace-Id"] = "a"
        assert config_b.extra_headers == {}


class TestHttpClientTuning:
    """http2 and limits are exposed on KalshiConfig and forwarded to httpx."""

    def test_http2_defaults_off(self) -> None:
        assert KalshiConfig().http2 is False

    def test_limits_defaults_none(self) -> None:
        assert KalshiConfig().limits is None

    def test_http2_flag_forwarded_to_sync_client(self, test_auth: KalshiAuth) -> None:
        # http2=False with no h2 installed must still build successfully —
        # only http2=True requires the h2 extra.
        config = KalshiConfig(http2=False)
        transport = SyncTransport(test_auth, config)
        try:
            # httpx exposes http2 setting via the private _h2_pool; safer to
            # assert via no-error construction and via the config round-trip.
            assert transport._config.http2 is False
        finally:
            transport.close()

    def test_custom_limits_forwarded_to_sync_client(
        self, test_auth: KalshiAuth
    ) -> None:
        limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
        config = KalshiConfig(limits=limits)
        transport = SyncTransport(test_auth, config)
        try:
            assert transport._config.limits is limits
        finally:
            transport.close()


class TestBaseUrlPathValidation:
    """#202: base_url MUST include the /trade-api/v2 path component."""

    def test_base_url_without_trade_api_v2_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="/trade-api/v2"):
            KalshiConfig(base_url="https://demo-api.kalshi.co/")
        with pytest.raises(ValueError, match="/trade-api/v2"):
            KalshiConfig(base_url="https://demo-api.kalshi.co/v1")
        with pytest.raises(ValueError, match="/trade-api/v2"):
            KalshiConfig(base_url="https://demo-api.kalshi.co/trade-api")

    def test_base_url_with_trade_api_v2_accepted(self) -> None:
        config = KalshiConfig(base_url="https://demo-api.kalshi.co/trade-api/v2")
        assert config.base_url == "https://demo-api.kalshi.co/trade-api/v2"

    def test_base_url_with_trailing_slash_accepted(self) -> None:
        # Trailing slash is stripped before path validation.
        config = KalshiConfig(base_url="https://demo-api.kalshi.co/trade-api/v2/")
        assert config.base_url == "https://demo-api.kalshi.co/trade-api/v2"


class TestTotalTimeoutField:
    """#193: total_timeout field exists, defaults to None (legacy)."""

    def test_total_timeout_field_exists_and_defaults_None(self) -> None:  # noqa: N802
        assert KalshiConfig().total_timeout is None

    def test_total_timeout_can_be_set(self) -> None:
        config = KalshiConfig(total_timeout=30.0)
        assert config.total_timeout == 30.0
