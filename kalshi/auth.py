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

import base64
import os
import time
from pathlib import Path

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi.errors import KalshiAuthError


class KalshiAuth:
    """RSA-PSS request signer for the Kalshi API.

    The private key is loaded once at construction time and cached in memory.
    Thread-safe: RSA signing is stateless.
    """

    def __init__(self, key_id: str, private_key: rsa.RSAPrivateKey) -> None:
        self._key_id = key_id
        self._private_key = private_key

    @classmethod
    def from_key_path(cls, key_id: str, key_path: str | Path) -> KalshiAuth:
        """Load auth from a PEM private key file.

        Supports ~ expansion (e.g., ~/kalshi.pem).
        """
        expanded = Path(key_path).expanduser()
        if not expanded.exists():
            raise KalshiAuthError(f"Private key file not found: {expanded}")
        try:
            pem_data = expanded.read_bytes()
        except PermissionError as e:
            raise KalshiAuthError(f"Permission denied reading private key: {expanded}") from e
        return cls.from_pem(key_id, pem_data)

    @classmethod
    def from_pem(cls, key_id: str, pem_data: str | bytes) -> KalshiAuth:
        """Load auth from PEM-encoded private key content."""
        if isinstance(pem_data, str):
            pem_data = pem_data.encode("utf-8")
        try:
            private_key = serialization.load_pem_private_key(pem_data, password=None)
        except TypeError as e:
            raise KalshiAuthError(
                "Passphrase-protected private keys are not supported. "
                "Remove the passphrase with: openssl pkey -in key.pem -out key_nopass.pem"
            ) from e
        except (ValueError, UnsupportedAlgorithm) as e:
            raise KalshiAuthError(
                f"Invalid PEM private key: {e}. Ensure the key is an RSA private key "
                "in PKCS8 PEM format (-----BEGIN PRIVATE KEY-----)."
            ) from e
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise KalshiAuthError(
                f"Expected RSA private key, got {type(private_key).__name__}. "
                "Kalshi requires RSA keys for API authentication."
            )
        return cls(key_id, private_key)

    @classmethod
    def from_env(cls) -> KalshiAuth:
        """Load auth from environment variables.

        Reads:
            KALSHI_KEY_ID (required)
            KALSHI_PRIVATE_KEY (PEM string) or KALSHI_PRIVATE_KEY_PATH (file path)
        """
        key_id = os.environ.get("KALSHI_KEY_ID")
        if not key_id:
            raise KalshiAuthError(
                "KALSHI_KEY_ID environment variable is not set. "
                "Set it to your Kalshi API key ID."
            )

        pem_string = os.environ.get("KALSHI_PRIVATE_KEY")
        if pem_string:
            return cls.from_pem(key_id, pem_string)

        key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        if key_path:
            return cls.from_key_path(key_id, key_path)

        raise KalshiAuthError(
            "Neither KALSHI_PRIVATE_KEY nor KALSHI_PRIVATE_KEY_PATH is set. "
            "Set one of these environment variables with your RSA private key."
        )

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

        # NOTE: Percent-encoded characters are NOT normalized (e.g., %2D stays as %2D).
        # Kalshi tickers are alphanumeric + hyphens, so percent-encoding is unlikely.
        # If Kalshi introduces tickers with encodable characters, this may need
        # urllib.parse.unquote() normalization — but only after verifying the server
        # normalizes before signature verification. See GitHub issue #2.

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
