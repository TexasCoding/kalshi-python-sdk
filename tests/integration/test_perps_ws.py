"""Integration tests for the perps (margin) WebSocket — live demo connection.

Connects to the demo margin WS feed (``external-api-margin-ws.demo.kalshi.co``)
via the ``perps_ws_session`` fixture (conftest), subscribes to the ``ticker``
channel, and asserts the perps-unique funding fields parse: ``funding_rate`` is a
``FundingRate`` object whose ``next_funding_time_ms`` is an int epoch-ms.

Ticker frames are best-effort coalesced broadcasts; a quiet demo market within
the window is valid state, so a timeout SKIPs (does not fail). The margin WS also
requires auth, so the fixture skips an unauthenticated client.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from kalshi.perps.client import PerpsClient
from kalshi.perps.ws.client import PerpsWebSocket
from kalshi.perps.ws.models.ticker import FundingRate, MarginTickerMessage
from tests.integration.coverage_harness import register_perps
from tests.integration.helpers import retry_transient

# The WS surface is not a REST resource, but registering it keeps the perps
# coverage check aware that the ticker channel is exercised live.
register_perps("PerpsWebSocket", ["subscribe_ticker"])


@pytest.fixture(scope="session")
def perps_ws_ticker(perps_sync_client: PerpsClient) -> str:
    """A margin market ticker to subscribe the WS ticker channel to."""
    markets = perps_sync_client.markets.list()
    if not markets:
        pytest.skip("No margin markets on demo server — cannot subscribe ticker")
    return markets[0].ticker


@pytest.mark.integration
@pytest.mark.asyncio
class TestPerpsWebSocketLive:
    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_connect(self, perps_ws_session: PerpsWebSocket) -> None:
        """Connect to demo margin WS and verify the session is live.

        The fixture establishes connect + auth; reaching here without a
        KalshiConnectionError means the handshake succeeded.
        """
        assert perps_ws_session._connection is not None

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_ticker(
        self,
        perps_ws_session: PerpsWebSocket,
        perps_ws_ticker: str,
    ) -> None:
        """Subscribe to ``ticker`` and parse funding fields from one update."""
        stream = await perps_ws_session.subscribe_ticker(tickers=[perps_ws_ticker])
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=15.0)
        except TimeoutError:
            pytest.skip(f"No margin ticker for {perps_ws_ticker} within 15s")

        assert isinstance(msg, MarginTickerMessage)
        assert msg.type == "ticker"
        assert msg.msg.market_ticker == perps_ws_ticker

        # funding_rate is optional on the payload; when present it carries an
        # int epoch-ms next-funding timestamp and a Decimal rate.
        funding = msg.msg.funding_rate
        if funding is not None:
            assert isinstance(funding, FundingRate)
            assert isinstance(funding.next_funding_time_ms, int)
            assert isinstance(funding.rate, Decimal)
            assert isinstance(funding.ts_ms, int)
