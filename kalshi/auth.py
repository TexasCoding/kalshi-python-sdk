"""RSA-PSS authentication for the Kalshi API.

Signing format:
    message = str(timestamp_ms) + METHOD + /trade-api/v2/endpoint_path
    signature = RSA-PSS(SHA256, MGF1(SHA256), salt_length=DIGEST_LENGTH)
    encoded = base64(signature)

Three headers per request:
    KALSHI-ACCESS-KEY: the API key ID
    KALSHI-ACCESS-SIGNATURE: base64-encoded RSA-PSS signature
    KALSHI-ACCESS-TIMESTAMP: unix timestamp in milliseconds (string)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi.errors import KalshiAuthError

logger = logging.getLogger("kalshi")


def _normalize_percent_encoding(path: str) -> str:
    """Normalize percent-encoded characters to uppercase hex digits.

    RFC 3986 section 2.1: percent-encoded octets should use uppercase
    hex digits for consistency. This ensures signing payloads are
    identical regardless of how the URL was constructed.

    Examples:
        /markets/ABC%2fDEF -> /markets/ABC%2FDEF
        /markets/ABC%2FDEF -> /markets/ABC%2FDEF (no change)
    """
    # #261: vast majority of signed paths contain no percent-encoding (e.g.
    # /trade-api/v2/markets); skip the regex compile + scan in the hot path.
    if "%" not in path:
        return path
    return re.sub(
        r"%([0-9a-fA-F]{2})",
        lambda m: "%" + m.group(1).upper(),
        path,
    )


class KalshiAuth:
    """RSA-PSS request signer for the Kalshi API.

    The private key is loaded once at construction time and cached in memory.
    Thread-safe: RSA signing is stateless.
    """

    def __init__(self, key_id: str, private_key: rsa.RSAPrivateKey) -> None:
        self._key_id = key_id
        self._private_key = private_key
        # Lazy-initialised dedicated ThreadPoolExecutor for async sign offload.
        # Two threads is enough for any realistic REST burst on a single client
        # (RSA-PSS sign ~1-3 ms on a 2048-bit key, ~10 ms on 4096-bit) and
        # keeps crypto off asyncio's default executor - which is shared with
        # `loop.getaddrinfo`, file I/O, and other `to_thread()` work. Without
        # isolation, a cold DNS resolution (5-50 ms) during a reconnect storm
        # would block sign behind it and re-introduce the loop stall as
        # await-latency rather than inline CPU. (#178)
        self._sign_executor: ThreadPoolExecutor | None = None
        self._sign_executor_lock = threading.Lock()
        # Set in close(); checked by _get_sign_executor so async signs after
        # close() raise instead of silently respawning the executor.
        self._closed: bool = False

    @classmethod
    def from_key_path(
        cls,
        key_id: str,
        key_path: str | Path,
        *,
        password: bytes | str | Callable[[], bytes | str] | None = None,
    ) -> KalshiAuth:
        """Load auth from a PEM private key file.

        Supports ~ expansion (e.g., ~/kalshi.pem).

        ``password`` accepts ``str`` / ``bytes`` / a zero-arg callable that
        returns either (the callable form lets you defer fetching the secret
        from a vault until load-time).
        """
        expanded = Path(key_path).expanduser()
        if not expanded.exists():
            raise KalshiAuthError(f"Private key file not found: {expanded}")
        try:
            pem_data = expanded.read_bytes()
        except PermissionError as e:
            raise KalshiAuthError(f"Permission denied reading private key: {expanded}") from e
        return cls.from_pem(key_id, pem_data, password=password)

    @classmethod
    def from_pem(
        cls,
        key_id: str,
        pem_data: str | bytes,
        *,
        password: bytes | str | Callable[[], bytes | str] | None = None,
    ) -> KalshiAuth:
        """Load auth from PEM-encoded private key content.

        ``password`` accepts ``str`` / ``bytes`` / a zero-arg callable that
        returns either; pass ``None`` (default) for an unencrypted PEM.
        """
        if isinstance(pem_data, str):
            pem_data = pem_data.encode("utf-8")
        pw_bytes: bytes | None = None
        if password is not None:
            raw = password() if callable(password) else password
            pw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
        try:
            private_key = serialization.load_pem_private_key(pem_data, password=pw_bytes)
        except TypeError as e:
            # cryptography raises TypeError when the PEM is encrypted and
            # ``password=None``, or when an unencrypted PEM is given a password.
            raise KalshiAuthError(
                "Passphrase-protected private key requires a password. "
                "Pass `password=` to KalshiAuth.from_pem / from_key_path / from_env, "
                "set the KALSHI_PRIVATE_KEY_PASSPHRASE environment variable, or "
                "strip the passphrase with: openssl pkey -in key.pem -out key_nopass.pem"
            ) from e
        except (ValueError, UnsupportedAlgorithm) as e:
            # Wrong password and malformed PEM both surface here as ValueError.
            raise KalshiAuthError(
                f"Invalid PEM private key: {e}. Ensure the key is an RSA private key "
                "in PKCS8 PEM format (-----BEGIN PRIVATE KEY-----) and that "
                "the supplied `password=` (if any) is correct."
            ) from e
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise KalshiAuthError(
                f"Expected RSA private key, got {type(private_key).__name__}. "
                "Kalshi requires RSA keys for API authentication."
            )
        return cls(key_id, private_key)

    @classmethod
    def from_env(
        cls,
        *,
        password: bytes | str | Callable[[], bytes | str] | None = None,
    ) -> KalshiAuth:
        """Load auth from environment variables.

        Reads:
            KALSHI_KEY_ID (required)
            KALSHI_PRIVATE_KEY (PEM string) or KALSHI_PRIVATE_KEY_PATH (file path)
            KALSHI_PRIVATE_KEY_PASSPHRASE (optional; used when the PEM is encrypted)

        The explicit ``password=`` keyword overrides
        ``KALSHI_PRIVATE_KEY_PASSPHRASE`` when both are supplied.
        """
        key_id = os.environ.get("KALSHI_KEY_ID")
        if not key_id:
            raise KalshiAuthError(
                "KALSHI_KEY_ID environment variable is not set. Set it to your Kalshi API key ID."
            )

        resolved_password = (
            password if password is not None else os.environ.get("KALSHI_PRIVATE_KEY_PASSPHRASE")
        )

        pem_string = os.environ.get("KALSHI_PRIVATE_KEY")
        key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        # #249: refuse ambiguous credential bundle — naming both env vars makes
        # the misconfiguration obvious in production logs.
        if pem_string and key_path:
            raise KalshiAuthError(
                "Both KALSHI_PRIVATE_KEY and KALSHI_PRIVATE_KEY_PATH are set. "
                "Provide exactly one — unset whichever you don't intend to use."
            )
        if pem_string:
            return cls.from_pem(key_id, pem_string, password=resolved_password)

        if key_path:
            return cls.from_key_path(key_id, key_path, password=resolved_password)

        raise KalshiAuthError(
            "Neither KALSHI_PRIVATE_KEY nor KALSHI_PRIVATE_KEY_PATH is set. "
            "Set one of these environment variables with your RSA private key."
        )

    @classmethod
    def try_from_env(
        cls,
        *,
        password: bytes | str | Callable[[], bytes | str] | None = None,
    ) -> KalshiAuth | None:
        """Load auth from environment variables, returning None if not configured.

        Returns None if KALSHI_KEY_ID is not set, or if neither
        KALSHI_PRIVATE_KEY nor KALSHI_PRIVATE_KEY_PATH is set.

        Note: Does not raise on *missing* variables, but may still raise
        KalshiAuthError if variables are set with invalid data (e.g.,
        malformed PEM content or nonexistent key file path).

        See :meth:`from_env` for the ``password`` /
        ``KALSHI_PRIVATE_KEY_PASSPHRASE`` semantics.
        """
        key_id = os.environ.get("KALSHI_KEY_ID")
        if not key_id:
            return None

        resolved_password = (
            password if password is not None else os.environ.get("KALSHI_PRIVATE_KEY_PASSPHRASE")
        )

        pem_string = os.environ.get("KALSHI_PRIVATE_KEY")
        key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        # #249: refuse ambiguous credential bundle — naming both env vars makes
        # the misconfiguration obvious in production logs.
        if pem_string and key_path:
            raise KalshiAuthError(
                "Both KALSHI_PRIVATE_KEY and KALSHI_PRIVATE_KEY_PATH are set. "
                "Provide exactly one — unset whichever you don't intend to use."
            )
        if pem_string:
            return cls.from_pem(key_id, pem_string, password=resolved_password)

        if key_path:
            return cls.from_key_path(key_id, key_path, password=resolved_password)

        logger.warning(
            "KALSHI_KEY_ID is set but neither KALSHI_PRIVATE_KEY nor "
            "KALSHI_PRIVATE_KEY_PATH is configured. Returning unauthenticated "
            "client. Set one of these variables to authenticate."
        )
        return None

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign_request(
        self, method: str, path: str, timestamp_ms: int | None = None
    ) -> dict[str, str]:
        """Sign a request and return the auth headers.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            path: Full API path (e.g., /trade-api/v2/markets). Query params are stripped.
            timestamp_ms: Unix timestamp in milliseconds. Auto-generated if None.

        Returns:
            Dict with KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE, KALSHI-ACCESS-TIMESTAMP.
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        # Strip query parameters before signing
        clean_path = path.split("?")[0]

        # Strip trailing slash for canonical form
        if clean_path != "/" and clean_path.endswith("/"):
            clean_path = clean_path.rstrip("/")

        # Normalize percent-encoding to uppercase hex (RFC 3986 section 2.1)
        clean_path = _normalize_percent_encoding(clean_path)

        ts_str = str(timestamp_ms)
        message = ts_str + method.upper() + clean_path
        message_bytes = message.encode("utf-8")

        signature = self._private_key.sign(
            message_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )

        sig_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-SIGNATURE": sig_b64,
            "KALSHI-ACCESS-TIMESTAMP": ts_str,
        }

    def _get_sign_executor(self) -> ThreadPoolExecutor:
        """Return the dedicated sign-offload executor, creating it on first use.

        Thread-safe lazy init: the lock guards both the ``_closed`` recheck
        and the assignment, so a concurrent :meth:`close` cannot interleave
        between "saw open" and "constructed pool" and leave a fresh executor
        dangling on a closed auth (#267).

        Raises ``RuntimeError`` after :meth:`close` so a closed auth does
        not silently respawn the executor (which would defeat the point of
        ``close()`` — the old executor's threads stay shut down but a new
        ThreadPoolExecutor would be allocated on the next async sign).
        """
        # Fast path: already constructed and not closed. ``_closed`` is only
        # ever flipped True under the lock, so reading it lock-free here is
        # safe — a stale False just falls through to the locked recheck.
        executor = self._sign_executor
        if executor is not None and not self._closed:
            return executor
        with self._sign_executor_lock:
            if self._closed:
                raise RuntimeError(
                    "KalshiAuth has been closed; create a new instance to sign further requests."
                )
            if self._sign_executor is None:
                self._sign_executor = ThreadPoolExecutor(
                    max_workers=2,
                    thread_name_prefix="kalshi-sign",
                )
            return self._sign_executor

    async def sign_request_async(
        self, method: str, path: str, timestamp_ms: int | None = None
    ) -> dict[str, str]:
        """Async variant of :meth:`sign_request` that offloads to a dedicated executor.

        Uses ``loop.run_in_executor(self._sign_executor, ...)`` so the
        ~1-10 ms of RSA-PSS CPU does not block the asyncio event loop.
        The executor is dedicated (not asyncio's default pool) so signs
        don't queue behind `getaddrinfo` / file I/O / other `to_thread()`
        work — relevant during WS reconnect storms where DNS dominates.

        The sync :meth:`sign_request` API is unchanged; callers running
        on the sync transport should keep using it.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._get_sign_executor(),
            self.sign_request,
            method,
            path,
            timestamp_ms,
        )

    def close(self) -> None:
        """Shut down the sign-offload executor and mark this auth closed.

        Idempotent. Safe to call without an executor having been initialised.
        Long-lived clients ordinarily rely on interpreter-shutdown cleanup
        (atexit-joined executor threads); this hook is for tests and other
        callers that want deterministic teardown.

        Terminal: a subsequent :meth:`sign_request_async` raises
        ``RuntimeError`` rather than silently respawning a fresh executor.
        The synchronous :meth:`sign_request` is unaffected — it never used
        the executor — but callers should treat the instance as retired.
        """
        with self._sign_executor_lock:
            self._closed = True
            if self._sign_executor is not None:
                self._sign_executor.shutdown(wait=False)
                self._sign_executor = None
