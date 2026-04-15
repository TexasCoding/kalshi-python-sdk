"""Unit tests for integration test helpers."""

from __future__ import annotations

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.frames import Close

from kalshi.errors import KalshiConnectionError
from tests.integration.helpers import retry_transient


@pytest.mark.asyncio
class TestRetryTransient:
    async def test_passes_through_assertion_error(self) -> None:
        """AssertionError must NOT be retried — it's a real test failure."""
        call_count = 0

        @retry_transient(max_retries=2)
        async def always_fails() -> None:
            nonlocal call_count
            call_count += 1
            raise AssertionError("test failure")

        with pytest.raises(AssertionError, match="test failure"):
            await always_fails()
        assert call_count == 1  # Called once, not retried

    async def test_retries_connection_error(self) -> None:
        """ConnectionError should be retried up to max_retries."""
        call_count = 0

        @retry_transient(max_retries=2, delay=0.01)
        async def fails_then_succeeds() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("socket closed")
            return "ok"

        result = await fails_then_succeeds()
        assert result == "ok"
        assert call_count == 3

    async def test_retries_kalshi_connection_error(self) -> None:
        """KalshiConnectionError should be retried."""
        call_count = 0

        @retry_transient(max_retries=1, delay=0.01)
        async def fails_once() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KalshiConnectionError("ws failed")
            return "ok"

        result = await fails_once()
        assert result == "ok"
        assert call_count == 2

    async def test_retries_timeout_error(self) -> None:
        """TimeoutError should be retried."""
        call_count = 0

        @retry_transient(max_retries=1, delay=0.01)
        async def times_out_once() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("timed out")
            return "ok"

        result = await times_out_once()
        assert result == "ok"
        assert call_count == 2

    async def test_retries_connection_closed_no_frame(self) -> None:
        """ConnectionClosed with rcvd=None (dropped) should be retried."""
        call_count = 0

        @retry_transient(max_retries=1, delay=0.01)
        async def drops_once() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionClosed(rcvd=None, sent=None)
            return "ok"

        result = await drops_once()
        assert result == "ok"
        assert call_count == 2

    async def test_passes_through_normal_close(self) -> None:
        """ConnectionClosed with code 1000 must NOT be retried."""
        call_count = 0

        @retry_transient(max_retries=2)
        async def normal_close() -> None:
            nonlocal call_count
            call_count += 1
            raise ConnectionClosed(rcvd=Close(1000, "normal"), sent=None)

        with pytest.raises(ConnectionClosed):
            await normal_close()
        assert call_count == 1

    async def test_exhausts_retries_and_raises(self) -> None:
        """After exhausting retries, the last exception is raised."""
        call_count = 0

        @retry_transient(max_retries=2, delay=0.01)
        async def always_timeout() -> None:
            nonlocal call_count
            call_count += 1
            raise TimeoutError("always")

        with pytest.raises(TimeoutError, match="always"):
            await always_timeout()
        assert call_count == 3  # 1 initial + 2 retries
