"""Integration tests for the perps SCM (Klear) client — live demo.

The Klear (Self-Clearing-Member) API authenticates with a pre-generated Bearer
token (``Authorization: Bearer <admin_user_id>:<access_token>``), NOT RSA-PSS, and
the demo server generally cannot service it without a margin-enabled SCM account.
So only a construction smoke test runs under the default ``@pytest.mark.integration``
marker; the actual SCM data calls are gated behind
``@pytest.mark.integration_real_api_only`` (skipped unless
``KALSHI_ENABLE_REAL_API_ONLY=1`` against a prod-like SCM account).

Credentials for the real-api-only path are read from the environment:
    KALSHI_KLEAR_ADMIN_USER_ID, KALSHI_KLEAR_ACCESS_TOKEN
"""

from __future__ import annotations

import os

import pytest

from kalshi.perps.klear import KlearClient
from kalshi.perps.klear.config import DEMO_KLEAR_URL
from kalshi.perps.klear.models.margin import GetSettlementBalanceResponse


@pytest.mark.integration
def test_klear_client_constructs_with_bearer_credentials() -> None:
    """A demo Klear client constructs with Bearer credentials and demo routing.

    No network call — this verifies the demo routing and that the Bearer header
    is wired, which is safe to run on every integration session.
    """
    with KlearClient(
        admin_user_id="smoke-admin", access_token="smoke-token", demo=True
    ) as client:
        assert client._config.base_url == DEMO_KLEAR_URL
        assert client._auth.authorization_header() == "Bearer smoke-admin:smoke-token"


@pytest.mark.integration
@pytest.mark.integration_real_api_only
class TestKlearRealApiOnly:
    def test_settlement_balance(self) -> None:
        """Call a Klear SCM endpoint with real Bearer credentials.

        Skipped by default (demo cannot service Klear without a margin-enabled
        SCM account). Enable with ``KALSHI_ENABLE_REAL_API_ONLY=1`` and the
        ``KALSHI_KLEAR_ADMIN_USER_ID`` / ``KALSHI_KLEAR_ACCESS_TOKEN`` set.
        """
        if not os.environ.get("KALSHI_KLEAR_ADMIN_USER_ID") or not os.environ.get(
            "KALSHI_KLEAR_ACCESS_TOKEN"
        ):
            pytest.skip("KALSHI_KLEAR_ADMIN_USER_ID / KALSHI_KLEAR_ACCESS_TOKEN not set")

        with KlearClient.from_env() as client:
            resp = client.margin.settlement_balance()
            assert isinstance(resp, GetSettlementBalanceResponse)
