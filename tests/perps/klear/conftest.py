"""Fixtures for the Klear (SCM) test package."""

from __future__ import annotations

import os

import pytest

from kalshi.perps.klear import AsyncKlearClient, KlearClient, KlearConfig

# Hermetic env: strip any Klear overrides the developer's shell may export.
for _v in (
    "KALSHI_KLEAR_API_BASE_URL",
    "KALSHI_KLEAR_DEMO",
    "KALSHI_KLEAR_ALLOW_UNKNOWN_HOST",
    "KALSHI_KLEAR_ADMIN_USER_ID",
    "KALSHI_KLEAR_ACCESS_TOKEN",
):
    os.environ.pop(_v, None)

KLEAR_BASE = "https://demo-api.kalshi.co/klear-api/v1"

# Test Bearer credentials shared across the Klear test package.
TEST_ADMIN_USER_ID = "test-admin"
TEST_ACCESS_TOKEN = "test-token"


@pytest.fixture
def klear_config() -> KlearConfig:
    return KlearConfig.demo(timeout=5.0, max_retries=2)


@pytest.fixture
def klear_client(klear_config: KlearConfig) -> KlearClient:
    return KlearClient(
        admin_user_id=TEST_ADMIN_USER_ID, access_token=TEST_ACCESS_TOKEN, config=klear_config
    )


@pytest.fixture
def async_klear_client(klear_config: KlearConfig) -> AsyncKlearClient:
    return AsyncKlearClient(
        admin_user_id=TEST_ADMIN_USER_ID, access_token=TEST_ACCESS_TOKEN, config=klear_config
    )
