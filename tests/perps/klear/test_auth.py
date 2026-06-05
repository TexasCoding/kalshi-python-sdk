"""Tests for the Klear (SCM) auth foundation (#399)."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from kalshi.errors import KalshiAuthError, KalshiRateLimitError
from kalshi.perps.klear import (
    AsyncKlearClient,
    KlearAuth,
    KlearClient,
    KlearConfig,
    LogInRequest,
    LogInResponse,
)

BASE = "https://demo-api.kalshi.co/klear-api/v1"


class TestLogInHappyPath:
    @respx.mock
    def test_login_captures_cookie_and_marks_session(self, klear_client: KlearClient) -> None:
        login = respx.post(f"{BASE}/log_in").mock(
            return_value=httpx.Response(
                200,
                json={"token": "TOK", "user_id": "u1", "access_level": "admin"},
                headers={"Set-Cookie": "session=COOKIEVAL; Path=/"},
            )
        )
        probe = respx.get(f"{BASE}/margin/settlement_balance").mock(
            return_value=httpx.Response(200, json={})
        )
        assert klear_client.is_authenticated is False
        resp = klear_client.login(email="a@b.com", password="pw")
        assert resp.required_mfa_method is None
        assert resp.token == "TOK"
        assert klear_client.is_authenticated is True
        # Body omits `code` when None.
        sent = json.loads(login.calls.last.request.content)
        assert sent == {"email": "a@b.com", "password": "pw"}
        # The captured session cookie is replayed on the next request.
        klear_client._transport.request("GET", "/margin/settlement_balance")
        assert "session=COOKIEVAL" in probe.calls.last.request.headers.get("cookie", "")
        klear_client.close()

    @respx.mock
    def test_login_body_includes_code_when_provided(self, klear_client: KlearClient) -> None:
        login = respx.post(f"{BASE}/log_in").mock(
            return_value=httpx.Response(
                200, json={"token": "T"}, headers={"Set-Cookie": "session=x"}
            )
        )
        klear_client.login(email="a@b.com", password="pw", code="123456")
        body = json.loads(login.calls.last.request.content)
        assert body["code"] == "123456"
        klear_client.close()


class TestMfaChallenge:
    @respx.mock
    def test_mfa_returns_without_autoretry(self, klear_client: KlearClient) -> None:
        route = respx.post(f"{BASE}/log_in").mock(
            return_value=httpx.Response(200, json={"required_mfa_method": "totp"})
        )
        resp = klear_client.login(email="a@b.com", password="pw")
        assert resp.required_mfa_method == "totp"
        assert klear_client.is_authenticated is False  # not active until code supplied
        assert route.call_count == 1  # SDK does not conjure the OOB code / auto-loop
        klear_client.close()


class TestErrorPaths:
    @respx.mock
    def test_401_maps_and_does_not_leak_credentials(self, klear_client: KlearClient) -> None:
        respx.post(f"{BASE}/log_in").mock(
            return_value=httpx.Response(401, json={"code": "unauthorized", "message": "bad creds"})
        )
        with pytest.raises(KalshiAuthError) as ei:
            klear_client.login(email="leak@x.com", password="leak-secret")
        msg = str(ei.value)
        assert "leak@x.com" not in msg and "leak-secret" not in msg
        klear_client.close()

    @respx.mock
    def test_429_not_retried(self) -> None:
        route = respx.post(f"{BASE}/log_in").mock(
            return_value=httpx.Response(429, json={"code": "rl", "message": "slow"})
        )
        client = KlearClient(config=KlearConfig.demo(max_retries=3))
        with pytest.raises(KalshiRateLimitError):
            client.login(email="a@b", password="p")
        assert route.call_count == 1  # POST /log_in is never retried
        client.close()


class TestSecurityRedaction:
    def test_login_request_repr_redacts(self) -> None:
        r = LogInRequest(email="a@b.com", password="hunter2", code="999")
        for secret in ("a@b.com", "hunter2", "999"):
            assert secret not in repr(r)
            assert secret not in str(r)

    def test_login_response_repr_redacts_token(self) -> None:
        r = LogInResponse(token="SECRET-TOKEN", user_id="u", required_mfa_method=None)
        assert "SECRET-TOKEN" not in repr(r)
        assert "required_mfa_method=None" in repr(r)  # the MFA signal is surfaced

    def test_klear_auth_repr_redacts_token(self) -> None:
        a = KlearAuth()
        a.mark_logged_in("SECRET")
        assert "SECRET" not in repr(a)
        assert repr(a) == "KlearAuth(authenticated=True)"

    @respx.mock
    def test_no_credentials_in_logs(
        self, klear_client: KlearClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        respx.post(f"{BASE}/log_in").mock(
            return_value=httpx.Response(
                200, json={"token": "T"}, headers={"Set-Cookie": "session=S"}
            )
        )
        with caplog.at_level(logging.DEBUG, logger="kalshi"):
            klear_client.login(email="log-leak@x.com", password="log-secret")
        blob = "\n".join(rec.getMessage() for rec in caplog.records)
        for secret in ("log-leak@x.com", "log-secret", "session=S", "token"):
            assert secret not in blob, f"{secret!r} leaked into logs"
        klear_client.close()


class TestRequestModel:
    def test_extra_forbid(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LogInRequest(email="a", password="b", bogus=1)


class TestAsync:
    @respx.mock
    async def test_async_login_happy(self, async_klear_client: AsyncKlearClient) -> None:
        respx.post(f"{BASE}/log_in").mock(
            return_value=httpx.Response(
                200, json={"token": "T"}, headers={"Set-Cookie": "session=S"}
            )
        )
        resp = await async_klear_client.login(email="a@b.com", password="pw")
        assert resp.token == "T"
        assert async_klear_client.is_authenticated is True
        await async_klear_client.close()

    @respx.mock
    async def test_async_login_401(self, async_klear_client: AsyncKlearClient) -> None:
        respx.post(f"{BASE}/log_in").mock(
            return_value=httpx.Response(401, json={"code": "x", "message": "no"})
        )
        with pytest.raises(KalshiAuthError):
            await async_klear_client.login(email="a@b.com", password="pw")
        await async_klear_client.close()
