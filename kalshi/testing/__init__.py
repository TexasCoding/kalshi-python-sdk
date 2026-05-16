"""Record/replay mock layer for testing against the Kalshi SDK.

Drop a :class:`RecordingTransport` (or :class:`AsyncRecordingTransport`) into the
client once to capture real API calls to disk, then swap in
:class:`ReplayTransport` (or :class:`AsyncReplayTransport`) to run tests offline.

Requests are matched by HTTP method + URL path + sorted query parameters. The
``KALSHI-ACCESS-SIGNATURE`` and ``KALSHI-ACCESS-TIMESTAMP`` headers are ignored,
so signature drift between record and replay does not cause misses.

Usage::

    from pathlib import Path
    from kalshi import KalshiClient
    from kalshi.testing import RecordingTransport, ReplayTransport

    # Record once against the real API:
    with KalshiClient.from_env(transport=RecordingTransport(Path("fixtures"))) as c:
        c.exchange.status()

    # Replay in tests, no network:
    with KalshiClient(transport=ReplayTransport(Path("fixtures"))) as c:
        c.exchange.status()  # served from fixtures/GET_trade-api_v2_exchange_status.json
"""

from kalshi.testing._recorder import AsyncRecordingTransport, RecordingTransport
from kalshi.testing._replay import (
    AsyncReplayTransport,
    FixtureNotFoundError,
    ReplayTransport,
)

__all__ = [
    "AsyncRecordingTransport",
    "AsyncReplayTransport",
    "FixtureNotFoundError",
    "RecordingTransport",
    "ReplayTransport",
]
