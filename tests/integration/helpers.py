"""Test helpers — retry decorator and fill guarantee."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, TypeVar

import pytest
from websockets.exceptions import ConnectionClosed

from kalshi.client import KalshiClient
from kalshi.errors import KalshiConnectionError, KalshiError

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
            assert last_exc is not None  # loop always sets last_exc before exhausting
            raise last_exc

        return wrapper  # type: ignore[return-value]

    return decorator


def fill_guarantee(
    client: KalshiClient,
    ticker: str,
    *,
    test_run_id: str,
    price: str = "0.50",
) -> tuple[str, str]:
    """Place opposing buy+sell orders to produce a fill.

    Places a YES buy and YES sell at the same price (both count=1).
    If the orderbook has liquidity, uses the midpoint. Otherwise falls
    back to the provided price (default $0.50). Returns (buy_order_id, sell_order_id).

    Skips the test if either order is rejected (e.g., self-trade prohibited).

    The caller is responsible for cleanup of any resting orders.
    """
    ob = client.markets.orderbook(ticker)

    if ob.yes and ob.no:
        # Use orderbook midpoint for best fill price
        best_bid = max(ob.yes, key=lambda lvl: lvl.price)
        best_ask = max(ob.no, key=lambda lvl: lvl.price)
        midpoint = ((best_bid.price + (Decimal("1") - best_ask.price)) / 2).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if Decimal("0.01") <= midpoint <= Decimal("0.99"):
            price = str(midpoint)

    # Place buy order
    try:
        buy_order = client.orders.create(
            ticker=ticker,
            side="yes",
            action="buy",
            count=1,
            yes_price=price,
            client_order_id=f"{test_run_id}-fill-buy",
        )
    except KalshiError as exc:
        pytest.skip(f"Buy order rejected: {exc}")

    # Place sell order to match against the buy
    try:
        sell_order = client.orders.create(
            ticker=ticker,
            side="yes",
            action="sell",
            count=1,
            yes_price=price,
            client_order_id=f"{test_run_id}-fill-sell",
        )
    except KalshiError as exc:
        # Clean up the resting buy order
        try:
            client.orders.cancel(buy_order.order_id)
        except KalshiError:
            logger.warning(
                "Failed to cancel buy order %s during fill_guarantee cleanup",
                buy_order.order_id,
            )
        pytest.skip(f"Sell order rejected (self-trade prohibited?): {exc}")

    return buy_order.order_id, sell_order.order_id
