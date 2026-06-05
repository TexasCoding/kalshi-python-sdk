"""Integration tests for the perps SCM (Klear) client — live demo.

The Klear (Self-Clearing-Member) API authenticates with email + password (+ MFA)
via ``POST /log_in`` — a session-cookie model, NOT RSA-PSS — and the demo server
generally cannot service it without a margin-enabled SCM account. So only a
construction smoke test runs under the default ``@pytest.mark.integration``
marker; the actual login + SCM data calls are gated behind
``@pytest.mark.integration_real_api_only`` (skipped unless
``KALSHI_ENABLE_REAL_API_ONLY=1`` against a prod-like SCM account).

Credentials for the real-api-only path are read from the environment:
    KALSHI_KLEAR_EMAIL, KALSHI_KLEAR_PASSWORD, KALSHI_KLEAR_MFA_CODE (optional)
"""

from __future__ import annotations

import os

import pytest

from kalshi.perps.klear import KlearClient
from kalshi.perps.klear.config import DEMO_KLEAR_URL
from kalshi.perps.klear.models.auth import LogInResponse


@pytest.mark.integration
def test_klear_client_constructs_unauthenticated() -> None:
    """A fresh demo Klear client is unauthenticated until ``login`` succeeds.

    No network call — this verifies the demo routing and the pre-login auth
    state, which is safe to run on every integration session.
    """
    with KlearClient(demo=True) as client:
        assert client._config.base_url == DEMO_KLEAR_URL
        assert client.is_authenticated is False


@pytest.mark.integration
@pytest.mark.integration_real_api_only
class TestKlearLoginRealApiOnly:
    def test_login(self) -> None:
        """Log in to the Klear API with real SCM credentials.

        Skipped by default (demo cannot service Klear without a margin-enabled
        SCM account). Enable with ``KALSHI_ENABLE_REAL_API_ONLY=1`` and the
        ``KALSHI_KLEAR_*`` credentials set.
        """
        email = os.environ.get("KALSHI_KLEAR_EMAIL")
        password = os.environ.get("KALSHI_KLEAR_PASSWORD")
        if not email or not password:
            pytest.skip("KALSHI_KLEAR_EMAIL / KALSHI_KLEAR_PASSWORD not set")
        code = os.environ.get("KALSHI_KLEAR_MFA_CODE")

        with KlearClient.from_env() as client:
            resp = client.login(email=email, password=password, code=code)
            assert isinstance(resp, LogInResponse)
            # If MFA is required and no code was supplied, re-call with the code.
            if resp.required_mfa_method and code:
                resp = client.login(email=email, password=password, code=code)
                assert isinstance(resp, LogInResponse)
