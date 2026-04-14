"""Tests for WebSocket config."""

from __future__ import annotations

from kalshi.config import DEMO_WS_URL, PRODUCTION_WS_URL, KalshiConfig


class TestWsConfig:
    def test_default_ws_url(self) -> None:
        config = KalshiConfig()
        assert config.ws_base_url == PRODUCTION_WS_URL

    def test_demo_ws_url(self) -> None:
        config = KalshiConfig.demo()
        assert config.ws_base_url == DEMO_WS_URL

    def test_custom_ws_url(self) -> None:
        config = KalshiConfig(ws_base_url="wss://custom.kalshi.com/ws")
        assert config.ws_base_url == "wss://custom.kalshi.com/ws"

    def test_ws_url_trailing_slash_stripped(self) -> None:
        config = KalshiConfig(ws_base_url="wss://custom.kalshi.com/ws/")
        assert config.ws_base_url == "wss://custom.kalshi.com/ws"

    def test_ws_max_retries_default(self) -> None:
        config = KalshiConfig()
        assert config.ws_max_retries == 10

    def test_ws_max_retries_custom(self) -> None:
        config = KalshiConfig(ws_max_retries=5)
        assert config.ws_max_retries == 5
