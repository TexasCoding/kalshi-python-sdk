"""Tests for KlearConfig (SCM host/path guards)."""

from __future__ import annotations

import pytest

from kalshi.config import KalshiConfig
from kalshi.perps.klear.config import DEMO_KLEAR_URL, PRODUCTION_KLEAR_URL, KlearConfig


class TestKlearConfig:
    def test_factories(self) -> None:
        assert KlearConfig.production().base_url == PRODUCTION_KLEAR_URL
        assert KlearConfig.demo().base_url == DEMO_KLEAR_URL

    def test_default_is_production_klear(self) -> None:
        assert KlearConfig().base_url == PRODUCTION_KLEAR_URL

    def test_is_kalshi_config_subclass(self) -> None:
        # Liskov: accepted where the reused transport expects KalshiConfig.
        assert issubclass(KlearConfig, KalshiConfig)
        assert isinstance(KlearConfig.demo(), KalshiConfig)

    def test_rejects_non_klear_path(self) -> None:
        with pytest.raises(ValueError, match="/klear-api/v1"):
            KlearConfig(base_url="https://api.klear.kalshi.com/trade-api/v2")

    def test_rejects_unknown_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_KLEAR_ALLOW_UNKNOWN_HOST", raising=False)
        with pytest.raises(ValueError, match="not a known Kalshi Klear endpoint"):
            KlearConfig(base_url="https://api.elections.kalshi.com/klear-api/v1")

    def test_allow_unknown_host_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_KLEAR_ALLOW_UNKNOWN_HOST", raising=False)
        c = KlearConfig(
            base_url="https://klear-mock.example.com/klear-api/v1", allow_unknown_host=True
        )
        assert c.base_url == "https://klear-mock.example.com/klear-api/v1"

    def test_plaintext_remote_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KALSHI_KLEAR_ALLOW_UNKNOWN_HOST", "1")
        with pytest.raises(ValueError, match="https://"):
            KlearConfig(base_url="http://klear-mock.example.com/klear-api/v1")

    def test_localhost_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_KLEAR_ALLOW_UNKNOWN_HOST", raising=False)
        c = KlearConfig(base_url="http://localhost/klear-api/v1")
        assert c.base_url == "http://localhost/klear-api/v1"

    def test_holds_no_credentials_in_repr(self) -> None:
        # KlearConfig carries no secrets; its repr is inherently safe.
        assert "password" not in repr(KlearConfig.demo()).lower()
