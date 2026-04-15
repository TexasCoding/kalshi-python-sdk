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

    def test_percent_encoded_path_preserved_but_normalized(
        self, rsa_private_key: rsa.RSAPrivateKey, test_auth: KalshiAuth
    ) -> None:
        """Percent-encoded paths are signed without decoding, but hex digits
        are normalized to uppercase per RFC 3986 section 2.1."""
        headers = test_auth.sign_request(
            "GET", "/trade-api/v2/events/TICKER%2DNAME", timestamp_ms=1000
        )
        sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        # Signature is against the raw (encoded) path
        expected_msg = b"1000GET/trade-api/v2/events/TICKER%2DNAME"
        rsa_private_key.public_key().verify(
            sig, expected_msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )

    def test_encoded_and_decoded_paths_differ(self, test_auth: KalshiAuth) -> None:
        """Encoded and decoded paths produce different signatures.
        %2D is the encoding of '-', but the signing payload preserves the
        encoding rather than decoding it."""
        h1 = test_auth.sign_request(
            "GET", "/trade-api/v2/events/TICKER%2DNAME", timestamp_ms=1000
        )
        h2 = test_auth.sign_request(
            "GET", "/trade-api/v2/events/TICKER-NAME", timestamp_ms=1000
        )
        assert h1["KALSHI-ACCESS-SIGNATURE"] != h2["KALSHI-ACCESS-SIGNATURE"]

    @pytest.mark.parametrize(
        "input_path,expected_canonical",
        [
            # Already uppercase — no change
            ("/trade-api/v2/markets/ABC%2FDEF", "/trade-api/v2/markets/ABC%2FDEF"),
            # Lowercase hex -> uppercase
            ("/trade-api/v2/markets/ABC%2fDEF", "/trade-api/v2/markets/ABC%2FDEF"),
            # Encoded space
            ("/trade-api/v2/markets/test%20name", "/trade-api/v2/markets/test%20name"),
            # Mixed case multiple
            ("/trade-api/v2/markets/%2F%2f%2F", "/trade-api/v2/markets/%2F%2F%2F"),
            # Lowercase + query (query stripped, then hex uppercased)
            ("/trade-api/v2/markets/ABC%2fDEF?q=1", "/trade-api/v2/markets/ABC%2FDEF"),
            # Lowercase + trailing slash
            ("/trade-api/v2/markets/ABC%2fDEF/", "/trade-api/v2/markets/ABC%2FDEF"),
            # No encoding needed
            ("/trade-api/v2/markets/simple", "/trade-api/v2/markets/simple"),
        ],
        ids=[
            "uppercase_passthrough",
            "lowercase_to_uppercase",
            "encoded_space",
            "mixed_case_multiple",
            "lowercase_plus_query",
            "lowercase_plus_trailing_slash",
            "no_encoding",
        ],
    )
    def test_percent_encoding_canonicalization(
        self,
        rsa_private_key: rsa.RSAPrivateKey,
        test_auth: KalshiAuth,
        input_path: str,
        expected_canonical: str,
    ) -> None:
        """Signing should normalize percent-encoding to uppercase hex."""
        ts = 1000
        headers = test_auth.sign_request("GET", input_path, timestamp_ms=ts)
        sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])

        expected_msg = f"{ts}GET{expected_canonical}".encode()
        # If the signing used the canonical path, verification will succeed.
        # If not, this will raise InvalidSignature.
        rsa_private_key.public_key().verify(
            sig,
            expected_msg,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )

    def test_case_variants_produce_same_canonical_path(
        self,
        rsa_private_key: rsa.RSAPrivateKey,
        test_auth: KalshiAuth,
    ) -> None:
        """Paths differing only in percent-encoding case should sign the same canonical message.

        RSA-PSS uses randomized padding, so signatures differ between calls even
        for the same input. Instead, verify both signatures against the canonical
        (uppercase) message.
        """
        canonical_msg = b"1000GET/trade-api/v2/events/TICKER%2DNAME"
        pub = rsa_private_key.public_key()
        pss = padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        )

        h1 = test_auth.sign_request(
            "GET", "/trade-api/v2/events/TICKER%2dNAME", timestamp_ms=1000
        )
        h2 = test_auth.sign_request(
            "GET", "/trade-api/v2/events/TICKER%2DNAME", timestamp_ms=1000
        )

        # Both signatures must verify against the same canonical message
        sig1 = base64.b64decode(h1["KALSHI-ACCESS-SIGNATURE"])
        sig2 = base64.b64decode(h2["KALSHI-ACCESS-SIGNATURE"])
        pub.verify(sig1, canonical_msg, pss, hashes.SHA256())
        pub.verify(sig2, canonical_msg, pss, hashes.SHA256())


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


class TestTryFromEnv:
    def test_returns_auth_when_env_vars_set(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "test-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        auth = KalshiAuth.try_from_env()
        assert auth is not None
        assert auth.key_id == "test-key"

    def test_returns_none_when_key_id_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        auth = KalshiAuth.try_from_env()
        assert auth is None

    def test_returns_none_when_key_id_set_but_no_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "test-key")
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        auth = KalshiAuth.try_from_env()
        assert auth is None
