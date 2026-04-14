"""Tests for AsyncKalshiClient WS integration."""
from __future__ import annotations

from kalshi.async_client import AsyncKalshiClient
from kalshi.ws.client import KalshiWebSocket


class TestAsyncClientWsProperty:
    def test_ws_returns_kalshi_websocket(self, test_auth, test_config) -> None:
        client = AsyncKalshiClient(auth=test_auth, config=test_config)
        ws = client.ws
        assert isinstance(ws, KalshiWebSocket)

    def test_ws_creates_new_instance_each_call(self, test_auth, test_config) -> None:
        client = AsyncKalshiClient(auth=test_auth, config=test_config)
        ws1 = client.ws
        ws2 = client.ws
        assert ws1 is not ws2  # Each call creates a new session

    def test_ws_shares_auth_and_config(self, test_auth, test_config) -> None:
        client = AsyncKalshiClient(auth=test_auth, config=test_config)
        ws = client.ws
        assert ws._auth is test_auth
        assert ws._config is test_config


class TestWsExports:
    def test_ws_package_exports(self) -> None:
        from kalshi.ws import ConnectionState, KalshiWebSocket, MessageQueue, OverflowStrategy
        assert ConnectionState is not None
        assert KalshiWebSocket is not None
        assert MessageQueue is not None
        assert OverflowStrategy is not None

    def test_top_level_error_exports(self) -> None:
        from kalshi import (
            KalshiBackpressureError,
            KalshiConnectionError,
            KalshiSequenceGapError,
            KalshiSubscriptionError,
            KalshiWebSocketError,
        )
        assert KalshiWebSocketError is not None
        assert KalshiConnectionError is not None
        assert KalshiBackpressureError is not None
        assert KalshiSequenceGapError is not None
        assert KalshiSubscriptionError is not None
