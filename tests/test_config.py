"""Tests for KalshiConfig normalization and request-layer plumbing.

Covers two gaps flagged by Wave 5 audit (issue #99):

* F-Q-05 — trailing-slash stripping on ``base_url`` / ``ws_base_url`` plus
  end-to-end verification that signed requests don't end up with ``//`` paths.
* F-Q-06 — ``extra_headers`` is forwarded to the httpx client and coexists
  with per-request auth headers (no overwrite either direction).
"""

from __future__ import annotations

import logging

import httpx
import pytest
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
        # Pair with matching demo ws_base_url to satisfy #239 split-env check.
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2/",
            ws_base_url=DEMO_WS_URL,
        )
        assert config.base_url == "https://demo-api.kalshi.co/trade-api/v2"

    def test_trailing_slash_stripped_on_ws_base_url(self) -> None:
        config = KalshiConfig(
            base_url=DEMO_BASE_URL,
            ws_base_url="wss://demo-api.kalshi.co/trade-api/ws/v2/",
        )
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
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2/",
            ws_base_url=DEMO_WS_URL,
        )
        assert config.base_url == DEMO_BASE_URL


class TestTrailingSlashSignedRequest:
    """F-Q-05: signed GET against a trailing-slash base must hit /v2/markets, not //markets."""

    @respx.mock
    def test_signed_get_with_trailing_slash_base_no_double_slash(
        self, test_auth: KalshiAuth
    ) -> None:
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2/",
            ws_base_url=DEMO_WS_URL,
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
            ws_base_url=DEMO_WS_URL,
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
    def test_extra_headers_persist_across_multiple_requests(self, test_auth: KalshiAuth) -> None:
        # Regression: extras are set on httpx.Client(headers=...), so every request
        # carries them — not just the first one.
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2",
            ws_base_url=DEMO_WS_URL,
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

    def test_extra_headers_rejects_kalshi_access_uppercase(self) -> None:
        # #298 follow-up: config.extra_headers must not be a back door for the
        # SDK-signed KALSHI-ACCESS-* surface. The per-request guard is not
        # enough on its own — the config path bypassed it.
        with pytest.raises(ValueError, match="KALSHI-ACCESS-"):
            KalshiConfig(extra_headers={"KALSHI-ACCESS-KEY": "spoofed"})

    def test_extra_headers_rejects_kalshi_access_lowercase(self) -> None:
        # Case-mismatched key (the forge surface that motivated the per-call
        # _ci_merge fix) must also fail at construction.
        with pytest.raises(ValueError, match=r"kalshi-access-key"):
            KalshiConfig(extra_headers={"kalshi-access-key": "x"})

    def test_extra_headers_rejects_kalshi_access_signature_and_timestamp(self) -> None:
        # Any KALSHI-ACCESS-* prefix is rejected, not just KALSHI-ACCESS-KEY.
        for header in ("KALSHI-ACCESS-SIGNATURE", "KALSHI-ACCESS-TIMESTAMP"):
            with pytest.raises(ValueError, match="KALSHI-ACCESS-"):
                KalshiConfig(extra_headers={header: "v"})

    def test_extra_headers_with_non_auth_keys_ok(self) -> None:
        # Sanity: regular custom headers still work.
        cfg = KalshiConfig(extra_headers={"X-Trace-Id": "a", "User-Agent": "sdk"})
        assert cfg.extra_headers == {"X-Trace-Id": "a", "User-Agent": "sdk"}


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

    def test_custom_limits_forwarded_to_sync_client(self, test_auth: KalshiAuth) -> None:
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
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2",
            ws_base_url=DEMO_WS_URL,
        )
        assert config.base_url == "https://demo-api.kalshi.co/trade-api/v2"

    def test_base_url_with_trailing_slash_accepted(self) -> None:
        # Trailing slash is stripped before path validation.
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2/",
            ws_base_url=DEMO_WS_URL,
        )
        assert config.base_url == "https://demo-api.kalshi.co/trade-api/v2"


class TestTotalTimeoutField:
    """#193: total_timeout field exists, defaults to None (legacy)."""

    def test_total_timeout_field_exists_and_defaults_None(self) -> None:  # noqa: N802
        assert KalshiConfig().total_timeout is None

    def test_total_timeout_can_be_set(self) -> None:
        config = KalshiConfig(total_timeout=30.0)
        assert config.total_timeout == 30.0


class TestWsExtraConfigFields:
    """#208 + #209: ws_ping_interval / ws_close_timeout / ws_json_loads /
    ws_json_dumps fields exist on KalshiConfig with sane defaults.
    """

    def test_ws_ping_interval_default_20(self) -> None:
        assert KalshiConfig().ws_ping_interval == 20.0

    def test_ws_close_timeout_default_5(self) -> None:
        assert KalshiConfig().ws_close_timeout == 5.0

    def test_ws_json_loads_default_None(self) -> None:  # noqa: N802
        assert KalshiConfig().ws_json_loads is None

    def test_ws_json_dumps_default_None(self) -> None:  # noqa: N802
        assert KalshiConfig().ws_json_dumps is None

    def test_ws_ping_interval_settable(self) -> None:
        cfg = KalshiConfig(ws_ping_interval=45.0)
        assert cfg.ws_ping_interval == 45.0

    def test_ws_close_timeout_settable(self) -> None:
        cfg = KalshiConfig(ws_close_timeout=1.5)
        assert cfg.ws_close_timeout == 1.5

    def test_ws_json_loads_callable_stored(self) -> None:
        import json

        cfg = KalshiConfig(ws_json_loads=json.loads, ws_json_dumps=json.dumps)
        assert cfg.ws_json_loads is json.loads
        assert cfg.ws_json_dumps is json.dumps


class TestHttp2ImportCheck:
    """P1.1: ``http2=True`` must fail-fast at construction if ``h2`` is missing,
    instead of deferring an opaque ImportError to the first request.
    """

    def test_http2_True_with_h2_missing_raises_at_construction(  # noqa: N802
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import importlib.util as _ilu

        real_find_spec = _ilu.find_spec

        def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
            if name == "h2":
                return None
            return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(_ilu, "find_spec", fake_find_spec)
        with pytest.raises(ValueError, match=r"http2=True requires the 'h2' package"):
            KalshiConfig(http2=True)

    def test_http2_True_with_h2_installed_succeeds(  # noqa: N802
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import importlib.machinery
        import importlib.util as _ilu

        real_find_spec = _ilu.find_spec
        sentinel = importlib.machinery.ModuleSpec("h2", loader=None)

        def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
            if name == "h2":
                return sentinel
            return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(_ilu, "find_spec", fake_find_spec)
        # Should NOT raise.
        config = KalshiConfig(http2=True)
        assert config.http2 is True

    def test_http2_False_does_not_check_h2(  # noqa: N802
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default http2=False must never touch find_spec — no startup cost."""
        called: list[str] = []
        import importlib.util as _ilu

        real_find_spec = _ilu.find_spec

        def tracking_find_spec(name: str, *args: object, **kwargs: object) -> object:
            called.append(name)
            return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(_ilu, "find_spec", tracking_find_spec)
        KalshiConfig()
        assert "h2" not in called


_UNKNOWN_BASE = "https://attacker.example/trade-api/v2"
_UNKNOWN_WS = "wss://attacker.example/trade-api/ws/v2"


class TestUnknownHostDefaultFail:
    """#250: a typo or hostile ``KALSHI_API_BASE_URL`` value used to slip
    through with only ``logger.warning``. Production log filters silently
    drop the warning while the SDK keeps signing every request — including
    the KALSHI-ACCESS-KEY and matching RSA-PSS signature — to the attacker.
    Now: default-fail, with explicit opt-in for mock servers and proxies."""

    def test_known_host_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_ALLOW_UNKNOWN_HOST", raising=False)
        config = KalshiConfig(base_url=PRODUCTION_BASE_URL, ws_base_url=PRODUCTION_WS_URL)
        assert config.base_url == PRODUCTION_BASE_URL

    def test_unknown_host_raises_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_ALLOW_UNKNOWN_HOST", raising=False)
        with pytest.raises(ValueError, match=r"not a known Kalshi endpoint"):
            KalshiConfig(base_url=_UNKNOWN_BASE, ws_base_url=_UNKNOWN_WS)

    def test_unknown_host_error_message_lists_known_hosts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_ALLOW_UNKNOWN_HOST", raising=False)
        with pytest.raises(ValueError) as excinfo:
            KalshiConfig(base_url=_UNKNOWN_BASE, ws_base_url=_UNKNOWN_WS)
        msg = str(excinfo.value)
        assert "api.elections.kalshi.com" in msg
        assert "demo-api.kalshi.co" in msg
        assert "allow_unknown_host=True" in msg
        assert "KALSHI_ALLOW_UNKNOWN_HOST=1" in msg

    def test_unknown_host_with_flag_opt_in(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("KALSHI_ALLOW_UNKNOWN_HOST", raising=False)
        with caplog.at_level(logging.WARNING, logger="kalshi"):
            config = KalshiConfig(
                base_url=_UNKNOWN_BASE,
                ws_base_url=_UNKNOWN_WS,
                allow_unknown_host=True,
            )
        assert config.base_url == _UNKNOWN_BASE
        assert any("not a known Kalshi endpoint" in r.message for r in caplog.records)

    def test_unknown_host_with_env_opt_in(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("KALSHI_ALLOW_UNKNOWN_HOST", "1")
        with caplog.at_level(logging.WARNING, logger="kalshi"):
            config = KalshiConfig(base_url=_UNKNOWN_BASE, ws_base_url=_UNKNOWN_WS)
        assert config.base_url == _UNKNOWN_BASE
        assert any("not a known Kalshi endpoint" in r.message for r in caplog.records)

    def test_env_opt_in_only_honors_exact_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Any value other than literal "1" must NOT opt in — otherwise a stale
        # ``KALSHI_ALLOW_UNKNOWN_HOST=0`` from a previous shell would silently
        # disable the check.
        monkeypatch.setenv("KALSHI_ALLOW_UNKNOWN_HOST", "0")
        with pytest.raises(ValueError, match=r"not a known Kalshi endpoint"):
            KalshiConfig(base_url=_UNKNOWN_BASE, ws_base_url=_UNKNOWN_WS)
        monkeypatch.setenv("KALSHI_ALLOW_UNKNOWN_HOST", "true")
        with pytest.raises(ValueError, match=r"not a known Kalshi endpoint"):
            KalshiConfig(base_url=_UNKNOWN_BASE, ws_base_url=_UNKNOWN_WS)

    def test_localhost_ok_without_opt_in(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_ALLOW_UNKNOWN_HOST", raising=False)
        config = KalshiConfig(
            base_url="http://localhost:8080/trade-api/v2",
            ws_base_url="ws://localhost:8080/trade-api/ws/v2",
        )
        assert "localhost" in config.base_url

    def test_unknown_ws_host_also_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Unknown ws_base_url with a known base_url must also default-fail —
        # the WS feed leaks the same KALSHI-ACCESS-KEY on connect.
        monkeypatch.delenv("KALSHI_ALLOW_UNKNOWN_HOST", raising=False)
        with pytest.raises(ValueError, match=r"not a known Kalshi endpoint"):
            KalshiConfig(
                base_url=PRODUCTION_BASE_URL,
                ws_base_url="wss://attacker.example/trade-api/ws/v2",
            )
