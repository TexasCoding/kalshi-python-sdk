"""Precision microbench for #178: RSA-PSS sign offload.

Measures the event-loop blocking impact of inline vs. executor-offloaded
signing under a concurrent burst. Not part of the unit-test suite — run
manually to validate the offload is buying what we think it is.

Methodology (corrected from the original acceptance criterion):
- A real `asyncio.sleep(target_interval)` ticker measures wall-clock gaps
  via `loop.time()` deltas. `asyncio.sleep(0)` is special-cased to a
  single `call_soon` yield (see `tasks.__sleep0`) and does NOT measure
  wall-clock blocking — it only measures task-queue ordering.
- Compare two modes:
    1. Inline (calls `sign_request` directly on the loop)
    2. Offload (calls `sign_request_async` → dedicated ThreadPoolExecutor)
- Report per-percentile ticker gap.

Usage:
    uv run python scripts/bench_sign_offload.py [--signs N] [--ticks N] [--key-size 2048|4096]
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.auth import KalshiAuth


async def _ticker(loop: asyncio.AbstractEventLoop, ticks: int, interval: float) -> list[float]:
    gaps: list[float] = []
    last = loop.time()
    for _ in range(ticks):
        await asyncio.sleep(interval)
        now = loop.time()
        gaps.append(now - last - interval)
        last = now
    return gaps


async def _inline_signs(auth: KalshiAuth, n: int) -> None:
    for _ in range(n):
        auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=1)
        await asyncio.sleep(0)  # yield so the ticker can run


async def _offloaded_signs(auth: KalshiAuth, n: int) -> None:
    for _ in range(n):
        await auth.sign_request_async("GET", "/trade-api/v2/markets", timestamp_ms=1)


def _summarize(label: str, gaps: list[float]) -> None:
    gaps_ms = [g * 1000 for g in gaps]
    gaps_ms.sort()
    p50 = statistics.median(gaps_ms)
    p95 = gaps_ms[int(len(gaps_ms) * 0.95)]
    p99 = gaps_ms[int(len(gaps_ms) * 0.99)]
    print(
        f"{label:>20}: p50={p50:6.2f} ms  p95={p95:6.2f} ms  "
        f"p99={p99:6.2f} ms  max={max(gaps_ms):6.2f} ms"
    )


async def _run(auth: KalshiAuth, signs: int, ticks: int, interval: float) -> None:
    loop = asyncio.get_running_loop()

    # Mode 1: inline signs.
    inline_gaps, _ = await asyncio.gather(
        _ticker(loop, ticks, interval),
        _inline_signs(auth, signs),
    )
    _summarize("inline (on loop)", inline_gaps)

    # Mode 2: offloaded signs.
    offload_gaps, _ = await asyncio.gather(
        _ticker(loop, ticks, interval),
        _offloaded_signs(auth, signs),
    )
    _summarize("offloaded (executor)", offload_gaps)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--signs", type=int, default=500, help="signs per mode (default 500)")
    parser.add_argument("--ticks", type=int, default=100, help="ticker samples (default 100)")
    parser.add_argument(
        "--interval", type=float, default=0.005,
        help="ticker interval in seconds (default 0.005)",
    )
    parser.add_argument(
        "--key-size", type=int, default=2048, choices=[2048, 4096],
        help="RSA key size for the benchmark key (default 2048)",
    )
    args = parser.parse_args()

    print(f"Generating {args.key_size}-bit RSA key...")
    t0 = time.perf_counter()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=args.key_size)
    print(f"  ({(time.perf_counter() - t0) * 1000:.0f} ms)")
    auth = KalshiAuth(key_id="bench", private_key=private_key)

    print(
        f"\nRunning {args.signs} signs against {args.ticks}x ticker @ {args.interval * 1000:.0f}ms "
        f"({args.key_size}-bit key)...\n"
    )
    try:
        asyncio.run(_run(auth, args.signs, args.ticks, args.interval))
    finally:
        auth.close()

    print(
        "\nExpect: inline gaps to track the sign cost (1-3 ms on 2048-bit, ~10 ms on 4096-bit), "
        "offloaded gaps to stay close to schedule jitter."
    )


if __name__ == "__main__":
    main()
