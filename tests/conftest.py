"""Shared test fixtures."""

from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig

# Tests assume a clean KALSHI_* environment. The user's shell may have these
# exported (real credentials, base URL overrides, etc.); strip them at import
# time so tests stay hermetic regardless of where they're run.
for _v in (
    "KALSHI_KEY_ID",
    "KALSHI_PRIVATE_KEY",
    "KALSHI_PRIVATE_KEY_PATH",
    "KALSHI_PRIVATE_KEY_PASSPHRASE",
    "KALSHI_API_BASE_URL",
    "KALSHI_WS_BASE_URL",
    "KALSHI_DEMO",
    "KALSHI_ALLOW_UNKNOWN_HOST",
):
    os.environ.pop(_v, None)

# #250: tests use ``https://test.kalshi.com/trade-api/v2`` as a respx-mocked
# sentinel host; default-fail on unknown hosts would break ~25 fixture-based
# files. Enabling the escape hatch process-wide here mirrors how a real caller
# pointing at a mock server would do it. The new tests in test_config.py for
# the default-fail behaviour explicitly ``monkeypatch.delenv`` it.
os.environ["KALSHI_ALLOW_UNKNOWN_HOST"] = "1"


@pytest.fixture
def rsa_private_key() -> rsa.RSAPrivateKey:
    """Generate a test RSA private key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def pem_bytes(rsa_private_key: rsa.RSAPrivateKey) -> bytes:
    """PEM-encoded private key bytes."""
    return rsa_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@pytest.fixture
def pem_string(pem_bytes: bytes) -> str:
    """PEM-encoded private key as string."""
    return pem_bytes.decode("utf-8")


@pytest.fixture
def test_auth(rsa_private_key: rsa.RSAPrivateKey) -> KalshiAuth:
    """A KalshiAuth instance with a test key."""
    return KalshiAuth(key_id="test-key-id", private_key=rsa_private_key)


@pytest.fixture
def test_config() -> KalshiConfig:
    """A test config pointing at a fake base URL."""
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=2,
    )
