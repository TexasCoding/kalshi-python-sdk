"""Integration tests for every KalshiClient constructor variant.

Today the integration suite only exercises ``KalshiClient.from_env()``. This
file constructs the client every supported way and verifies each can make at
least one authenticated round-trip against the demo API. A signing bug that
manifests only with ``from_key_path()`` vs ``from_pem()`` would slip through
the existing suite — these tests close that gap.

Closes #54.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import DEMO_BASE_URL, KalshiConfig
from kalshi.models.exchange import UserDataTimestamp

DEMO_HOST = "demo-api.kalshi.co"


def _require_credentials() -> tuple[str, Path]:
    """Return (key_id, private_key_path) or skip the test.

    Mirrors the conftest skip-mechanism: tests are skipped when integration
    credentials are absent so the file is collectable in CI without secrets.
    """
    key_id = os.environ.get("KALSHI_KEY_ID")
    key_path_str = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
    if not key_id or not key_path_str:
        pytest.skip(
            "KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH must be set — "
            "skipping client-construction integration tests"
        )
    key_path = Path(key_path_str).expanduser()
    if not key_path.exists():
        pytest.skip(f"Private key file does not exist: {key_path}")
    return key_id, key_path


def _assert_authenticated_roundtrip(client: KalshiClient) -> None:
    """Hit an authenticated GET and verify the round-trip succeeded.

    ``exchange.user_data_timestamp`` requires auth and is a cheap read-only
    call. A non-2xx response would raise; reaching the assertion means the
    HTTP layer returned 200 and the body parsed cleanly.
    """
    result = client.exchange.user_data_timestamp()
    assert isinstance(result, UserDataTimestamp)


@pytest.mark.integration
class TestClientConstruction:
    """Each constructor path must produce a working authenticated client."""

    def test_from_env(self) -> None:
        """Smoke test: ``from_env()`` round-trip (already implicitly covered)."""
        _require_credentials()
        os.environ.setdefault("KALSHI_DEMO", "true")
        client = KalshiClient.from_env()
        try:
            assert DEMO_HOST in client._config.base_url
            assert client.is_authenticated
            _assert_authenticated_roundtrip(client)
        finally:
            client.close()

    def test_key_id_with_private_key_path(self) -> None:
        """``KalshiClient(key_id=..., private_key_path=...)`` — PEM on disk."""
        key_id, key_path = _require_credentials()
        client = KalshiClient(
            key_id=key_id,
            private_key_path=key_path,
            demo=True,
        )
        try:
            assert DEMO_HOST in client._config.base_url
            assert client.is_authenticated
            _assert_authenticated_roundtrip(client)
        finally:
            client.close()

    def test_key_id_with_private_key_pem_string(self) -> None:
        """``KalshiClient(key_id=..., private_key=<PEM string>)`` — PEM in memory."""
        key_id, key_path = _require_credentials()
        pem_string = key_path.read_text()
        client = KalshiClient(
            key_id=key_id,
            private_key=pem_string,
            demo=True,
        )
        try:
            assert DEMO_HOST in client._config.base_url
            assert client.is_authenticated
            _assert_authenticated_roundtrip(client)
        finally:
            client.close()

    def test_auth_object(self) -> None:
        """``KalshiClient(auth=KalshiAuth(...))`` — pre-built auth object."""
        key_id, key_path = _require_credentials()
        auth = KalshiAuth.from_key_path(key_id, key_path)
        client = KalshiClient(auth=auth, demo=True)
        try:
            assert DEMO_HOST in client._config.base_url
            assert client.is_authenticated
            _assert_authenticated_roundtrip(client)
        finally:
            client.close()

    def test_demo_flag_sets_base_url(self) -> None:
        """``demo=True`` must route to the demo base URL and still authenticate."""
        key_id, key_path = _require_credentials()
        auth = KalshiAuth.from_key_path(key_id, key_path)
        client = KalshiClient(auth=auth, demo=True)
        try:
            assert client._config.base_url == DEMO_BASE_URL
            assert isinstance(client._config, KalshiConfig)
            assert client.is_authenticated
            _assert_authenticated_roundtrip(client)
        finally:
            client.close()
