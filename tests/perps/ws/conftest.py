"""Fake perps (margin) WebSocket server + fixtures for transport tests.

Mirrors ``tests/ws/conftest.py`` but speaks the **perps command grammar**:
``subscribe`` (``params.channels``), ``unsubscribe`` (``params.sids``),
``update_subscription`` (object ``ok`` ack), and ``list_subscriptions``
(array ``ok`` ack). Reuses the RSA-key fixtures from ``tests/conftest.py`` via
``test_auth``; the perps unknown-host escape hatch is enabled process-wide by
``tests/perps/conftest.py`` so a loopback ``ws://127.0.0.1:PORT/...`` URL passes
``PerpsConfig`` validation.
"""

from __future__ import annotations

import builtins
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import websockets.datastructures
from websockets.asyncio.server import ServerConnection, serve
from websockets.http11 import Request, Response

from kalshi.auth import KalshiAuth
from kalshi.perps.config import PerpsConfig

_WS_PATH = "/trade-api/ws/v2/margin"


class FakePerpsWS:
    """A fake Kalshi perps (margin) WebSocket server for testing.

    Configurable:
        reject_auth: reject connections during HTTP handshake (401).
        force_error: reply to ``subscribe`` with a ``type:"error"`` frame.
    """

    def __init__(self) -> None:
        self.connections: builtins.list[ServerConnection] = []
        self.subscriptions: dict[int, dict[str, Any]] = {}
        self._next_sid = 1
        self._server: Any = None
        self.port: int = 0
        self.received_commands: builtins.list[dict[str, Any]] = []
        self.reject_auth: bool = False
        self.force_error: bool = False
        self.error_code: int = 6

    def _process_request(
        self, connection: ServerConnection, request: Request
    ) -> Response | None:
        if self.reject_auth:
            return Response(
                401, "Unauthorized", websockets.datastructures.Headers()
            )
        return None

    async def handler(self, ws: ServerConnection) -> None:
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
        cmd = msg.get("cmd")
        msg_id = msg.get("id", 0)
        if cmd == "subscribe":
            if self.force_error:
                await ws.send(json.dumps({
                    "id": msg_id, "type": "error",
                    "msg": {"code": self.error_code, "msg": "Forced error"},
                }))
                return
            channels: builtins.list[str] = msg.get("params", {}).get("channels", [])
            for channel in channels:
                sid = self._next_sid
                self._next_sid += 1
                self.subscriptions[sid] = {
                    "channel": channel, "params": msg.get("params", {}),
                }
                await ws.send(json.dumps({
                    "id": msg_id, "type": "subscribed",
                    "msg": {"channel": channel, "sid": sid},
                }))
        elif cmd == "unsubscribe":
            for sid in msg.get("params", {}).get("sids", []):
                self.subscriptions.pop(sid, None)
                await ws.send(json.dumps({
                    "id": msg_id, "sid": sid, "seq": 1, "type": "unsubscribed",
                }))
        elif cmd == "update_subscription":
            tickers = msg.get("params", {}).get("market_tickers", [])
            await ws.send(json.dumps({
                "id": msg_id, "type": "ok", "msg": {"market_tickers": tickers},
            }))
        elif cmd == "list_subscriptions":
            subs = [
                {"channel": v["channel"], "sid": k}
                for k, v in self.subscriptions.items()
            ]
            await ws.send(json.dumps({"id": msg_id, "type": "ok", "msg": subs}))

    async def send_to_all(self, msg: dict[str, Any]) -> None:
        raw = json.dumps(msg)
        for ws in self.connections:
            await ws.send(raw)

    async def start(self) -> None:
        self._server = await serve(
            self.handler, "127.0.0.1", 0, process_request=self._process_request
        )
        sockets = self._server.sockets
        assert sockets is not None
        self.port = sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def ws_url(self) -> str:
        """Full perps margin WS URL for connecting to this fake server."""
        return f"ws://127.0.0.1:{self.port}{_WS_PATH}"


@pytest.fixture
async def fake_perps_ws() -> AsyncGenerator[FakePerpsWS]:
    """Provide a running FakePerpsWS server, stopped after the test."""
    server = FakePerpsWS()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def perps_ws_config(fake_perps_ws: FakePerpsWS) -> PerpsConfig:
    """A perps config whose ws_base_url points at the fake server (loopback).

    REST base_url stays on the demo host (a known perps host) so PerpsConfig's
    split-environment guard is satisfied; only the WS URL is the loopback fake.
    """
    return PerpsConfig(
        base_url="https://external-api.demo.kalshi.co/trade-api/v2",
        ws_base_url=fake_perps_ws.ws_url,
        ws_max_retries=2,
    )


@pytest.fixture
def perps_auth(test_auth: KalshiAuth) -> KalshiAuth:
    """Alias the shared RSA test auth for perps WS tests."""
    return test_auth
