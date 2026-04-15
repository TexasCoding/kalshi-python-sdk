"""Base client with shared HTTP transport logic, retry, and error handling.

Provides both sync and async transports. Resource methods are transport-agnostic
and dispatch to whichever transport the client was constructed with.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import (
    KalshiAuthError,
    KalshiError,
    KalshiNotFoundError,
    KalshiRateLimitError,
    KalshiServerError,
    KalshiValidationError,
)

logger = logging.getLogger("kalshi")

RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
# DELETE excluded: cancel/batch_cancel are not safely idempotent
RETRYABLE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _map_error(response: httpx.Response) -> KalshiError:
    """Map an HTTP error response to the appropriate SDK exception."""
    status = response.status_code
    try:
        body = response.json()
    except Exception:
        body = {}

    message = body.get("message") or body.get("error") or response.text or f"HTTP {status}"

    if status == 400:
        details = body.get("details") or body.get("errors")
        return KalshiValidationError(
            message=str(message),
            status_code=status,
            details=details if isinstance(details, dict) else None,
        )
    if status in (401, 403):
        return KalshiAuthError(message=str(message), status_code=status)
    if status == 404:
        return KalshiNotFoundError(message=str(message), status_code=status)
    if status == 429:
        retry_after = response.headers.get("Retry-After")
        retry_after_val: float | None = None
        if retry_after:
            try:
                retry_after_val = float(retry_after)
            except ValueError:
                retry_after_val = None  # HTTP-date format, fall back to computed backoff
        return KalshiRateLimitError(
            message=str(message), status_code=status, retry_after=retry_after_val
        )
    if status >= 500:
        return KalshiServerError(message=str(message), status_code=status)

    return KalshiError(message=str(message), status_code=status)


def _compute_backoff(attempt: int, config: KalshiConfig) -> float:
    """Exponential backoff with jitter."""
    delay = config.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)
    return float(min(delay, config.retry_max_delay))


class SyncTransport:
    """Synchronous HTTP transport using httpx.Client."""

    def __init__(self, auth: KalshiAuth | None, config: KalshiConfig) -> None:
        self._auth = auth
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            headers=config.extra_headers,
        )

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
    ) -> httpx.Response:
        """Make an authenticated HTTP request with retry logic."""
        # Sign with path-only (not full URL). Kalshi expects: /trade-api/v2/endpoint
        sign_path = urlparse(self._config.base_url).path + path
        last_error: KalshiError | None = None

        for attempt in range(self._config.max_retries + 1):
            auth_headers = self._auth.sign_request(method.upper(), sign_path) if self._auth else {}

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
                    headers=auth_headers,
                )
            except httpx.TimeoutException as e:
                last_error = KalshiError(f"Request timed out: {e}")
                if method.upper() in RETRYABLE_METHODS and attempt < self._config.max_retries:
                    delay = _compute_backoff(attempt, self._config)
                    logger.warning("Timeout on %s %s, retrying in %.1fs", method, path, delay)
                    time.sleep(delay)
                    continue
                raise last_error from e
            except httpx.HTTPError as e:
                raise KalshiError(f"HTTP error: {e}") from e

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

            # Use Retry-After header if available for 429
            if isinstance(error, KalshiRateLimitError) and error.retry_after:
                delay = min(error.retry_after, self._config.retry_max_delay)
            else:
                delay = _compute_backoff(attempt, self._config)

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

    def __init__(self, auth: KalshiAuth | None, config: KalshiConfig) -> None:
        self._auth = auth
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            headers=config.extra_headers,
        )

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
    ) -> httpx.Response:
        """Make an authenticated async HTTP request with retry logic."""
        import asyncio

        # Sign with path-only (not full URL). Kalshi expects: /trade-api/v2/endpoint
        sign_path = urlparse(self._config.base_url).path + path
        last_error: KalshiError | None = None

        for attempt in range(self._config.max_retries + 1):
            auth_headers = self._auth.sign_request(method.upper(), sign_path) if self._auth else {}

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
                    headers=auth_headers,
                )
            except httpx.TimeoutException as e:
                last_error = KalshiError(f"Request timed out: {e}")
                if method.upper() in RETRYABLE_METHODS and attempt < self._config.max_retries:
                    delay = _compute_backoff(attempt, self._config)
                    logger.warning("Timeout on %s %s, retrying in %.1fs", method, path, delay)
                    await asyncio.sleep(delay)
                    continue
                raise last_error from e
            except httpx.HTTPError as e:
                raise KalshiError(f"HTTP error: {e}") from e

            logger.debug(
                "Async response: %s %s → %d", method.upper(), path, response.status_code
            )

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

            if isinstance(error, KalshiRateLimitError) and error.retry_after:
                delay = min(error.retry_after, self._config.retry_max_delay)
            else:
                delay = _compute_backoff(attempt, self._config)

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
