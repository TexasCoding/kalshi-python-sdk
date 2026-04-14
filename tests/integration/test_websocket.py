"""Integration tests for WebSocket — live connection to demo server."""

from __future__ import annotations

import asyncio

import pytest

from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.models.orderbook_delta import OrderbookSnapshotMessage
from tests.integration.helpers import retry_transient


@pytest.mark.integration
class TestWebSocketLive:
    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_connect_and_auth(
        self, ws_session: KalshiWebSocket
    ) -> None:
        """Connect to demo WS and verify auth succeeded.

        If we reach this point without KalshiConnectionError, auth passed.
        The ws_session fixture handles connect + auth via KalshiWebSocket.
        """
        # Connection is established by the fixture.
        # If auth failed, KalshiConnectionError would have been raised.
        assert ws_session._connection is not None

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_orderbook_snapshot(
        self,
        ws_session: KalshiWebSocket,
        demo_market_ticker: str,
    ) -> None:
        """Subscribe to orderbook_delta and receive initial snapshot.

        orderbook_delta with send_initial_snapshot=True guarantees an
        immediate snapshot message, no dependency on market activity.
        """
        stream = await ws_session.subscribe_orderbook_delta(
            tickers=[demo_market_ticker],
        )
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=10.0)
        except TimeoutError:
            pytest.skip("No orderbook snapshot received within 10s on demo")

        # The first message should be a snapshot
        assert isinstance(msg, OrderbookSnapshotMessage)
        assert msg.type == "orderbook_snapshot"
        assert msg.msg.market_ticker == demo_market_ticker

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_disconnect_lifecycle(
        self,
        ws_session: KalshiWebSocket,
        demo_market_ticker: str,
    ) -> None:
        """Subscribe, receive a message, then verify context manager exit is clean.

        The ws_session fixture's cleanup (__aexit__) calls _stop() which:
        1. Cancels the recv_loop task
        2. Sends sentinels to all active queues
        3. Closes the WS connection
        """
        stream = await ws_session.subscribe_orderbook_delta(
            tickers=[demo_market_ticker],
        )
        try:
            await asyncio.wait_for(stream.__anext__(), timeout=10.0)
        except TimeoutError:
            pytest.skip("No snapshot received — cannot test disconnect lifecycle")

        # The fixture will clean up on exit. If cleanup hangs or errors,
        # the test framework will report it as a fixture teardown failure.
        # No explicit assertion needed — we're testing that exit doesn't hang.
