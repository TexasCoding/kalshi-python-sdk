"""Bounded message queue with configurable overflow strategies."""
from __future__ import annotations

import asyncio
import collections
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from kalshi.errors import KalshiBackpressureError

T = TypeVar("T")

_SENTINEL = object()


@dataclass(frozen=True)
class _ErrorSentinel:
    """Wraps a terminal exception so the iterator can raise it from ``__anext__``.

    Used by :meth:`MessageQueue.put_error` to surface real, programmatic
    error signals (e.g. ``KalshiBackpressureError`` from the recv loop)
    to ``async for`` consumers — previously such errors were swallowed
    and the iterator exited indistinguishably from a clean shutdown
    (#207). The exception is buffered like any other item and raised
    only when the consumer reaches it, preserving any prior in-flight
    messages that landed before the error fired.
    """

    exc: BaseException


class OverflowStrategy(Enum):
    """What to do when the message queue is full."""

    DROP_OLDEST = "drop_oldest"
    """Ring buffer: evict oldest message, keep newest. Safe for latest-wins channels (ticker)."""

    ERROR = "error"
    """Raise KalshiBackpressureError. Use for stateful channels (orderbook_delta)."""


class MessageQueue(Generic[T]):
    """Bounded async queue with configurable overflow behavior.

    Implements AsyncIterator so consumers can ``async for msg in queue``.
    Iteration stops when a sentinel is pushed (graceful shutdown), and
    raises the wrapped exception when an error sentinel from
    :meth:`put_error` is reached (#207).
    """

    def __init__(
        self,
        maxsize: int = 1000,
        overflow: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        *,
        channel: str | None = None,
        client_id: int | None = None,
    ) -> None:
        self._maxsize = maxsize
        self._overflow = overflow
        # #256: identity metadata used to populate ``KalshiBackpressureError``
        # fields at the ``put()`` raise site, so consumers iterating multiple
        # queues can ``except KalshiBackpressureError as e: route(e.channel,
        # e.client_id, ...)`` without parsing the message string.
        self._channel = channel
        self._client_id = client_id
        # `maxlen=maxsize+1` is a hard memory ceiling enforced by deque
        # itself. Even if the size check is bypassed for any reason, the buffer
        # still cannot grow without bound. +1 because put_sentinel appends
        # without going through the size-check overflow path. (#173)
        self._buffer: collections.deque[T | object] = collections.deque(maxlen=maxsize + 1)
        self._event = asyncio.Event()
        self._closed = False

    async def put(self, item: T) -> None:
        """Add an item to the queue, applying overflow strategy if full."""
        if self._closed:
            return

        if len(self._buffer) >= self._maxsize:
            if self._overflow is OverflowStrategy.DROP_OLDEST:
                self._buffer.popleft()
            elif self._overflow is OverflowStrategy.ERROR:
                raise KalshiBackpressureError(
                    f"Message queue full ({self._maxsize} items). "
                    "Consumer is too slow. Consider increasing maxsize or "
                    "switching to DROP_OLDEST overflow strategy.",
                    channel=self._channel,
                    client_id=self._client_id,
                    maxsize=self._maxsize,
                )

        self._buffer.append(item)
        self._event.set()

    async def put_sentinel(self) -> None:
        """Push shutdown sentinel. Causes async iteration to stop.

        Idempotent: after the queue is closed (sentinel or error sentinel
        already pushed), subsequent calls are no-ops. Without this the
        deque's ``maxlen=maxsize+1`` would evict a real buffered item to
        make room for a redundant sentinel — losing the last in-flight
        message between e.g. an ERROR-overflow ``put_error`` and the
        recv-loop's broadcast ``put_sentinel`` fan-out.
        """
        if self._closed:
            return
        self._closed = True
        self._buffer.append(_SENTINEL)
        self._event.set()

    async def put_error(self, exc: BaseException) -> None:
        """Push a terminal error sentinel.

        The iterator yields any items already in the buffer first, then
        raises ``exc`` when it reaches the sentinel. Subsequent ``put`` /
        ``put_error`` / ``put_sentinel`` calls are silently dropped (the
        queue is now closed). Used by the recv loop on
        ``KalshiBackpressureError`` so consumers see the failure rather
        than a silent ``StopAsyncIteration`` (#207).
        """
        if self._closed:
            return
        self._closed = True
        self._buffer.append(_ErrorSentinel(exc=exc))
        self._event.set()

    async def get(self) -> T:
        """Get next item, waiting if empty."""
        while not self._buffer:
            self._event.clear()
            await self._event.wait()

        item = self._buffer.popleft()
        if item is _SENTINEL:
            raise StopAsyncIteration
        if isinstance(item, _ErrorSentinel):
            raise item.exc
        return item  # type: ignore[return-value]

    def qsize(self) -> int:
        """Number of items currently in the queue (excludes sentinel). O(1).

        Derived from ``len(self._buffer)`` minus one when a terminal sentinel
        has been appended (``put_sentinel`` / ``put_error`` both flip
        ``_closed`` and push exactly one sentinel-shaped item).
        """
        n = len(self._buffer)
        if self._closed and n:
            return n - 1
        return n

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    async def __anext__(self) -> T:
        while not self._buffer:
            self._event.clear()
            await self._event.wait()

        item = self._buffer.popleft()
        if item is _SENTINEL:
            raise StopAsyncIteration
        if isinstance(item, _ErrorSentinel):
            raise item.exc
        return item  # type: ignore[return-value]
