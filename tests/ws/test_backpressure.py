"""Tests for MessageQueue backpressure."""
from __future__ import annotations

import asyncio

import pytest

from kalshi.errors import KalshiBackpressureError
from kalshi.ws.backpressure import MessageQueue, OverflowStrategy


@pytest.mark.asyncio
class TestMessageQueue:
    async def test_put_and_get(self) -> None:
        q: MessageQueue[str] = MessageQueue(maxsize=10)
        await q.put("hello")
        msg = await q.get()
        assert msg == "hello"

    async def test_sentinel_stops_iteration(self) -> None:
        q: MessageQueue[str] = MessageQueue(maxsize=10)
        await q.put("a")
        await q.put_sentinel()
        items: list[str] = []
        async for item in q:
            items.append(item)
        assert items == ["a"]

    async def test_drop_oldest_on_overflow(self) -> None:
        q: MessageQueue[int] = MessageQueue(
            maxsize=3, overflow=OverflowStrategy.DROP_OLDEST
        )
        await q.put(1)
        await q.put(2)
        await q.put(3)
        await q.put(4)  # should drop 1
        items: list[int] = []
        await q.put_sentinel()
        async for item in q:
            items.append(item)
        assert items == [2, 3, 4]

    async def test_error_on_overflow(self) -> None:
        q: MessageQueue[int] = MessageQueue(
            maxsize=2, overflow=OverflowStrategy.ERROR
        )
        await q.put(1)
        await q.put(2)
        with pytest.raises(KalshiBackpressureError, match="queue full"):
            await q.put(3)

    async def test_qsize(self) -> None:
        q: MessageQueue[str] = MessageQueue(maxsize=10)
        assert q.qsize() == 0
        await q.put("a")
        assert q.qsize() == 1

    async def test_async_iterator_protocol(self) -> None:
        q: MessageQueue[str] = MessageQueue(maxsize=10)
        await q.put("x")
        await q.put_sentinel()
        result = [item async for item in q]
        assert result == ["x"]

    async def test_multiple_drops(self) -> None:
        """Drop oldest should handle multiple overflows correctly."""
        q: MessageQueue[int] = MessageQueue(
            maxsize=2, overflow=OverflowStrategy.DROP_OLDEST
        )
        await q.put(1)
        await q.put(2)
        await q.put(3)  # drops 1
        await q.put(4)  # drops 2
        await q.put(5)  # drops 3
        await q.put_sentinel()
        items = [item async for item in q]
        assert items == [4, 5]

    async def test_put_after_sentinel_is_noop(self) -> None:
        """Putting items after sentinel should not error."""
        q: MessageQueue[str] = MessageQueue(maxsize=10)
        await q.put("a")
        await q.put_sentinel()
        await q.put("b")  # should be silently ignored
        items = [item async for item in q]
        assert items == ["a"]

    async def test_get_waits_for_item(self) -> None:
        """get() should block until an item is available."""
        q: MessageQueue[str] = MessageQueue(maxsize=10)

        async def delayed_put() -> None:
            await asyncio.sleep(0.05)
            await q.put("delayed")

        asyncio.create_task(delayed_put())
        msg = await asyncio.wait_for(q.get(), timeout=1.0)
        assert msg == "delayed"
