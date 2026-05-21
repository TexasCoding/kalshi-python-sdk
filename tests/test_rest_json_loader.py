"""Tests for #260: pluggable REST JSON loader (``KalshiConfig.rest_json_loads``).

The loader, when set, receives ``response.content`` (bytes) and its return value
drives every ``_get`` / ``_post`` / ``_put`` / ``_delete`` call. ``None`` falls
back to ``httpx.Response.json()`` (stdlib).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from kalshi import AsyncKalshiClient, KalshiClient
from kalshi.auth import KalshiAuth
from kalshi.config import DEMO_WS_URL, KalshiConfig

MOCK_BASE = "https://demo-api.kalshi.co/trade-api/v2"


def _config(**overrides: Any) -> KalshiConfig:
    return KalshiConfig(
        base_url=MOCK_BASE,
        ws_base_url=DEMO_WS_URL,
        timeout=5.0,
        max_retries=0,
        **overrides,
    )


class TestConfigField:
    def test_default_is_none(self) -> None:
        assert _config().rest_json_loads is None

    def test_accepts_callable(self) -> None:
        cfg = _config(rest_json_loads=lambda b: {"loaded": True})
        assert callable(cfg.rest_json_loads)


class TestLoaderApplied:
    @respx.mock
    def test_sync_loader_used_on_get(self, test_auth: KalshiAuth) -> None:
        seen: list[bytes] = []
        sentinel = {"__sentinel__": True, "exchange_active": False}

        def loader(content: bytes) -> Any:
            seen.append(content)
            return sentinel

        cfg = _config(rest_json_loads=loader)
        respx.get(f"{MOCK_BASE}/exchange/status").mock(
            return_value=httpx.Response(200, json={"exchange_active": True})
        )
        with KalshiClient(auth=test_auth, config=cfg) as client:
            data = client.exchange._get("/exchange/status")
        assert data is sentinel
        assert len(seen) == 1
        assert isinstance(seen[0], bytes)
        assert b"exchange_active" in seen[0]

    @respx.mock
    def test_sync_loader_used_on_post(self, test_auth: KalshiAuth) -> None:
        sentinel = {"__sentinel__": "post"}
        cfg = _config(rest_json_loads=lambda b: sentinel)
        respx.post(f"{MOCK_BASE}/anything").mock(
            return_value=httpx.Response(200, json={"k": 1})
        )
        with KalshiClient(auth=test_auth, config=cfg) as client:
            data = client.exchange._post("/anything", json={})
        assert data is sentinel

    @respx.mock
    def test_default_none_uses_response_json(self, test_auth: KalshiAuth) -> None:
        respx.get(f"{MOCK_BASE}/exchange/status").mock(
            return_value=httpx.Response(200, json={"exchange_active": True})
        )
        with KalshiClient(auth=test_auth, config=_config()) as client:
            data = client.exchange._get("/exchange/status")
        assert data == {"exchange_active": True}

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_loader_used_on_get(self, test_auth: KalshiAuth) -> None:
        sentinel = {"__sentinel__": "async"}
        cfg = _config(rest_json_loads=lambda b: sentinel)
        respx.get(f"{MOCK_BASE}/exchange/status").mock(
            return_value=httpx.Response(200, json={"exchange_active": True})
        )
        async with AsyncKalshiClient(auth=test_auth, config=cfg) as client:
            data = await client.exchange._get("/exchange/status")
        assert data is sentinel
