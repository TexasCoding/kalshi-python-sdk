"""Integration tests for SDK error handling against real API responses.

Verifies that the error hierarchy in kalshi/errors.py correctly maps
HTTP error codes from the demo API to the right exception classes.

Tests are sync-only because error mapping lives in _map_error() which
is shared between SyncTransport and AsyncTransport.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import KalshiConfig
from kalshi.errors import (
    KalshiAuthError,
    KalshiNotFoundError,
    KalshiValidationError,
)


@pytest.mark.integration
class TestErrorPaths:
    """Verify SDK exception hierarchy against real API error responses."""

    def test_invalid_ticker_returns_not_found(
        self, sync_client: KalshiClient
    ) -> None:
        """GET /markets/{ticker} with a nonexistent ticker should raise KalshiNotFoundError."""
        with pytest.raises(KalshiNotFoundError) as exc_info:
            sync_client.markets.get("NONEXISTENT_TICKER_XYZ_99")

        exc = exc_info.value
        assert exc.status_code == 404
        assert str(exc)  # message is non-empty

    def test_malformed_params_returns_validation_error(
        self, sync_client: KalshiClient
    ) -> None:
        """Malformed request params should raise KalshiValidationError (400)."""
        # Use an obviously invalid limit value
        with pytest.raises(KalshiValidationError) as exc_info:
            sync_client.markets.list(limit=-1)

        exc = exc_info.value
        assert exc.status_code == 400
        assert str(exc)  # message is non-empty

    def test_bad_auth_returns_auth_error(self) -> None:
        """A client with invalid credentials should raise KalshiAuthError (401/403).

        Uses a throwaway client with a valid RSA key but wrong key_id,
        so signing succeeds but the server rejects the credentials.
        """
        dummy_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
        auth = KalshiAuth(
            key_id="invalid-key-id-for-test", private_key=dummy_key
        )
        config = KalshiConfig(
            base_url="https://demo-api.kalshi.co/trade-api/v2"
        )
        client = KalshiClient(auth=auth, config=config)

        try:
            with pytest.raises(KalshiAuthError) as exc_info:
                client.markets.list(limit=1)

            exc = exc_info.value
            assert exc.status_code in (401, 403)
            assert str(exc)  # message is non-empty
        finally:
            client.close()

    def test_not_found_error_has_status_code_attribute(
        self, sync_client: KalshiClient
    ) -> None:
        """Verify the exception object carries structured data, not just a message."""
        with pytest.raises(KalshiNotFoundError) as exc_info:
            sync_client.markets.get("ANOTHER_FAKE_TICKER_ABC_00")

        exc = exc_info.value
        # KalshiError base class stores status_code
        assert hasattr(exc, "status_code")
        assert isinstance(exc.status_code, int)

    def test_validation_error_details_attribute(
        self, sync_client: KalshiClient
    ) -> None:
        """KalshiValidationError should have a details attribute (may be None or dict)."""
        with pytest.raises(KalshiValidationError) as exc_info:
            sync_client.markets.list(limit=-1)

        exc = exc_info.value
        assert hasattr(exc, "details")
        # details is either None or a dict — both are valid
        assert exc.details is None or isinstance(exc.details, dict)
