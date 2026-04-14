"""Test helpers — retry decorator and fill guarantee."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from websockets.exceptions import ConnectionClosed

from kalshi.errors import KalshiConnectionError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_RETRYABLE_CLOSE_CODES = frozenset({1006, 1012, 1013})


def retry_transient(max_retries: int = 2, delay: float = 1.0) -> Callable[[F], F]:
    """Retry on transient WS/network failures. Pass through real errors.

    Retries on:
      - ConnectionError (raw socket failure)
      - TimeoutError (asyncio timeout)
      - KalshiConnectionError (SDK-wrapped connection failure)
      - websockets.ConnectionClosed with rcvd=None (dropped) or
        rcvd.code in {1006, 1012, 1013} (abnormal closure)

    Does NOT retry on:
      - AssertionError (test failure)
      - ConnectionClosed with code 1000 (normal), 1008 (policy), 1003 (unsupported)
      - Any other exception (parse errors, validation errors, etc.)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (ConnectionError, TimeoutError, KalshiConnectionError) as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        logger.info(
                            "retry_transient: %s on attempt %d, retrying in %.1fs",
                            type(exc).__name__, attempt + 1, delay,
                        )
                        await asyncio.sleep(delay)
                    continue
                except ConnectionClosed as exc:
                    if exc.rcvd is None or exc.rcvd.code in _RETRYABLE_CLOSE_CODES:
                        last_exc = exc
                        if attempt < max_retries:
                            code = exc.rcvd.code if exc.rcvd else "None"
                            logger.info(
                                "retry_transient: ConnectionClosed"
                                " (code=%s) on attempt %d, retrying",
                                code,
                                attempt + 1,
                            )
                            await asyncio.sleep(delay)
                        continue
                    raise  # Non-retryable close code
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
