"""Microbench for the WS recv-loop parse+apply hot path.

Feeds N raw orderbook_snapshot + orderbook_delta frames through the
same json-loads → model_validate → ``_apply_*_inplace`` sequence
:meth:`KalshiWebSocket._process_frame` runs, without standing up the
dispatcher / connection / subscription manager. Reports frames/sec
and GC counts before/after.

Usage::

    uv run python scripts/bench_ws_recv.py [--frames N] [--depth D]
"""

from __future__ import annotations

import argparse
import gc
import json
import time

from kalshi.ws.models.orderbook_delta import (
    OrderbookDeltaMessage,
    OrderbookSnapshotMessage,
)
from kalshi.ws.orderbook import OrderbookManager


def _snapshot_frame(ticker: str, depth: int) -> str:
    return json.dumps({
        "type": "orderbook_snapshot",
        "sid": 1,
        "seq": 1,
        "msg": {
            "market_ticker": ticker,
            "market_id": ticker,
            "yes_dollars_fp": [
                [f"0.{i:04d}", "100.00"] for i in range(1, depth + 1)
            ],
            "no_dollars_fp": [
                [f"0.{i:04d}", "100.00"] for i in range(1, depth + 1)
            ],
        },
    })


def _delta_frame(ticker: str, seq: int, depth: int) -> str:
    price_idx = (seq % depth) + 1
    return json.dumps({
        "type": "orderbook_delta",
        "sid": 1,
        "seq": seq,
        "msg": {
            "market_ticker": ticker,
            "market_id": ticker,
            "price_dollars": f"0.{price_idx:04d}",
            "delta_fp": "1.00" if seq % 2 == 0 else "-1.00",
            "side": "yes" if seq % 2 == 0 else "no",
        },
    })


def _process(raw: str, mgr: OrderbookManager) -> None:
    """Mirror of ``KalshiWebSocket._process_frame``'s orderbook fast path."""
    data = json.loads(raw)
    msg_type = data.get("type")
    if msg_type == "orderbook_snapshot":
        snap = OrderbookSnapshotMessage.model_validate(data)
        mgr._apply_snapshot_inplace(snap, sid=snap.sid)
    elif msg_type == "orderbook_delta":
        delta = OrderbookDeltaMessage.model_validate(data)
        mgr._apply_delta_inplace(delta)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", type=int, default=10_000)
    p.add_argument("--depth", type=int, default=100, choices=[10, 100, 500])
    args = p.parse_args()

    ticker = "BENCH-WSRECV"
    payloads = [_snapshot_frame(ticker, args.depth)]
    payloads.extend(
        _delta_frame(ticker, seq=i + 2, depth=args.depth)
        for i in range(args.frames - 1)
    )

    mgr = OrderbookManager()
    gc.collect()
    gc_before = gc.get_count()
    t0 = time.perf_counter()
    for raw in payloads:
        _process(raw, mgr)
    elapsed = time.perf_counter() - t0
    gc_after = gc.get_count()

    rate = args.frames / elapsed if elapsed > 0 else float("inf")
    print(f"frames={args.frames} depth={args.depth}")
    print(f"  elapsed={elapsed * 1000:.1f} ms  rate={rate:,.0f} frames/sec")
    print(f"  gc_count before={gc_before} after={gc_after}")


if __name__ == "__main__":
    main()
