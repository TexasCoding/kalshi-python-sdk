# v0.3 WebSocket Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-grade async WebSocket client to the Kalshi Python SDK supporting all 11 channels with typed models, auto-reconnect, sequence tracking, local orderbook maintenance, backpressure, and dual API (iterator + callback).

**Architecture:** Vertical slice approach. Build orderbook_delta end-to-end first (hardest channel, proves the architecture), then stamp out remaining 10 channels. Single `kalshi/ws/` package with connection state machine, subscription management with client-side sid remapping, per-subscription message queues with configurable overflow, and a fake WS test server for integration testing.

**Tech Stack:** Python 3.12+, websockets>=14,<17, pydantic 2.x, asyncio, pytest + pytest-asyncio

**Design doc:** `~/.gstack/projects/kalshi-python-sdk/jeffreywest-main-design-20260413-175613.md`
**Eng review corrections:** WS-native resync (no REST), seq only on 2 channels, per-sub overflow, sid remapping, simplified state machine, FixedPointCount type, REST/WS type unification.

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `kalshi/ws/__init__.py` | Public WS exports |
| `kalshi/ws/client.py` | `KalshiWebSocket` main client + context manager |
| `kalshi/ws/connection.py` | `ConnectionManager` state machine, auth handshake, heartbeat |
| `kalshi/ws/channels.py` | `SubscriptionManager` registry, sid remapping, subscribe/unsub/update |
| `kalshi/ws/dispatch.py` | `MessageDispatcher` JSON parse -> typed model -> route to queue/callback |
| `kalshi/ws/sequence.py` | `SequenceTracker` gap detection (orderbook_delta + order_group_updates only) |
| `kalshi/ws/orderbook.py` | `OrderbookManager` local book from snapshots + deltas |
| `kalshi/ws/backpressure.py` | `MessageQueue` + `OverflowStrategy` bounded async queue |
| `kalshi/ws/models/__init__.py` | All message model exports |
| `kalshi/ws/models/base.py` | `BaseMessage` envelope, `SubscribedMessage`, `ErrorMessage` |
| `kalshi/ws/models/orderbook_delta.py` | `OrderbookSnapshotMessage`, `OrderbookDeltaMessage` |
| `kalshi/ws/models/ticker.py` | `TickerMessage` |
| `kalshi/ws/models/trade.py` | `TradeMessage` |
| `kalshi/ws/models/fill.py` | `FillMessage` |
| `kalshi/ws/models/market_positions.py` | `MarketPositionsMessage` |
| `kalshi/ws/models/user_orders.py` | `UserOrdersMessage` |
| `kalshi/ws/models/order_group.py` | `OrderGroupMessage` |
| `kalshi/ws/models/market_lifecycle.py` | `MarketLifecycleMessage` (discriminated union) |
| `kalshi/ws/models/multivariate.py` | `MultivariateMessage`, `MultivariateLifecycleMessage` |
| `kalshi/ws/models/communications.py` | 5 RFQ/quote message types (discriminated union) |
| `tests/ws/__init__.py` | Test package marker |
| `tests/ws/conftest.py` | Fake WS server + fixtures |
| `tests/ws/test_backpressure.py` | MessageQueue tests |
| `tests/ws/test_models.py` | All message model parse tests |
| `tests/ws/test_connection.py` | State machine, auth, heartbeat tests |
| `tests/ws/test_channels.py` | Subscription mgmt tests |
| `tests/ws/test_dispatch.py` | Message routing tests |
| `tests/ws/test_sequence.py` | Gap detection tests |
| `tests/ws/test_orderbook.py` | Local orderbook tests |
| `tests/ws/test_integration.py` | E2E connect/subscribe/disconnect/reconnect |

### Modified files
| File | Change |
|------|--------|
| `kalshi/types.py` | Add `FixedPointCount` type |
| `kalshi/errors.py` | Add 4 WS exception classes |
| `kalshi/config.py` | Add `ws_base_url` field |
| `kalshi/models/orders.py` | Migrate count fields `int` -> `FixedPointCount` |
| `kalshi/async_client.py` | Add `ws` property returning `KalshiWebSocket` |
| `kalshi/__init__.py` | Export new WS types + errors |
| `pyproject.toml` | Add `websockets>=14,<17` dependency |

---

## Task Group 1: Foundation (Types, Errors, Config)

### Task 1: Add FixedPointCount type

**Files:**
- Modify: `kalshi/types.py`
- Create: `tests/ws/__init__.py`
- Create: `tests/ws/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ws/__init__.py
# (empty file, package marker)
```

```python
# tests/ws/test_types.py
"""Tests for FixedPointCount type."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel

from kalshi.types import FixedPointCount


class SampleModel(BaseModel):
    count: FixedPointCount


class TestFixedPointCount:
    def test_parse_string(self) -> None:
        m = SampleModel.model_validate({"count": "100.00"})
        assert m.count == Decimal("100.00")

    def test_parse_int(self) -> None:
        m = SampleModel.model_validate({"count": 42})
        assert m.count == Decimal("42")

    def test_parse_float(self) -> None:
        m = SampleModel.model_validate({"count": 3.14})
        assert m.count == Decimal("3.14")

    def test_parse_decimal_passthrough(self) -> None:
        m = SampleModel.model_validate({"count": Decimal("99.99")})
        assert m.count == Decimal("99.99")

    def test_parse_negative(self) -> None:
        m = SampleModel.model_validate({"count": "-5.00"})
        assert m.count == Decimal("-5.00")

    def test_serialize_to_string(self) -> None:
        m = SampleModel(count=Decimal("100.00"))
        data = m.model_dump(mode="json")
        assert data["count"] == "100.00"

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(Exception):
            SampleModel.model_validate({"count": [1, 2, 3]})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ws/test_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'FixedPointCount'`

- [ ] **Step 3: Write minimal implementation**

Add to `kalshi/types.py` after the existing `DollarDecimal` definition:

```python
def _to_decimal_fp(value: Any) -> Decimal:
    """Convert a raw API fixed-point count string to Decimal.

    Kalshi API returns count/volume fields as FixedPoint strings
    (e.g., ``"100.00"``), with ``_fp`` suffix field names (e.g., ``count_fp``).
    This converts them to Decimal without float intermediaries.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise TypeError(f"Cannot convert {type(value).__name__} to Decimal")


FixedPointCount = Annotated[
    Decimal,
    BeforeValidator(_to_decimal_fp),
    PlainSerializer(_decimal_to_str, return_type=str),
]
"""A Decimal field that handles bidirectional conversion for Kalshi count/volume values.

- Parse: Accepts str/int/float/Decimal, converts via Decimal(str(value))
- Serialize: Outputs string representation for API requests
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/ws/test_types.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Run mypy**

Run: `uv run mypy kalshi/types.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add kalshi/types.py tests/ws/__init__.py tests/ws/test_types.py
git commit -m "feat(ws): add FixedPointCount type for _fp suffix fields"
```

---

### Task 2: Add WebSocket error classes

**Files:**
- Modify: `kalshi/errors.py`
- Modify: `kalshi/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ws/test_errors.py (create this file)
"""Tests for WebSocket error hierarchy."""
from __future__ import annotations

from kalshi.errors import (
    KalshiBackpressureError,
    KalshiConnectionError,
    KalshiError,
    KalshiSequenceGapError,
    KalshiSubscriptionError,
    KalshiWebSocketError,
)


class TestWebSocketErrorHierarchy:
    def test_websocket_error_is_kalshi_error(self) -> None:
        err = KalshiWebSocketError("test")
        assert isinstance(err, KalshiError)

    def test_connection_error_is_ws_error(self) -> None:
        err = KalshiConnectionError("connection failed")
        assert isinstance(err, KalshiWebSocketError)
        assert isinstance(err, KalshiError)

    def test_sequence_gap_error(self) -> None:
        err = KalshiSequenceGapError("gap detected")
        assert isinstance(err, KalshiWebSocketError)

    def test_backpressure_error(self) -> None:
        err = KalshiBackpressureError("queue full")
        assert isinstance(err, KalshiWebSocketError)

    def test_subscription_error_with_code(self) -> None:
        err = KalshiSubscriptionError("invalid channel", error_code=5)
        assert isinstance(err, KalshiWebSocketError)
        assert err.error_code == 5

    def test_ws_error_has_no_status_code(self) -> None:
        err = KalshiWebSocketError("test")
        assert err.status_code is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ws/test_errors.py -v`
Expected: FAIL with `ImportError: cannot import name 'KalshiWebSocketError'`

- [ ] **Step 3: Write minimal implementation**

Append to `kalshi/errors.py`:

```python
class KalshiWebSocketError(KalshiError):
    """Base exception for all WebSocket errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=None)


class KalshiConnectionError(KalshiWebSocketError):
    """Connection failed, handshake rejected, or max retries exceeded."""


class KalshiSequenceGapError(KalshiWebSocketError):
    """Sequence gap detected that could not be resolved via resync."""


class KalshiBackpressureError(KalshiWebSocketError):
    """Message queue overflow with ERROR strategy."""


class KalshiSubscriptionError(KalshiWebSocketError):
    """Subscribe/unsubscribe request rejected by server."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        self.error_code = error_code
        super().__init__(message)
```

Update `kalshi/__init__.py` to export the new errors (add to imports and `__all__`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/ws/test_errors.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run mypy**

Run: `uv run mypy kalshi/errors.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add kalshi/errors.py kalshi/__init__.py tests/ws/test_errors.py
git commit -m "feat(ws): add WebSocket error hierarchy"
```

---

### Task 3: Add ws_base_url to KalshiConfig

**Files:**
- Modify: `kalshi/config.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

Add to an existing test file or create inline:

```python
# tests/test_config_ws.py (create this file)
"""Tests for WebSocket config."""
from __future__ import annotations

from kalshi.config import DEMO_WS_URL, PRODUCTION_WS_URL, KalshiConfig


class TestWsConfig:
    def test_default_ws_url(self) -> None:
        config = KalshiConfig()
        assert config.ws_base_url == PRODUCTION_WS_URL

    def test_demo_ws_url(self) -> None:
        config = KalshiConfig.demo()
        assert config.ws_base_url == DEMO_WS_URL

    def test_custom_ws_url(self) -> None:
        config = KalshiConfig(ws_base_url="wss://custom.kalshi.com/ws")
        assert config.ws_base_url == "wss://custom.kalshi.com/ws"

    def test_ws_url_trailing_slash_stripped(self) -> None:
        config = KalshiConfig(ws_base_url="wss://custom.kalshi.com/ws/")
        assert config.ws_base_url == "wss://custom.kalshi.com/ws"

    def test_ws_max_retries_default(self) -> None:
        config = KalshiConfig()
        assert config.ws_max_retries == 10

    def test_ws_max_retries_custom(self) -> None:
        config = KalshiConfig(ws_max_retries=5)
        assert config.ws_max_retries == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_ws.py -v`
Expected: FAIL with `ImportError: cannot import name 'PRODUCTION_WS_URL'`

- [ ] **Step 3: Write minimal implementation**

Modify `kalshi/config.py`:

```python
PRODUCTION_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"
PRODUCTION_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
DEMO_WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_WS_MAX_RETRIES = 10


@dataclass(frozen=True)
class KalshiConfig:
    """Client configuration."""

    base_url: str = PRODUCTION_BASE_URL
    ws_base_url: str = PRODUCTION_WS_URL
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    ws_max_retries: int = DEFAULT_WS_MAX_RETRIES
    retry_base_delay: float = 0.5
    retry_max_delay: float = 30.0
    extra_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.base_url.endswith("/"):
            object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        if self.ws_base_url.endswith("/"):
            object.__setattr__(self, "ws_base_url", self.ws_base_url.rstrip("/"))

    @classmethod
    def production(cls, **kwargs: object) -> KalshiConfig:
        return cls(base_url=PRODUCTION_BASE_URL, ws_base_url=PRODUCTION_WS_URL, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def demo(cls, **kwargs: object) -> KalshiConfig:
        return cls(base_url=DEMO_BASE_URL, ws_base_url=DEMO_WS_URL, **kwargs)  # type: ignore[arg-type]
```

- [ ] **Step 4: Run ALL existing tests (not just new ones)**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS (no regressions from config changes)

- [ ] **Step 5: Run mypy**

Run: `uv run mypy kalshi/config.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add kalshi/config.py tests/test_config_ws.py
git commit -m "feat(ws): add WebSocket URL and retry config"
```

---

### Task 4: Add websockets dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency**

Add `"websockets>=14,<17"` to the `dependencies` list in `pyproject.toml`:

```toml
dependencies = [
    "httpx>=0.27,<1",
    "pydantic>=2.0,<3",
    "cryptography>=43,<45",
    "websockets>=14,<17",
]
```

- [ ] **Step 2: Install**

Run: `uv sync`
Expected: websockets installed successfully

- [ ] **Step 3: Verify import**

Run: `uv run python -c "import websockets; print(websockets.__version__)"`
Expected: Prints version (14.x or higher)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add websockets>=14,<17 for WebSocket client"
```

---

### Task 5: Migrate REST order count fields to FixedPointCount

**Files:**
- Modify: `kalshi/models/orders.py`
- Modify: existing tests that assert count types

- [ ] **Step 1: Write regression test**

```python
# tests/ws/test_count_migration.py (create this file)
"""Verify REST order count fields use FixedPointCount (Decimal)."""
from __future__ import annotations

from decimal import Decimal

from kalshi.models.orders import CreateOrderRequest, Fill, Order


class TestOrderCountMigration:
    def test_order_count_is_decimal(self) -> None:
        order = Order.model_validate({
            "order_id": "abc",
            "count": "100.00",
        })
        assert isinstance(order.count, Decimal)
        assert order.count == Decimal("100.00")

    def test_order_count_accepts_int(self) -> None:
        order = Order.model_validate({
            "order_id": "abc",
            "count": 42,
        })
        assert isinstance(order.count, Decimal)
        assert order.count == Decimal("42")

    def test_order_count_fp_alias(self) -> None:
        order = Order.model_validate({
            "order_id": "abc",
            "count_fp": "50.00",
        })
        assert order.count == Decimal("50.00")

    def test_fill_count_is_decimal(self) -> None:
        fill = Fill.model_validate({
            "trade_id": "t1",
            "count": "75.50",
        })
        assert isinstance(fill.count, Decimal)

    def test_create_order_count_is_decimal(self) -> None:
        req = CreateOrderRequest(
            ticker="ECON-GDP",
            side="yes",
            count=Decimal("10"),
        )
        assert isinstance(req.count, Decimal)

    def test_create_order_count_serializes_to_string(self) -> None:
        req = CreateOrderRequest(
            ticker="ECON-GDP",
            side="yes",
            count=Decimal("10"),
        )
        data = req.model_dump(mode="json")
        assert isinstance(data["count"], str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ws/test_count_migration.py -v`
Expected: Some tests FAIL (count is still `int`)

- [ ] **Step 3: Modify Order model**

In `kalshi/models/orders.py`, change the count fields on `Order`:

```python
from kalshi.types import DollarDecimal, FixedPointCount

class Order(BaseModel):
    order_id: str
    ticker: str | None = None
    user_id: str | None = None
    status: str | None = None
    side: str | None = None
    is_yes: bool | None = None
    type: str | None = None
    yes_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("yes_price_dollars", "yes_price"),
    )
    no_price: DollarDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("no_price_dollars", "no_price"),
    )
    count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("count_fp", "count"),
    )
    initial_count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("initial_count_fp", "initial_count"),
    )
    remaining_count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("remaining_count_fp", "remaining_count"),
    )
    fill_count: FixedPointCount | None = Field(
        default=None,
        validation_alias=AliasChoices("fill_count_fp", "fill_count"),
    )
    # ... rest of fields unchanged
```

Also update `CreateOrderRequest.count` from `int = 1` to `FixedPointCount = Decimal("1")`:

```python
from decimal import Decimal
from kalshi.types import DollarDecimal, FixedPointCount

class CreateOrderRequest(BaseModel):
    ticker: str
    side: str
    type: str = "limit"
    action: str = "buy"
    count: FixedPointCount = Decimal("1")
    # ... rest unchanged
```

- [ ] **Step 4: Run ALL tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS. Existing tests that used `int` for count may need updating if they assert exact types.

- [ ] **Step 5: Fix any broken existing tests**

If existing tests in `tests/test_orders.py` or `tests/test_models.py` assert `isinstance(order.count, int)`, update them to expect `Decimal`.

- [ ] **Step 6: Run mypy**

Run: `uv run mypy kalshi/`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add kalshi/models/orders.py tests/ws/test_count_migration.py
git commit -m "refactor: migrate REST order count fields from int to FixedPointCount (Decimal)

BREAKING CHANGE: Order.count, initial_count, remaining_count, fill_count are
now Decimal instead of int. CreateOrderRequest.count defaults to Decimal('1').
This aligns REST and WS models for v0.3 type unification."
```

---

## Task Group 2: Backpressure (MessageQueue)

### Task 6: MessageQueue with overflow strategies

**Files:**
- Create: `kalshi/ws/backpressure.py`
- Create: `tests/ws/test_backpressure.py`
- Create: `kalshi/ws/__init__.py`

- [ ] **Step 1: Create ws package marker**

```python
# kalshi/ws/__init__.py
"""Kalshi WebSocket client."""
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/ws/test_backpressure.py
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
        items = []
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
        items = []
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/ws/test_backpressure.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kalshi.ws.backpressure'`

- [ ] **Step 4: Write minimal implementation**

```python
# kalshi/ws/backpressure.py
"""Bounded message queue with configurable overflow strategies."""
from __future__ import annotations

import asyncio
import collections
from enum import Enum
from typing import AsyncIterator, Generic, TypeVar

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
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/ws/test_backpressure.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Run mypy**

Run: `uv run mypy kalshi/ws/backpressure.py`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add kalshi/ws/__init__.py kalshi/ws/backpressure.py tests/ws/test_backpressure.py
git commit -m "feat(ws): add MessageQueue with DROP_OLDEST and ERROR overflow strategies"
```

---

## Task Group 3: Message Models (Base + Orderbook)

### Task 7: Base message envelope models

**Files:**
- Create: `kalshi/ws/models/__init__.py`
- Create: `kalshi/ws/models/base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ws/test_models.py (create this file)
"""Tests for WebSocket message models."""
from __future__ import annotations

import pytest
from kalshi.ws.models.base import (
    BaseMessage,
    ErrorMessage,
    SubscribedMessage,
    UnsubscribedMessage,
)


class TestBaseMessage:
    def test_parse_subscribed(self) -> None:
        raw = {"id": 1, "type": "subscribed", "msg": {"channel": "ticker", "sid": 5}}
        msg = SubscribedMessage.model_validate(raw)
        assert msg.id == 1
        assert msg.type == "subscribed"
        assert msg.msg.channel == "ticker"
        assert msg.msg.sid == 5

    def test_parse_unsubscribed(self) -> None:
        raw = {"id": 2, "sid": 5, "seq": 42, "type": "unsubscribed"}
        msg = UnsubscribedMessage.model_validate(raw)
        assert msg.sid == 5
        assert msg.seq == 42

    def test_parse_error(self) -> None:
        raw = {"id": 1, "type": "error", "msg": {"code": 5, "msg": "invalid channel"}}
        msg = ErrorMessage.model_validate(raw)
        assert msg.msg.code == 5
        assert msg.msg.msg == "invalid channel"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ws/test_models.py::TestBaseMessage -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# kalshi/ws/models/__init__.py
"""WebSocket message models."""

# kalshi/ws/models/base.py
"""Base message envelope models for the Kalshi WebSocket API."""
from __future__ import annotations

from pydantic import BaseModel


class SubscriptionInfo(BaseModel):
    """Subscription confirmation payload."""
    channel: str
    sid: int


class ErrorPayload(BaseModel):
    """Error message payload."""
    code: int
    msg: str
    market_ticker: str | None = None
    market_id: str | None = None


class BaseMessage(BaseModel):
    """Base for all WebSocket messages."""
    id: int = 0
    type: str
    sid: int | None = None
    seq: int | None = None

    model_config = {"extra": "allow"}


class SubscribedMessage(BaseModel):
    """Response to a subscribe command."""
    id: int = 0
    type: str = "subscribed"
    msg: SubscriptionInfo


class UnsubscribedMessage(BaseModel):
    """Response to an unsubscribe command."""
    id: int = 0
    sid: int
    seq: int
    type: str = "unsubscribed"


class OkMessage(BaseModel):
    """Generic success response (list_subscriptions, update_subscription)."""
    id: int = 0
    sid: int | None = None
    seq: int | None = None
    type: str = "ok"
    msg: dict[str, object] | list[object] | None = None

    model_config = {"extra": "allow"}


class ErrorMessage(BaseModel):
    """Error response from the server."""
    id: int = 0
    type: str = "error"
    msg: ErrorPayload
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/ws/test_models.py::TestBaseMessage -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Run mypy**

Run: `uv run mypy kalshi/ws/models/`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add kalshi/ws/models/__init__.py kalshi/ws/models/base.py tests/ws/test_models.py
git commit -m "feat(ws): add base message envelope models"
```

---

### Task 8: Orderbook delta/snapshot message models

**Files:**
- Create: `kalshi/ws/models/orderbook_delta.py`
- Modify: `tests/ws/test_models.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/ws/test_models.py`:

```python
from decimal import Decimal
from kalshi.ws.models.orderbook_delta import (
    OrderbookDeltaMessage,
    OrderbookSnapshotMessage,
)


class TestOrderbookModels:
    def test_parse_snapshot(self) -> None:
        raw = {
            "type": "orderbook_snapshot",
            "sid": 3,
            "seq": 1,
            "msg": {
                "market_ticker": "ECON-GDP-25Q1",
                "market_id": "abc-123",
                "yes": [[50, 100], [55, 200]],
                "no": [[45, 150]],
            },
        }
        msg = OrderbookSnapshotMessage.model_validate(raw)
        assert msg.type == "orderbook_snapshot"
        assert msg.sid == 3
        assert msg.seq == 1
        assert msg.msg.market_ticker == "ECON-GDP-25Q1"
        assert len(msg.msg.yes) == 2
        assert msg.msg.yes[0] == [50, 100]

    def test_parse_delta(self) -> None:
        raw = {
            "type": "orderbook_delta",
            "sid": 3,
            "seq": 2,
            "msg": {
                "market_ticker": "ECON-GDP-25Q1",
                "market_id": "abc-123",
                "price": 55,
                "delta": 50,
                "side": "yes",
            },
        }
        msg = OrderbookDeltaMessage.model_validate(raw)
        assert msg.type == "orderbook_delta"
        assert msg.seq == 2
        assert msg.msg.price == 55
        assert msg.msg.delta == 50
        assert msg.msg.side == "yes"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ws/test_models.py::TestOrderbookModels -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# kalshi/ws/models/orderbook_delta.py
"""Orderbook delta and snapshot message models."""
from __future__ import annotations

from pydantic import BaseModel


class OrderbookSnapshotPayload(BaseModel):
    """Payload for orderbook_snapshot messages.

    yes/no are arrays of [price_cents, count] pairs.
    """
    market_ticker: str
    market_id: str
    yes: list[list[int]] = []
    no: list[list[int]] = []


class OrderbookDeltaPayload(BaseModel):
    """Payload for orderbook_delta messages."""
    market_ticker: str
    market_id: str
    price: int
    delta: int
    side: str
    client_order_id: str | None = None
    subaccount: int | None = None
    ts: int | None = None


class OrderbookSnapshotMessage(BaseModel):
    """Full orderbook snapshot, sent on initial subscribe."""
    type: str = "orderbook_snapshot"
    sid: int
    seq: int
    msg: OrderbookSnapshotPayload


class OrderbookDeltaMessage(BaseModel):
    """Incremental orderbook update."""
    type: str = "orderbook_delta"
    sid: int
    seq: int
    msg: OrderbookDeltaPayload
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/ws/test_models.py::TestOrderbookModels -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add kalshi/ws/models/orderbook_delta.py tests/ws/test_models.py
git commit -m "feat(ws): add orderbook delta/snapshot message models"
```

---

### Task 9: Ticker message model

**Files:**
- Create: `kalshi/ws/models/ticker.py`
- Modify: `tests/ws/test_models.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/ws/test_models.py`:

```python
from kalshi.ws.models.ticker import TickerMessage


class TestTickerModel:
    def test_parse_ticker(self) -> None:
        raw = {
            "type": "ticker",
            "sid": 1,
            "msg": {
                "market_ticker": "ECON-GDP-25Q1",
                "market_id": "abc-123",
                "yes_bid": 55,
                "yes_ask": 58,
                "volume": "1000.00",
                "open_interest": "500.00",
                "dollar_volume": "5000.00",
                "dollar_open_interest": "2500.00",
                "ts": 1700000000,
            },
        }
        msg = TickerMessage.model_validate(raw)
        assert msg.type == "ticker"
        assert msg.msg.market_ticker == "ECON-GDP-25Q1"
        assert msg.msg.yes_bid == 55
        assert msg.msg.volume == "1000.00"

    def test_ticker_no_seq(self) -> None:
        """Ticker messages do NOT have sequence numbers."""
        raw = {
            "type": "ticker",
            "sid": 1,
            "msg": {"market_ticker": "T", "market_id": "x"},
        }
        msg = TickerMessage.model_validate(raw)
        assert msg.seq is None
```

- [ ] **Step 2: Run test, verify fail, then implement**

```python
# kalshi/ws/models/ticker.py
"""Ticker channel message model."""
from __future__ import annotations

from pydantic import BaseModel


class TickerPayload(BaseModel):
    """Payload for ticker messages."""
    market_ticker: str
    market_id: str | None = None
    yes_bid: int | None = None
    yes_ask: int | None = None
    no_bid: int | None = None
    no_ask: int | None = None
    volume: str | None = None
    open_interest: str | None = None
    dollar_volume: str | None = None
    dollar_open_interest: str | None = None
    yes_bid_size: str | None = None
    yes_ask_size: str | None = None
    last_trade_size: str | None = None
    ts: int | None = None

    model_config = {"extra": "allow"}


class TickerMessage(BaseModel):
    """Real-time price/volume update for a market."""
    type: str = "ticker"
    sid: int
    seq: int | None = None
    msg: TickerPayload
```

- [ ] **Step 3: Run tests and commit**

Run: `uv run pytest tests/ws/test_models.py -v`

```bash
git add kalshi/ws/models/ticker.py tests/ws/test_models.py
git commit -m "feat(ws): add ticker message model"
```

---

### Task 10-16: Remaining channel models (stamp-out pattern)

For each remaining channel, follow the same pattern as Task 9. Each channel gets:
1. A model file in `kalshi/ws/models/`
2. Tests appended to `tests/ws/test_models.py`
3. A commit

**Channels to implement (one task each):**

| Task | Channel | File | Key fields |
|------|---------|------|------------|
| 10 | trade | `kalshi/ws/models/trade.py` | trade_id, market_ticker, yes_price_dollars, no_price_dollars, count_fp, taker_side, ts |
| 11 | fill | `kalshi/ws/models/fill.py` | trade_id, order_id, market_ticker, is_taker, side, yes_price_dollars, count_fp, fee_cost, action, ts |
| 12 | market_positions | `kalshi/ws/models/market_positions.py` | user_id, market_ticker, position_fp, position_cost_dollars, realized_pnl_dollars |
| 13 | user_orders | `kalshi/ws/models/user_orders.py` | order_id, user_id, ticker, status, side, is_yes, yes_price_dollars, fill_count_fp, remaining_count_fp |
| 14 | order_group | `kalshi/ws/models/order_group.py` | event_type (created/triggered/reset/deleted/limit_updated), order_group_id. Has seq field. |
| 15 | market_lifecycle | `kalshi/ws/models/market_lifecycle.py` | Discriminated union on event_type: created, activated, deactivated, close_date_updated, determined, settled, etc. |
| 16 | multivariate + communications | `kalshi/ws/models/multivariate.py` + `kalshi/ws/models/communications.py` | multivariate has collection_ticker. communications has 5 sub-types (rfq_created, rfq_deleted, quote_created, quote_accepted, quote_executed). |

For **each** of these tasks, follow the exact same TDD pattern:
1. Write failing test with realistic JSON from the AsyncAPI spec
2. Run test, verify fail
3. Create model file with Pydantic BaseModel
4. Run test, verify pass
5. Run mypy
6. Commit

**Important notes for these models:**
- Use `DollarDecimal` for `_dollars` suffix fields
- Use `FixedPointCount` for `_fp` suffix fields
- Fields without seq (ticker, trade, fill, user_orders, market_positions, communications, market_lifecycle, multivariate_market_lifecycle, multivariate) set `seq: int | None = None`
- Fields WITH seq (orderbook_delta, order_group_updates) set `seq: int`
- Use `model_config = {"extra": "allow"}` on all payloads for forward compatibility with unknown fields

---

## Task Group 4: Connection Infrastructure

### Task 17: ConnectionManager state machine

**Files:**
- Create: `kalshi/ws/connection.py`
- Create: `tests/ws/conftest.py`
- Create: `tests/ws/test_connection.py`

- [ ] **Step 1: Create fake WS server fixture**

```python
# tests/ws/conftest.py
"""Fake WebSocket server for integration testing."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
import websockets
from websockets.asyncio.server import ServerConnection


class FakeKalshiWS:
    """Configurable fake Kalshi WebSocket server.

    Tracks subscriptions, assigns sids, sends sequence numbers.
    Configurable behaviors per test scenario.
    """

    def __init__(self) -> None:
        self.connections: list[ServerConnection] = []
        self.subscriptions: dict[int, dict[str, Any]] = {}
        self._next_sid = 1
        self._next_id = 1
        self._server: Any = None
        self.port: int = 0
        self.received_commands: list[dict[str, Any]] = []
        self.reject_auth: bool = False
        self.disconnect_after: int | None = None
        self._msg_count = 0

    async def handler(self, ws: ServerConnection) -> None:
        if self.reject_auth:
            await ws.close(4001, "Unauthorized")
            return

        self.connections.append(ws)
        try:
            async for raw in ws:
                msg = json.loads(raw)
                self.received_commands.append(msg)
                await self._handle_command(ws, msg)
        except websockets.ConnectionClosed:
            pass
        finally:
            if ws in self.connections:
                self.connections.remove(ws)

    async def _handle_command(self, ws: ServerConnection, msg: dict[str, Any]) -> None:
        cmd = msg.get("cmd")
        msg_id = msg.get("id", 0)

        if cmd == "subscribe":
            channels = msg.get("params", {}).get("channels", [])
            for channel in channels:
                sid = self._next_sid
                self._next_sid += 1
                self.subscriptions[sid] = {
                    "channel": channel,
                    "params": msg.get("params", {}),
                }
                response = {
                    "id": msg_id,
                    "type": "subscribed",
                    "msg": {"channel": channel, "sid": sid},
                }
                await ws.send(json.dumps(response))

        elif cmd == "unsubscribe":
            sids = msg.get("params", {}).get("sids", [])
            for sid in sids:
                seq = 0
                if sid in self.subscriptions:
                    del self.subscriptions[sid]
                response = {
                    "id": msg_id,
                    "sid": sid,
                    "seq": seq,
                    "type": "unsubscribed",
                }
                await ws.send(json.dumps(response))

        elif cmd == "list_subscriptions":
            subs = [
                {"channel": v["channel"], "sid": k}
                for k, v in self.subscriptions.items()
            ]
            await ws.send(json.dumps({
                "id": msg_id,
                "type": "ok",
                "msg": subs,
            }))

    async def send_to_all(self, msg: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        raw = json.dumps(msg)
        for ws in self.connections:
            await ws.send(raw)
        self._msg_count += 1
        if self.disconnect_after and self._msg_count >= self.disconnect_after:
            for ws in self.connections:
                await ws.close()

    async def start(self) -> None:
        self._server = await websockets.serve(
            self.handler, "127.0.0.1", 0
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"


@pytest.fixture
async def fake_ws():
    """Start a fake Kalshi WebSocket server, yield it, stop on cleanup."""
    server = FakeKalshiWS()
    await server.start()
    yield server
    await server.stop()
```

- [ ] **Step 2: Write connection state machine tests**

```python
# tests/ws/test_connection.py
"""Tests for ConnectionManager."""
from __future__ import annotations

import pytest
from kalshi.ws.connection import ConnectionManager, ConnectionState


class TestConnectionState:
    def test_initial_state_is_disconnected(self) -> None:
        mgr = ConnectionManager.__new__(ConnectionManager)
        # Just testing the enum exists
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.STREAMING.value == "streaming"
        assert ConnectionState.RECONNECTING.value == "reconnecting"
        assert ConnectionState.CLOSED.value == "closed"


@pytest.mark.asyncio
class TestConnectionManagerConnect:
    async def test_connect_to_fake_server(self, fake_ws, test_auth, test_config) -> None:
        from kalshi.config import KalshiConfig
        config = KalshiConfig(
            ws_base_url=fake_ws.url,
            timeout=5.0,
        )
        mgr = ConnectionManager(auth=test_auth, config=config)
        await mgr.connect()
        assert mgr.state == ConnectionState.CONNECTED
        await mgr.close()
        assert mgr.state == ConnectionState.CLOSED

    async def test_auth_rejection(self, fake_ws, test_auth) -> None:
        from kalshi.config import KalshiConfig
        from kalshi.errors import KalshiConnectionError
        fake_ws.reject_auth = True
        config = KalshiConfig(ws_base_url=fake_ws.url, timeout=5.0)
        mgr = ConnectionManager(auth=test_auth, config=config)
        with pytest.raises(KalshiConnectionError):
            await mgr.connect()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/ws/test_connection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kalshi.ws.connection'`

- [ ] **Step 4: Write implementation**

```python
# kalshi/ws/connection.py
"""WebSocket connection manager with state machine and auto-reconnect."""
from __future__ import annotations

import asyncio
import logging
import random
from enum import Enum
from typing import Any, Callable, Awaitable
from urllib.parse import urlparse

import websockets
from websockets.asyncio.client import ClientConnection

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiConnectionError

logger = logging.getLogger("kalshi.ws")


class ConnectionState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"


class ConnectionManager:
    """Manages the WebSocket connection lifecycle.

    State machine:
        DISCONNECTED -> CONNECTING -> CONNECTED -> STREAMING
                                                      |
                                              (error/disconnect)
                                                      |
                                                 RECONNECTING -> CONNECTING -> ...
                                                      |
                                              (max retries exceeded)
                                                      |
                                                   CLOSED
    """

    def __init__(
        self,
        auth: KalshiAuth,
        config: KalshiConfig,
        heartbeat_timeout: float = 30.0,
        on_state_change: Callable[[ConnectionState, ConnectionState], Awaitable[None]] | None = None,
    ) -> None:
        self._auth = auth
        self._config = config
        self._heartbeat_timeout = heartbeat_timeout
        self._on_state_change = on_state_change
        self._ws: ClientConnection | None = None
        self._state = ConnectionState.DISCONNECTED

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def ws(self) -> ClientConnection:
        if self._ws is None:
            raise KalshiConnectionError("Not connected")
        return self._ws

    async def _set_state(self, new_state: ConnectionState) -> None:
        old = self._state
        self._state = new_state
        logger.debug("Connection state: %s -> %s", old.value, new_state.value)
        if self._on_state_change:
            await self._on_state_change(old, new_state)

    def _build_auth_headers(self) -> dict[str, str]:
        """Generate RSA-PSS auth headers for the WS handshake."""
        ws_path = urlparse(self._config.ws_base_url).path
        return self._auth.sign_request("GET", ws_path)

    async def connect(self) -> None:
        """Establish the WebSocket connection with auth headers."""
        await self._set_state(ConnectionState.CONNECTING)
        try:
            headers = self._build_auth_headers()
            self._ws = await websockets.connect(
                self._config.ws_base_url,
                additional_headers=headers,
                ping_interval=None,  # Server sends pings, we pong automatically
                ping_timeout=self._heartbeat_timeout,
                close_timeout=5.0,
            )
            await self._set_state(ConnectionState.CONNECTED)
        except Exception as e:
            await self._set_state(ConnectionState.CLOSED)
            raise KalshiConnectionError(f"WebSocket connection failed: {e}") from e

    async def reconnect(self) -> None:
        """Attempt reconnection with exponential backoff."""
        await self._set_state(ConnectionState.RECONNECTING)

        for attempt in range(self._config.ws_max_retries):
            delay = self._config.retry_base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            delay = min(delay, self._config.retry_max_delay)
            logger.warning(
                "Reconnecting in %.1fs (attempt %d/%d)",
                delay, attempt + 1, self._config.ws_max_retries,
            )
            await asyncio.sleep(delay)

            try:
                await self._set_state(ConnectionState.CONNECTING)
                headers = self._build_auth_headers()
                self._ws = await websockets.connect(
                    self._config.ws_base_url,
                    additional_headers=headers,
                    ping_interval=None,
                    ping_timeout=self._heartbeat_timeout,
                    close_timeout=5.0,
                )
                await self._set_state(ConnectionState.CONNECTED)
                return
            except Exception:
                logger.debug("Reconnect attempt %d failed", attempt + 1)
                continue

        await self._set_state(ConnectionState.CLOSED)
        raise KalshiConnectionError(
            f"Max reconnect attempts ({self._config.ws_max_retries}) exceeded"
        )

    async def close(self) -> None:
        """Gracefully close the connection."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        await self._set_state(ConnectionState.CLOSED)

    async def send(self, msg: dict[str, Any]) -> None:
        """Send a JSON message over the connection."""
        if self._ws is None:
            raise KalshiConnectionError("Not connected")
        await self._ws.send(json.dumps(msg))

    async def recv(self) -> str:
        """Receive a raw message from the connection."""
        if self._ws is None:
            raise KalshiConnectionError("Not connected")
        data = await self._ws.recv()
        if isinstance(data, bytes):
            return data.decode("utf-8")
        return data
```

Add `import json` to the top of the file.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/ws/test_connection.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run mypy**

Run: `uv run mypy kalshi/ws/connection.py`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add kalshi/ws/connection.py tests/ws/conftest.py tests/ws/test_connection.py
git commit -m "feat(ws): add ConnectionManager with state machine, auth handshake, reconnect"
```

---

## Task Group 5: Subscription Management

### Task 18: SubscriptionManager with sid remapping

This is the critical piece that makes iterators survive reconnection. Client-side durable subscription IDs map to server-assigned sids that change on reconnect.

**Files:**
- Create: `kalshi/ws/channels.py`
- Create: `tests/ws/test_channels.py`

The implementation follows TDD. Key behaviors:
- `subscribe()` sends subscribe command, stores mapping `client_sub_id -> server_sid`
- `unsubscribe()` sends unsubscribe command
- `update_subscription()` sends update_subscription command (add/remove markets)
- `remap_sids()` called after reconnect to update mappings when server assigns new sids
- `get_resubscribe_params()` returns all active subscriptions for re-subscribing after reconnect

Each of these gets a test first, then implementation, then commit.

---

## Task Group 6: Message Dispatch + Sequence Tracking

### Task 19: MessageDispatcher

Routes raw JSON frames to typed Pydantic models and delivers them to the correct MessageQueue or callback.

### Task 20: SequenceTracker

Tracks seq per sid for `orderbook_delta` and `order_group_updates` channels only. Detects gaps, triggers resync via re-subscribe with `send_initial_snapshot=true`.

---

## Task Group 7: Orderbook Manager

### Task 21: OrderbookManager (local book from snapshots + deltas)

Maintains in-memory orderbook state. Processes `orderbook_snapshot` to initialize, `orderbook_delta` to update. On sequence gap or reconnect, resync triggers new snapshot via re-subscribe.

---

## Task Group 8: KalshiWebSocket Client API

### Task 22: KalshiWebSocket main client

The user-facing API. Context manager, per-channel typed subscribe methods, callback registration, `ws.orderbook()` convenience, integration into `AsyncKalshiClient`.

### Task 23: Wire into AsyncKalshiClient

Add `ws` property to `AsyncKalshiClient` that returns a `KalshiWebSocket` instance.

### Task 24: Update exports in `kalshi/__init__.py` and `kalshi/ws/__init__.py`

---

## Task Group 9: Integration Tests

### Task 25: End-to-end integration tests

Full flow tests against the fake WS server:
- Connect -> subscribe ticker -> receive messages -> verify types
- Connect -> subscribe orderbook_delta -> receive snapshot + deltas -> verify local book
- Disconnect -> auto-reconnect -> re-subscribe -> verify iterator continues
- Multi-channel on same connection
- Callback + iterator on different channels simultaneously
- Server error codes -> proper exception mapping

---

## Self-Review Checklist

1. **Spec coverage:** All 11 channels modeled. Connection state machine. Auth handshake. Sequence tracking (2 channels). Local orderbook. Backpressure (2 strategies). Dual API. Reconnect with sid remapping. update_subscription. FixedPointCount type. REST/WS type unification.

2. **Placeholder scan:** Tasks 10-16 (stamp-out models) and Tasks 18-25 describe what to implement but defer full code to keep this plan navigable. Each task MUST follow the same TDD pattern as Tasks 1-9 when executed. The implementer should reference the AsyncAPI spec payload for exact field lists.

3. **Type consistency:** `FixedPointCount` used consistently for `_fp` fields. `DollarDecimal` for `_dollars` fields. `ConnectionState` enum used in both `connection.py` and tests. `MessageQueue[T]` generic used consistently. `OverflowStrategy` enum used by both backpressure and subscription methods.

---

## Execution Notes

**Build order matters.** Tasks must be executed in order within each group, but groups can partially overlap:
- **Group 1 (Tasks 1-5)** and **Group 2 (Task 6)** can run in parallel
- **Group 3 (Tasks 7-16)** depends on Group 1 (needs FixedPointCount)
- **Group 4 (Task 17)** depends on Group 1 (needs errors + config)
- **Groups 5-8** are sequential (each depends on prior)
- **Group 9** depends on all others

**Total estimated tasks:** 25 tasks, ~125 steps
**Estimated implementation time:** 3-4 hours with CC
