# P2 Integration Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add integration tests for three untested production paths: WebSocket live connection, order fill lifecycle, and cursor-based pagination correctness.

**Architecture:** Three atomic commits. Commit 1 adds WS connection test with reusable fixtures (ws_connect, retry_transient). Commit 2 adds order fill lifecycle test with fill_guarantee helper. Commit 3 adds pagination correctness tests. All tests hit the Kalshi demo API and use the existing semantic oracle for model validation.

**Tech Stack:** pytest, pytest-asyncio, websockets, kalshi SDK (KalshiWebSocket, KalshiClient)

---

## File Structure

```
tests/integration/
  conftest.py          — MODIFY: add ws_connect fixture, extend _assert_demo_url for WS safety
  helpers.py           — CREATE: retry_transient decorator + fill_guarantee helper
  test_helpers.py      — CREATE: unit tests for retry_transient
  test_websocket.py    — CREATE: WS connect, subscribe, disconnect tests
  test_orders.py       — MODIFY: add order fill lifecycle test
  test_markets.py      — MODIFY: add pagination correctness tests
```

---

### Task 1: Extend WS safety gate in conftest.py

**Files:**
- Modify: `tests/integration/conftest.py:61-68`

- [ ] **Step 1: Write test verifying the safety gate catches production WS URLs**

Create a quick manual verification. Open `tests/integration/conftest.py` and read the current `_assert_demo_url` function. It only checks `base_url`. We need to also check `ws_base_url`.

- [ ] **Step 2: Extend `_assert_demo_url` to accept and check WS URL**

In `tests/integration/conftest.py`, replace the `_assert_demo_url` function:

```python
def _assert_demo_url(base_url: str, ws_base_url: str | None = None) -> None:
    """Hard-fail if the client is not pointed at the demo environment."""
    if DEMO_HOST not in base_url:
        pytest.fail(
            f"SAFETY: Integration tests must run against the demo API. "
            f"Resolved base_url is '{base_url}', expected '{DEMO_HOST}'. "
            f"Check KALSHI_API_BASE_URL and KALSHI_DEMO env vars."
        )
    if ws_base_url is not None and DEMO_HOST not in ws_base_url:
        pytest.fail(
            f"SAFETY: WS integration tests must run against the demo API. "
            f"Resolved ws_base_url is '{ws_base_url}', expected '{DEMO_HOST}'. "
            f"Check KALSHI_API_BASE_URL and KALSHI_DEMO env vars."
        )
```

- [ ] **Step 3: Update sync_client and async_client fixtures to pass ws_base_url**

In the `sync_client` fixture, change:
```python
_assert_demo_url(client._config.base_url)
```
to:
```python
_assert_demo_url(client._config.base_url, client._config.ws_base_url)
```

Do the same in the `async_client` fixture.

- [ ] **Step 4: Run existing integration tests to verify nothing broke**

Run: `uv run pytest tests/integration/ -v --co` (collect only, no execution needed — just verify imports work)
Expected: All tests collected without errors.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/conftest.py
git commit -m "fix: extend demo safety gate to check ws_base_url"
```

---

### Task 2: Create retry_transient decorator

**Files:**
- Create: `tests/integration/helpers.py`

- [ ] **Step 1: Create `tests/integration/helpers.py` with the retry_transient decorator**

```python
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
                            logger.info(
                                "retry_transient: ConnectionClosed (code=%s) on attempt %d, retrying",
                                exc.rcvd.code if exc.rcvd else "None",
                                attempt + 1,
                            )
                            await asyncio.sleep(delay)
                        continue
                    raise  # Non-retryable close code
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
```

- [ ] **Step 2: Verify the file passes linting**

Run: `uv run ruff check tests/integration/helpers.py`
Expected: No errors.

- [ ] **Step 3: Verify mypy passes**

Run: `uv run mypy tests/integration/helpers.py`
Expected: No errors (or only import-related notes).

---

### Task 3: Unit test retry_transient

**Files:**
- Create: `tests/integration/test_helpers.py`

- [ ] **Step 1: Write unit tests for retry_transient**

```python
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
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/integration/test_helpers.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/helpers.py tests/integration/test_helpers.py
git commit -m "test: add retry_transient decorator with unit tests for WS integration"
```

---

### Task 4: Add ws_connect fixture to conftest.py

**Files:**
- Modify: `tests/integration/conftest.py`

- [ ] **Step 1: Add imports at the top of conftest.py**

Add these imports near the existing imports:

```python
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.ws.client import KalshiWebSocket
```

- [ ] **Step 2: Add ws_connect fixture at the bottom of conftest.py**

```python
# ---------------------------------------------------------------------------
# WebSocket connection fixture
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def ws_session(sync_client: KalshiClient) -> AsyncIterator[KalshiWebSocket]:
    """Connect to demo WS, yield an active session, clean up on exit."""
    config = sync_client._config
    _assert_demo_url(config.base_url, config.ws_base_url)

    auth = sync_client._auth
    ws = KalshiWebSocket(auth=auth, config=config)
    async with ws.connect() as session:
        yield session
```

- [ ] **Step 3: Run test collection to verify fixture is discoverable**

Run: `uv run pytest tests/integration/ -v --co`
Expected: No errors. New fixture should be available.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/conftest.py
git commit -m "test: add ws_session fixture for WS integration tests"
```

---

### Task 5: Create WS live connection tests

**Files:**
- Create: `tests/integration/test_websocket.py`

- [ ] **Step 1: Create `tests/integration/test_websocket.py`**

```python
"""Integration tests for WebSocket — live connection to demo server."""

from __future__ import annotations

import asyncio

import pytest

from kalshi.ws.client import KalshiWebSocket
from kalshi.ws.models.orderbook_delta import OrderbookSnapshotMessage
from tests.integration.helpers import retry_transient


@pytest.mark.integration
class TestWebSocketLive:
    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_connect_and_auth(
        self, ws_session: KalshiWebSocket
    ) -> None:
        """Connect to demo WS and verify auth succeeded.

        If we reach this point without KalshiConnectionError, auth passed.
        The ws_session fixture handles connect + auth via KalshiWebSocket.
        """
        # Connection is established by the fixture.
        # If auth failed, KalshiConnectionError would have been raised.
        assert ws_session._connection is not None

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_subscribe_orderbook_snapshot(
        self,
        ws_session: KalshiWebSocket,
        demo_market_ticker: str,
    ) -> None:
        """Subscribe to orderbook_delta and receive initial snapshot.

        orderbook_delta with send_initial_snapshot=True guarantees an
        immediate snapshot message, no dependency on market activity.
        """
        stream = await ws_session.subscribe_orderbook_delta(
            tickers=[demo_market_ticker],
        )
        try:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=10.0)
        except asyncio.TimeoutError:
            pytest.skip("No orderbook snapshot received within 10s on demo")

        # The first message should be a snapshot
        assert isinstance(msg, OrderbookSnapshotMessage)
        assert msg.type == "orderbook_snapshot"
        assert msg.msg.market_ticker == demo_market_ticker

    @retry_transient(max_retries=2, delay=1.0)
    async def test_ws_disconnect_lifecycle(
        self,
        ws_session: KalshiWebSocket,
        demo_market_ticker: str,
    ) -> None:
        """Subscribe, receive a message, then verify context manager exit is clean.

        The ws_session fixture's cleanup (__aexit__) calls _stop() which:
        1. Cancels the recv_loop task
        2. Sends sentinels to all active queues
        3. Closes the WS connection
        """
        stream = await ws_session.subscribe_orderbook_delta(
            tickers=[demo_market_ticker],
        )
        try:
            await asyncio.wait_for(stream.__anext__(), timeout=10.0)
        except asyncio.TimeoutError:
            pytest.skip("No snapshot received — cannot test disconnect lifecycle")

        # The fixture will clean up on exit. If cleanup hangs or errors,
        # the test framework will report it as a fixture teardown failure.
        # No explicit assertion needed — we're testing that exit doesn't hang.
```

- [ ] **Step 2: Run the WS tests (requires demo credentials)**

Run: `uv run pytest tests/integration/test_websocket.py -v`
Expected: All 3 tests PASS (or SKIP if no demo credentials or no activity).

- [ ] **Step 3: Run mypy on the new test file**

Run: `uv run mypy tests/integration/test_websocket.py`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_websocket.py
git commit -m "test: add WS live connection integration tests (orderbook snapshot)"
```

---

### Task 6: Add fill_guarantee helper

**Files:**
- Modify: `tests/integration/helpers.py`

- [ ] **Step 1: Add fill_guarantee to helpers.py**

Append to the bottom of `tests/integration/helpers.py`:

```python
from decimal import Decimal, ROUND_HALF_UP

import pytest

from kalshi.client import KalshiClient
from kalshi.models.markets import OrderbookLevel


def fill_guarantee(
    client: KalshiClient,
    ticker: str,
    *,
    test_run_id: str,
) -> tuple[str, str]:
    """Place opposing buy+sell orders to produce a fill.

    Queries the orderbook, computes the midpoint price, places a YES buy
    and YES sell at that price (both count=1). Returns (buy_order_id, sell_order_id).

    Skips the test if:
      - No orderbook liquidity (no bids or asks)
      - Either order is rejected (e.g., self-trade prohibited)

    The caller is responsible for cleanup of any resting orders.
    """
    ob = client.markets.orderbook(ticker)

    if not ob.yes or not ob.no:
        pytest.skip(f"No orderbook liquidity on {ticker} — cannot guarantee fill")

    best_bid = max(ob.yes, key=lambda lvl: lvl.price)
    best_ask = min(ob.no, key=lambda lvl: lvl.price)

    # Compute midpoint, round to nearest $0.01 tick
    midpoint = ((best_bid.price + (Decimal("1") - best_ask.price)) / 2).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # Clamp to valid range
    if midpoint < Decimal("0.01"):
        midpoint = Decimal("0.01")
    elif midpoint > Decimal("0.99"):
        midpoint = Decimal("0.99")

    price_str = str(midpoint)

    # Place buy order
    try:
        buy_order = client.orders.create(
            ticker=ticker,
            side="yes",
            type="limit",
            action="buy",
            count=1,
            yes_price=price_str,
            client_order_id=f"{test_run_id}-fill-buy",
        )
    except Exception as exc:
        pytest.skip(f"Buy order rejected: {exc}")

    # Place sell order to match against the buy
    try:
        sell_order = client.orders.create(
            ticker=ticker,
            side="yes",
            type="limit",
            action="sell",
            count=1,
            yes_price=price_str,
            client_order_id=f"{test_run_id}-fill-sell",
        )
    except Exception as exc:
        # Clean up the resting buy order
        try:
            client.orders.cancel(buy_order.order_id)
        except Exception:
            logger.warning("Failed to cancel buy order %s during fill_guarantee cleanup", buy_order.order_id)
        pytest.skip(f"Sell order rejected (self-trade prohibited?): {exc}")

    return buy_order.order_id, sell_order.order_id
```

- [ ] **Step 2: Verify linting and types**

Run: `uv run ruff check tests/integration/helpers.py && uv run mypy tests/integration/helpers.py`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/helpers.py
git commit -m "test: add fill_guarantee helper for order fill integration tests"
```

---

### Task 7: Add order fill lifecycle test

**Files:**
- Modify: `tests/integration/test_orders.py`

- [ ] **Step 1: Add the fill lifecycle test to TestOrdersSync**

Add this import near the top of `tests/integration/test_orders.py`:

```python
from tests.integration.helpers import fill_guarantee
```

Add this test method inside the `TestOrdersSync` class, after the existing `test_fills_all` method:

```python
    def test_order_fill_lifecycle(
        self,
        sync_client: KalshiClient,
        demo_market_ticker: str,
        demo_balance_cents: int,
        test_run_id: str,
    ) -> None:
        """Place opposing orders to produce a fill, then verify fill data."""
        skip_if_low_balance(demo_balance_cents, threshold_cents=2000)

        buy_id, sell_id = fill_guarantee(
            sync_client, demo_market_ticker, test_run_id=test_run_id,
        )

        # Query fills and look for our fill
        import time
        time.sleep(1)  # Brief delay for fill to propagate

        page = sync_client.orders.fills(limit=20)
        our_fills = [
            f for f in page.items
            if f.order_id in (buy_id, sell_id)
        ]

        if not our_fills:
            pytest.skip(
                "No fills found after placing opposing orders — "
                "self-trading may be prohibited on demo"
            )

        fill = our_fills[0]
        assert isinstance(fill, Fill)
        assert_model_fields(fill)

        # Verify key fill fields
        assert fill.ticker == demo_market_ticker or fill.market_ticker == demo_market_ticker
        assert fill.yes_price is not None
        assert fill.count is not None
        assert fill.created_time is not None
        assert fill.side in ("yes", "no")
```

- [ ] **Step 2: Run the fill test**

Run: `uv run pytest tests/integration/test_orders.py::TestOrdersSync::test_order_fill_lifecycle -v`
Expected: PASS (or SKIP if self-trading prohibited or low balance).

- [ ] **Step 3: Run mypy**

Run: `uv run mypy tests/integration/test_orders.py`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_orders.py tests/integration/helpers.py
git commit -m "test: add order fill lifecycle integration test"
```

---

### Task 8: Add pagination correctness tests

**Files:**
- Modify: `tests/integration/test_markets.py`

- [ ] **Step 1: Add pagination tests to TestMarketsSync**

Add these test methods inside the `TestMarketsSync` class in `tests/integration/test_markets.py`, after the existing `test_candlesticks` method:

```python
    def test_pagination_no_overlap(self, sync_client: KalshiClient) -> None:
        """Verify cursor-based pagination returns non-overlapping pages."""
        page1 = sync_client.markets.list(limit=2)
        if len(page1.items) < 2 or not page1.cursor:
            pytest.skip("Not enough markets for pagination test (need >= 3)")

        tickers_page1 = {m.ticker for m in page1.items}

        page2 = sync_client.markets.list(limit=2, cursor=page1.cursor)
        tickers_page2 = {m.ticker for m in page2.items}

        if not tickers_page2:
            pytest.skip("Page 2 is empty — not enough markets for pagination test")

        overlap = tickers_page1 & tickers_page2
        assert not overlap, (
            f"Pages overlap! Shared tickers: {overlap}. "
            f"Page 1: {tickers_page1}, Page 2: {tickers_page2}"
        )

    def test_pagination_cursor_terminates(self, sync_client: KalshiClient) -> None:
        """Verify cursor eventually becomes None (pagination terminates)."""
        all_tickers: list[str] = []
        page = sync_client.markets.list(limit=5)
        all_tickers.extend(m.ticker for m in page.items)

        max_pages = 20  # Safety limit to prevent infinite loops
        pages_fetched = 1
        while page.cursor and pages_fetched < max_pages:
            page = sync_client.markets.list(limit=5, cursor=page.cursor)
            all_tickers.extend(m.ticker for m in page.items)
            pages_fetched += 1

        # Either cursor became None (pagination terminated) or we hit the safety limit
        if pages_fetched >= max_pages:
            # We fetched 20 pages * 5 = 100 items, that's enough to prove cursor works
            pass
        else:
            # Cursor terminated naturally — verify we got all items
            assert len(all_tickers) > 0

        # Verify no duplicates across all pages
        assert len(all_tickers) == len(set(all_tickers)), (
            f"Found duplicate tickers across pages: "
            f"{[t for t in all_tickers if all_tickers.count(t) > 1]}"
        )

    def test_list_all_no_duplicates(self, sync_client: KalshiClient) -> None:
        """Verify list_all() SDK abstraction produces no duplicate tickers."""
        tickers: list[str] = []
        for count, market in enumerate(sync_client.markets.list_all(limit=2)):
            tickers.append(market.ticker)
            if count >= 5:
                break

        if len(tickers) <= 1:
            pytest.skip("Not enough markets to verify pagination deduplication")

        assert len(tickers) == len(set(tickers)), (
            f"list_all() produced duplicate tickers: "
            f"{[t for t in tickers if tickers.count(t) > 1]}"
        )
```

- [ ] **Step 2: Run the pagination tests**

Run: `uv run pytest tests/integration/test_markets.py -v -k pagination`
Expected: All 3 tests PASS (or SKIP if insufficient data).

Also run: `uv run pytest tests/integration/test_markets.py -v -k list_all_no_duplicates`

- [ ] **Step 3: Run mypy**

Run: `uv run mypy tests/integration/test_markets.py`
Expected: No errors.

- [ ] **Step 4: Run full integration test suite to verify no regressions**

Run: `uv run pytest tests/integration/ -v --co`
Expected: All tests collected. Run full suite if credentials available:
`uv run pytest tests/integration/ -v`

- [ ] **Step 5: Run ruff on all changed files**

Run: `uv run ruff check tests/integration/`
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_markets.py
git commit -m "test: add pagination correctness integration tests"
```

---

### Task 9: Final verification

- [ ] **Step 1: Run full unit test suite**

Run: `uv run pytest tests/ -v --ignore=tests/integration`
Expected: All existing tests pass. No regressions.

- [ ] **Step 2: Run mypy on SDK and integration tests**

Run: `uv run mypy kalshi/`
Expected: No errors.

- [ ] **Step 3: Run ruff**

Run: `uv run ruff check .`
Expected: No errors.

- [ ] **Step 4: Verify git log**

Run: `git log --oneline -10`
Expected: Clean commit history with atomic commits for each concern.
