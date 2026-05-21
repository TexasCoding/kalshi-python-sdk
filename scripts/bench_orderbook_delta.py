"""Microbench for :meth:`OrderbookManager._apply_delta_inplace` (#199 hot path).

Seeds one book at a given depth, then drives N alternating positive /
negative deltas against the inner price levels. Reports updates/sec.

Usage::

    uv run python scripts/bench_orderbook_delta.py [--depth D] [--updates N]
"""

from __future__ import annotations

import argparse
import gc
import time
from decimal import Decimal

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


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--depth", type=int, default=100)
    p.add_argument("--updates", type=int, default=100_000)
    args = p.parse_args()

    ticker = "BENCH-DELTA"
    mgr = OrderbookManager()
    mgr._apply_snapshot_inplace(_build_snapshot(ticker, args.depth))

    # Pre-build deltas so the loop only measures _apply_delta_inplace.
    prices = [Decimal("0." + f"{(i % args.depth) + 1:04d}") for i in range(args.updates)]
    deltas = [
        _build_delta(
            ticker,
            seq=i + 2,
            price=prices[i],
            delta=Decimal("1.00") if i % 2 == 0 else Decimal("-1.00"),
            side="yes" if i % 2 == 0 else "no",
        )
        for i in range(args.updates)
    ]

    gc.collect()
    t0 = time.perf_counter()
    applied = 0
    for d in deltas:
        if mgr._apply_delta_inplace(d):
            applied += 1
    elapsed = time.perf_counter() - t0

    rate = args.updates / elapsed if elapsed > 0 else float("inf")
    print(f"depth={args.depth} updates={args.updates} applied={applied}")
    print(f"  elapsed={elapsed * 1000:.1f} ms  rate={rate:,.0f} updates/sec")


if __name__ == "__main__":
    main()
