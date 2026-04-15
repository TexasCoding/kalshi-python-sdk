"""Exception hierarchy for the Kalshi SDK."""

from __future__ import annotations


class KalshiError(Exception):
    """Base exception for all Kalshi SDK errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class KalshiAuthError(KalshiError):
    """Authentication or authorization failure (401/403)."""


class AuthRequiredError(KalshiAuthError):
    """Raised when an unauthenticated client calls a private endpoint."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "This endpoint requires authentication. "
            "Provide key_id + private_key_path, or use KalshiClient.from_env().",
            status_code=None,
        )


class KalshiNotFoundError(KalshiError):
    """Resource not found (404)."""


class KalshiValidationError(KalshiError):
    """Request validation failure (400). May include field-level details."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict[str, str] | None = None,
    ) -> None:
        self.details = details or {}
        super().__init__(message, status_code)


class KalshiRateLimitError(KalshiError):
    """Rate limit exceeded (429). Check retry_after for backoff hint."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code)


class KalshiServerError(KalshiError):
    """Server-side error (5xx)."""


class KalshiWebSocketError(KalshiError):
    """Base exception for all WebSocket errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=None)


class KalshiConnectionError(KalshiWebSocketError):
    """Connection failed, handshake rejected, or max retries exceeded."""


class KalshiSequenceGapError(KalshiWebSocketError):
    """Sequence gap detected that could not be resolved via resync."""


class KalshiBackpressureError(KalshiWebSocketError):
    """Message queue overflow with ERROR strategy."""


class KalshiSubscriptionError(KalshiWebSocketError):
    """Subscribe/unsubscribe request rejected by server."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        self.error_code = error_code
        super().__init__(message)
