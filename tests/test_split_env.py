"""Regression tests for #239: split REST/WS environment rejection.

If ``demo=True`` was combined with an explicit production ``base_url`` (or
``KALSHI_DEMO=true`` with ``KALSHI_API_BASE_URL=<prod>``), the old
``setdefault`` logic in the client constructors silently honored ``base_url``
while still pinning ``ws_base_url`` to the demo WS feed — REST hit production
(real money) while a WS-driven strategy made decisions against a demo book.
``KalshiConfig`` itself never cross-checked that REST and WS resolved to the
same Kalshi environment.

These tests pin down the new contract:

* ``KalshiConfig.__post_init__`` rejects a base_url/ws_base_url pair whose
  hosts resolve to different known Kalshi environments (prod vs demo).
* ``KalshiClient`` / ``AsyncKalshiClient`` constructors reject
  ``demo=True`` combined with an explicit non-demo ``base_url`` (and the
  ``from_env`` env-var equivalent) before building the config.
* Localhost on either side is fine (mock servers); both-prod and both-demo
  remain valid.
"""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.config import (
    DEMO_BASE_URL,
    DEMO_WS_URL,
    PRODUCTION_BASE_URL,
    PRODUCTION_WS_URL,
    KalshiConfig,
)


class TestKalshiConfigSplitEnv:
    """KalshiConfig cross-check of base_url vs ws_base_url environment."""

    def test_prod_base_demo_ws_rejected(self) -> None:
        with pytest.raises(ValueError, match="split REST/WS environment"):
            KalshiConfig(base_url=PRODUCTION_BASE_URL, ws_base_url=DEMO_WS_URL)

    def test_demo_base_prod_ws_rejected(self) -> None:
        with pytest.raises(ValueError, match="split REST/WS environment"):
            KalshiConfig(base_url=DEMO_BASE_URL, ws_base_url=PRODUCTION_WS_URL)

    def test_both_production_ok(self) -> None:
        config = KalshiConfig(
            base_url=PRODUCTION_BASE_URL, ws_base_url=PRODUCTION_WS_URL
        )
        assert config.base_url == PRODUCTION_BASE_URL
        assert config.ws_base_url == PRODUCTION_WS_URL

    def test_both_demo_ok(self) -> None:
        config = KalshiConfig(base_url=DEMO_BASE_URL, ws_base_url=DEMO_WS_URL)
        assert config.base_url == DEMO_BASE_URL
        assert config.ws_base_url == DEMO_WS_URL

    def test_localhost_base_demo_ws_ok(self) -> None:
        # Mock REST server + real demo WS: legitimate dev setup, not a split env.
        config = KalshiConfig(
            base_url="http://localhost:8080/trade-api/v2",
            ws_base_url=DEMO_WS_URL,
        )
        assert config.ws_base_url == DEMO_WS_URL

    def test_prod_base_localhost_ws_ok(self) -> None:
        # Real REST + mock WS server: also legitimate; not a known-env mismatch.
        config = KalshiConfig(
            base_url=PRODUCTION_BASE_URL,
            ws_base_url="ws://localhost:8080/trade-api/ws/v2",
        )
        assert config.base_url == PRODUCTION_BASE_URL


class TestKalshiClientSplitEnv:
    """Sync client rejects demo=True paired with a non-demo base_url."""

    def test_demo_true_with_prod_base_url_raises(self) -> None:
        with pytest.raises(ValueError, match="demo=True"):
            KalshiClient(demo=True, base_url=PRODUCTION_BASE_URL)

    def test_demo_true_with_demo_base_url_ok(self) -> None:
        # Redundant but consistent — must not raise.
        client = KalshiClient(demo=True, base_url=DEMO_BASE_URL)
        assert client._config.base_url == DEMO_BASE_URL
        assert client._config.ws_base_url == DEMO_WS_URL
        client.close()

    def test_demo_false_with_demo_base_url_raises_via_config(self) -> None:
        # demo=False (default) + demo REST URL leaves ws_base_url pointing at
        # production. The config-level cross-check catches the resulting split.
        with pytest.raises(ValueError, match="split REST/WS environment"):
            KalshiClient(base_url=DEMO_BASE_URL)

    def test_from_env_demo_plus_prod_base_url_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.setenv("KALSHI_DEMO", "true")
        monkeypatch.setenv("KALSHI_API_BASE_URL", PRODUCTION_BASE_URL)
        with pytest.raises(ValueError, match="demo=True"):
            KalshiClient.from_env()


class TestAsyncKalshiClientSplitEnv:
    """Async client mirrors the sync rejection."""

    def test_demo_true_with_prod_base_url_raises(self) -> None:
        with pytest.raises(ValueError, match="demo=True"):
            AsyncKalshiClient(demo=True, base_url=PRODUCTION_BASE_URL)

    def test_from_env_demo_plus_prod_base_url_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.setenv("KALSHI_DEMO", "true")
        monkeypatch.setenv("KALSHI_API_BASE_URL", PRODUCTION_BASE_URL)
        with pytest.raises(ValueError, match="demo=True"):
            AsyncKalshiClient.from_env()
