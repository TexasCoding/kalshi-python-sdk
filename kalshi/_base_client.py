"""Base client with shared HTTP transport logic, retry, and error handling.

Provides both sync and async transports. Resource methods are transport-agnostic
and dispatch to whichever transport the client was constructed with.
"""

from __future__ import annotations

import email.utils
import logging
import math
import random
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import (
    KalshiAuthError,
    KalshiConflictError,
    KalshiError,
    KalshiNetworkError,
    KalshiNotFoundError,
    KalshiPoolExhaustedError,
    KalshiRateLimitError,
    KalshiServerError,
    KalshiTimeoutError,
    KalshiValidationError,
)

logger = logging.getLogger("kalshi")

RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}
# DELETE excluded: cancel/batch_cancel are not safely idempotent
RETRYABLE_METHODS = {"GET", "HEAD", "OPTIONS"}

# _map_error body-size guards: refuse to parse and never let one error
# message dominate a log line / Sentry payload.
MAX_ERROR_BODY_BYTES = 16 * 1024
MAX_ERROR_MESSAGE_CHARS = 1024


def _map_error(response: httpx.Response) -> KalshiError:
    """Map an HTTP error response to the appropriate SDK exception."""
    status = response.status_code

    # #203: cap body buffering. If the server advertises an oversized body,
    # short-circuit before httpx materialises it into memory. We still fall
    # through to status dispatch so the typed exception class is preserved
    # (#252) — only the message changes.
    content_length = response.headers.get("content-length")
    suppressed: bool = False
    if content_length:
        try:
            if int(content_length) > MAX_ERROR_BODY_BYTES:
                suppressed = True
        except ValueError:
            pass  # malformed Content-Length — fall through to normal parse

    body: dict[str, Any]
    if suppressed:
        body = {}
        message = f"HTTP {status} (body {content_length} bytes, suppressed)"
    else:
        try:
            body = response.json()
        except Exception:
            body = {}
        raw_message = body.get("message") or body.get("error") or response.text or f"HTTP {status}"
        # Truncate to bound log-line and exception-message size.
        message = str(raw_message)[:MAX_ERROR_MESSAGE_CHARS]

    if status in (400, 422):
        details = body.get("details") or body.get("errors")
        return KalshiValidationError(
            message=message,
            status_code=status,
            details=details if isinstance(details, dict) else None,
        )
    if status in (401, 403):
        return KalshiAuthError(message=message, status_code=status)
    if status == 404:
        return KalshiNotFoundError(message=message, status_code=status)
    if status == 409:
        return KalshiConflictError(message=message, status_code=status)
    if status == 429:
        retry_after = response.headers.get("Retry-After")
        retry_after_val: float | None = None
        if retry_after:
            try:
                retry_after_val = float(retry_after)
                # Reject non-finite/negative: NaN crashes time.sleep, negative busy-loops.
                if retry_after_val < 0 or not math.isfinite(retry_after_val):
                    retry_after_val = None
            except ValueError:
                # RFC 7231 §7.1.3: Retry-After may also be an HTTP-date.
                try:
                    dt = email.utils.parsedate_to_datetime(retry_after)
                except (TypeError, ValueError):
                    dt = None
                if dt is None:
                    logger.debug(
                        "Retry-After %r is neither delta-seconds nor HTTP-date; "
                        "falling back to computed backoff",
                        retry_after,
                    )
                else:
                    # RFC 5322 dates without a tz are interpreted as UTC by
                    # parsedate_to_datetime; ensure aware before subtracting.
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                    delta = (dt - datetime.now(tz=UTC)).total_seconds()
                    # Clamp negatives (date in the past) to 0 — retry immediately.
                    # The transport caller caps at config.retry_max_delay.
                    retry_after_val = max(0.0, delta)
        return KalshiRateLimitError(
            message=message, status_code=status, retry_after=retry_after_val
        )
    # #251: 408 Request Timeout and 504 Gateway Timeout carry the same
    # "may have committed" semantic as a transport-level timeout. Route them
    # to KalshiTimeoutError so callers can branch on it (e.g., reconcile via
    # client_order_id before retrying an order create).
    if status in (408, 504):
        return KalshiTimeoutError(message=message, status_code=status)
    if status >= 500:
        return KalshiServerError(message=message, status_code=status)

    return KalshiError(message=message, status_code=status)


def _compute_backoff(attempt: int, config: KalshiConfig) -> float:
    """Exponential backoff with AWS "Full Jitter".

    Spreads colliding retries evenly across the full backoff window, so
    parallel clients that hit a rate limit at the same time don't bunch up
    in a narrow sub-window (the failure mode of fixed-magnitude jitter).
    Formula: ``sleep = random_uniform(0, min(cap, base * 2 ** attempt))``.
    Reference: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
    """
    capped = min(config.retry_base_delay * (2**attempt), config.retry_max_delay)
    return float(random.uniform(0, capped))


def _would_exceed_budget(start: float, delay: float, total_timeout: float | None) -> bool:
    """#193: True iff sleeping ``delay`` now would push past ``total_timeout``."""
    if total_timeout is None:
        return False
    return (time.monotonic() - start) + delay > total_timeout


class SyncTransport:
    """Synchronous HTTP transport using httpx.Client."""

    def __init__(
        self,
        auth: KalshiAuth | None,
        config: KalshiConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._auth = auth
        self._config = config
        # Cached once: base_url is immutable on a frozen KalshiConfig.
        self._base_path = urlparse(config.base_url).path
        client_kwargs: dict[str, Any] = {
            "base_url": config.base_url,
            "timeout": config.timeout,
            "headers": config.extra_headers,
            "transport": transport,
            "http2": config.http2,
        }
        if config.limits is not None:
            client_kwargs["limits"] = config.limits
        self._client = httpx.Client(**client_kwargs)

    @property
    def is_authenticated(self) -> bool:
        """Whether this transport has auth credentials configured."""
        return self._auth is not None

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an authenticated HTTP request with retry logic.

        ``extra_headers`` are merged per-request on top of
        ``config.extra_headers`` (so a per-call ``X-Request-ID`` overrides a
        client-default one), but the ``KALSHI-ACCESS-*`` auth headers always
        win — callers cannot forge them via ``extra_headers``.
        """
        if json is not None and content is not None:
            raise TypeError("request() accepts `json=` or `content=`, not both.")
        # P1.6: canonicalize trailing slash BEFORE both signing and httpx call
        # so the wire path and the signed payload stay byte-identical. Root "/"
        # is preserved.
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/") or "/"
        # Sign with path-only (not full URL). Kalshi expects: /trade-api/v2/endpoint
        sign_path = self._base_path + path
        last_error: KalshiError | None = None
        # #193: wall-clock budget across the whole request including retries.
        start = time.monotonic()
        total_timeout = self._config.total_timeout
        config_extra = self._config.extra_headers or {}
        per_call_extra = extra_headers or {}
        body_headers = headers or {}

        for attempt in range(self._config.max_retries + 1):
            auth_headers = self._auth.sign_request(method.upper(), sign_path) if self._auth else {}
            # Order matters: config defaults < per-request overrides
            #               < body-helper headers < signed auth.
            merged_headers = {
                **config_extra,
                **per_call_extra,
                **body_headers,
                **auth_headers,
            }

            logger.debug(
                "Request: %s %s (attempt %d/%d)",
                method.upper(),
                path,
                attempt + 1,
                self._config.max_retries + 1,
            )

            try:
                response = self._client.request(
                    method=method.upper(),
                    url=path,
                    params=params,
                    json=json,
                    content=content,
                    headers=merged_headers,
                )
            except httpx.PoolTimeout as e:
                # #204: pool exhaustion never reached the wire — safe to retry
                # even for POST/DELETE.
                last_error = KalshiPoolExhaustedError(
                    f"Connection pool exhausted on {method.upper()} {path}. "
                    f"Raise KalshiConfig.limits.max_connections."
                )
                if attempt < self._config.max_retries:
                    delay = _compute_backoff(attempt, self._config)
                    if _would_exceed_budget(start, delay, total_timeout):
                        raise last_error from None
                    logger.warning(
                        "Pool exhausted on %s %s, retrying in %.1fs",
                        method,
                        path,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise last_error from e
            except httpx.TimeoutException as e:
                # F-O-09: don't interpolate httpx exception strings — they
                # include the full URL with query string and can leak
                # token-like values into uncaught-exception sinks. The
                # underlying exception is preserved via `__cause__`.
                last_error = KalshiTimeoutError(f"Request timed out: {method.upper()} {path}")
                if method.upper() in RETRYABLE_METHODS and attempt < self._config.max_retries:
                    delay = _compute_backoff(attempt, self._config)
                    if _would_exceed_budget(start, delay, total_timeout):
                        raise last_error from None
                    logger.warning("Timeout on %s %s, retrying in %.1fs", method, path, delay)
                    time.sleep(delay)
                    continue
                raise last_error from e
            except httpx.TransportError as e:
                # #240: TCP/TLS/DNS/protocol faults. Idempotent verbs retry on
                # any transport error; non-idempotent verbs only retry on
                # ConnectError (mirrors PoolTimeout — request never reached
                # the wire, so no partial-commit risk). ReadError/WriteError/
                # RemoteProtocolError on POST/DELETE may indicate the server
                # accepted bytes already; surface them so the caller can
                # reconcile via client_order_id.
                last_error = KalshiNetworkError(f"Network error: {method.upper()} {path}")
                pre_wire = isinstance(e, httpx.ConnectError)
                idempotent = method.upper() in RETRYABLE_METHODS
                if (idempotent or pre_wire) and attempt < self._config.max_retries:
                    delay = _compute_backoff(attempt, self._config)
                    if _would_exceed_budget(start, delay, total_timeout):
                        raise last_error from e
                    logger.warning(
                        "Network error on %s %s, retrying in %.1fs",
                        method,
                        path,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise last_error from e
            except httpx.HTTPError as e:
                raise KalshiError(f"HTTP error: {method.upper()} {path}") from e

            logger.debug("Response: %s %s → %d", method.upper(), path, response.status_code)

            if response.is_success:
                return response

            error = _map_error(response)
            last_error = error

            # Only retry safe methods on transient errors
            should_retry = (
                response.status_code in RETRYABLE_STATUS_CODES
                and method.upper() in RETRYABLE_METHODS
                and attempt < self._config.max_retries
            )

            if not should_retry:
                raise error

            # Use Retry-After header if available for 429.
            # `is not None` — not truthy — so Retry-After: 0 ("retry immediately") is honored.
            if isinstance(error, KalshiRateLimitError) and error.retry_after is not None:
                delay = min(error.retry_after, self._config.retry_max_delay)
            else:
                delay = _compute_backoff(attempt, self._config)

            if _would_exceed_budget(start, delay, total_timeout):
                raise error from None

            logger.warning(
                "%s %s returned %d, retrying in %.1fs (attempt %d/%d)",
                method.upper(),
                path,
                response.status_code,
                delay,
                attempt + 1,
                self._config.max_retries,
            )
            time.sleep(delay)

        # Should not reach here, but just in case
        if last_error:
            raise last_error
        raise KalshiError("Max retries exhausted")

    def close(self) -> None:
        self._client.close()


class AsyncTransport:
    """Asynchronous HTTP transport using httpx.AsyncClient."""

    def __init__(
        self,
        auth: KalshiAuth | None,
        config: KalshiConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._auth = auth
        self._config = config
        # Cached once: base_url is immutable on a frozen KalshiConfig.
        self._base_path = urlparse(config.base_url).path
        client_kwargs: dict[str, Any] = {
            "base_url": config.base_url,
            "timeout": config.timeout,
            "headers": config.extra_headers,
            "transport": transport,
            "http2": config.http2,
        }
        if config.limits is not None:
            client_kwargs["limits"] = config.limits
        self._client = httpx.AsyncClient(**client_kwargs)

    @property
    def is_authenticated(self) -> bool:
        """Whether this transport has auth credentials configured."""
        return self._auth is not None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an authenticated async HTTP request with retry logic.

        See :meth:`SyncTransport.request` for ``extra_headers`` semantics.
        """
        import asyncio

        if json is not None and content is not None:
            raise TypeError("request() accepts `json=` or `content=`, not both.")

        # P1.6: canonicalize trailing slash BEFORE both signing and httpx call.
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/") or "/"
        # Sign with path-only (not full URL). Kalshi expects: /trade-api/v2/endpoint
        sign_path = self._base_path + path
        last_error: KalshiError | None = None
        # #193: wall-clock budget across the whole request including retries.
        start = time.monotonic()
        total_timeout = self._config.total_timeout
        config_extra = self._config.extra_headers or {}
        per_call_extra = extra_headers or {}
        body_headers = headers or {}

        for attempt in range(self._config.max_retries + 1):
            if self._auth:
                auth_headers = await self._auth.sign_request_async(method.upper(), sign_path)
            else:
                auth_headers = {}
            merged_headers = {
                **config_extra,
                **per_call_extra,
                **body_headers,
                **auth_headers,
            }

            logger.debug(
                "Async request: %s %s (attempt %d/%d)",
                method.upper(),
                path,
                attempt + 1,
                self._config.max_retries + 1,
            )

            try:
                response = await self._client.request(
                    method=method.upper(),
                    url=path,
                    params=params,
                    json=json,
                    content=content,
                    headers=merged_headers,
                )
            except httpx.PoolTimeout as e:
                # #204: pool exhaustion never reached the wire — safe to retry
                # even for POST/DELETE.
                last_error = KalshiPoolExhaustedError(
                    f"Connection pool exhausted on {method.upper()} {path}. "
                    f"Raise KalshiConfig.limits.max_connections."
                )
                if attempt < self._config.max_retries:
                    delay = _compute_backoff(attempt, self._config)
                    if _would_exceed_budget(start, delay, total_timeout):
                        raise last_error from None
                    logger.warning(
                        "Pool exhausted on %s %s, retrying in %.1fs",
                        method,
                        path,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise last_error from e
            except httpx.TimeoutException as e:
                # F-O-09: see sync transport above.
                last_error = KalshiTimeoutError(f"Request timed out: {method.upper()} {path}")
                if method.upper() in RETRYABLE_METHODS and attempt < self._config.max_retries:
                    delay = _compute_backoff(attempt, self._config)
                    if _would_exceed_budget(start, delay, total_timeout):
                        raise last_error from None
                    logger.warning("Timeout on %s %s, retrying in %.1fs", method, path, delay)
                    await asyncio.sleep(delay)
                    continue
                raise last_error from e
            except httpx.TransportError as e:
                # #240: see SyncTransport above for the retry rules.
                last_error = KalshiNetworkError(f"Network error: {method.upper()} {path}")
                pre_wire = isinstance(e, httpx.ConnectError)
                idempotent = method.upper() in RETRYABLE_METHODS
                if (idempotent or pre_wire) and attempt < self._config.max_retries:
                    delay = _compute_backoff(attempt, self._config)
                    if _would_exceed_budget(start, delay, total_timeout):
                        raise last_error from e
                    logger.warning(
                        "Network error on %s %s, retrying in %.1fs",
                        method,
                        path,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise last_error from e
            except httpx.HTTPError as e:
                raise KalshiError(f"HTTP error: {method.upper()} {path}") from e

            logger.debug("Async response: %s %s → %d", method.upper(), path, response.status_code)

            if response.is_success:
                return response

            error = _map_error(response)
            last_error = error

            should_retry = (
                response.status_code in RETRYABLE_STATUS_CODES
                and method.upper() in RETRYABLE_METHODS
                and attempt < self._config.max_retries
            )

            if not should_retry:
                raise error

            # `is not None` so Retry-After: 0 ("retry immediately") is honored.
            if isinstance(error, KalshiRateLimitError) and error.retry_after is not None:
                delay = min(error.retry_after, self._config.retry_max_delay)
            else:
                delay = _compute_backoff(attempt, self._config)

            if _would_exceed_budget(start, delay, total_timeout):
                raise error from None

            logger.warning(
                "%s %s returned %d, retrying in %.1fs (attempt %d/%d)",
                method.upper(),
                path,
                response.status_code,
                delay,
                attempt + 1,
                self._config.max_retries,
            )
            await asyncio.sleep(delay)

        if last_error:
            raise last_error
        raise KalshiError("Max retries exhausted")

    async def close(self) -> None:
        await self._client.aclose()
