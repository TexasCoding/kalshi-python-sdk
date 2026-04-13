"""Tests for kalshi.auth — RSA-PSS signing."""

from __future__ import annotations

import base64
import os
import tempfile

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi.auth import KalshiAuth
from kalshi.errors import KalshiAuthError


class TestSignRequest:
    def test_returns_three_headers(self, test_auth: KalshiAuth) -> None:
        headers = test_auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=1703123456789)
        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers

    def test_key_id_in_header(self, test_auth: KalshiAuth) -> None:
        headers = test_auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=1000)
        assert headers["KALSHI-ACCESS-KEY"] == "test-key-id"

    def test_timestamp_is_string(self, test_auth: KalshiAuth) -> None:
        headers = test_auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=1703123456789)
        assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1703123456789"

    def test_signature_is_valid_base64(self, test_auth: KalshiAuth) -> None:
        headers = test_auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=1000)
        sig_bytes = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        assert len(sig_bytes) > 0

    def test_signature_verifies(
        self, rsa_private_key: rsa.RSAPrivateKey, test_auth: KalshiAuth
    ) -> None:
        ts = 1703123456789
        method = "GET"
        path = "/trade-api/v2/markets"
        headers = test_auth.sign_request(method, path, timestamp_ms=ts)

        sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        message = f"{ts}{method}{path}".encode()

        # Should not raise
        rsa_private_key.public_key().verify(
            sig,
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )

    def test_strips_query_params(
        self, rsa_private_key: rsa.RSAPrivateKey, test_auth: KalshiAuth
    ) -> None:
        """Signing /path?query=x should produce a signature that verifies against /path."""
        headers = test_auth.sign_request(
            "GET", "/trade-api/v2/markets?limit=50&status=open", timestamp_ms=1000
        )
        sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        # The signature should verify against the STRIPPED path (no query params)
        expected_msg = b"1000GET/trade-api/v2/markets"
        rsa_private_key.public_key().verify(
            sig, expected_msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )

    def test_strips_trailing_slash(
        self, rsa_private_key: rsa.RSAPrivateKey, test_auth: KalshiAuth
    ) -> None:
        """Signing /path/ should produce a signature that verifies against /path."""
        headers = test_auth.sign_request("GET", "/trade-api/v2/markets/", timestamp_ms=1000)
        sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        expected_msg = b"1000GET/trade-api/v2/markets"
        rsa_private_key.public_key().verify(
            sig, expected_msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )

    def test_method_case_insensitive(
        self, rsa_private_key: rsa.RSAPrivateKey, test_auth: KalshiAuth
    ) -> None:
        """Signing with 'get' should produce a signature that verifies against 'GET'."""
        headers = test_auth.sign_request("get", "/trade-api/v2/markets", timestamp_ms=1000)
        sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        expected_msg = b"1000GET/trade-api/v2/markets"
        rsa_private_key.public_key().verify(
            sig, expected_msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )

    def test_auto_generates_timestamp(self, test_auth: KalshiAuth) -> None:
        headers = test_auth.sign_request("GET", "/trade-api/v2/markets")
        ts = int(headers["KALSHI-ACCESS-TIMESTAMP"])
        assert ts > 1_700_000_000_000  # after 2023


class TestFromKeyPath:
    def test_loads_valid_pem_file(self, pem_bytes: bytes) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_bytes)
            f.flush()
            auth = KalshiAuth.from_key_path("my-key", f.name)
            assert auth.key_id == "my-key"
            headers = auth.sign_request("GET", "/test", timestamp_ms=1000)
            assert "KALSHI-ACCESS-SIGNATURE" in headers
        os.unlink(f.name)

    def test_tilde_expansion(self, pem_bytes: bytes) -> None:
        home = os.path.expanduser("~")
        path = os.path.join(home, ".kalshi_test_key.pem")
        try:
            with open(path, "wb") as f:
                f.write(pem_bytes)
            auth = KalshiAuth.from_key_path("my-key", "~/.kalshi_test_key.pem")
            assert auth.key_id == "my-key"
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        with pytest.raises(KalshiAuthError, match="not found"):
            KalshiAuth.from_key_path("my-key", "/nonexistent/path.pem")

    def test_invalid_pem_content(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(b"not a valid PEM file")
            f.flush()
            with pytest.raises(KalshiAuthError, match="Invalid PEM"):
                KalshiAuth.from_key_path("my-key", f.name)
        os.unlink(f.name)


class TestFromPem:
    def test_accepts_bytes(self, pem_bytes: bytes) -> None:
        auth = KalshiAuth.from_pem("key-1", pem_bytes)
        assert auth.key_id == "key-1"

    def test_accepts_string(self, pem_string: str) -> None:
        auth = KalshiAuth.from_pem("key-2", pem_string)
        assert auth.key_id == "key-2"

    def test_rejects_invalid_content(self) -> None:
        with pytest.raises(KalshiAuthError, match="Invalid PEM"):
            KalshiAuth.from_pem("key-3", "garbage data")

    def test_rejects_non_rsa_key(self) -> None:
        from cryptography.hazmat.primitives.asymmetric import ec

        ec_key = ec.generate_private_key(ec.SECP256R1())
        ec_pem = ec_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with pytest.raises(KalshiAuthError, match="Expected RSA"):
            KalshiAuth.from_pem("key-4", ec_pem)


class TestFromEnv:
    def test_missing_key_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        with pytest.raises(KalshiAuthError, match="KALSHI_KEY_ID"):
            KalshiAuth.from_env()

    def test_missing_both_key_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "test-id")
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        with pytest.raises(KalshiAuthError, match="KALSHI_PRIVATE_KEY"):
            KalshiAuth.from_env()

    def test_from_pem_env_var(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        auth = KalshiAuth.from_env()
        assert auth.key_id == "env-key"

    def test_from_path_env_var(
        self, monkeypatch: pytest.MonkeyPatch, pem_bytes: bytes
    ) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_bytes)
            f.flush()
            monkeypatch.setenv("KALSHI_KEY_ID", "path-key")
            monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
            monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", f.name)
            auth = KalshiAuth.from_env()
            assert auth.key_id == "path-key"
        os.unlink(f.name)
