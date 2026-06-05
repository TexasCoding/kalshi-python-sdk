"""Perps (margin) WebSocket connection manager.

Mirrors :class:`kalshi.ws.connection.ConnectionManager` for the margin WS host.
The base manager is already config-driven — it reads ``ws_base_url``,
``ws_ping_interval``, ``ws_close_timeout``, ``ws_max_retries`` and the
``retry_*`` knobs off the injected config, and signs the WS upgrade with
``GET`` + the ws path via the shared :class:`kalshi.auth.KalshiAuth`. Since
:class:`kalshi.perps.config.PerpsConfig` is a :class:`kalshi.config.KalshiConfig`
subclass carrying all of those fields (pointed at the margin host), the entire
state machine, AWS full-jitter reconnect, ``_open_socket`` / ``connect`` /
``reconnect`` / ``close`` / ``send`` / ``recv`` flow, and the path-only
(no-query-string) :class:`~kalshi.errors.KalshiConnectionError` message are
reused verbatim.

This subclass exists only to:

* pin the config parameter type to :class:`PerpsConfig` so callers get the
  perps-specific host validation and demo/production helpers, and
* give the perps WS package the same module layout as ``kalshi/ws/`` (mirror
  parity) and a clear seam if the margin handshake ever needs to diverge.

:class:`~kalshi.ws.connection.ConnectionState` is reused as-is (re-exported here
for convenience); it is NOT redefined.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from kalshi.auth import KalshiAuth
from kalshi.perps.config import PerpsConfig
from kalshi.ws.connection import ConnectionManager, ConnectionState

__all__ = ["ConnectionState", "PerpsConnectionManager"]


class PerpsConnectionManager(ConnectionManager):
    """:class:`ConnectionManager` pinned to the perps margin WS host/config."""

    def __init__(
        self,
        auth: KalshiAuth,
        config: PerpsConfig,
        heartbeat_timeout: float = 30.0,
        on_state_change: (
            Callable[[ConnectionState, ConnectionState], Awaitable[None]] | None
        ) = None,
    ) -> None:
        super().__init__(
            auth=auth,
            config=config,
            heartbeat_timeout=heartbeat_timeout,
            on_state_change=on_state_change,
        )
