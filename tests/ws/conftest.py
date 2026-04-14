"""Fake WebSocket server for integration testing."""

from __future__ import annotations

import builtins
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import websockets.datastructures
from websockets.asyncio.server import ServerConnection, serve
from websockets.http11 import Request, Response


class FakeKalshiWS:
    """A fake Kalshi WebSocket server for testing.

    Configurable behaviors:
        reject_auth: If True, reject connections during HTTP handshake (401).
        disconnect_after: If set, close all connections after N broadcast messages.
    """

    def __init__(self) -> None:
        self.connections: builtins.list[ServerConnection] = []
        self.subscriptions: dict[int, dict[str, Any]] = {}
        self._next_sid = 1
        self._server: Any = None
        self.port: int = 0
        self.received_commands: builtins.list[dict[str, Any]] = []
        self.reject_auth: bool = False
        self.disconnect_after: int | None = None
        self._msg_count = 0
        self._force_error: bool = False

    def _process_request(
        self, connection: ServerConnection, request: Request
    ) -> Response | None:
        """Reject connections during handshake if reject_auth is True."""
        if self.reject_auth:
            return Response(
                401,
                "Unauthorized",
                websockets.datastructures.Headers(),
            )
        return None

    async def handler(self, ws: ServerConnection) -> None:
        """Handle an incoming WebSocket connection."""
        self.connections.append(ws)
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                msg: dict[str, Any] = json.loads(raw)
                self.received_commands.append(msg)
                await self._handle_command(ws, msg)
        except websockets.ConnectionClosed:
            pass
        finally:
            if ws in self.connections:
                self.connections.remove(ws)

    async def _handle_command(
        self, ws: ServerConnection, msg: dict[str, Any]
    ) -> None:
        """Dispatch a command received from the client."""
        cmd = msg.get("cmd")
        msg_id = msg.get("id", 0)
        if cmd == "subscribe":
            if self._force_error:
                await ws.send(
                    json.dumps(
                        {
                            "id": msg_id,
                            "type": "error",
                            "msg": {"code": 400, "msg": "Forced error"},
                        }
                    )
                )
                return
            channels: builtins.list[str] = msg.get("params", {}).get(
                "channels", []
            )
            for channel in channels:
                sid = self._next_sid
                self._next_sid += 1
                self.subscriptions[sid] = {
                    "channel": channel,
                    "params": msg.get("params", {}),
                }
                await ws.send(
                    json.dumps(
                        {
                            "id": msg_id,
                            "type": "subscribed",
                            "msg": {"channel": channel, "sid": sid},
                        }
                    )
                )
        elif cmd == "unsubscribe":
            for sid in msg.get("params", {}).get("sids", []):
                self.subscriptions.pop(sid, None)
                await ws.send(
                    json.dumps(
                        {
                            "id": msg_id,
                            "sid": sid,
                            "seq": 0,
                            "type": "unsubscribed",
                        }
                    )
                )
        elif cmd == "update_subscription":
            await ws.send(
                json.dumps({"id": msg_id, "type": "ok", "msg": {}})
            )
        elif cmd == "list_subscriptions":
            subs = [
                {"channel": v["channel"], "sid": k}
                for k, v in self.subscriptions.items()
            ]
            await ws.send(
                json.dumps({"id": msg_id, "type": "ok", "msg": subs})
            )

    async def send_to_all(self, msg: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        raw = json.dumps(msg)
        for ws in self.connections:
            await ws.send(raw)
        self._msg_count += 1
        if (
            self.disconnect_after is not None
            and self._msg_count >= self.disconnect_after
        ):
            for ws in builtins.list(self.connections):
                await ws.close()

    async def start(self) -> None:
        """Start the fake server on a random OS-assigned port."""
        self._server = await serve(
            self.handler,
            "127.0.0.1",
            0,
            process_request=self._process_request,
        )
        sockets = self._server.sockets
        assert sockets is not None
        self.port = sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop the fake server."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def url(self) -> str:
        """WebSocket URL for connecting to this server."""
        return f"ws://127.0.0.1:{self.port}"


@pytest.fixture
async def fake_ws() -> AsyncGenerator[FakeKalshiWS]:
    """Provide a running FakeKalshiWS server, stopped after the test."""
    server = FakeKalshiWS()
    await server.start()
    yield server
    await server.stop()
