"""Tests for kalshi.auth — RSA-PSS signing."""

from __future__ import annotations

import asyncio
import base64
import os
import tempfile

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi.auth import KalshiAuth, _normalize_percent_encoding
from kalshi.errors import KalshiAuthError


class TestNormalizePercentEncoding:
    """#261: short-circuit when the path contains no ``%`` so the hot REST
    signing path doesn't burn a regex compile + scan per request."""

    def test_no_percent_returns_input_identity(self) -> None:
        # Identity (``is``) is the contract — short-circuit must not allocate.
        path = "/trade-api/v2/markets"
        assert _normalize_percent_encoding(path) is path

    def test_uppercase_percent_passthrough(self) -> None:
        path = "/trade-api/v2/markets/ABC%2FDEF"
        assert _normalize_percent_encoding(path) == path

    def test_lowercase_percent_uppercased(self) -> None:
        assert (
            _normalize_percent_encoding("/trade-api/v2/markets/ABC%2fDEF")
            == "/trade-api/v2/markets/ABC%2FDEF"
        )


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
            sig,
            expected_msg,
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
            sig,
            expected_msg,
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
            sig,
            expected_msg,
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
            sig,
            expected_msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )

    def test_encoded_and_decoded_paths_differ(self, test_auth: KalshiAuth) -> None:
        """Encoded and decoded paths produce different signatures.
        %2D is the encoding of '-', but the signing payload preserves the
        encoding rather than decoding it."""
        h1 = test_auth.sign_request("GET", "/trade-api/v2/events/TICKER%2DNAME", timestamp_ms=1000)
        h2 = test_auth.sign_request("GET", "/trade-api/v2/events/TICKER-NAME", timestamp_ms=1000)
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

        h1 = test_auth.sign_request("GET", "/trade-api/v2/events/TICKER%2dNAME", timestamp_ms=1000)
        h2 = test_auth.sign_request("GET", "/trade-api/v2/events/TICKER%2DNAME", timestamp_ms=1000)

        # Both signatures must verify against the same canonical message
        sig1 = base64.b64decode(h1["KALSHI-ACCESS-SIGNATURE"])
        sig2 = base64.b64decode(h2["KALSHI-ACCESS-SIGNATURE"])
        pub.verify(sig1, canonical_msg, pss, hashes.SHA256())
        pub.verify(sig2, canonical_msg, pss, hashes.SHA256())


class TestSignRequestAsync:
    """Async sign offload (#178).

    Verifies the executor-offloaded path produces identical signatures to the
    sync path, and (in the loop-blocking microbench) that signing in flight
    does not stall the event loop.
    """

    @pytest.mark.asyncio
    async def test_async_signature_verifies_for_same_message(self, test_auth: KalshiAuth) -> None:
        """Sync and async signing produce headers that both verify against the
        same canonical message. RSA-PSS is randomized (PSS salt), so signature
        bytes differ between calls — assert verifiability, not equality.
        """
        ts = 1703123456789
        sync_headers = test_auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=ts)
        async_headers = await test_auth.sign_request_async(
            "GET", "/trade-api/v2/markets", timestamp_ms=ts
        )
        assert async_headers["KALSHI-ACCESS-KEY"] == sync_headers["KALSHI-ACCESS-KEY"]
        assert async_headers["KALSHI-ACCESS-TIMESTAMP"] == sync_headers["KALSHI-ACCESS-TIMESTAMP"]
        pub = test_auth._private_key.public_key()
        canonical = (str(ts) + "GET/trade-api/v2/markets").encode("utf-8")
        pss = padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        )
        pub.verify(
            base64.b64decode(sync_headers["KALSHI-ACCESS-SIGNATURE"]),
            canonical,
            pss,
            hashes.SHA256(),
        )
        pub.verify(
            base64.b64decode(async_headers["KALSHI-ACCESS-SIGNATURE"]),
            canonical,
            pss,
            hashes.SHA256(),
        )

    @pytest.mark.asyncio
    async def test_lazy_executor_creation(self, test_auth: KalshiAuth) -> None:
        assert test_auth._sign_executor is None
        await test_auth.sign_request_async("GET", "/x", timestamp_ms=1)
        assert test_auth._sign_executor is not None
        # Idempotent — second call reuses the same pool.
        first = test_auth._sign_executor
        await test_auth.sign_request_async("GET", "/y", timestamp_ms=2)
        assert test_auth._sign_executor is first
        test_auth.close()
        assert test_auth._sign_executor is None

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, test_auth: KalshiAuth) -> None:
        """Double-close (and triple-close) must not raise. The terminality
        check lives in ``test_close_is_terminal_no_silent_respawn`` /
        ``test_closed_auth_raises_on_sign_request_async``."""
        test_auth.close()  # no executor yet
        test_auth.close()
        test_auth.close()  # triple-close OK

    @pytest.mark.asyncio
    async def test_closed_auth_raises_on_sign_request_async(
        self,
        test_auth: KalshiAuth,
    ) -> None:
        """P4.6: ``close()`` is terminal — a subsequent ``sign_request_async``
        raises ``RuntimeError`` instead of silently respawning the
        ThreadPoolExecutor (which would defeat the lifecycle contract and
        prevent clients from detecting use-after-close in tests)."""
        await test_auth.sign_request_async("GET", "/x", timestamp_ms=1)
        test_auth.close()
        with pytest.raises(RuntimeError, match=r"KalshiAuth has been closed"):
            await test_auth.sign_request_async("GET", "/y", timestamp_ms=2)

    @pytest.mark.asyncio
    async def test_close_is_terminal_no_silent_respawn(
        self,
        test_auth: KalshiAuth,
    ) -> None:
        """P4.6: after ``close()``, the executor stays None — the lazy-init
        in ``_get_sign_executor`` never reinstates it. Pre-fix it would
        have re-allocated a fresh ``ThreadPoolExecutor`` on the next
        async sign, leaking resources past the lifecycle bound."""
        await test_auth.sign_request_async("GET", "/x", timestamp_ms=1)
        assert test_auth._sign_executor is not None
        test_auth.close()
        assert test_auth._sign_executor is None
        with pytest.raises(RuntimeError):
            await test_auth.sign_request_async("GET", "/y", timestamp_ms=2)
        assert test_auth._sign_executor is None  # no silent respawn

    @pytest.mark.asyncio
    async def test_close_during_locked_init_does_not_spawn_executor(
        self,
        test_auth: KalshiAuth,
    ) -> None:
        """#267 item 1: simulate close() racing with the locked branch of
        ``_get_sign_executor``. Pre-fix, thread A saw ``_closed=False`` outside
        the lock, ``close()`` then ran to completion, and thread A still
        entered the locked init and spun up a fresh ``ThreadPoolExecutor`` on
        a closed auth — leaking the pool past the documented lifecycle bound.
        Post-fix the recheck under the lock raises before construction.
        """
        # Force the fast path to fall through (no cached executor), then
        # interpose ``close()`` between the fast-path check and the locked
        # construction by wrapping the lock's ``__enter__``.
        assert test_auth._sign_executor is None
        original_lock = test_auth._sign_executor_lock

        class _RacyLock:
            def __init__(self, inner: object, auth: KalshiAuth) -> None:
                self._inner = inner
                self._auth = auth
                self._fired = False

            def __enter__(self) -> object:
                # Race: close() runs after the lock-free check observed
                # _closed=False but before we hold the lock. Restore the
                # real lock first so close()'s own ``with`` uses it (and
                # so we only fire the race once).
                if not self._fired:
                    self._fired = True
                    self._auth._sign_executor_lock = self._inner  # type: ignore[assignment]
                    self._auth.close()
                return self._inner.__enter__()  # type: ignore[attr-defined]

            def __exit__(self, *exc: object) -> None:
                self._inner.__exit__(*exc)  # type: ignore[attr-defined]

        test_auth._sign_executor_lock = _RacyLock(original_lock, test_auth)  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match=r"KalshiAuth has been closed"):
                test_auth._get_sign_executor()
        finally:
            test_auth._sign_executor_lock = original_lock
        assert test_auth._sign_executor is None, (
            "raced close() must not leave a fresh ThreadPoolExecutor dangling"
        )

    @pytest.mark.asyncio
    async def test_concurrent_signs_do_not_stall_event_loop(self, test_auth: KalshiAuth) -> None:
        """Microbench (#178). Run a real ``asyncio.sleep(0.01)`` ticker
        concurrently with a batch of signs and confirm the ticker's
        observed gaps stay tight.

        Pre-offload (signs inline on the loop) the ticker would see gaps
        proportional to the inline sign work (~1-3 ms per sign x N signs
        between ticks). Post-offload, signs run on the dedicated executor
        and the ticker only sees scheduler jitter.

        The threshold is generous (max gap < 30 ms) so this test stays
        green under load on CI runners. It's a regression bound, not a
        precision benchmark — the script under ``scripts/`` runs the
        precision version.
        """
        loop = asyncio.get_running_loop()
        gaps: list[float] = []
        target_interval = 0.01

        async def ticker() -> None:
            last = loop.time()
            for _ in range(40):
                await asyncio.sleep(target_interval)
                now = loop.time()
                gaps.append(now - last - target_interval)
                last = now

        async def signs() -> None:
            # 200 signs covers a realistic batch_create burst.
            for _ in range(200):
                await test_auth.sign_request_async("GET", "/trade-api/v2/markets", timestamp_ms=1)

        await asyncio.gather(ticker(), signs())
        test_auth.close()

        # Slack: schedule jitter + threadpool dispatch can each cost a few ms.
        # Pre-offload inline RSA-PSS would push the max gap well past this.
        assert max(gaps) < 0.030, f"max ticker gap {max(gaps) * 1000:.1f}ms exceeds 30ms budget"


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

    @pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permission checks")
    def test_permission_denied_wraps_with_helpful_message(self, pem_bytes: bytes) -> None:
        """A key file the user can't read raises KalshiAuthError, not PermissionError."""
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_bytes)
            f.flush()
            path = f.name
        try:
            os.chmod(path, 0o000)
            with pytest.raises(KalshiAuthError, match="Permission denied"):
                KalshiAuth.from_key_path("my-key", path)
        finally:
            os.chmod(path, 0o600)
            os.unlink(path)

    def test_passphrase_protected_key_raises_helpful_error(
        self, rsa_private_key: rsa.RSAPrivateKey
    ) -> None:
        """Encrypted keys produce a KalshiAuthError pointing at the openssl fix."""
        encrypted_pem = rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(b"pw"),
        )
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(encrypted_pem)
            f.flush()
            path = f.name
        try:
            with pytest.raises(KalshiAuthError) as exc_info:
                KalshiAuth.from_key_path("my-key", path)
            msg = str(exc_info.value)
            assert "Passphrase-protected" in msg
            assert "openssl pkey" in msg
        finally:
            os.unlink(path)


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

    def test_issue_335_from_pem_openssh_format_error_message(self) -> None:
        openssh_pem = (
            b"-----BEGIN OPENSSH PRIVATE KEY-----\n"
            b"b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAAB\n"
            b"-----END OPENSSH PRIVATE KEY-----\n"
        )
        with pytest.raises(KalshiAuthError, match="OpenSSH private-key format") as exc:
            KalshiAuth.from_pem("key-ossh", openssh_pem)
        assert "ssh-keygen -p -m PKCS8" in str(exc.value)


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

    def test_from_pem_env_var(self, monkeypatch: pytest.MonkeyPatch, pem_string: str) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        auth = KalshiAuth.from_env()
        assert auth.key_id == "env-key"

    def test_from_path_env_var(self, monkeypatch: pytest.MonkeyPatch, pem_bytes: bytes) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_bytes)
            f.flush()
            monkeypatch.setenv("KALSHI_KEY_ID", "path-key")
            monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
            monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", f.name)
            auth = KalshiAuth.from_env()
            assert auth.key_id == "path-key"
        os.unlink(f.name)

    def test_from_env_rejects_both_pem_and_path_set(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        """#249: ``from_env`` must raise when both ``KALSHI_PRIVATE_KEY`` and
        ``KALSHI_PRIVATE_KEY_PATH`` are populated. Silent precedence (PEM wins)
        hid key-rotation mishaps; the message must name both env vars so the
        misconfiguration is obvious from a single 401/403 incident."""
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_string.encode())
            f.flush()
            try:
                monkeypatch.setenv("KALSHI_KEY_ID", "conflict-key")
                monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
                monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", f.name)
                with pytest.raises(
                    KalshiAuthError,
                    match=r"KALSHI_PRIVATE_KEY.*KALSHI_PRIVATE_KEY_PATH",
                ):
                    KalshiAuth.from_env()
            finally:
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

    def test_returns_none_when_key_id_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        auth = KalshiAuth.try_from_env()
        assert auth is None

    def test_returns_none_when_key_id_set_but_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "test-key")
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        auth = KalshiAuth.try_from_env()
        assert auth is None

    def test_try_from_env_rejects_both_pem_and_path_set(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        """#249: mirror of the ``from_env`` regression — ``try_from_env`` must
        raise (not return ``None``, not silently pick PEM) when both env vars
        are populated to non-empty values."""
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_string.encode())
            f.flush()
            try:
                monkeypatch.setenv("KALSHI_KEY_ID", "conflict-key")
                monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
                monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", f.name)
                with pytest.raises(
                    KalshiAuthError,
                    match=r"KALSHI_PRIVATE_KEY.*KALSHI_PRIVATE_KEY_PATH",
                ):
                    KalshiAuth.try_from_env()
            finally:
                os.unlink(f.name)


class TestPassphraseSupport:
    """#217: KalshiAuth loaders accept ``password=`` so callers don't have to
    write plaintext keys to disk just to use this SDK.
    """

    @staticmethod
    def _encrypted_pem(key: rsa.RSAPrivateKey, passphrase: bytes) -> bytes:
        return key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(passphrase),
        )

    def test_from_pem_with_passphrase_succeeds(self, rsa_private_key: rsa.RSAPrivateKey) -> None:
        encrypted = self._encrypted_pem(rsa_private_key, b"correct-horse")
        auth = KalshiAuth.from_pem("key", encrypted, password="correct-horse")
        assert auth.key_id == "key"
        # Sanity-check signing still works post-load.
        headers = auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=1000)
        assert headers["KALSHI-ACCESS-KEY"] == "key"

    def test_from_pem_with_passphrase_bytes_succeeds(
        self, rsa_private_key: rsa.RSAPrivateKey
    ) -> None:
        encrypted = self._encrypted_pem(rsa_private_key, b"correct-horse")
        auth = KalshiAuth.from_pem("key", encrypted, password=b"correct-horse")
        assert auth.key_id == "key"

    def test_from_pem_with_wrong_passphrase_raises_KalshiAuthError(  # noqa: N802
        self, rsa_private_key: rsa.RSAPrivateKey
    ) -> None:
        encrypted = self._encrypted_pem(rsa_private_key, b"correct-horse")
        with pytest.raises(KalshiAuthError, match=r"Invalid PEM private key"):
            KalshiAuth.from_pem("key", encrypted, password="wrong")

    def test_from_pem_encrypted_without_password_points_at_password_kwarg(
        self, rsa_private_key: rsa.RSAPrivateKey
    ) -> None:
        encrypted = self._encrypted_pem(rsa_private_key, b"pw")
        with pytest.raises(KalshiAuthError) as exc_info:
            KalshiAuth.from_pem("key", encrypted)
        msg = str(exc_info.value)
        # New message mentions both the password= kwarg and the legacy openssl recipe.
        assert "password=" in msg
        assert "KALSHI_PRIVATE_KEY_PASSPHRASE" in msg
        assert "openssl pkey" in msg

    def test_from_pem_with_callable_passphrase_invoked(
        self, rsa_private_key: rsa.RSAPrivateKey
    ) -> None:
        encrypted = self._encrypted_pem(rsa_private_key, b"sekrit")
        calls = {"n": 0}

        def supply_pw() -> bytes:
            calls["n"] += 1
            return b"sekrit"

        auth = KalshiAuth.from_pem("k", encrypted, password=supply_pw)
        assert auth.key_id == "k"
        assert calls["n"] == 1, "callable passphrase must be invoked exactly once"

    def test_from_key_path_with_passphrase_succeeds(
        self, rsa_private_key: rsa.RSAPrivateKey
    ) -> None:
        encrypted = self._encrypted_pem(rsa_private_key, b"pw")
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(encrypted)
            f.flush()
            path = f.name
        try:
            auth = KalshiAuth.from_key_path("k", path, password="pw")
            assert auth.key_id == "k"
        finally:
            os.unlink(path)

    def test_from_env_picks_up_KALSHI_PRIVATE_KEY_PASSPHRASE(  # noqa: N802
        self,
        monkeypatch: pytest.MonkeyPatch,
        rsa_private_key: rsa.RSAPrivateKey,
    ) -> None:
        encrypted = self._encrypted_pem(rsa_private_key, b"envpw")
        monkeypatch.setenv("KALSHI_KEY_ID", "env-encrypted")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", encrypted.decode("utf-8"))
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PASSPHRASE", "envpw")
        auth = KalshiAuth.from_env()
        assert auth.key_id == "env-encrypted"

    def test_from_env_explicit_password_beats_env_passphrase(
        self,
        monkeypatch: pytest.MonkeyPatch,
        rsa_private_key: rsa.RSAPrivateKey,
    ) -> None:
        encrypted = self._encrypted_pem(rsa_private_key, b"realpw")
        monkeypatch.setenv("KALSHI_KEY_ID", "env-encrypted")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", encrypted.decode("utf-8"))
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PASSPHRASE", "wrong-pw-in-env")
        # Explicit kwarg overrides the env var: load must succeed with realpw.
        auth = KalshiAuth.from_env(password="realpw")
        assert auth.key_id == "env-encrypted"

    def test_try_from_env_picks_up_KALSHI_PRIVATE_KEY_PASSPHRASE(  # noqa: N802
        self,
        monkeypatch: pytest.MonkeyPatch,
        rsa_private_key: rsa.RSAPrivateKey,
    ) -> None:
        encrypted = self._encrypted_pem(rsa_private_key, b"envpw")
        monkeypatch.setenv("KALSHI_KEY_ID", "env-encrypted")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", encrypted.decode("utf-8"))
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PASSPHRASE", "envpw")
        auth = KalshiAuth.try_from_env()
        assert auth is not None
        assert auth.key_id == "env-encrypted"


class TestTrailingSlashCanonicalization:
    """P1.6: the transport canonicalizes trailing slashes BEFORE both signing
    and the httpx call, so a future ``/markets/`` couldn't desync wire-path and
    signed-path.
    """

    def test_trailing_slash_path_canonicalized(
        self,
        rsa_private_key: rsa.RSAPrivateKey,
        test_auth: KalshiAuth,
    ) -> None:
        import httpx
        import respx

        from kalshi._base_client import SyncTransport
        from kalshi.config import KalshiConfig

        config = KalshiConfig(base_url="https://test.kalshi.com/trade-api/v2", timeout=5.0)
        transport = SyncTransport(test_auth, config)
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        with respx.mock:
            # Match the canonicalized (no-trailing-slash) URL — if the transport
            # forwarded "/markets/" to httpx, respx would 404 this request.
            respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(side_effect=handler)
            resp = transport.request("GET", "/markets/")
        assert resp.status_code == 200
        sent = captured[0]
        # Wire URL was canonicalized to the no-slash form.
        assert sent.url.path == "/trade-api/v2/markets"
        # Signed path agrees with the wire path: re-derive the expected message
        # from the timestamp header and check the signature verifies against
        # the canonical (no-slash) form.
        ts = sent.headers["KALSHI-ACCESS-TIMESTAMP"]
        sig = base64.b64decode(sent.headers["KALSHI-ACCESS-SIGNATURE"])
        canonical = f"{ts}GET/trade-api/v2/markets".encode()
        rsa_private_key.public_key().verify(
            sig,
            canonical,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        transport.close()
