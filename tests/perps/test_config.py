"""Tests for PerpsConfig (perps base URLs + security guards)."""

from __future__ import annotations

import pytest

from kalshi.config import KalshiConfig
from kalshi.perps.config import (
    PERPS_DEMO_BASE_URL,
    PERPS_DEMO_WS_URL,
    PERPS_PRODUCTION_BASE_URL,
    PERPS_PRODUCTION_WS_URL,
    PerpsConfig,
)


class TestPerpsConfigFactories:
    def test_production_urls(self) -> None:
        c = PerpsConfig.production()
        assert c.base_url == PERPS_PRODUCTION_BASE_URL
        assert c.ws_base_url == PERPS_PRODUCTION_WS_URL

    def test_demo_urls(self) -> None:
        c = PerpsConfig.demo()
        assert c.base_url == PERPS_DEMO_BASE_URL
        assert c.ws_base_url == PERPS_DEMO_WS_URL

    def test_default_is_production_perps(self) -> None:
        # The @dataclass(frozen=True) re-decoration must flip the inherited
        # default from the prediction-API URL to the perps prod URL.
        c = PerpsConfig()
        assert c.base_url == PERPS_PRODUCTION_BASE_URL
        assert c.ws_base_url == PERPS_PRODUCTION_WS_URL

    def test_is_kalshi_config_subclass(self) -> None:
        # Liskov: PerpsConfig must be accepted where the transport expects
        # KalshiConfig (the transport is reused unchanged).
        assert issubclass(PerpsConfig, KalshiConfig)
        assert isinstance(PerpsConfig.demo(), KalshiConfig)

    def test_trailing_slash_stripped(self) -> None:
        c = PerpsConfig(
            base_url=PERPS_DEMO_BASE_URL + "/",
            ws_base_url=PERPS_DEMO_WS_URL + "/",
        )
        assert c.base_url == PERPS_DEMO_BASE_URL
        assert c.ws_base_url == PERPS_DEMO_WS_URL


class TestPerpsConfigGuards:
    def test_unknown_host_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_PERPS_ALLOW_UNKNOWN_HOST", raising=False)
        with pytest.raises(ValueError, match="not a known Kalshi perps endpoint"):
            PerpsConfig(base_url="https://api.elections.kalshi.com/trade-api/v2")

    def test_prediction_host_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A prediction-API host must NOT be accepted by PerpsConfig.
        monkeypatch.delenv("KALSHI_PERPS_ALLOW_UNKNOWN_HOST", raising=False)
        with pytest.raises(ValueError):
            PerpsConfig(base_url="https://demo-api.kalshi.co/trade-api/v2")

    def test_allow_unknown_host_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_PERPS_ALLOW_UNKNOWN_HOST", raising=False)
        c = PerpsConfig(
            base_url="https://perps-test.kalshi.com/trade-api/v2",
            ws_base_url=PERPS_PRODUCTION_WS_URL,
            allow_unknown_host=True,
        )
        assert c.base_url == "https://perps-test.kalshi.com/trade-api/v2"

    def test_allow_unknown_host_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KALSHI_PERPS_ALLOW_UNKNOWN_HOST", "1")
        c = PerpsConfig(base_url="https://perps-test.kalshi.com/trade-api/v2")
        assert c.base_url == "https://perps-test.kalshi.com/trade-api/v2"

    def test_missing_v2_path_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KALSHI_PERPS_ALLOW_UNKNOWN_HOST", "1")
        with pytest.raises(ValueError, match="/trade-api/v2"):
            PerpsConfig(base_url="https://external-api.kalshi.com/trade-api/v1")

    def test_plaintext_to_remote_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KALSHI_PERPS_ALLOW_UNKNOWN_HOST", "1")
        with pytest.raises(ValueError, match="https://"):
            PerpsConfig(base_url="http://perps-test.kalshi.com/trade-api/v2")

    def test_access_header_in_extra_headers_rejected(self) -> None:
        with pytest.raises(ValueError, match="KALSHI-ACCESS"):
            PerpsConfig.demo(extra_headers={"KALSHI-ACCESS-KEY": "forged"})

    def test_split_rest_ws_environment_rejected(self) -> None:
        with pytest.raises(ValueError, match="split REST/WS"):
            PerpsConfig(
                base_url=PERPS_PRODUCTION_BASE_URL,
                ws_base_url=PERPS_DEMO_WS_URL,
            )

    def test_localhost_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_PERPS_ALLOW_UNKNOWN_HOST", raising=False)
        c = PerpsConfig(
            base_url="http://localhost/trade-api/v2",
            ws_base_url="ws://localhost/trade-api/ws/v2/margin",
        )
        assert c.base_url == "http://localhost/trade-api/v2"
