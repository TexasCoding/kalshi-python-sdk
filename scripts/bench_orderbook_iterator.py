"""Microbench for :class:`_OrderbookIterator.__anext__` end-to-end (#271 item 4).

Existing ``bench_orderbook_delta.py`` measures the in-place mutation cost
(``_apply_delta_inplace``) but stops short of the materialization that
``async for book in ws.orderbook(ticker)`` consumers actually pay:
``mgr.get(ticker)`` re-sorts the inner price levels and validates an
:class:`Orderbook` model on every update.

This bench drives a synthetic stream through the iterator so we measure
the full hot path a strategy sees: stream.__anext__ + mgr.get +
Orderbook validation.

Usage::

    uv run python scripts/bench_orderbook_iterator.py [--depth D] [--updates N]
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import time
from collections.abc import AsyncIterator
from decimal import Decimal

from kalshi.ws.client import _OrderbookIterator
from kalshi.ws.models.orderbook_delta import (
    OrderbookDeltaMessage,
    OrderbookDeltaPayload,
    OrderbookSnapshotMessage,
    OrderbookSnapshotPayload,
)
from kalshi.ws.orderbook import OrderbookManager


def _build_snapshot(ticker: str, depth: int) -> OrderbookSnapshotMessage:
    yes = [(Decimal("0." + f"{i:04d}"), Decimal("100.00")) for i in range(1, depth + 1)]
    no = [(Decimal("0." + f"{i:04d}"), Decimal("100.00")) for i in range(1, depth + 1)]
    return OrderbookSnapshotMessage(
        sid=1,
        seq=1,
        msg=OrderbookSnapshotPayload(
            market_ticker=ticker,
            market_id=ticker,
            yes=yes,
            no=no,
        ),
    )


def _build_delta(
    ticker: str,
    seq: int,
    price: Decimal,
    delta: Decimal,
    side: str,
) -> OrderbookDeltaMessage:
    return OrderbookDeltaMessage(
        sid=1,
        seq=seq,
        msg=OrderbookDeltaPayload(
            market_ticker=ticker,
            market_id=ticker,
            price=price,
            delta=delta,
            side=side,  # type: ignore[arg-type]
        ),
    )


async def _drive(depth: int, updates: int) -> tuple[float, int]:
    ticker = "BENCH-ITER"
    mgr = OrderbookManager()
    mgr._apply_snapshot_inplace(_build_snapshot(ticker, depth))

    deltas = [
        _build_delta(
            ticker,
            seq=i + 2,
            price=Decimal("0." + f"{(i % depth) + 1:04d}"),
            delta=Decimal("1.00") if i % 2 == 0 else Decimal("-1.00"),
            side="yes" if i % 2 == 0 else "no",
        )
        for i in range(updates)
    ]

    async def stream() -> AsyncIterator[OrderbookDeltaMessage]:
        # Simulates the recv loop: apply delta to the manager, then yield.
        # The iterator under test reads `mgr.get(ticker)` after each yield.
        for d in deltas:
            mgr._apply_delta_inplace(d)
            yield d

    it = _OrderbookIterator(stream(), mgr, ticker)
    gc.collect()
    t0 = time.perf_counter()
    consumed = 0
    async for _book in it:
        consumed += 1
    elapsed = time.perf_counter() - t0
    return elapsed, consumed


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--depth", type=int, default=100)
    p.add_argument("--updates", type=int, default=1_000)
    args = p.parse_args()

    elapsed, consumed = asyncio.run(_drive(args.depth, args.updates))
    rate = consumed / elapsed if elapsed > 0 else float("inf")
    print(f"depth={args.depth} updates={args.updates} consumed={consumed}")
    print(f"  elapsed={elapsed * 1000:.1f} ms  rate={rate:,.0f} updates/sec")


if __name__ == "__main__":
    main()
