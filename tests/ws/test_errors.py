"""Tests for WebSocket error hierarchy."""
from __future__ import annotations

from kalshi.errors import (
    KalshiBackpressureError,
    KalshiConnectionError,
    KalshiError,
    KalshiSequenceGapError,
    KalshiSubscriptionError,
    KalshiWebSocketError,
)


class TestWebSocketErrorHierarchy:
    def test_websocket_error_is_kalshi_error(self) -> None:
        err = KalshiWebSocketError("test")
        assert isinstance(err, KalshiError)

    def test_connection_error_is_ws_error(self) -> None:
        err = KalshiConnectionError("connection failed")
        assert isinstance(err, KalshiWebSocketError)
        assert isinstance(err, KalshiError)

    def test_sequence_gap_error(self) -> None:
        err = KalshiSequenceGapError("gap detected")
        assert isinstance(err, KalshiWebSocketError)

    def test_backpressure_error(self) -> None:
        err = KalshiBackpressureError("queue full")
        assert isinstance(err, KalshiWebSocketError)

    def test_subscription_error_with_code(self) -> None:
        err = KalshiSubscriptionError("invalid channel", error_code=5)
        assert isinstance(err, KalshiWebSocketError)
        assert err.error_code == 5

    def test_ws_error_has_no_status_code(self) -> None:
        err = KalshiWebSocketError("test")
        assert err.status_code is None
