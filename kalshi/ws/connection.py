"""WebSocket connection manager with state machine and auto-reconnect."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from websockets.asyncio.client import ClientConnection, connect

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiConnectionError

logger = logging.getLogger("kalshi.ws")


class ConnectionState(Enum):
    """WebSocket connection lifecycle states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"


class ConnectionManager:
    """Manages the WebSocket connection lifecycle.

    State machine:
        DISCONNECTED -> CONNECTING -> CONNECTED -> STREAMING
                                                      |
                                            (error/disconnect)
                                                      |
                                                 RECONNECTING -> CONNECTING -> ...
                                                      |
                                            (max retries exceeded)
                                                      |
                                                   CLOSED

    Auth happens during the CONNECTING phase via HTTP upgrade headers.
    """

    def __init__(
        self,
        auth: KalshiAuth,
        config: KalshiConfig,
        heartbeat_timeout: float = 30.0,
        on_state_change: (
            Callable[[ConnectionState, ConnectionState], Awaitable[None]] | None
        ) = None,
    ) -> None:
        self._auth = auth
        self._config = config
        self._heartbeat_timeout = heartbeat_timeout
        self._on_state_change = on_state_change
        self._ws: ClientConnection | None = None
        self._state = ConnectionState.DISCONNECTED

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    @property
    def ws(self) -> ClientConnection:
        """The underlying WebSocket connection.

        Raises:
            KalshiConnectionError: If not connected.
        """
        if self._ws is None:
            raise KalshiConnectionError("Not connected")
        return self._ws

    async def _set_state(self, new_state: ConnectionState) -> None:
        """Transition to a new state, logging and notifying the callback."""
        old = self._state
        self._state = new_state
        logger.debug("Connection state: %s -> %s", old.value, new_state.value)
        if self._on_state_change is not None:
            await self._on_state_change(old, new_state)

    async def mark_streaming(self) -> None:
        """Public transition from CONNECTED to STREAMING.

        The recv loop calls this after a successful reconnect+resubscribe
        so the manager can fire `on_state_change` with the right caller.
        Replaces the previous reach-through to private `_set_state` (#88).
        """
        await self._set_state(ConnectionState.STREAMING)

    async def _build_auth_headers(self) -> dict[str, str]:
        """Build RSA-PSS auth headers for the WebSocket upgrade request.

        Async + executor-offloaded so the ~1-10 ms RSA-PSS sign doesn't
        block the event loop on connect / reconnect. See #178.
        """
        ws_path = urlparse(self._config.ws_base_url).path
        return await self._auth.sign_request_async("GET", ws_path)

    async def connect(self) -> None:
        """Establish a WebSocket connection with RSA-PSS auth headers.

        Transitions: DISCONNECTED -> CONNECTING -> CONNECTED

        Raises:
            KalshiConnectionError: If the connection fails.
        """
        await self._set_state(ConnectionState.CONNECTING)
        try:
            headers = await self._build_auth_headers()
            self._ws = await connect(
                self._config.ws_base_url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=self._heartbeat_timeout,
                close_timeout=5.0,
            )
            await self._set_state(ConnectionState.CONNECTED)
        except Exception as e:
            await self._set_state(ConnectionState.CLOSED)
            # F-O-09: don't interpolate the underlying exception string —
            # it may include the full ws URL with query params and leak into
            # uncaught-exception sinks. The cause is preserved via `__cause__`.
            # Include the path (no query string) for debug context; per
            # F-O-09 the original exception's URL stays out of __str__.
            ws_path = urlparse(self._config.ws_base_url).path
            raise KalshiConnectionError(
                f"WebSocket connection failed: {ws_path}"
            ) from e

    async def reconnect(self) -> None:
        """Reconnect with exponential backoff and jitter.

        Uses the same backoff pattern as the REST transport:
            delay = retry_base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            delay = min(delay, retry_max_delay)

        Transitions: -> RECONNECTING -> CONNECTING -> CONNECTED
                     or -> CLOSED (if max retries exceeded)

        Raises:
            KalshiConnectionError: If max retries exceeded.
        """
        # Close existing connection first
        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None

        await self._set_state(ConnectionState.RECONNECTING)
        for attempt in range(self._config.ws_max_retries):
            delay = self._config.retry_base_delay * (
                2**attempt
            ) + random.uniform(0, 0.5)
            delay = min(delay, self._config.retry_max_delay)
            logger.warning(
                "Reconnecting in %.1fs (attempt %d/%d)",
                delay,
                attempt + 1,
                self._config.ws_max_retries,
            )
            await asyncio.sleep(delay)
            try:
                await self._set_state(ConnectionState.CONNECTING)
                headers = await self._build_auth_headers()
                self._ws = await connect(
                    self._config.ws_base_url,
                    additional_headers=headers,
                    ping_interval=20,
                    ping_timeout=self._heartbeat_timeout,
                    close_timeout=5.0,
                )
                await self._set_state(ConnectionState.CONNECTED)
                return
            except Exception:
                logger.debug("Reconnect attempt %d failed", attempt + 1)
                continue
        await self._set_state(ConnectionState.CLOSED)
        raise KalshiConnectionError(
            f"Max reconnect attempts ({self._config.ws_max_retries}) exceeded"
        )

    async def close(self) -> None:
        """Gracefully close the WebSocket connection with code 1000.

        Transitions: -> CLOSED
        """
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        await self._set_state(ConnectionState.CLOSED)

    async def send(self, msg: dict[str, Any]) -> None:
        """Send a JSON message over the WebSocket.

        Args:
            msg: Dictionary to serialize as JSON and send.

        Raises:
            KalshiConnectionError: If not connected.
        """
        if self._ws is None:
            raise KalshiConnectionError("Not connected")
        await self._ws.send(json.dumps(msg))

    async def recv(self) -> str:
        """Receive a raw string message from the WebSocket.

        Returns:
            The received message as a string.

        Raises:
            KalshiConnectionError: If not connected.
        """
        if self._ws is None:
            raise KalshiConnectionError("Not connected")
        data = await self._ws.recv()
        if isinstance(data, bytes):
            return data.decode("utf-8")
        return data
