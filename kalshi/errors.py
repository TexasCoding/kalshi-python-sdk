"""Exception hierarchy for the Kalshi SDK."""

from __future__ import annotations

from typing import Literal


class KalshiError(Exception):
    """Base exception for all Kalshi SDK errors.

    ``retry_after`` carries the server's RFC 7231 §7.1.3 Retry-After hint
    (parsed to seconds) when present. Populated for 408/429/503/504 and
    other retryable 5xx responses; ``None`` otherwise. The transport
    retry loop reads it via plain attribute access regardless of error
    subclass (#322).
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(message)


class KalshiAuthError(KalshiError):
    """Authentication or authorization failure (401/403)."""


class AuthRequiredError(KalshiAuthError):
    """Raised when an unauthenticated client calls a private endpoint."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "This endpoint requires authentication. "
            "Provide key_id + private_key_path when constructing the client, "
            "or set KALSHI_KEY_ID + (KALSHI_PRIVATE_KEY_PATH or KALSHI_PRIVATE_KEY) "
            "environment variables. See "
            "https://texascoding.github.io/kalshi-python-sdk/authentication/",
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


class KalshiConflictError(KalshiError):
    """409 Conflict (e.g., duplicate ``client_order_id``)."""


class KalshiTimeoutError(KalshiError):
    """Request timed out. The server may or may not have processed it.

    On POST endpoints like order create, query the server using
    ``client_order_id`` to determine whether the request committed.
    """


class KalshiPoolExhaustedError(KalshiError):
    """Connection pool exhausted; request never reached the wire.

    Safe to retry regardless of HTTP method. Raise
    ``KalshiConfig.limits.max_connections`` if this fires under normal load.
    """


class KalshiNetworkError(KalshiError):
    """Transport-level network failure (TCP/TLS/DNS/protocol).

    Raised after the retry loop has exhausted attempts on a transient
    ``httpx.TransportError`` — ``ConnectError``, ``ReadError``,
    ``WriteError``, ``RemoteProtocolError``, etc. The original httpx
    exception is chained via ``__cause__``.
    """


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

    def __init__(
        self,
        message: str,
        *,
        channel: str | None = None,
        sid: int | None = None,
        client_id: int | None = None,
        last_seq: int | None = None,
        next_seq: int | None = None,
    ) -> None:
        self.channel = channel
        self.sid = sid
        self.client_id = client_id
        self.last_seq = last_seq
        self.next_seq = next_seq
        super().__init__(message)


class KalshiBackpressureError(KalshiWebSocketError):
    """Message queue overflow with ERROR strategy.

    Carries structured context so consumers iterating multiple
    subscriptions can route the failure by channel/sid/client_id
    without parsing the error message string.
    """

    def __init__(
        self,
        message: str,
        *,
        channel: str | None = None,
        sid: int | None = None,
        client_id: int | None = None,
        maxsize: int | None = None,
    ) -> None:
        self.channel = channel
        self.sid = sid
        self.client_id = client_id
        self.maxsize = maxsize
        super().__init__(message)


class KalshiOrderbookUnavailableError(KalshiWebSocketError):
    """Local orderbook is empty between teardown and resync snapshot.

    Raised by :class:`KalshiWebSocket.orderbook` when the underlying
    delta stream yields an item but the orderbook manager has no book
    for the requested ticker. This can happen between a gap-triggered
    ``remove_by_sid`` and the resync snapshot landing — the iterator
    previously yielded an empty :class:`Orderbook`, which is
    indistinguishable from a real market with zero liquidity and could
    cause a strategy to place orders against an empty book.
    """

    def __init__(
        self,
        message: str,
        *,
        ticker: str | None = None,
    ) -> None:
        self.ticker = ticker
        super().__init__(message)


class KalshiSubscriptionError(KalshiWebSocketError):
    """Subscribe/unsubscribe request rejected by server."""

    def __init__(
        self,
        message: str,
        error_code: int | None = None,
        *,
        channel: str | None = None,
        client_id: int | None = None,
        op: Literal["subscribe", "unsubscribe", "update_subscription"] | None = None,
    ) -> None:
        self.error_code = error_code
        self.channel = channel
        self.client_id = client_id
        self.op = op
        super().__init__(message)
