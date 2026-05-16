"""Integration tests for every KalshiClient constructor variant. Closes #54."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import DEMO_BASE_URL
from kalshi.models.exchange import UserDataTimestamp

from .conftest import _assert_demo_url, _credentials_available


def _require_credentials() -> tuple[str, Path]:
    """Return (key_id, private_key_path) or skip the test."""
    if not _credentials_available():
        pytest.skip("KALSHI_KEY_ID not set — skipping client-construction integration tests")
    key_id = os.environ["KALSHI_KEY_ID"]
    key_path_str = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
    if not key_path_str:
        pytest.skip("KALSHI_PRIVATE_KEY_PATH not set")
    key_path = Path(key_path_str).expanduser()
    if not key_path.exists():
        pytest.skip(f"Private key file does not exist: {key_path}")
    return key_id, key_path


def _assert_authenticated_roundtrip(client: KalshiClient) -> None:
    result = client.exchange.user_data_timestamp()
    assert isinstance(result, UserDataTimestamp)


async def _assert_async_authenticated_roundtrip(client: AsyncKalshiClient) -> None:
    result = await client.exchange.user_data_timestamp()
    assert isinstance(result, UserDataTimestamp)


@pytest.mark.integration
class TestClientConstruction:
    """Each constructor path must produce a working authenticated client."""

    def test_from_env(self) -> None:
        if not _credentials_available():
            pytest.skip("KALSHI_KEY_ID not set — skipping client-construction integration tests")
        os.environ.setdefault("KALSHI_DEMO", "true")
        client = KalshiClient.from_env()
        try:
            _assert_demo_url(client._config.base_url, client._config.ws_base_url)
            assert client.is_authenticated
            _assert_authenticated_roundtrip(client)
        finally:
            client.close()

    def test_key_id_with_private_key_path(self) -> None:
        key_id, key_path = _require_credentials()
        client = KalshiClient(key_id=key_id, private_key_path=key_path, demo=True)
        try:
            _assert_demo_url(client._config.base_url, client._config.ws_base_url)
            assert client.is_authenticated
            _assert_authenticated_roundtrip(client)
        finally:
            client.close()

    def test_key_id_with_private_key_pem_string(self) -> None:
        key_id, key_path = _require_credentials()
        pem_string = key_path.read_text()
        client = KalshiClient(key_id=key_id, private_key=pem_string, demo=True)
        try:
            _assert_demo_url(client._config.base_url, client._config.ws_base_url)
            assert client.is_authenticated
            _assert_authenticated_roundtrip(client)
        finally:
            client.close()

    def test_auth_object_with_demo_flag(self) -> None:
        """Pre-built ``KalshiAuth`` + ``demo=True`` routes to the demo base URL."""
        key_id, key_path = _require_credentials()
        auth = KalshiAuth.from_key_path(key_id, key_path)
        client = KalshiClient(auth=auth, demo=True)
        try:
            _assert_demo_url(client._config.base_url, client._config.ws_base_url)
            assert client._config.base_url == DEMO_BASE_URL
            assert client.is_authenticated
            _assert_authenticated_roundtrip(client)
        finally:
            client.close()


@pytest.mark.integration
@pytest.mark.asyncio
class TestAsyncClientConstruction:
    """Async sibling — catches signing/auth drift in the async transport path."""

    async def test_async_key_id_with_private_key_path(self) -> None:
        key_id, key_path = _require_credentials()
        client = AsyncKalshiClient(key_id=key_id, private_key_path=key_path, demo=True)
        try:
            _assert_demo_url(client._config.base_url, client._config.ws_base_url)
            assert client.is_authenticated
            await _assert_async_authenticated_roundtrip(client)
        finally:
            await client.close()
