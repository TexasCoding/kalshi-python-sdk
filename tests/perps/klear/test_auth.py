"""Tests for the Klear (SCM) Bearer auth (migrated from cookie-session, #443)."""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from kalshi.errors import KalshiAuthError
from kalshi.perps.klear import AsyncKlearClient, KlearAuth, KlearClient, KlearConfig

BASE = "https://demo-api.kalshi.co/klear-api/v1"
EXPECTED_HEADER = "Bearer test-admin:test-token"
_BALANCE_BODY = {"user_id": "u1", "balance_available_centicents": 0}


class TestKlearAuth:
    def test_authorization_header_format(self) -> None:
        auth = KlearAuth("admin-123", "tok-abc")
        assert auth.authorization_header() == "Bearer admin-123:tok-abc"
        assert auth.admin_user_id == "admin-123"
        assert auth.access_token == "tok-abc"

    def test_empty_credentials_rejected(self) -> None:
        with pytest.raises(ValueError):
            KlearAuth("", "tok")
        with pytest.raises(ValueError):
            KlearAuth("admin", "")
        # Whitespace-only is also rejected (would yield a malformed header).
        with pytest.raises(ValueError):
            KlearAuth("   ", "tok")
        with pytest.raises(ValueError):
            KlearAuth("admin", "  ")

    def test_padded_credentials_are_stripped(self) -> None:
        # Surrounding whitespace is stripped before storage so the header is
        # well-formed (not "Bearer   admin-id  :  tok  ").
        auth = KlearAuth("  admin-id  ", "  tok  ")
        assert auth.admin_user_id == "admin-id"
        assert auth.access_token == "tok"
        assert auth.authorization_header() == "Bearer admin-id:tok"

    def test_repr_redacts_access_token(self) -> None:
        auth = KlearAuth("admin-123", "SECRET-TOKEN")
        assert "SECRET-TOKEN" not in repr(auth)
        assert "SECRET-TOKEN" not in str(auth)
        assert "admin-123" in repr(auth)


class TestBearerHeaderInjection:
    @respx.mock
    def test_header_sent_on_every_request(self, klear_client: KlearClient) -> None:
        route = respx.get(f"{BASE}/margin/settlement_balance").mock(
            return_value=httpx.Response(200, json=_BALANCE_BODY)
        )
        klear_client.margin.settlement_balance()
        assert route.calls.last.request.headers.get("authorization") == EXPECTED_HEADER
        klear_client.close()

    @respx.mock
    def test_header_on_paginated_endpoint(self, klear_client: KlearClient) -> None:
        route = respx.get(f"{BASE}/margin/obligation_history").mock(
            return_value=httpx.Response(200, json={"obligations": [], "cursor": ""})
        )
        klear_client.margin.obligation_history()
        assert route.calls.last.request.headers.get("authorization") == EXPECTED_HEADER
        klear_client.close()

    @respx.mock
    def test_401_maps_to_auth_error(self, klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_balance").mock(
            return_value=httpx.Response(401, json={"code": "unauthorized", "message": "bad token"})
        )
        with pytest.raises(KalshiAuthError):
            klear_client.margin.settlement_balance()
        klear_client.close()


class TestSecurityRedaction:
    @respx.mock
    def test_access_token_not_in_logs(
        self, klear_config: KlearConfig, caplog: pytest.LogCaptureFixture
    ) -> None:
        respx.get(f"{BASE}/margin/settlement_balance").mock(
            return_value=httpx.Response(200, json=_BALANCE_BODY)
        )
        client = KlearClient(
            admin_user_id="admin-x", access_token="LOG-SECRET-TOKEN", config=klear_config
        )
        with caplog.at_level(logging.DEBUG, logger="kalshi"):
            client.margin.settlement_balance()
        blob = "\n".join(rec.getMessage() for rec in caplog.records)
        assert "LOG-SECRET-TOKEN" not in blob
        client.close()


class TestFromEnv:
    def test_from_env_reads_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KALSHI_KLEAR_ADMIN_USER_ID", "env-admin")
        monkeypatch.setenv("KALSHI_KLEAR_ACCESS_TOKEN", "env-token")
        monkeypatch.setenv("KALSHI_KLEAR_DEMO", "true")
        client = KlearClient.from_env()
        assert client._auth.authorization_header() == "Bearer env-admin:env-token"
        client.close()

    def test_from_env_missing_credentials_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_KLEAR_ADMIN_USER_ID", raising=False)
        monkeypatch.delenv("KALSHI_KLEAR_ACCESS_TOKEN", raising=False)
        with pytest.raises(ValueError):
            KlearClient.from_env()

    def test_from_env_one_credential_missing_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Either credential alone is insufficient.
        monkeypatch.setenv("KALSHI_KLEAR_ADMIN_USER_ID", "env-admin")
        monkeypatch.delenv("KALSHI_KLEAR_ACCESS_TOKEN", raising=False)
        with pytest.raises(ValueError):
            KlearClient.from_env()
        monkeypatch.delenv("KALSHI_KLEAR_ADMIN_USER_ID", raising=False)
        monkeypatch.setenv("KALSHI_KLEAR_ACCESS_TOKEN", "env-token")
        with pytest.raises(ValueError):
            KlearClient.from_env()


class TestAsync:
    @respx.mock
    async def test_async_header_injection(self, async_klear_client: AsyncKlearClient) -> None:
        route = respx.get(f"{BASE}/margin/settlement_balance").mock(
            return_value=httpx.Response(200, json=_BALANCE_BODY)
        )
        await async_klear_client.margin.settlement_balance()
        assert route.calls.last.request.headers.get("authorization") == EXPECTED_HEADER
        await async_klear_client.close()
