"""Fixtures for the Klear (SCM) test package."""

from __future__ import annotations

import os

import pytest

from kalshi.perps.klear import AsyncKlearClient, KlearClient, KlearConfig

# Hermetic env: strip any Klear overrides the developer's shell may export.
for _v in ("KALSHI_KLEAR_API_BASE_URL", "KALSHI_KLEAR_DEMO", "KALSHI_KLEAR_ALLOW_UNKNOWN_HOST"):
    os.environ.pop(_v, None)

KLEAR_BASE = "https://demo-api.kalshi.co/klear-api/v1"


@pytest.fixture
def klear_config() -> KlearConfig:
    return KlearConfig.demo(timeout=5.0, max_retries=2)


@pytest.fixture
def klear_client(klear_config: KlearConfig) -> KlearClient:
    return KlearClient(config=klear_config)


@pytest.fixture
def async_klear_client(klear_config: KlearConfig) -> AsyncKlearClient:
    return AsyncKlearClient(config=klear_config)
