"""Bounded message queue with configurable overflow strategies."""
from __future__ import annotations

import asyncio
import collections
from collections.abc import AsyncIterator
from enum import Enum
from typing import Generic, TypeVar

from kalshi.errors import KalshiBackpressureError

T = TypeVar("T")

_SENTINEL = object()


class OverflowStrategy(Enum):
    """What to do when the message queue is full."""

    DROP_OLDEST = "drop_oldest"
    """Ring buffer: evict oldest message, keep newest. Safe for latest-wins channels (ticker)."""

    ERROR = "error"
    """Raise KalshiBackpressureError. Use for stateful channels (orderbook_delta)."""


class MessageQueue(Generic[T]):
    """Bounded async queue with configurable overflow behavior.

    Implements AsyncIterator so consumers can ``async for msg in queue``.
    Iteration stops when a sentinel is pushed (graceful shutdown).
    """

    def __init__(
        self,
        maxsize: int = 1000,
        overflow: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
    ) -> None:
        self._maxsize = maxsize
        self._overflow = overflow
        self._buffer: collections.deque[T | object] = collections.deque(maxlen=None)
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
                    "switching to DROP_OLDEST overflow strategy."
                )

        self._buffer.append(item)
        self._event.set()

    async def put_sentinel(self) -> None:
        """Push shutdown sentinel. Causes async iteration to stop."""
        self._closed = True
        self._buffer.append(_SENTINEL)
        self._event.set()

    async def get(self) -> T:
        """Get next item, waiting if empty."""
        while not self._buffer:
            self._event.clear()
            await self._event.wait()

        item = self._buffer.popleft()
        if item is _SENTINEL:
            raise StopAsyncIteration
        return item  # type: ignore[return-value]

    def qsize(self) -> int:
        """Number of items currently in the queue (excludes sentinel)."""
        return sum(1 for item in self._buffer if item is not _SENTINEL)

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    async def __anext__(self) -> T:
        while not self._buffer:
            self._event.clear()
            await self._event.wait()

        item = self._buffer.popleft()
        if item is _SENTINEL:
            raise StopAsyncIteration
        return item  # type: ignore[return-value]
