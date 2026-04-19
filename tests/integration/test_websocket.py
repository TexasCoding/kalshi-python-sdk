"""Integration tests for WebSocket — live connection to demo server."""

from __future__ import annotations

import asyncio

import pytest

from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.models.orderbook_delta import OrderbookSnapshotMessage
from tests.integration.helpers import retry_transient


@pytest.mark.integration
@pytest.mark.asyncio
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
        # Using private _connection because KalshiWebSocket has no public
        # is_connected property yet (tracked as a future improvement).
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

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_ticker(
        self,
        ws_session: KalshiWebSocket,
        demo_market_ticker: str,
    ) -> None:
        """Subscribe to ticker channel and receive one update.

        Ticker frames are best-effort broadcasts; if the market is quiet
        for 10s we skip (not fail). A quiet market is valid demo state.
        """
        from kalshi.ws.models.ticker import TickerMessage
        stream = await ws_session.subscribe_ticker(tickers=[demo_market_ticker])
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=10.0)
        except TimeoutError:
            pytest.skip(f"No ticker update for {demo_market_ticker} within 10s")
        assert isinstance(msg, TickerMessage)
        assert msg.type == "ticker"

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_trade(
        self,
        ws_session: KalshiWebSocket,
        demo_market_ticker: str,
    ) -> None:
        """Subscribe to trade channel. Skip if no trades occur in window."""
        from kalshi.ws.models.trade import TradeMessage
        stream = await ws_session.subscribe_trade(tickers=[demo_market_ticker])
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=10.0)
        except TimeoutError:
            pytest.skip(f"No trade on {demo_market_ticker} within 10s")
        assert isinstance(msg, TradeMessage)
        assert msg.type == "trade"

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_orderbook_delta_emits_delta(
        self,
        ws_session: KalshiWebSocket,
        demo_market_ticker: str,
    ) -> None:
        """Subscribe to orderbook_delta; expect snapshot first, then at least one delta.

        Extends the existing snapshot smoke test by waiting for a second
        frame to exercise the OrderbookDeltaMessage branch of the dispatcher.
        """
        from kalshi.ws.models.orderbook_delta import (
            OrderbookDeltaMessage,
            OrderbookSnapshotMessage,
        )
        stream = await ws_session.subscribe_orderbook_delta(
            tickers=[demo_market_ticker],
        )
        try:
            first = await asyncio.wait_for(stream.__anext__(), timeout=10.0)
        except TimeoutError:
            pytest.skip("No orderbook snapshot within 10s")
        assert isinstance(first, OrderbookSnapshotMessage)

        try:
            second = await asyncio.wait_for(stream.__anext__(), timeout=10.0)
        except TimeoutError:
            pytest.skip("Snapshot received but no delta within 10s")
        assert isinstance(second, (OrderbookDeltaMessage, OrderbookSnapshotMessage))

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_market_lifecycle(
        self,
        ws_session: KalshiWebSocket,
    ) -> None:
        """Subscribe to market_lifecycle_v2 (no ticker filter).

        Lifecycle events fire on market open/close/settle; on quiet demo
        windows we skip.
        """
        from kalshi.ws.models.market_lifecycle import MarketLifecycleMessage
        stream = await ws_session.subscribe_market_lifecycle()
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=10.0)
        except TimeoutError:
            pytest.skip("No market_lifecycle_v2 event within 10s")
        assert isinstance(msg, MarketLifecycleMessage)
        assert msg.type == "market_lifecycle_v2"

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_communications(
        self,
        ws_session: KalshiWebSocket,
    ) -> None:
        """Subscribe to communications (RFQ / quote broadcasts)."""
        from kalshi.ws.models.communications import CommunicationsMessage
        stream = await ws_session.subscribe_communications()
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=10.0)
        except TimeoutError:
            pytest.skip("No communications event within 10s")
        assert isinstance(msg, CommunicationsMessage)
        assert msg.type == "communications"

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_multivariate(
        self,
        ws_session: KalshiWebSocket,
    ) -> None:
        """Subscribe to multivariate channel. Skip if demo has no active collections."""
        from kalshi.ws.models.multivariate import MultivariateMessage
        stream = await ws_session.subscribe_multivariate()
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=15.0)
        except TimeoutError:
            pytest.skip(
                "No multivariate frame within 15s — demo likely has no active collections"
            )
        assert isinstance(msg, MultivariateMessage)
        # Envelope type aligned to spec 'multivariate_lookup' in v0.14.0.
        assert msg.type == "multivariate_lookup"

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_multivariate_lifecycle(
        self,
        ws_session: KalshiWebSocket,
    ) -> None:
        """Subscribe to multivariate_market_lifecycle."""
        from kalshi.ws.models.multivariate import MultivariateLifecycleMessage
        stream = await ws_session.subscribe_multivariate_lifecycle()
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=15.0)
        except TimeoutError:
            pytest.skip("No multivariate_market_lifecycle event within 15s")
        assert isinstance(msg, MultivariateLifecycleMessage)
        assert msg.type == "multivariate_market_lifecycle"

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_fill(
        self,
        ws_session: KalshiWebSocket,
    ) -> None:
        """Subscribe to fill channel. Skip if account has no fills in window."""
        from kalshi.ws.models.fill import FillMessage
        stream = await ws_session.subscribe_fill()
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=5.0)
        except TimeoutError:
            pytest.skip("No fill for demo account within 5s (expected if idle)")
        assert isinstance(msg, FillMessage)
        assert msg.type == "fill"

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_market_positions(
        self,
        ws_session: KalshiWebSocket,
    ) -> None:
        """Subscribe to market_positions channel. Skip if demo account has no positions."""
        from kalshi.ws.models.market_positions import MarketPositionsMessage
        stream = await ws_session.subscribe_market_positions()
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=5.0)
        except TimeoutError:
            pytest.skip(
                "No market_positions frame within 5s (expected if demo acct is flat)"
            )
        assert isinstance(msg, MarketPositionsMessage)
        # Envelope type aligned to spec 'market_position' in v0.14.0.
        assert msg.type == "market_position"

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_user_orders(
        self,
        ws_session: KalshiWebSocket,
    ) -> None:
        """Subscribe to user_orders channel. Skip if demo account has no resting orders."""
        from kalshi.ws.models.user_orders import UserOrdersMessage
        stream = await ws_session.subscribe_user_orders()
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=5.0)
        except TimeoutError:
            pytest.skip(
                "No user_orders frame within 5s (expected if demo acct has no open orders)"
            )
        assert isinstance(msg, UserOrdersMessage)
        # Envelope type aligned to spec 'user_order' in v0.14.0.
        assert msg.type == "user_order"

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_order_group(
        self,
        ws_session: KalshiWebSocket,
    ) -> None:
        """Subscribe to order_group_updates. Skip if demo account has no order groups."""
        from kalshi.ws.models.order_group import OrderGroupMessage
        stream = await ws_session.subscribe_order_group()
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=5.0)
        except TimeoutError:
            pytest.skip(
                "No order_group_updates within 5s (expected if demo acct has no groups)"
            )
        assert isinstance(msg, OrderGroupMessage)
        assert msg.type == "order_group_updates"
