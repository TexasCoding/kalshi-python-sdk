"""Shared fixtures for the perps (margin) test package.

Reuses the RSA-key fixtures from ``tests/conftest.py`` (``rsa_private_key`` /
``pem_bytes`` / ``pem_string`` / ``test_auth``) and adds perps-specific config /
client fixtures pointed at the **demo** perps base URL (a known host, so no
escape hatch is needed for the happy paths).
"""

from __future__ import annotations

import os

import pytest

from kalshi.auth import KalshiAuth
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig

# Strip any perps credentials/overrides the developer's shell may export so the
# perps tests stay hermetic, mirroring the prediction-API conftest. Then enable
# the perps unknown-host escape hatch process-wide so respx-mocked sentinel
# hosts (e.g. https://perps-test.kalshi.com/trade-api/v2) work; the host-check
# tests in test_config.py explicitly ``monkeypatch.delenv`` it.
for _v in (
    "KALSHI_PERPS_KEY_ID",
    "KALSHI_PERPS_PRIVATE_KEY",
    "KALSHI_PERPS_PRIVATE_KEY_PATH",
    "KALSHI_PERPS_PRIVATE_KEY_PASSPHRASE",
    "KALSHI_PERPS_API_BASE_URL",
    "KALSHI_PERPS_DEMO",
    "KALSHI_PERPS_ALLOW_UNKNOWN_HOST",
):
    os.environ.pop(_v, None)

os.environ["KALSHI_PERPS_ALLOW_UNKNOWN_HOST"] = "1"


@pytest.fixture
def perps_config() -> PerpsConfig:
    """A perps config pointed at the demo perps environment."""
    return PerpsConfig.demo(timeout=5.0, max_retries=2)


@pytest.fixture
def perps_client(test_auth: KalshiAuth, perps_config: PerpsConfig) -> PerpsClient:
    """An authenticated sync perps client on the demo perps base URL."""
    return PerpsClient(auth=test_auth, config=perps_config)


@pytest.fixture
def async_perps_client(test_auth: KalshiAuth, perps_config: PerpsConfig) -> AsyncPerpsClient:
    """An authenticated async perps client on the demo perps base URL."""
    return AsyncPerpsClient(auth=test_auth, config=perps_config)
