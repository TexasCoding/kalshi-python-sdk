"""Exception hierarchy for the Kalshi SDK."""

from __future__ import annotations


class KalshiError(Exception):
    """Base exception for all Kalshi SDK errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class KalshiAuthError(KalshiError):
    """Authentication or authorization failure (401/403)."""


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
